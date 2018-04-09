#!/usr/bin/env python3
import shlex
import logging
import asyncio
import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import asyncssh

from kubessh.shell import Shell

shell_argparser = argparse.ArgumentParser()
shell_argparser.add_argument(
    '--image',
    default='alpine:3.6',
    help='Image to launch for this shell'
)
shell_argparser.add_argument(
    'command',
    nargs='*',
    default=['/bin/sh']
)

def make_shell(process, default_namespace):
    username = process.channel.get_extra_info('username')

    # Execute user's command if we are given it.
    # Otherwise spawn /bin/bash
    # FIXME: Make shell configurable
    raw_command = process.get_command()
    if raw_command is None:
        raw_command = ''

    shell_args = shell_argparser.parse_args(shlex.split(raw_command))
    logging.info(shell_args)

    return Shell(username, default_namespace, shell_args.image, shell_args.command)

async def handle_client(default_namespace, process):
    shell = make_shell(process, default_namespace)

    term_size = process.get_terminal_size()
    proc = await shell.execute((term_size[1], term_size[0]))

    await process.redirect(proc, proc, proc)

    loop = asyncio.get_event_loop()

    # Future for spawned process dying
    # We explicitly create a threadpool of 1 threads for every run_in_executor call
    # to help reason about interaction between asyncio and threads. A global threadpool
    # is fine when using it as a queue (when doing HTTP requests, for example), but not
    # here since we could end up deadlocking easily.
    shell_completed = loop.run_in_executor(ThreadPoolExecutor(1), proc.wait)
    # Future for ssh connection closing
    read_stdin = asyncio.ensure_future(process.stdin.read())

    # This loops is here to pass TerminalSizeChanged events through to ptyprocess
    # It needs to break when the ssh connection is gone or when the spawned process is gone.
    # See https://github.com/ronf/asyncssh/issues/134 for info on how this works
    while not process.stdin.at_eof() and not shell_completed.done():
        try:
            if read_stdin.done():
                read_stdin = asyncio.ensure_future(process.stdin.read())
            done, _ = await asyncio.wait([read_stdin, shell_completed], return_when=asyncio.FIRST_COMPLETED)
            # asyncio.wait doesn't await the futures - it only waits for them to complete.
            # We need to explicitly await them to retreive any exceptions from them
            for future in done:
                await future
        except asyncssh.misc.TerminalSizeChanged as exc:
            proc.setwinsize(exc.height, exc.width)

    # SSH Client is gone, but process is still alive. Let's kill it!
    if process.stdin.at_eof() and not shell_completed.done():
        await loop.run_in_executor(ThreadPoolExecutor(1), proc.terminate, force=True)
        logging.info('Terminated process')

    process.exit(shell_completed.result())



class Server(asyncssh.SSHServer):
    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return username == password

async def start_server(port, default_namespace, ssh_host_key):
    await asyncssh.create_server(
        host='', 
        port=port,
        server_factory=Server, process_factory=partial(handle_client, default_namespace),
        kex_algs=[alg.decode('ascii') for alg in asyncssh.kex.get_kex_algs()],
        server_host_keys=[ssh_host_key],
        session_encoding=None
    )

def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        '--debug',
        action='store_true',
        help="Enable debugging Logging"
    )
    argparser.add_argument(
        '--port',
        type=int,
        help='Port to listen on',
        default=8022
    )

    argparser.add_argument(
        '--default-spawn-namespace',
        help="Default namespace to spawn users into",
        default=None
    )

    argparser.add_argument(
        '--host-key-path',
        help='Path to host ssh private key. If unspecified, an ephemeral key is generated for this session',
        default=None
    )

    args = argparser.parse_args()

    logging.basicConfig(format='%(asctime)s %(message)s', level='DEBUG' if args.debug else 'INFO')

    # If no namespace to spawn into is specified, use current pod's namespace by default
    # if we aren't running inside k8s, just use the `default` namespace
    if args.default_spawn_namespace is None:
        if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/namespace'):
            with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace') as f:
                args.default_spawn_namespace = f.read().strip()
        else:
            args.default_spawn_namespace = 'default'


    if args.host_key_path is None:
        # We'll generate a temporary key in-memory key for this run only
        ssh_host_key = asyncssh.generate_private_key('ssh-rsa')
        logging.warn('No --host-key-path provided, generating an ephemeral host key')
    else:
        with open(args.host_key_path) as f:
            ssh_host_key = asyncssh.import_private_key(f.read())
        logging.info(f'Loaded host key from {args.host_key_path}')


    loop = asyncio.get_event_loop()

    loop.run_until_complete(start_server(args.port, args.default_spawn_namespace, ssh_host_key))
    loop.run_forever()

if __name__ == '__main__':
    main()
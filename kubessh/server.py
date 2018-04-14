#!/usr/bin/env python3
import shlex
import logging
import asyncio
import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import itertools
from traitlets.config import Application
from traitlets import Unicode, Bool, Integer, Type, default

import asyncssh

from kubessh.shell import UserPod, Shell, ShellState
from kubessh.authentication import Authenticator
from kubessh.authentication.github import GitHubAuthenticator

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




class KubeSSH(Application):
    config_file = Unicode(
        'kubessh_config.py',
        help="""
        Config file to load KubeSSH config from
        """,
        config=True
    )

    port = Integer(
        8022,
        help="""
        Port the ssh server should listen on
        """,
        config=True
    )

    host_key_path = Unicode(
        None,
        allow_none=True,
        help="""
        Path to host's private SSH Key.

        If set to None, an ephemeral key is generated for this session
        """,
        config=True
    )

    debug = Bool(
        False,
        help="""
        Turn on debug logging
        """,
        config=True
    )

    authenticator_class = Type(
        GitHubAuthenticator,
        klass=Authenticator,
        config=True,
        help="""
        Class used to perform authentication.

        Should be a subclass of kubessh.authentication.Authenticator.
        """
    )

    default_namespace = Unicode(
        help="""
        Default namespace to spawn user shells to
        """,
        config=True
    )

    @default('default_namespace')
    def _populate_default_namespace(self):
        # If no namespace to spawn into is specified, use current pod's namespace by default
        # if we aren't running inside k8s, just use the `default` namespace
        if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/namespace'):
            with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace') as f:
                return f.read().strip()
        else:
            return 'default'

    async def handle_client(self, process):
        username = process.channel.get_extra_info('username')

        # Execute user's command if we are given it.
        # Otherwise spawn /bin/bash
        # FIXME: Make shell configurable
        raw_command = process.get_command()
        if raw_command is None:
            raw_command = ''
        try:
            shell_args = shell_argparser.parse_args(shlex.split(raw_command))
            command = shell_args.command
            image = shell_args.image
        except SystemExit:
            # This just means there's an argument parser error
            # We should then treat this as purely a command
            command = shlex.split(raw_command)
            image = 'alpine:3.6'

        pod = UserPod(parent=self, username=username, namespace=self.default_namespace, image=image)

        spinner = itertools.cycle(['-', '/', '|', '\\'])

        async for status in pod.ensure_running():
            if status == ShellState.RUNNING:
                process.stdout.write('\r\033[K'.encode('ascii'))
            elif status == ShellState.STARTING:
                process.stdout.write('\b'.encode('ascii'))
                process.stdout.write(next(spinner).encode('ascii'))

        shell = Shell(parent=self, user_pod=pod, command=command)
        term_size = process.get_terminal_size()
        await shell.execute((term_size[1], term_size[0]))
        proc = shell.process

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

    def initialize(self, *args, **kwargs):
        logging.basicConfig(format='%(asctime)s %(message)s', level='DEBUG' if self.debug else 'INFO')
        self.load_config_file(self.config_file)

        if self.host_key_path is None:
            # We'll generate a temporary key in-memory key for this run only
            self.ssh_host_key = asyncssh.generate_private_key('ssh-rsa')
            self.log.warn('No --host-key-path provided, generating an ephemeral host key')
        else:
            with open(self.host_key_path) as f:
                self.ssh_host_key = asyncssh.import_private_key(f.read())
            self.log.info(f'Loaded host key from {self.host_key_path}')

    async def start(self):
        await asyncssh.create_server(
            host='',
            port=self.port,
            server_factory=partial(self.authenticator_class, parent=self),
            process_factory=self.handle_client,
            kex_algs=[alg.decode('ascii') for alg in asyncssh.kex.get_kex_algs()],
            server_host_keys=[self.ssh_host_key],
            session_encoding=None
        )

app = KubeSSH()

def main():
    loop = asyncio.get_event_loop()

    app.initialize()
    loop.run_until_complete(app.start())
    loop.run_forever()

if __name__ == '__main__':
    main()
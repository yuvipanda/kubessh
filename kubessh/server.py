#!/usr/bin/env python3
import shlex
import logging
import asyncio
import argparse
import os
from functools import partial

import asyncssh

from kubessh.shell import Shell


async def handle_client(default_namespace, process):
    username = process.channel.get_extra_info('username')
    shell = Shell(username, default_namespace, 'alpine:3.6')

    # Execute user's command if we are given it.
    # Otherwise spawn /bin/bash
    # FIXME: Make shell configurable
    raw_command = process.get_command()
    if raw_command is None:
        command = ['/bin/sh']
    else:
        command = shlex.split(raw_command)
    proc = shell.execute(command)
    await process.redirect(proc, proc, proc)
    # Run this in an executor, since proc.wait blocks
    loop = asyncio.get_event_loop()
    ret = await loop.run_in_executor(None, proc.wait)
    process.exit(ret)



class Server(asyncssh.SSHServer):
    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return username == password

async def start_server(default_namespace):
    await asyncssh.create_server(
        host='', 
        port=8022,
        server_factory=Server, process_factory=partial(handle_client, default_namespace),
        kex_algs=[alg.decode('ascii') for alg in asyncssh.kex.get_kex_algs()],
        server_host_keys='server',
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
        '--default-spawn-namespace',
        help="Default namespace to spawn users into",
        default=None
    )

    args = argparser.parse_args()

    if args.default_spawn_namespace is None:
        if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount'):
            with open('/var/run/secrets/kubernetes.io/serviceaccount') as f:
                args.default_spawn_namespace = f.read().strip()
        else:
            args.default_spawn_namespace = 'default'

    logging.basicConfig(format='%(asctime)s %(message)s', level='DEBUG' if args.debug else 'INFO')

    loop = asyncio.get_event_loop()

    loop.run_until_complete(start_server(args.default_spawn_namespace))
    loop.run_forever()

if __name__ == '__main__':
    main()
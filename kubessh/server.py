#!/usr/bin/env python3
import shlex
import logging
import asyncio
import argparse

import asyncssh

from kubessh.shell import Shell


async def handle_client(process):
    username = process.channel.get_extra_info('username')
    shell = Shell(username, 'default', 'ubuntu:latest')

    # Execute user's command if we are given it.
    # Otherwise spawn /bin/bash
    # FIXME: Make shell configurable
    raw_command = process.get_command()
    if raw_command is None:
        command = ['/bin/bash']
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

async def start_server():
    await asyncssh.create_server(
        host='', 
        port=8022,
        server_factory=Server,
        process_factory=handle_client,
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

    args = argparser.parse_args()

    logging.basicConfig(format='%(asctime)s %(message)s', level='DEBUG' if args.debug else 'INFO')

    loop = asyncio.get_event_loop()

    loop.run_until_complete(start_server())
    loop.run_forever()

if __name__ == '__main__':
    main()
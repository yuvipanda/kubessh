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

from kubessh.pod import UserPod, PodState
from kubessh.authentication import Authenticator
from kubessh.authentication.github import GitHubAuthenticator


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

        pod = UserPod(parent=self, username=username, namespace=self.default_namespace)


        spinner = itertools.cycle(['-', '/', '|', '\\'])

        async for status in pod.ensure_running():
            if status == PodState.RUNNING:
                process.stdout.write('\r\033[K'.encode('ascii'))
            elif status == PodState.STARTING:
                process.stdout.write('\b'.encode('ascii'))
                process.stdout.write(next(spinner).encode('ascii'))

        await pod.execute(process)

    def init_logging(self):
        """
        Fix logging so both asyncssh & traitlet logging works
        """
        self.log.setLevel(logging.DEBUG if self.debug else logging.INFO)
        self.log.propagate = True
        UserPod.log = self.log

        asyncssh_logger = logging.getLogger('asyncssh')
        asyncssh_logger.propagate = True
        asyncssh_logger.parent = self.log
        asyncssh_logger.setLevel(self.log.level)


    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)
        self.load_config_file(self.config_file)
        self.init_logging()

        if self.host_key_path is None:
            # We'll generate a temporary key in-memory key for this run only
            self.ssh_host_key = asyncssh.generate_private_key('ssh-rsa')
            self.log.warn('No --host-key-path provided, generating an ephemeral host key')
        else:
            with open(self.host_key_path) as f:
                self.ssh_host_key = asyncssh.import_private_key(f.read())
            self.log.info(f'Loaded host key from {self.host_key_path}')

    async def start(self):
        await asyncssh.listen(
            host='',
            port=self.port,
            # Pass log through so we keep same logging infrastructure everywhere
            server_factory=partial(self.authenticator_class, parent=self, namespace=self.default_namespace, log=self.log),
            process_factory=self.handle_client,
            kex_algs=[alg.decode('ascii') for alg in asyncssh.kex.get_kex_algs()],
            server_host_keys=[self.ssh_host_key],
            encoding=None,
            agent_forwarding=False, # The cause of so much pain! Let's not allow this by default
            keepalive_interval=30 # FIXME: Make this configurable
        )

app = KubeSSH()

def main():
    loop = asyncio.get_event_loop()

    app.initialize()
    loop.run_until_complete(app.start())
    loop.run_forever()

if __name__ == '__main__':
    main()

import asyncio
import subprocess
from ptyprocess import PtyProcess
import time
import argparse
import os
from kubernetes import client as k
import kubernetes.config
import escapism
import functools
from enum import Enum
import shlex
import string
from concurrent.futures import ThreadPoolExecutor
from traitlets.config import LoggingConfigurable
from traitlets import Dict, Unicode, List

from .serialization import make_pod_from_dict

try:
    kubernetes.config.load_incluster_config()
except kubernetes.config.ConfigException:
    kubernetes.config.load_kube_config()

# FIXME: Figure out if making this global is a problem
v1 = k.CoreV1Api()

class ShellState(Enum):
    UNKNOWN = 0
    STARTING = 1
    RUNNING = 2

class UserPod(LoggingConfigurable):
    """
    A kubernetes pod of specific configuration for one user.

    There might be multiple shells opened concurrently to this pod.

    Config from administrators and the ssh command from the user are
    mapped here to a running Kubernetes pod. This allows multiple ssh
    sessions to be running concurrently in the same kubernetes pod.

    Config from administrators is set via traitlets in config.
    """
    pod_template = Dict(
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {},
            "spec": {
                "automountServiceAccountToken": False,
                "containers": [
                    {
                        "command": ["/bin/sh"],
                        "image": "buildpack-deps:bionic-scm",
                        "name": "shell",
                        "stdin": True,
                        "tty": True,
                    },
                    {
                        "command": ["/bin/sh"],
                        "image": "alpine/socat",
                        "name": "socat",
                        "stdin": True,
                        "tty": True
                    }
                ],
            },
        },
        help="""
        Template for creating user pods.

        This should be a dict containing a fully specified Kubernetes
        Pod object. Specific components of it may be changed to
        match the configuration of the Shell object requested.
        """,
        config=True
    )

    username = Unicode(
        None,
        allow_none=True,
        help="""
        Username this shell belongs to.

        Will be sanitized wherever required.
        """,
        config=True
    )

    namespace = Unicode(
        None,
        allow_none=True,
        help="""
        Kubernetes Namespace this shell will be spawned into.

        This namespace must already exist.
        """,
        config=True
    )

    def _expand_user_properties(self, template):
        # Make sure username and servername match the restrictions for DNS labels
        # Note: '-' is not in safe_chars, as it is being used as escape character
        safe_chars = set(string.ascii_lowercase + string.digits)

        safe_username = escapism.escape(self.username, safe=safe_chars, escape_char='-').lower()

        return template.format(
            username=safe_username,
        )

    def _expand_all(self, src):
        if isinstance(src, list):
            return [self._expand_all(i) for i in src]
        elif isinstance(src, dict):
            return {k: self._expand_all(v) for k, v in src.items()}
        elif isinstance(src, str):
            return self._expand_user_properties(src)
        else:
            return src

    def __init__(self, username, namespace, *args, **kwargs):
        self.username = username
        self.namespace = namespace
        super().__init__(*args, **kwargs)

        self.required_labels = {
            'kubessh.yuvi.in/username': escapism.escape(self.username, escape_char='-'),
        }

        # Threads required to perform all activities in this shell
        # These should probably be a well sized global threadpool, since this is being
        # used as a sort of queue. We will currently use a threadpool of 1 thread per shell
        # for simplicity. The number of threads here needs to be the maximum number of threads
        # this object could possibly use at the same time. Eventually, this needs to be a
        # global threadpool with well enforced limits #FIXME
        self.kube_api_threadpool = ThreadPoolExecutor(1)

    def _run_in_executor(self, func, *args, **kwargs):
        return asyncio.get_event_loop().run_in_executor(self.kube_api_threadpool, functools.partial(func, *args, **kwargs))

    def _make_labelselector(self, labels):
        return ','.join([f'{k}={v}' for k, v in labels.items()])

    def make_pod_spec(self):
        pod = make_pod_from_dict(self._expand_all(self.pod_template))
        pod.metadata.generate_name = escapism.escape(self.username, escape_char='-') + '-'

        if pod.metadata.labels is None:
            pod.metadata.labels = {}
        pod.metadata.labels.update(self.required_labels)

        return pod

    async def cleanup_pods(self, pods):
        """
        Delete all Failed and Succeeded pods

        Return list of pods that are not in Failed or Succeeded phases
        """
        remaining_pods = []
        for pod in pods.items:
            if pod.status.phase in ['Failed', 'Succeeded']:
                await self._run_in_executor(
                    v1.delete_namespaced_pod,
                    pod.metadata.name, pod.metadata.namespace, body=k.V1DeleteOptions(grace_period_seconds=0)
                )
            else:
                remaining_pods.append(pod)

        return remaining_pods

    async def ensure_running(self):
        # Get list of current running pods that might be for our user
        all_user_pods = await self._run_in_executor(
            v1.list_namespaced_pod,
            self.namespace, label_selector=self._make_labelselector(self.required_labels)
        )

        current_user_pods = await self.cleanup_pods(all_user_pods)

        if len(current_user_pods) == 0:
            # No pods exist! Let's create some!
            yield ShellState.STARTING
            pod = await self._run_in_executor(
                v1.create_namespaced_pod,
                self.namespace, self.make_pod_spec()
            )
        else:
            pod = current_user_pods[0]
            # FIXME: What do we do if we have more than 1 running user pod?

        while pod.status.phase != 'Running':
            yield ShellState.STARTING
            await asyncio.sleep(1)
            pod = await self._run_in_executor(
                v1.read_namespaced_pod,
                pod.metadata.name, pod.metadata.namespace
            )
        yield ShellState.RUNNING
        self.pod = pod

    async def execute(self, ssh_process):
        command = shlex.split(ssh_process.command) if ssh_process.command else ["/bin/bash", "-l"]
        tty_args = ['--tty'] if ssh_process.get_terminal_type() else []
        kubectl_command = [
            'kubectl',
            '--namespace', self.pod.metadata.namespace,
            'exec',
            '-c', 'shell',
            '--stdin'
            ] + tty_args + [
            self.pod.metadata.name,
            '--'
        ] + command
        print(f'Executing {kubectl_command}')

        # FIXME: Is this async friendly?
        if ssh_process.get_terminal_type():
            # PtyProcess and asyncssh disagree on ordering of terminal size
            ts = ssh_process.get_terminal_size()
            process = PtyProcess.spawn(argv=kubectl_command, dimensions=(ts[1], ts[0]))
            await ssh_process.redirect(process, process, process)

            loop = asyncio.get_event_loop()

            # Future for spawned process dying
            # We explicitly create a threadpool of 1 threads for every run_in_executor call
            # to help reason about interaction between asyncio and threads. A global threadpool
            # is fine when using it as a queue (when doing HTTP requests, for example), but not
            # here since we could end up deadlocking easily.
            shell_completed = loop.run_in_executor(ThreadPoolExecutor(1), process.wait)
            # Future for ssh connection closing
            read_stdin = asyncio.ensure_future(ssh_process.stdin.read())

            # This loops is here to pass TerminalSizeChanged events through to ptyprocess
            # It needs to break when the ssh connection is gone or when the spawned process is gone.
            # See https://github.com/ronf/asyncssh/issues/134 for info on how this works
            while not ssh_process.stdin.at_eof() and not shell_completed.done():
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
            if ssh_process.stdin.at_eof() and not shell_completed.done():
                await loop.run_in_executor(ThreadPoolExecutor(1), lambda: proc.terminate(force=True))
                logging.info('Terminated process')

            ssh_process.exit(shell_completed.result())
        else:
            process = await asyncio.create_subprocess_exec(
                *kubectl_command,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await ssh_process.redirect(stdin=process.stdin, stdout=process.stdout, stderr=process.stderr)

            ssh_process.exit(await process.wait())

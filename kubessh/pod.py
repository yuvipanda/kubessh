import asyncio
import asyncssh
import subprocess
from ptyprocess import PtyProcess
import time
import argparse
import os
import sys
from kubernetes import client as k
import kubernetes.config
import escapism
import functools
from enum import Enum
import shlex
import string
from concurrent.futures import ThreadPoolExecutor
from traitlets.config import LoggingConfigurable
from traitlets import Dict, Unicode, List, default

from .serialization import make_api_object_from_dict

try:
    kubernetes.config.load_incluster_config()
except kubernetes.config.ConfigException:
    kubernetes.config.load_kube_config()

# FIXME: Figure out if making this global is a problem
v1 = k.CoreV1Api()

class PodState(Enum):
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
                        "image": "jupyter/base-notebook",
                        "name": "shell",
                        "stdin": True,
                        "tty": True,
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

    pvc_templates = List(
        [],
        help="""
        List of templates for creating user persistent volume claims.

        Elements should be dicts with fully specified Kubernetes
        PersistentVolumeClaim objects. If empty (the default), no persistent
        volumes will be created. The templates must ensure that claim names are
        unique by including the string '{username}', which is expanded to the
        name of the user that the shell belongs to. In order to use the created
        persistent volumes, they should be referenced in the pod_template's
        spec.volumes.
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

    pod_name = Unicode(
        None,
        allow_none=True,
        help="""
        Name of this particular pod.

        Auto-generated to be 'ssh-{username}' if not set.
        """,
    )

    @default('pod_name')
    def _pod_name_default(self):
        return self._expand_all("ssh-{username}")

    namespace = Unicode(
        None,
        allow_none=True,
        help="""
        Kubernetes Namespace this shell will be spawned into.

        This namespace must already exist.
        """,
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
        pod = make_api_object_from_dict(self._expand_all(self.pod_template), k.V1Pod)
        pod.metadata.name = self.pod_name

        if pod.metadata.labels is None:
            pod.metadata.labels = {}
        pod.metadata.labels.update(self.required_labels)

        return pod

    def make_pvc_spec(self, template):
        pvc = make_api_object_from_dict(self._expand_all(template), k.V1PersistentVolumeClaim)

        if pvc.metadata.labels is None:
            pvc.metadata.labels = {}
        pvc.metadata.labels.update(self.required_labels)

        return pvc

    async def ensure_running(self):
        """
        Ensure this user pod is running.

        1. If pod already exists, and is in running state, just return
        2. If pod already exists, and has completed, delete it.
        3. If pod doesn't exist, create new pod & wait for it to be running
        """
        try:
            pod = await self._run_in_executor(
                v1.read_namespaced_pod,
                self.pod_name, self.namespace
            )
        except kubernetes.client.rest.ApiException as e:
            if e.status == 404:
                pod = None
            else:
                raise

        if pod and pod.status.phase == 'Running':
            # Pod exists, and is running. Nothing to do
            self.pod = pod
            yield PodState.RUNNING
            return

        # FIXME: Deal with pods in Terminating state
        if pod and pod.status.phase in ['Failed', 'Succeeded']:
            # Pod exists, but is in an unusable state.
            # Delete it, and say there is no pod
            await self._run_in_executor(
                v1.delete_namespaced_pod,
                pod.metadata.name,
                pod.metadata.namespace, body=k.V1DeleteOptions(grace_period_seconds=0)
            )
            pod = None

        if not pod:
            # There is no pod, so start one!
            yield PodState.STARTING

            # create persistent volumes, if any
            for template in self.pvc_templates:
                pvc_spec = self.make_pvc_spec(template)
                try:
                    pvc = await self._run_in_executor(v1.create_namespaced_persistent_volume_claim, self.namespace, pvc_spec)
                    self.log.info(f"Successfully created PVC {pvc.metadata.name}")
                    self.log.debug(pvc)
                except kubernetes.client.rest.ApiException as e:
                    if e.status == 409:
                        self.log.info(f"PVC {pvc_spec.metadata.name} already exists, did not create a new PVC.")
                    elif e.status == 403:
                        t, v, tb = sys.exc_info()
                        try:
                            pvc = await self._run_in_executor(v1.read_namespaced_persistent_volume_claim, pvc_spec.metadata.name, self.namespace, pvc_spec)
                        except:
                            raise v.with_traceback(tb)
                        self.log.info(f"PVC {pvc_spec.metadata.name} already exists, possibly have reached quota.")
                    else:
                        raise

            pod = await self._run_in_executor(
                v1.create_namespaced_pod,
                self.namespace, self.make_pod_spec()
            )

        while pod.status.phase != 'Running':
            # By now, a pod exists but is not necessarily in 'Running' state
            # So we just wait for that to be the case, and return
            yield PodState.STARTING
            await asyncio.sleep(1)
            pod = await self._run_in_executor(
                v1.read_namespaced_pod,
                pod.metadata.name, pod.metadata.namespace
            )
        yield PodState.RUNNING

    async def execute(self, ssh_process):
        command = shlex.split(ssh_process.command) if ssh_process.command else ["/bin/bash", "-l"]
        tty_args = ['--tty'] if ssh_process.get_terminal_type() else []
        kubectl_command = [
            'kubectl',
            '--namespace', self.namespace,
            'exec',
            '-c', 'shell',
            '--stdin'
            ] + tty_args + [
            self.pod_name,
            '--'
        ] + command

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
                        read_stdin = asyncio.ensure_future(ssh_process.stdin.read())
                    done, _ = await asyncio.wait([read_stdin, shell_completed], return_when=asyncio.FIRST_COMPLETED)
                    # asyncio.wait doesn't await the futures - it only waits for them to complete.
                    # We need to explicitly await them to retreive any exceptions from them
                    for future in done:
                        await future
                except asyncssh.misc.TerminalSizeChanged as exc:
                    process.setwinsize(exc.height, exc.width)

            # SSH Client is gone, but process is still alive. Let's kill it!
            if ssh_process.stdin.at_eof() and not shell_completed.done():
                await loop.run_in_executor(ThreadPoolExecutor(1), lambda: process.terminate(force=True))
                self.log.info('Terminated process')

            ssh_process.exit(shell_completed.result())
        else:
            process = await asyncio.create_subprocess_exec(
                *kubectl_command,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await ssh_process.redirect(stdin=process.stdin, stdout=process.stdout, stderr=process.stderr)

            ssh_process.exit(await process.wait())

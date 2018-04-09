#!/usr/bin/env python3
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
from concurrent.futures import ThreadPoolExecutor

try:
    kubernetes.config.load_kube_config()
except FileNotFoundError:
    kubernetes.config.load_incluster_config()

# FIXME: Figure out if making this global is a problem
v1 = k.CoreV1Api()

class ShellState(Enum):
    UNKNOWN = 0
    STARTING = 1
    RUNNING = 2

class Shell:
    """
    A shell running in a pod
    """
    def __init__(self, name, namespace, image, command):
        self.name = name
        self.namespace = namespace
        self.image = image
        self.command = command

        self.labels = {
            'kubessh.yuvi.in/username': escapism.escape(name, escape_char='-'),
            'kubessh.yuvi.in/image': escapism.escape(image, escape_char='-')
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
        return k.V1Pod(
            metadata=k.V1ObjectMeta(
                generate_name=self.name + '-',
                labels=self.labels
            ),
            spec=k.V1PodSpec(
                restart_policy='Never',
                containers=[
                    k.V1Container(
                        name='shell',
                        image=self.image,
                        stdin=True,
                        tty=True,
                        command=['/bin/sh']
                    )
                ],
            )
        )

    async def cleanup_pods(self, pods):
        """
        Delete all Failed and Succeeded pods

        Return list of pods that are not in Failed or Succeeded phases
        """
        remaining_pods = []
        for pod in pods.items:
            if pod.status.phase == 'Failed' or pod.status.phase == 'Succeeded':
                await self._run_in_executor(
                    v1.delete_namespaced_pod,
                    pod.metadata.name, pod.metadata.namespace, k.V1DeleteOptions(grace_period_seconds=0)
                )
            else:
                remaining_pods.append(pod)

        return remaining_pods

    async def execute(self, terminal_size):
        # Get list of current running pods that might be for our user
        all_user_pods = await self._run_in_executor(
            v1.list_namespaced_pod,
            self.namespace, label_selector=self._make_labelselector(self.labels)
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

        command = [
            'kubectl',
            '--namespace', self.namespace,
            'exec',
            '--stdin',
            '--tty',
            pod.metadata.name,
        ] + self.command

        # FIXME: Is this async friendly?
        self.process = PtyProcess.spawn(argv=command, dimensions=terminal_size)
        yield ShellState.RUNNING
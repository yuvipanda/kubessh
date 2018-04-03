#!/usr/bin/env python3
import subprocess
import time
import argparse
import os
from kubernetes import client as k
import kubernetes.config

user = 'yuvipanda'

def make_pod(username):
    return k.V1Pod(
        metadata=k.V1ObjectMeta(
            generate_name=user,
            labels={
                'kubessh.yuvi.in/username': username
            }
        ),
        spec=k.V1PodSpec(
            restart_policy='Never',
            containers=[
                k.V1Container(
                    name='shell',
                    image='ubuntu:latest',
                    stdin=True,
                    tty=True,
                    command=['/bin/sh']
                )
            ],
        )
    )

kubernetes.config.load_kube_config()

v1 = k.CoreV1Api()


def create_pod(namespace, pod_template):
    created_pod = v1.create_namespaced_pod(namespace, pod_template)
    return created_pod

def wait_for_running(pod):
    while True:
        if pod.status.phase == 'Running':
            return
        pod = v1.read_namespaced_pod(pod.metadata.name, pod.metadata.namespace)
        print(pod)
        time.sleep(1)

def ensure_pod(username):
    current_pods = v1.list_namespaced_pod('default', label_selector=f'kubessh.yuvi.in/username={username}')
    if len(current_pods.items) == 0:
        pod = create_pod('default', make_pod(username))
    else:
        for pod in current_pods.items:
            if pod.status.phase == 'Failed' or pod.status.phase == 'Succeeded':
                v1.delete_namespaced_pod(pod.metadata.name, 'default', k.V1DeleteOptions(grace_period_seconds=0))
            else:
                return pod
        pod = create_pod('default', pod_template)

def exec_in_pod(pod, command):
    command = [
        'kubectl',
        'exec',
        '--stdin',
        '--tty',
        pod.metadata.name,
    ] + command
    os.execvp(command[0], command)

def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        'command',
        nargs=argparse.REMAINDER,
        default=['/bin/bash']
    )

    args = argparser.parse_args()

    pod = ensure_pod('yuvipanda')
    wait_for_running(pod)
    exec_in_pod(pod, args.command)

main()
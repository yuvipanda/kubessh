<!-- Try to keep this in sync with docs/index.md -->
# KubeSSH

KubeSSH brings the familiar SSH experience to a modern cluster manager.

> I have some code that requires more RAM / CPU / GPUs / Network / Time to run than my laptop can offer.
> What is the simplest, most user friendly way to run this code?

KubeSSH is an experiment in trying to answer this question.

## What?

Normally, you use `ssh` to get a shell on a particular single machine to do work in.
You might be editing files, reading logs, submitting jobs or running some code.

With KubeSSH, each user sshing in gets their own isolated [Kubernetes Pod](https://kubernetes.io/docs/concepts/workloads/pods/pod/).
This pod can be customized to provide CPU / RAM / GPUs / disk as the user / cluster admin
sees fit. Users can then run their code *interactively* using all these resources.

## Why?

Putting each user in their own Kubernetes Pod has several advantages over traditional
SSH.

1. Users can use different container images, providing a large amount of flexibility in what
   software is available. No waits for admins to install specific packages, or conflicts
   with packages needed by other users.
2. Strong resource guarantees (CPU, RAM, GPUs, etc) prevent users from exhausting resources
   on any single login node.
3. Can scale dynamically to a very large number of simultaneous users.
4. Authentication and Authorization can be much more dynamic, since we are no longer
   tied to the traditional POSIX model of user accounts. For example, you can allow
   users to log in via OAuth2 / OpenID Connect providers!
5. Provide access to kubernetes API for users to run jobs and do all the cool things
   Kubernetes can do, without having to set up `kubectl` and friends on their local
   computers.

KubeSSH brings the familiar SSH experience to a modern cluster manager.
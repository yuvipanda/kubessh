# Customizing the User Pod

Every user logging into KubeSSH is given their own [kubernetes pod](https://kubernetes.io/docs/concepts/workloads/pods/pod/).
Admins can configure how this pod looks with a `podTemplate`, letting them
use all the options available in Kubernetes without waiting for support
in KubeSSH.

## Specifying template used for user pods

After [installing with helm](../install), you can specify the template
used to create pods in your `config.yaml`. Here is a minimal example:

```yaml
apiVersion: v1
kind: Pod
metadata: {}
spec:
  containers:
  - image: jupyter/base-notebook
    name: shell
    stdin: True
    tty: True
  automountServiceAccountToken: False
```

This creates user pods with the `jupyter/base-notebook` image and no
other customizations. If we were to [limit each user](https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/)
to 1G of memory, it would instead look like:

```yaml
apiVersion: v1
kind: Pod
metadata: {}
spec:
  containers:
  - image: jupyter/base-notebook
    name: shell
    stdin: True
    tty: True
    resources:
      requests:
        memory: 1Gi
  automountServiceAccountToken: False
```

The [kubernetes documentation](https://kubernetes.io/docs/tasks/configure-pod-container/) has a lot of examples
on configuring pods to do different things.

## Template requirements

Admins have almost full control over how the pods look, but some restrictions
are imposed.

1. A container named `shell` must exist. User will be placed inside this
   container when they ssh in. Sidecar container can exist if needed.
2. The `shell` container must have both `tty` and `stdin` set to `True. This
   tells Kubernetes to allocate the required devices for interactive usage.

KubeSSH will also modify your template in the following ways:

1. The name of the pod will be automatically set by KubeSSH.
2. KubeSSH will add some required labels to the pod so it can track them
   better
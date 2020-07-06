# Installing KubeSSH

KubeSSH can be easily installed onto any Kubernetes cluster
with [helm](https://helm.sh), using our provided [helm chart](https://chart.kubessh.org/)

## Pre-requisites

1. A [kubernetes cluster](https://k8s.io) you have access to.
   If `kubectl` commands work, you are probably good to go.
2. A local install of [helm](https://helm.sh). Minimum recommended version
   is 3.2.

## Prepare your `config.yaml`

Helm uses [YAML](https://en.wikipedia.org/wiki/YAML) files to store
configuration. Installing KubeSSH requires some custom config to be set,
so let's prepare that first.

### Create a host key

ssh clients authenticate the server via a [host key](https://www.ssh.com/ssh/host-key/),
which should remain the same for the same server. You must supply KubeSSH
a hostkey to use, so it can stay consistent over time.

You can create a hostkey with the following command:

```bash
ssh-keygen -f kubessh-hostkey
```

Enter a nil passphrase. This should create two files:

1. A *private* hostkey, at `kubessh-hostkey`
2. A *public* hostkey, at `kubessh-hostkey.pub`

Now, create a `config.yaml` file, and put the *private* hostkey in there,
with the following format:

```yaml
hostKey: |
    -----BEGIN OPENSSH PRIVATE KEY-----
    asdglkjasglkjsag..... (more stuff)
    many lines of random bits here
    indentation is important!
    -----END OPENSSH PRIVATE KEY-----
```

Note that the `|` and the indentation are very important!

### List users who are allowed to log in

KubeSSH uses a user's [GitHub SSH Keys](https://docs.github.com/en/github/authenticating-to-github/connecting-to-github-with-ssh)
to authenticate them by default. You will need to explicitly list the GitHub
usernames of users who are allowed in your `config.yaml` file.

```yaml
auth:
  github:
    allowedUsers:
      - yuvipanda
      - username1
      - username2
      - username3
```

GitHub exposes a user's public keys at URL `https://github.com/<username>.keys`
([here is mine](https://github.com/yuvipanda.keys)). This is very useful,
since the same SSH key you use to push to GitHub can now be used to log
in to KubeSSH

Now you have a functional `config.yaml` file that can be used to install
KubeSSH!

## Install KubeSSH

### Add kubessh repo to helm

We automatically publish a [helm chart repository](https://helm.sh/docs/topics/chart_repository/)
with every PR merged to KubeSSH. You need to tell helm where to find it,
so it can use it to install KubeSSH.

```bash
helm repo add kubessh https://chart.kubessh.org
helm repo update
```

### Find an appropriate version to use

KubeSSH is still in very alpha state, so you should explicitly pick a version
to use - currently there are no stability guarantees. Go to [chart.kubessh.org](https://chart.kubessh.org/#development-releases-kubessh), and find
the latest version there.

For example, if the release name is `kubessh-0.0.1-n001.he1506d0`, the version
number is `0.0.1-n001.he1506d0` - everything after `kubessh-`. This lets us
consistently install a particular version regardless of new changes upstream.

### Install via Helm

Time to actually install the application! Run the following command, replacing
`<version>` with the version you determined in the previous setting. You can
also replace `my-kubessh-install` to be something more descriptive.

```bash
helm upgrade \
    --install --create-namespace \
    --namespace my-kubessh-install \
    --version 0.0.1-n001.h2068e92 \
    my-kubessh-install \
    kubessh/kubessh \
    -f config.yaml
```

## Test it out

### Find the public IP to ssh to

By default, KubeSSH will create a kubernetes [LoadBalancer](https://kubernetes.io/docs/concepts/services-networking/service/#loadbalancer)
to get a public IP for users to SSH into.

```bash
kubectl -n my-kubessh-install get svc
```

This command should output something like:

```
NAME                 TYPE           CLUSTER-IP    EXTERNAL-IP    PORT(S)        AGE
my-kubessh-install   LoadBalancer   10.87.9.143   35.231.2.147   22:30145/TCP   5m3s
```

The name of the service currently is the same as the namespace. You can
now connect to the external IP!

### SSH in

Finally, you can ssh in as an allowed user with your GitHub key to KubeSSH!

```bash
ssh <username>@<external-ip>
```

Where `<username>` is a GitHub user name in the `allowedList` of your `config.yaml` file,
and `<external-ip>` is the external IP we just discovered in the last step.

This should show you a spinner for a while, and then put you in a shell!

```bash
jovyan@ssh-username~$
```

We use the [jupyter/base-notebook](https://hub.docker.com/r/jupyter/base-notebook/)
image by default, but that can be configured to be whatever you need.

### Session persistentce

If you exit your shell, and ssh in again, you'll end up in the same pod.
Pods are persistent, and don't go away until you explicitly kill them
by running `kill 1` from inside your shell. This lets you do interesting
things like run `screen` inside your shell.
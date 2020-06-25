# Setting up development environment


## Pre-requisites

1. [minikube](https://kubernetes.io/docs/tasks/tools/install-minikube/) installed
   on your machine locally
2. [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/) installed &
   configured to talk to minikube
3. Python 3

## Setting up development environment

We recommend creating a [virtual environment](https://docs.python.org/3/library/venv.html)
to install kubessh into for development, although other methods should work just as
fine.

1. Create a virtual environment in the root of your clone of this repository

   ```bash
   python3 -m venv venv/
   ```

2. Activate the virtual environment

   ```bash
   source venv/bin/activate
   ```

3. Install kubessh & all its dependencies into this environment

   ```bash
   pip install --editable .
   ```

4. Create a ssh server key for kubessh to use. This will be presented by kubessh
   to any clients to verify its authenticity. If you don't create this manually,
   kubessh will use an ephemeral key - this will cause warnings in your ssh
   client each time you restart your server.

   ```bash
   ssh-keygen -f dummy-kubessh-host-key
   ```

   Don't use a passphrase when generating this key.

## Run kubessh

You're all set to run kubessh now!

1. Start the kubessh process

   ```bash
   kubessh --KubeSSH.config_file=kubessh_dummy_config.py
   ```

   This should start kubessh in debug mode, with `DummyAuthenticator`
   for authentication. You can see the other options chosen in
   `kubessh_dummy_config.py` file, using [traitlets](https://traitlets.readthedocs.io/en/stable/)
   to specify configuration. You can copy this file and make
   changes to try out various options.

2. In another terminal, ssh into kubessh, with any username & password same as
   username.

   ```bash
   ssh -p 8022 yourname@localhost
   ```

   Since we use `DummyAuthenticator` by default, you should use the username
   as the password.

   This should spawn a user pod in minikube, and ssh you into it! \o/

Now you have a working local install, and can fiddle around with it as you
please.

kubessh doesn't clean up user pods when it restarts. If you make a change
that modifies the structure of the pod being spawned, you must manually
delete the pod before ssh'ing again.
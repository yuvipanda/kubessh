from ruamel.yaml import YAML
from kubessh.authentication.github import GitHubAuthenticator
from kubessh.authentication.gitlab import GitLabAuthenticator
from kubessh.authentication.dummy import DummyAuthenticator

yaml = YAML()

c.KubeSSH.host_key_path = '/etc/kubessh/secrets/kubessh.host-key'
c.KubeSSH.debug = True

with open('/etc/kubessh/config/values.yaml') as f:
    config = yaml.load(f)

if config['auth']['type'] == 'github':
    c.KubeSSH.authenticator_class = GitHubAuthenticator
    c.KubeSSH.authenticator_class.allowed_users = config['auth']['github']['allowedUsers']
elif config['auth']['type'] == 'gitlab':
    c.KubeSSH.authenticator_class = GitLabAuthenticator
    c.KubeSSH.authenticator_class.instance_url = config['auth']['gitlab']['instanceUrl']
    c.KubeSSH.authenticator_class.allowed_users = config['auth']['gitlab']['allowedUsers']

elif config['auth']['type'] == 'dummy':
    c.KubeSSH.authenticator_class = DummyAuthenticator


if 'podTemplate' in config:
    c.UserPod.pod_template = config['podTemplate']

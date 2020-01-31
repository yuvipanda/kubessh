from ruamel.yaml import YAML

yaml = YAML()

c.KubeSSH.host_key_path = '/etc/kubessh/secrets/kubessh.host-key'
c.KubeSSH.debug = True

with open('/etc/kubessh/config/values.yaml') as f:
    config = yaml.load(f)

if config['auth']['type'] == 'github':
    c.GitHubAuthenticator.allowed_users = config['auth']['github']['allowedUsers']

if 'podTemplate' in config:
    c.UserPod.pod_template = config['podTemplate']
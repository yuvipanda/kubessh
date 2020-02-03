"""
Standalone daemon to clean up finished shell pods.

User pods can mark themselves as 'completed' by killing their
pid 1 (kill 1)d

"""
import kubernetes
import time
import logging
import os
from traitlets.config import Application
from traitlets import Unicode, default, Bool

class KubeSanitation(Application):
    config_file = Unicode(
        'kubesanitation_config.py',
        help="""
        Config file to load KubeSanitation config from
        """,
        config=True
    )
    namespace = Unicode(
        help="""
        Namespace to cleanup resources in
        """,
        config=True
    )

    debug = Bool(
        False,
        help="""
        Turn on debug logging
        """,
        config=True
    )

    @default('namespace')
    def _populate_default_namespace(self):
        # If no namespace to spawn into is specified, use current pod's namespace by default
        # if we aren't running inside k8s, just use the `default` namespace
        if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/namespace'):
            with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace') as f:
                return f.read().strip()
        else:
            return 'default'

    def initialize(self, *args, **kwargs):
        self.load_config_file(self.config_file)
        self.log.setLevel(logging.DEBUG if self.debug else logging.INFO)
        try:
            kubernetes.config.load_incluster_config()
        except kubernetes.config.ConfigException:
            kubernetes.config.load_kube_config()

    def start(self):
        v1 = kubernetes.client.CoreV1Api()
        while True:
            pods = v1.list_namespaced_pod(self.namespace, field_selector="status.phase=Succeeded")
            if len(pods.items):
                for pod in pods.items:
                    self.log.info(f"Deleting pod {pod.metadata.name}...")
                    v1.delete_namespaced_pod(pod.metadata.name, self.namespace)
            else:
                self.log.info("No completed pods found")
            time.sleep(30)


def main():
    app = KubeSanitation()
    app.initialize()
    app.start()

if __name__ == '__main__':
    main()
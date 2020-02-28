import asyncssh
from kubessh.server import BaseServer

class Authenticator(BaseServer):
    """
    Base class for Authentication plugins for KubeSSH.

    Should override the authentication specific methods of
    asyncssh.SSHServer
    """
    pass
import asyncssh
from traitlets.config import LoggingConfigurable

class Authenticator(asyncssh.SSHServer, LoggingConfigurable):
    """
    Base class for Authentication plugins for KubeSSH.

    Should override the authentication specific methods of
    asyncssh.SSHServer
    """
    pass

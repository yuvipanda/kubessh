from kubessh.authentication import Authenticator
import async_timeout
import aiohttp
import asyncssh
import re
from traitlets import Unicode, List

class GitLabAuthenticator(Authenticator):
    """
    Authenticate with GitLab SSH keys
    """
    instance_url = Unicode(
        "https://gitlab.com",
        config=True,
        help="""
        URL to the Gitlab instance whose users should be able to authenticate with public keys.

        Defaults to the public Gitlab instance at gitlab.com
        """
    )

    allowed_users = List(
        [],
        config=True,
        help="""
        List of Gitlab users allowed to log in. If None, all users are allowed.

        By default, no users are allowed.
        """
    )

    def connection_made(self, conn):
        self.conn = conn

    def public_key_auth_supported(self):
        return True

    async def begin_auth(self, username):
        """
        Fetch and save user's keys for comparison later
        """
        if self.allowed_users is not None and username not in self.allowed_users:
            # Deny all users not explicitly allowed
            self.log.info(f"User {username} not in allowed_users, authentication denied")
            return True
        url = f'{self.instance_url}/{username}.keys'
        async with aiohttp.ClientSession() as session, async_timeout.timeout(5):
            async with session.get(url) as response:
                keys = await response.text()
        if keys:
            # Remove comment fields from SSH keys, as asyncssh seems to choke on those
            keys = "\n".join(re.findall("^[^ ]+ [^ ]+", keys, flags=re.M))
            self.conn.set_authorized_keys(asyncssh.import_authorized_keys(keys))
        # Return true to indicate we always *must* authenticate
        return True

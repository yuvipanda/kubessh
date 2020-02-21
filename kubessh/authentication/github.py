from kubessh.authentication import Authenticator
import async_timeout
import aiohttp
import asyncssh
from traitlets import List

class GitHubAuthenticator(Authenticator):
    """
    Authenticate with GitHub SSH keys
    """
    allowed_users = List(
        [],
        config=True,
        help="""
        List of GitHub users allowed to log in.

        By default, no users are allowed
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
        if username not in self.allowed_users:
            # Deny all users not explicitly allowed
            self.log.info(f"User {username} not in allowed_users, authentication denied")
            return True
        url = f'https://github.com/{username}.keys'
        async with aiohttp.ClientSession() as session, async_timeout.timeout(5):
            async with session.get(url) as response:
                keys = await response.text()
        if keys:
            self.conn.set_authorized_keys(asyncssh.import_authorized_keys(keys))
        # Return true to indicate we always *must* authenticate
        return True

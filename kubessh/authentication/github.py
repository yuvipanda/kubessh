from kubessh.authentication import Authenticator
import async_timeout
import aiohttp
import asyncssh

class GitHubAuthenticator(Authenticator):
    """
    Authenticate with GitHub SSH keys
    """
    def connection_made(self, conn):
        self.conn = conn

    def public_key_auth_supported(self):
        return True

    async def begin_auth(self, username):
        """
        Fetch and save user's keys for comparison later
        """
        url = f'https://github.com/{username}.keys'
        async with aiohttp.ClientSession() as session, async_timeout.timeout(1):
            async with session.get(url) as response:
                keys = await response.text()
                if keys:
                    self.conn.set_authorized_keys(asyncssh.import_authorized_keys(keys))
        # Return true to indicate we always *must* authenticate
        return True

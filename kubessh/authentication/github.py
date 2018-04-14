from kubessh.authentication import Authenticator
import async_timeout
import aiohttp
import asyncssh

class GitHubAuthenticator(Authenticator):
    """
    Authenticate with GitHub SSH keys
    """
    def public_key_auth_supported(self):
        return True

    async def begin_auth(self, username):
        """
        Fetch and save user's keys for comparison later
        """
        url = f'https://github.com/{username}.keys'
        async with aiohttp.ClientSession() as session, async_timeout.timeout(10):
            async with session.get(url) as response:
                self.keys = asyncssh.import_authorized_keys(await response.text())

    async def validate_public_key(self, key):
        """
        Validate the user can login with this key
        """
        # FIXME: Figure out what the client address validation is for
        return self.keys.validate(key, '0.0.0.0')


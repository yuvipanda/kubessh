from kubessh.authentication import Authenticator
import async_timeout
import aiohttp
import asyncssh
import re
from traitlets import Unicode

class GitLabAuthenticator(Authenticator):
    """
    Authenticate with GitLab SSH keys
    """
    instance_url = Unicode(
        "",
        config=True,
        help="""
        URL to the Gitlab instance whose users should be able to authenticate with public keys.
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
        import sys
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

from kubessh.authentication import Authenticator

class DummyAuthenticator(Authenticator):
    """
    Dummy SSH Authenticator.

    Allows ssh logins where the username is the same as the password.
    """
    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        self.log.info(f"Login attempted by {username}")
        return username == password

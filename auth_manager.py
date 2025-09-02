import os
import logging
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired,
    TwoFactorRequired,
    ChallengeRequired,
    BadPassword,
)

class AuthManager:
    """
    Manages Instagram authentication, including session handling and 2FA.
    """
    SESSION_FILE = "ig_session.json"

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.client = Client()
        self.login_status = "UNKNOWN"
        self.login_error_message = ""

    def login(self, verification_code: str = None, two_factor_code: str = None) -> tuple[bool, str]:
        """
        Handles the complete Instagram login flow.

        Args:
            verification_code (str, optional): The SMS or email verification code.
            two_factor_code (str, optional): The 2FA (TOTP) code.

        Returns:
            A tuple containing:
            - bool: True for successful login, False otherwise.
            - str: A status message ('SUCCESS', '2FA_REQUIRED', 'SMS_REQUIRED', 'FAILURE').
        """
        # If already logged in, no need to do it again.
        if self.client.user_id:
            return True, "SUCCESS"

        # Step 6.1 & 6.2: Check for and try to use a session file.
        if os.path.exists(self.SESSION_FILE):
            logging.info(f"Session file '{self.SESSION_FILE}' found. Attempting to log in.")
            try:
                self.client.load_settings(self.SESSION_FILE)
                self.client.login(self.username, self.password)
                self.client.get_timeline_feed() # Check if the session is valid
                logging.info("Login successful using session file.")
                self.login_status = "SUCCESS"
                return True, self.login_status
            except (LoginRequired, BadPassword, Exception) as e:
                logging.warning(f"Session file is invalid or expired, will perform a fresh login. Reason: {e}")
                # Delete the invalid session file
                os.remove(self.SESSION_FILE)
        
        # Step 6.3: Fresh login using username and password
        logging.info("No valid session found. Attempting a fresh login.")
        try:
            if two_factor_code:
                # Handle 2FA login
                logging.info("Attempting login with 2FA code.")
                self.client.login(self.username, self.password, verification_code=two_factor_code)
            elif verification_code:
                # Handle SMS/email challenge code
                logging.info("Attempting login with verification code.")
                self.client.challenge_code_login(verification_code)
            else:
                # Standard login
                self.client.login(self.username, self.password)

        except TwoFactorRequired:
            self.login_status = "2FA_REQUIRED"
            logging.info("2FA code is required.")
            return False, self.login_status
        
        except ChallengeRequired:
            # This exception means a verification code (SMS/email) is needed.
            # The client state is now waiting for the code. We need to inform the handler.
            logging.info("Challenge code (SMS/Email) is required.")
            self.login_status = "SMS_REQUIRED"
            return False, self.login_status
            
        except (BadPassword, LoginRequired) as e:
            self.login_status = "FAILURE"
            self.login_error_message = f"Login failed: Incorrect username or password. Details: {e}"
            logging.error(self.login_error_message)
            return False, self.login_status

        except Exception as e:
            self.login_status = "FAILURE"
            self.login_error_message = f"An unexpected error occurred during login: {e}"
            logging.error(self.login_error_message)
            return False, self.login_status

        # Step 6.8: Save session if login is successful
        logging.info("Login successful.")
        self.client.dump_settings(self.SESSION_FILE)
        logging.info(f"Session settings saved to '{self.SESSION_FILE}'.")
        self.login_status = "SUCCESS"
        return True, self.login_status

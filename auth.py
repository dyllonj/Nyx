import os
import getpass
import config
from garminconnect import Garmin, GarminConnectAuthenticationError


def get_client() -> Garmin:
    """Return an authenticated Garmin client.
    Tokens are stored in TOKENSTORE_DIR and reused on subsequent calls.
    First run prompts for credentials; after that, fully silent.
    """
    os.makedirs(config.TOKENSTORE_DIR, exist_ok=True)

    try:
        client = Garmin()
        client.login(tokenstore=config.TOKENSTORE_DIR)
        return client
    except (GarminConnectAuthenticationError, FileNotFoundError, Exception):
        pass

    # First-time or expired: prompt for credentials
    print("Garmin Connect login required.")
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    client = Garmin(email=email, password=password)
    client.login(tokenstore=config.TOKENSTORE_DIR)
    print("Login successful. Tokens saved.")
    return client

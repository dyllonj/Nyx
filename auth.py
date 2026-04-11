import os
import getpass
import config

from errors import DependencyError, HarnessError


def get_client():
    """Return an authenticated Garmin client.
    Tokens are stored in TOKENSTORE_DIR and reused on subsequent calls.
    First run prompts for credentials; after that, fully silent.
    """
    try:
        from garminconnect import Garmin, GarminConnectAuthenticationError
    except ImportError as e:
        raise DependencyError(
            "missing_garmin_dependency",
            "Garmin sync requires the `python-garminconnect` package.",
            hint="Run `pip install -r requirements.txt` to enable Garmin sync.",
            details=str(e),
        ) from e

    os.makedirs(config.TOKENSTORE_DIR, exist_ok=True)

    try:
        client = Garmin()
        client.login(tokenstore=config.TOKENSTORE_DIR)
        return client
    except (GarminConnectAuthenticationError, FileNotFoundError):
        client = None
    except Exception as e:
        raise HarnessError(
            "garmin_token_login_failed",
            "Saved Garmin credentials could not be used.",
            hint="Delete `.garmin_tokens/` and re-run sync if the token store is corrupted.",
            details=str(e),
        ) from e

    # First-time or expired: prompt for credentials
    print("Garmin Connect login required.")
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    try:
        client = Garmin(email=email, password=password)
        client.login(tokenstore=config.TOKENSTORE_DIR)
    except GarminConnectAuthenticationError as e:
        raise HarnessError(
            "garmin_auth_failed",
            "Garmin authentication failed.",
            hint="Double-check your Garmin credentials and any MFA requirements.",
            details=str(e),
        ) from e
    except Exception as e:
        raise HarnessError(
            "garmin_login_failed",
            "Garmin login failed unexpectedly.",
            hint="Retry in a minute. If it keeps failing, re-run with fresh credentials.",
            details=str(e),
        ) from e

    print("Login successful. Tokens saved.")
    return client

import os
import getpass
from pathlib import Path
import config

from errors import DependencyError, HarnessError


def get_client(
    *,
    email: str | None = None,
    password: str | None = None,
    interactive: bool = True,
):
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

    tokenstores = []
    env_tokenstore = os.getenv("GARMINTOKENS")
    if env_tokenstore:
        tokenstores.append(str(Path(env_tokenstore).expanduser()))

    tokenstores.append(config.TOKENSTORE_DIR)
    upstream_tokenstore = str(Path("~/.garminconnect").expanduser())
    if upstream_tokenstore not in tokenstores:
        tokenstores.append(upstream_tokenstore)

    tokenstore_errors = []
    for tokenstore in tokenstores:
        try:
            client = Garmin()
            client.login(tokenstore=tokenstore)
            return client
        except (GarminConnectAuthenticationError, FileNotFoundError) as e:
            tokenstore_errors.append(f"{tokenstore}: {e}")
            client = None
        except Exception as e:
            raise HarnessError(
                "garmin_token_login_failed",
                "Saved Garmin credentials could not be used.",
                hint="Delete the saved Garmin token cache and re-run sync if the token store is corrupted.",
                details=f"{tokenstore}: {e}",
            ) from e

    # First-time or expired: credentials required
    if not email or not password:
        if not interactive:
            raise HarnessError(
                "garmin_login_required",
                "Garmin login is required before sync can continue.",
                hint="Provide Garmin credentials in the UI, or run sync once from the terminal to create a token cache.",
            )

        print("Garmin Connect login required.")
        email = input("Email: ").strip()
        password = getpass.getpass("Password: ")

    try:
        garmin_kwargs = {
            "email": email,
            "password": password,
        }
        if interactive:
            garmin_kwargs["prompt_mfa"] = lambda: input("MFA code: ").strip()

        client = Garmin(**garmin_kwargs)
        client.login(tokenstore=config.TOKENSTORE_DIR)
    except GarminConnectAuthenticationError as e:
        details = str(e)
        if "429" in details or "Cloudflare" in details:
            raise HarnessError(
                "garmin_rate_limited",
                "Garmin Connect is rate-limiting or blocking this login attempt.",
                hint="Wait before retrying. Repeated login attempts can extend the block. If you already created tokens with python-garminconnect, Nyx can also reuse ~/.garminconnect.",
                details=details,
            ) from e
        raise HarnessError(
            "garmin_auth_failed",
            "Garmin authentication failed.",
            hint="Double-check your Garmin credentials and any MFA requirements.",
            details=details,
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

import logging
import os
import getpass
from pathlib import Path
import config

from errors import DependencyError, HarnessError
from logging_utils import get_logger, log_event


logger = get_logger("auth")


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
        from garminconnect import (
            Garmin,
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
        )
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
            log_event(logger, logging.INFO, "garmin.auth.token_login_succeeded", tokenstore=tokenstore)
            return client
        except (GarminConnectAuthenticationError, FileNotFoundError) as e:
            tokenstore_errors.append(f"{tokenstore}: {e}")
            client = None
        except Exception as e:
            log_event(
                logger,
                logging.ERROR,
                "garmin.auth.token_login_failed",
                tokenstore=tokenstore,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise HarnessError(
                "garmin_token_login_failed",
                "Saved Garmin credentials could not be used.",
                hint="Delete the saved Garmin token cache and re-run sync if the token store is corrupted.",
                details=f"{tokenstore}: {e}",
            ) from e

    # First-time or expired: credentials required
    if not email or not password:
        if not interactive:
            log_event(logger, logging.WARNING, "garmin.auth.login_required", interactive=interactive)
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
        log_event(
            logger,
            logging.INFO,
            "garmin.auth.login_succeeded",
            tokenstore=config.TOKENSTORE_DIR,
            interactive=interactive,
        )
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as e:
        details = str(e)
        if "429" in details or "Cloudflare" in details or isinstance(e, GarminConnectConnectionError):
            log_event(
                logger,
                logging.WARNING,
                "garmin.auth.rate_limited",
                interactive=interactive,
                error=details,
            )
            raise HarnessError(
                "garmin_rate_limited",
                "Garmin Connect is rate-limiting or blocking all login strategies.",
                hint=(
                    "All login strategies failed. This is a known Garmin SSO issue (cyberjunky/python-garminconnect#344). "
                    "Wait 15–30 minutes before retrying. If you have tokens from a working machine, "
                    "copy them to ~/.garminconnect or set the GARMINTOKENS env var."
                ),
                details=details,
            ) from e
        log_event(
            logger,
            logging.ERROR,
            "garmin.auth.failed",
            interactive=interactive,
            error=details,
        )
        raise HarnessError(
            "garmin_auth_failed",
            "Garmin authentication failed.",
            hint="Double-check your Garmin credentials and any MFA requirements.",
            details=details,
        ) from e
    except Exception as e:
        log_event(
            logger,
            logging.ERROR,
            "garmin.auth.unexpected_error",
            interactive=interactive,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HarnessError(
            "garmin_login_failed",
            "Garmin login failed unexpectedly.",
            hint="Retry in a minute. If it keeps failing, re-run with fresh credentials.",
            details=str(e),
        ) from e

    print("Login successful. Tokens saved.")
    return client

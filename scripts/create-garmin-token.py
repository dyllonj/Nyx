#!/usr/bin/env python3
import argparse
import getpass
from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or refresh a Garmin token cache for Nyx."
    )
    parser.add_argument(
        "--tokenstore",
        default="~/.garminconnect",
        help="Directory or JSON file path to write tokens to. Default: ~/.garminconnect",
    )
    args = parser.parse_args()

    tokenstore = Path(args.tokenstore).expanduser()
    tokenfile = (
        tokenstore / "garmin_tokens.json"
        if tokenstore.suffix != ".json"
        else tokenstore
    )

    try:
        client = Garmin()
        client.login(tokenstore=str(tokenstore))
        print(f"Existing Garmin token cache is valid: {tokenfile}")
        return 0
    except Exception:
        pass

    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    try:
        client = Garmin(
            email=email,
            password=password,
            prompt_mfa=lambda: input("MFA code: ").strip(),
        )
        client.login(tokenstore=str(tokenstore))
    except GarminConnectAuthenticationError as exc:
        print(f"Garmin authentication failed: {exc}")
        return 1

    print(f"Saved Garmin tokens to: {tokenfile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import datetime
import json
import os
import secrets
import sqlite3
from urllib import error, parse, request

import config
import store
from errors import HarnessError


PROVIDER = "whoop"
WHOOP_AUTHORIZE_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_REVOKE_URL = "https://api.prod.whoop.com/developer/v2/user/access"
DEFAULT_SCOPES = (
    "offline",
    "read:profile",
    "read:body_measurement",
    "read:cycles",
    "read:sleep",
    "read:recovery",
    "read:workout",
)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_timestamp(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _iso_utc(value: datetime.datetime) -> str:
    return value.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def _whoop_client_credentials() -> tuple[str, str]:
    client_id = os.getenv("WHOOP_CLIENT_ID", "").strip()
    client_secret = os.getenv("WHOOP_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HarnessError(
            "whoop_not_configured",
            "WHOOP OAuth credentials are not configured.",
            hint="Set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET before using WHOOP integration.",
        )
    return client_id, client_secret


def generate_oauth_state() -> str:
    return secrets.token_hex(8)


def build_authorization_url(
    redirect_uri: str,
    *,
    state: str,
    scopes: list[str] | None = None,
) -> str:
    client_id, _ = _whoop_client_credentials()
    requested_scopes = scopes or list(DEFAULT_SCOPES)
    query = parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(requested_scopes),
            "state": state,
        }
    )
    return f"{WHOOP_AUTHORIZE_URL}?{query}"


def _post_form(url: str, payload: dict[str, str]) -> dict:
    encoded = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        url,
        data=encoded,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with request.urlopen(req, timeout=config.WHOOP_HTTP_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        code = "whoop_unauthorized" if exc.code == 401 else "whoop_oauth_failed"
        raise HarnessError(
            code,
            "WHOOP rejected the OAuth token request." if exc.code == 401 else "WHOOP OAuth exchange failed.",
            hint="Verify the authorization code, redirect URI, and WHOOP app credentials.",
            details=body or str(exc),
        ) from exc
    except error.URLError as exc:
        raise HarnessError(
            "whoop_oauth_failed",
            "WHOOP OAuth exchange could not reach the WHOOP API.",
            hint="Retry the request. If this persists, inspect WHOOP API connectivity and client credentials.",
            details=str(exc),
        ) from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HarnessError(
            "whoop_oauth_failed",
            "WHOOP OAuth exchange returned an invalid response.",
            details=body,
        ) from exc
    if not isinstance(parsed, dict):
        raise HarnessError(
            "whoop_oauth_failed",
            "WHOOP OAuth exchange returned an unexpected response type.",
            details=body,
        )
    return parsed


def _token_expiry_from_response(payload: dict) -> str | None:
    expires_in = payload.get("expires_in")
    try:
        expires_in_sec = int(expires_in)
    except (TypeError, ValueError):
        return None
    return _iso_utc(_utc_now() + datetime.timedelta(seconds=expires_in_sec))


def _scopes_from_token_payload(payload: dict) -> list[str]:
    scope = str(payload.get("scope") or "").strip()
    return [item for item in scope.split(" ") if item]


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    client_id, client_secret = _whoop_client_credentials()
    token_payload = _post_form(
        WHOOP_TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    token_payload["scope_list"] = _scopes_from_token_payload(token_payload)
    token_payload["token_expires_at"] = _token_expiry_from_response(token_payload)
    return token_payload


def get_connected_account(conn: sqlite3.Connection) -> sqlite3.Row:
    account = store.get_provider_account(conn, PROVIDER)
    if account is None or account["status"] != "connected" or not account["access_token"]:
        raise HarnessError(
            "whoop_not_connected",
            "WHOOP is not connected.",
            hint="Start the WHOOP OAuth flow with POST /api/providers/whoop/connect.",
        )
    return account


def refresh_access_token(conn: sqlite3.Connection, *, force: bool = False) -> sqlite3.Row:
    account = get_connected_account(conn)
    expires_at = _parse_timestamp(account["token_expires_at"])
    refresh_token = account["refresh_token"]
    if not force and expires_at is not None:
        threshold = _utc_now() + datetime.timedelta(seconds=config.WHOOP_TOKEN_REFRESH_LEEWAY_SEC)
        if expires_at > threshold:
            return account
    if not refresh_token:
        return account

    client_id, client_secret = _whoop_client_credentials()
    token_payload = _post_form(
        WHOOP_TOKEN_URL,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "offline",
        },
    )
    stored_scopes = json.loads(account["scopes_json"]) if account["scopes_json"] else None
    scopes = _scopes_from_token_payload(token_payload) or stored_scopes
    store.update_provider_account_tokens(
        conn,
        provider=PROVIDER,
        access_token=str(token_payload["access_token"]),
        refresh_token=str(token_payload.get("refresh_token") or refresh_token),
        token_type=str(token_payload.get("token_type") or account["token_type"] or "bearer"),
        scopes=scopes,
        token_expires_at=_token_expiry_from_response(token_payload),
        refresh_token_expires_at=account["refresh_token_expires_at"],
    )
    refreshed = store.get_provider_account(conn, PROVIDER)
    if refreshed is None:
        raise HarnessError("whoop_refresh_failed", "WHOOP token refresh did not persist correctly.")
    return refreshed


def ensure_fresh_access_token(conn: sqlite3.Connection) -> str:
    account = refresh_access_token(conn)
    access_token = account["access_token"]
    if not access_token:
        raise HarnessError(
            "whoop_not_connected",
            "WHOOP credentials are missing from the local store.",
            hint="Reconnect WHOOP to refresh the stored tokens.",
        )
    return str(access_token)


def revoke_remote_access(access_token: str) -> None:
    req = request.Request(
        WHOOP_REVOKE_URL,
        method="DELETE",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with request.urlopen(req, timeout=config.WHOOP_HTTP_TIMEOUT_SEC):
            return None
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HarnessError(
            "whoop_disconnect_failed",
            "WHOOP rejected the revoke request.",
            hint="The local connection can still be cleared, but WHOOP may keep the token active until it expires.",
            details=body or str(exc),
        ) from exc
    except error.URLError as exc:
        raise HarnessError(
            "whoop_disconnect_failed",
            "WHOOP revoke request could not reach the WHOOP API.",
            hint="The local connection can still be cleared, but WHOOP may keep the token active until it expires.",
            details=str(exc),
        ) from exc

from __future__ import annotations

import base64
import datetime
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import config
from errors import HarnessError


OURA_AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"


def _require_client_credentials() -> tuple[str, str]:
    client_id = os.getenv("OURA_CLIENT_ID", "").strip()
    client_secret = os.getenv("OURA_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        return client_id, client_secret
    raise HarnessError(
        "oura_oauth_not_configured",
        "Oura OAuth credentials are not configured.",
        hint="Set OURA_CLIENT_ID and OURA_CLIENT_SECRET in the Nyx environment before connecting Oura.",
    )


def generate_state() -> str:
    return secrets.token_urlsafe(24)


def build_authorization_url(
    *,
    redirect_uri: str | None = None,
    state: str,
    scopes: list[str] | tuple[str, ...] | None = None,
) -> str:
    client_id, _ = _require_client_credentials()
    requested_scopes = list(scopes or config.OURA_DEFAULT_SCOPES)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "scope": " ".join(requested_scopes),
        "state": state,
    }
    if redirect_uri:
        params["redirect_uri"] = redirect_uri
    return f"{OURA_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str, *, redirect_uri: str | None = None) -> dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
    }
    if redirect_uri:
        form["redirect_uri"] = redirect_uri
    return _post_token_form(form)


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    return _post_token_form(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )


def _post_token_form(form: dict[str, str]) -> dict[str, Any]:
    client_id, client_secret = _require_client_credentials()
    body = urllib.parse.urlencode(form).encode("utf-8")
    headers = {
        "Authorization": "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii"),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    request = urllib.request.Request(OURA_TOKEN_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=config.OURA_HTTP_TIMEOUT_SEC) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        details = _error_details(body)
        raise HarnessError(
            "oura_oauth_failed",
            "Oura OAuth token exchange failed.",
            hint="Retry the connect flow. If the error persists, verify the redirect URI configured in your Oura app.",
            details=details or f"HTTP {exc.code}",
        ) from exc
    except urllib.error.URLError as exc:
        raise HarnessError(
            "oura_oauth_unreachable",
            "Nyx could not reach the Oura OAuth token endpoint.",
            hint="Check network connectivity and retry the Oura connect flow.",
            details=str(exc.reason),
        ) from exc
    except json.JSONDecodeError as exc:
        raise HarnessError(
            "oura_oauth_invalid_response",
            "Oura returned an unreadable OAuth response.",
            hint="Retry the connect flow. If it keeps happening, inspect the raw Oura response.",
            details=str(exc),
        ) from exc

    return _normalize_token_payload(payload)


def _normalize_token_payload(payload: dict[str, Any]) -> dict[str, Any]:
    expires_in = int(payload.get("expires_in", 0) or 0)
    expires_at = None
    if expires_in > 0:
        expires_at = (
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=expires_in)
        ).isoformat(timespec="seconds")

    scopes = payload.get("scope") or payload.get("scopes") or ""
    if isinstance(scopes, str):
        parsed_scopes = [scope for scope in scopes.split() if scope]
    elif isinstance(scopes, list):
        parsed_scopes = [str(scope) for scope in scopes if str(scope).strip()]
    else:
        parsed_scopes = []

    return {
        "access_token": payload.get("access_token"),
        "refresh_token": payload.get("refresh_token"),
        "token_type": payload.get("token_type", "bearer"),
        "expires_in": expires_in,
        "expires_at": expires_at,
        "scope": " ".join(parsed_scopes),
        "scopes": parsed_scopes,
    }


def _error_details(body: str) -> str:
    if not body:
        return ""
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body
    if isinstance(parsed, dict):
        error = parsed.get("error")
        description = parsed.get("error_description")
        if error and description:
            return f"{error}: {description}"
        if error:
            return str(error)
        return json.dumps(parsed, sort_keys=True)
    return body

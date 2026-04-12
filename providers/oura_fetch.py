from __future__ import annotations

import datetime
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

import config
from errors import HarnessError
from logging_utils import get_logger, log_event
from providers.base import ProviderPage
from resilience import CircuitBreaker, CircuitBreakerOpenError


logger = get_logger("providers.oura.fetch")
OURA_API_BASE_URL = "https://api.ouraring.com"
oura_circuit_breaker = CircuitBreaker(
    "oura_api",
    failure_threshold=config.OURA_CIRCUIT_BREAKER_FAILURES,
    recovery_timeout_sec=config.OURA_CIRCUIT_BREAKER_TIMEOUT_SEC,
)


def _retry_delay_sec(attempt: int) -> int:
    return min(config.OURA_RETRY_BASE_DELAY_SEC * (2 ** attempt), config.OURA_RETRY_MAX_DELAY_SEC)


class OuraApiClient:
    def __init__(
        self,
        *,
        access_token: str,
        refresh_token: str | None = None,
        token_expires_at: str | None = None,
        refresh_token_fn: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires_at = token_expires_at
        self._refresh_token_fn = refresh_token_fn

    def get_personal_info(self) -> dict[str, Any]:
        return self._request_json("personal info", "/v2/usercollection/personal_info")

    def list_workouts(
        self,
        *,
        start_date: str,
        end_date: str | None = None,
        next_token: str | None = None,
    ) -> ProviderPage:
        return self._list_document_collection(
            "workout list",
            "/v2/usercollection/workout",
            start_date=start_date,
            end_date=end_date,
            next_token=next_token,
            resource="workout",
        )

    def get_workout(self, document_id: str) -> dict[str, Any]:
        return self._request_json(f"workout {document_id}", f"/v2/usercollection/workout/{document_id}")

    def list_daily_activity(
        self,
        *,
        start_date: str,
        end_date: str | None = None,
        next_token: str | None = None,
    ) -> ProviderPage:
        return self._list_document_collection(
            "daily activity list",
            "/v2/usercollection/daily_activity",
            start_date=start_date,
            end_date=end_date,
            next_token=next_token,
            resource="daily_activity",
        )

    def get_daily_activity(self, document_id: str) -> dict[str, Any]:
        return self._request_json(
            f"daily activity {document_id}",
            f"/v2/usercollection/daily_activity/{document_id}",
        )

    def list_daily_sleep(
        self,
        *,
        start_date: str,
        end_date: str | None = None,
        next_token: str | None = None,
    ) -> ProviderPage:
        return self._list_document_collection(
            "daily sleep list",
            "/v2/usercollection/daily_sleep",
            start_date=start_date,
            end_date=end_date,
            next_token=next_token,
            resource="daily_sleep",
        )

    def list_daily_readiness(
        self,
        *,
        start_date: str,
        end_date: str | None = None,
        next_token: str | None = None,
    ) -> ProviderPage:
        return self._list_document_collection(
            "daily readiness list",
            "/v2/usercollection/daily_readiness",
            start_date=start_date,
            end_date=end_date,
            next_token=next_token,
            resource="daily_readiness",
        )

    def get_daily_readiness(self, document_id: str) -> dict[str, Any]:
        return self._request_json(
            f"daily readiness {document_id}",
            f"/v2/usercollection/daily_readiness/{document_id}",
        )

    def list_sleep(
        self,
        *,
        start_date: str,
        end_date: str | None = None,
        next_token: str | None = None,
    ) -> ProviderPage:
        return self._list_document_collection(
            "sleep list",
            "/v2/usercollection/sleep",
            start_date=start_date,
            end_date=end_date,
            next_token=next_token,
            resource="sleep",
        )

    def get_sleep(self, document_id: str) -> dict[str, Any]:
        return self._request_json(f"sleep {document_id}", f"/v2/usercollection/sleep/{document_id}")

    def list_heartrate(
        self,
        *,
        start_datetime: str,
        end_datetime: str,
        next_token: str | None = None,
    ) -> ProviderPage:
        payload = self._request_json(
            "heartrate list",
            "/v2/usercollection/heartrate",
            query={
                "start_datetime": start_datetime,
                "end_datetime": end_datetime,
                "next_token": next_token,
            },
        )
        return ProviderPage(
            resource="heartrate",
            items=list(payload.get("data", [])),
            next_cursor=payload.get("next_token"),
        )

    def _list_document_collection(
        self,
        label: str,
        path: str,
        *,
        start_date: str,
        end_date: str | None,
        next_token: str | None,
        resource: str,
    ) -> ProviderPage:
        payload = self._request_json(
            label,
            path,
            query={
                "start_date": start_date,
                "end_date": end_date,
                "next_token": next_token,
            },
        )
        return ProviderPage(
            resource=resource,
            items=list(payload.get("data", [])),
            next_cursor=payload.get("next_token"),
        )

    def _request_json(
        self,
        label: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        allow_refresh: bool = True,
    ) -> dict[str, Any]:
        try:
            return oura_circuit_breaker.call(
                lambda: self._retry_request_json(label, path, query=query, allow_refresh=allow_refresh)
            )
        except CircuitBreakerOpenError as exc:
            log_event(
                logger,
                logging.WARNING,
                "oura.circuit_open",
                label=label,
                retry_after_sec=round(exc.retry_after_sec, 1),
            )
            raise HarnessError(
                "oura_temporarily_unavailable",
                "Oura requests are temporarily paused after repeated failures.",
                hint=f"Wait about {int(round(exc.retry_after_sec))} seconds and retry the Oura sync.",
                details=str(exc),
            ) from exc

    def _retry_request_json(
        self,
        label: str,
        path: str,
        *,
        query: dict[str, Any] | None,
        allow_refresh: bool,
    ) -> dict[str, Any]:
        refreshed = False
        for attempt in range(config.OURA_RETRY_ATTEMPTS):
            try:
                if self._token_is_stale() and not refreshed and self._refresh_access_token():
                    refreshed = True
                return self._perform_request(path, query=query)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 401 and allow_refresh and not refreshed and self._refresh_access_token():
                    refreshed = True
                    continue
                if exc.code == 403:
                    raise HarnessError(
                        "oura_access_forbidden",
                        "Oura denied access to the requested resource.",
                        hint="This usually means the Oura account membership or granted scopes do not allow this data.",
                        details=_extract_error_message(body) or "HTTP 403",
                    ) from exc
                if exc.code in {429, 500, 502, 503, 504}:
                    if attempt == config.OURA_RETRY_ATTEMPTS - 1:
                        raise HarnessError(
                            "oura_rate_limited" if exc.code == 429 else "oura_fetch_failed",
                            "Oura request retries were exhausted.",
                            hint="Retry the Oura sync shortly. If this keeps happening, reduce backfill scope and inspect provider health.",
                            details=_extract_error_message(body) or f"HTTP {exc.code}",
                        ) from exc
                    delay = _retry_delay_sec(attempt)
                    log_event(
                        logger,
                        logging.WARNING,
                        "oura.retry_scheduled",
                        label=label,
                        status_code=exc.code,
                        attempt=attempt + 1,
                        retry_in_sec=delay,
                    )
                    time.sleep(delay)
                    continue
                raise HarnessError(
                    "oura_fetch_failed",
                    f"Oura request failed during `{label}`.",
                    hint="Verify the connected Oura account scopes and retry.",
                    details=_extract_error_message(body) or f"HTTP {exc.code}",
                ) from exc
            except urllib.error.URLError as exc:
                if attempt == config.OURA_RETRY_ATTEMPTS - 1:
                    raise HarnessError(
                        "oura_unreachable",
                        "Nyx could not reach the Oura API.",
                        hint="Check network connectivity and retry the Oura sync.",
                        details=str(exc.reason),
                    ) from exc
                delay = _retry_delay_sec(attempt)
                log_event(
                    logger,
                    logging.WARNING,
                    "oura.retry_scheduled",
                    label=label,
                    attempt=attempt + 1,
                    retry_in_sec=delay,
                    error_type=type(exc).__name__,
                )
                time.sleep(delay)

        raise HarnessError("oura_fetch_failed", f"Oura request failed during `{label}`.")

    def _perform_request(self, path: str, *, query: dict[str, Any] | None) -> dict[str, Any]:
        url = f"{OURA_API_BASE_URL}{path}"
        cleaned_query = {key: value for key, value in (query or {}).items() if value is not None and value != ""}
        if cleaned_query:
            url = f"{url}?{urllib.parse.urlencode(cleaned_query)}"

        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=config.OURA_HTTP_TIMEOUT_SEC) as response:
            raw = response.read()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _token_is_stale(self) -> bool:
        if not self.token_expires_at:
            return False
        try:
            expires_at = datetime.datetime.fromisoformat(self.token_expires_at)
        except ValueError:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.UTC)
        now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=config.OURA_TOKEN_REFRESH_SKEW_SEC)
        return now >= expires_at

    def _refresh_access_token(self) -> bool:
        if not self.refresh_token or self._refresh_token_fn is None:
            return False
        token_payload = self._refresh_token_fn(self.refresh_token)
        self.access_token = str(token_payload.get("access_token") or self.access_token)
        self.refresh_token = str(token_payload.get("refresh_token") or self.refresh_token)
        self.token_expires_at = token_payload.get("expires_at") or self.token_expires_at
        log_event(logger, logging.INFO, "oura.token_refreshed")
        return True


def _extract_error_message(body: str) -> str:
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if message:
            return str(message)
        return json.dumps(payload, sort_keys=True)
    return body

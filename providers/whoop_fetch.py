import json
import logging
import sqlite3
import time
from urllib import error, parse, request

import config
from errors import HarnessError
from logging_utils import get_logger, log_event
from providers import whoop_auth
from resilience import CircuitBreaker, CircuitBreakerOpenError


logger = get_logger("providers.whoop_fetch")
WHOOP_API_BASE_URL = "https://api.prod.whoop.com/developer/v2"
whoop_circuit_breaker = CircuitBreaker(
    "whoop_api",
    failure_threshold=config.WHOOP_CIRCUIT_BREAKER_FAILURES,
    recovery_timeout_sec=config.WHOOP_CIRCUIT_BREAKER_TIMEOUT_SEC,
)


def _retry_delay_sec(attempt: int) -> int:
    return min(
        config.WHOOP_RETRY_BASE_DELAY_SEC * (2 ** attempt),
        config.WHOOP_RETRY_MAX_DELAY_SEC,
    )


def _request_json(
    method: str,
    url: str,
    *,
    access_token: str,
    params: dict[str, str | int | None] | None = None,
) -> dict:
    query_params = {key: value for key, value in (params or {}).items() if value is not None}
    if query_params:
        url = f"{url}?{parse.urlencode(query_params)}"
    req = request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    with request.urlopen(req, timeout=config.WHOOP_HTTP_TIMEOUT_SEC) as response:
        body = response.read().decode("utf-8")
        if response.status == 204 or not body:
            return {}
        return json.loads(body)


def _retryable_http_status(status_code: int) -> bool:
    return status_code in {429, 500, 502, 503, 504}


class WhoopApiClient:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection | None = None,
        access_token: str | None = None,
    ) -> None:
        self._conn = conn
        self._access_token = access_token

    def _resolve_access_token(self, *, force_refresh: bool = False) -> str:
        if self._conn is not None:
            if force_refresh:
                return str(whoop_auth.refresh_access_token(self._conn, force=True)["access_token"])
            return whoop_auth.ensure_fresh_access_token(self._conn)
        if not self._access_token:
            raise HarnessError("whoop_not_connected", "WHOOP access token is unavailable.")
        return self._access_token

    def _call_api(
        self,
        label: str,
        fn,
        *,
        attempts: int | None = None,
    ) -> dict:
        attempts = attempts or config.WHOOP_RETRY_ATTEMPTS

        def execute():
            unauthorized_retry_used = False
            for attempt in range(attempts):
                try:
                    return fn(force_refresh=False)
                except error.HTTPError as exc:
                    body = exc.read().decode("utf-8", errors="replace")
                    if exc.code == 401 and self._conn is not None and not unauthorized_retry_used:
                        unauthorized_retry_used = True
                        return fn(force_refresh=True)
                    if exc.code == 401:
                        raise HarnessError(
                            "whoop_unauthorized",
                            "WHOOP rejected the access token.",
                            hint="Reconnect WHOOP if the stored token is no longer valid.",
                            details=body or str(exc),
                        ) from exc
                    if _retryable_http_status(exc.code):
                        if attempt == attempts - 1:
                            code = "whoop_rate_limited" if exc.code == 429 else "whoop_fetch_failed"
                            raise HarnessError(
                                code,
                                "WHOOP rate-limited the request too many times."
                                if exc.code == 429
                                else f"WHOOP request failed repeatedly during `{label}`.",
                                hint="Retry the WHOOP sync shortly.",
                                details=body or str(exc),
                            ) from exc
                        delay = _retry_delay_sec(attempt)
                        log_event(
                            logger,
                            logging.WARNING,
                            "whoop.retry_scheduled",
                            label=label,
                            attempt=attempt + 1,
                            retry_in_sec=delay,
                            http_status=exc.code,
                        )
                        time.sleep(delay)
                        continue
                    raise HarnessError(
                        "whoop_fetch_failed",
                        f"WHOOP request failed during `{label}`.",
                        hint="Inspect WHOOP credentials, scopes, and API availability.",
                        details=body or str(exc),
                    ) from exc
                except error.URLError as exc:
                    if attempt == attempts - 1:
                        raise HarnessError(
                            "whoop_fetch_failed",
                            f"WHOOP connectivity failed during `{label}`.",
                            hint="Retry the WHOOP sync shortly.",
                            details=str(exc),
                        ) from exc
                    delay = _retry_delay_sec(attempt)
                    log_event(
                        logger,
                        logging.WARNING,
                        "whoop.retry_scheduled",
                        label=label,
                        attempt=attempt + 1,
                        retry_in_sec=delay,
                        error_type=type(exc).__name__,
                    )
                    time.sleep(delay)
                except json.JSONDecodeError as exc:
                    raise HarnessError(
                        "whoop_fetch_failed",
                        f"WHOOP returned invalid JSON during `{label}`.",
                        details=str(exc),
                    ) from exc

            raise HarnessError("whoop_fetch_failed", f"WHOOP request failed during `{label}`.")

        try:
            return whoop_circuit_breaker.call(execute)
        except CircuitBreakerOpenError as exc:
            raise HarnessError(
                "whoop_temporarily_unavailable",
                "WHOOP requests are temporarily paused after repeated failures.",
                hint=f"Wait about {int(round(exc.retry_after_sec))} seconds, then retry sync.",
                details=str(exc),
            ) from exc

    def _get(self, path: str, *, label: str, params: dict[str, str | int | None] | None = None) -> dict:
        url = f"{WHOOP_API_BASE_URL}{path}"

        def do_request(*, force_refresh: bool) -> dict:
            token = self._resolve_access_token(force_refresh=force_refresh)
            return _request_json("GET", url, access_token=token, params=params)

        return self._call_api(label, do_request)

    def get_basic_profile(self) -> dict:
        return self._get("/user/profile/basic", label="profile")

    def get_body_measurements(self) -> dict:
        return self._get("/user/measurement/body", label="body measurement")

    def get_cycle(self, cycle_id: int | str) -> dict:
        return self._get(f"/cycle/{cycle_id}", label=f"cycle {cycle_id}")

    def list_cycles(self, *, start: str | None = None, end: str | None = None) -> list[dict]:
        return self._iter_collection("/cycle", label="cycle collection", start=start, end=end)

    def get_sleep(self, sleep_id: str) -> dict:
        return self._get(f"/activity/sleep/{sleep_id}", label=f"sleep {sleep_id}")

    def list_sleeps(self, *, start: str | None = None, end: str | None = None) -> list[dict]:
        return self._iter_collection("/activity/sleep", label="sleep collection", start=start, end=end)

    def get_recovery(self, cycle_id: int | str) -> dict:
        return self._get(f"/cycle/{cycle_id}/recovery", label=f"recovery {cycle_id}")

    def list_recoveries(self, *, start: str | None = None, end: str | None = None) -> list[dict]:
        return self._iter_collection("/recovery", label="recovery collection", start=start, end=end)

    def get_workout(self, workout_id: str) -> dict:
        return self._get(f"/activity/workout/{workout_id}", label=f"workout {workout_id}")

    def list_workouts(self, *, start: str | None = None, end: str | None = None) -> list[dict]:
        return self._iter_collection("/activity/workout", label="workout collection", start=start, end=end)

    def _iter_collection(
        self,
        path: str,
        *,
        label: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        records: list[dict] = []
        next_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            payload = self._get(
                path,
                label=label,
                params={
                    "limit": config.WHOOP_SYNC_PAGE_SIZE,
                    "start": start,
                    "end": end,
                    "nextToken": next_token,
                },
            )
            page_records = payload.get("records")
            if isinstance(page_records, list):
                records.extend(record for record in page_records if isinstance(record, dict))
            next_token = payload.get("next_token")
            if not next_token or not isinstance(next_token, str) or next_token in seen_tokens:
                return records
            seen_tokens.add(next_token)

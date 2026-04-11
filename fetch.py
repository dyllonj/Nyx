import logging
import time

import config
from errors import DependencyError, HarnessError
from logging_utils import get_logger, log_event
from resilience import CircuitBreaker, CircuitBreakerOpenError


logger = get_logger("fetch")
garmin_circuit_breaker = CircuitBreaker(
    "garmin_api",
    failure_threshold=config.GARMIN_CIRCUIT_BREAKER_FAILURES,
    recovery_timeout_sec=config.GARMIN_CIRCUIT_BREAKER_TIMEOUT_SEC,
)


def _garmin_error_types():
    try:
        from garminconnect import (
            GarminConnectConnectionError,
            GarminConnectTooManyRequestsError,
        )
    except ImportError as e:
        raise DependencyError(
            "missing_garmin_dependency",
            "Garmin sync requires the `python-garminconnect` package.",
            hint="Run `pip install -r requirements.txt` to enable Garmin sync.",
            details=str(e),
        ) from e
    return GarminConnectTooManyRequestsError, GarminConnectConnectionError


def _retry_delay_sec(attempt: int) -> int:
    return min(
        config.GARMIN_RETRY_BASE_DELAY_SEC * (2 ** attempt),
        config.GARMIN_RETRY_MAX_DELAY_SEC,
    )


def _retry_garmin_call(label: str, fn, *, attempts: int | None = None):
    rate_limit_error, connection_error = _garmin_error_types()
    attempts = attempts or config.GARMIN_RETRY_ATTEMPTS
    for attempt in range(attempts):
        try:
            return fn()
        except (rate_limit_error, connection_error) as e:
            if attempt == attempts - 1:
                is_rate_limited = isinstance(e, rate_limit_error)
                raise HarnessError(
                    "garmin_rate_limited" if is_rate_limited else "garmin_fetch_failed",
                    (
                        f"Garmin rate-limited the `{label}` request too many times."
                        if is_rate_limited
                        else f"Garmin connectivity failed repeatedly during `{label}`."
                    ),
                    hint=(
                        "Wait a few minutes, then retry `python cli.py sync`."
                        if is_rate_limited
                        else "Retry the sync shortly. If this persists, inspect Garmin connectivity and token health."
                    ),
                    details=str(e),
                ) from e
            delay = _retry_delay_sec(attempt)
            log_event(
                logger,
                logging.WARNING,
                "garmin.retry_scheduled",
                label=label,
                attempt=attempt + 1,
                retry_in_sec=delay,
                error_type=type(e).__name__,
            )
            time.sleep(delay)
        except Exception as e:
            log_event(
                logger,
                logging.ERROR,
                "garmin.fetch_failed",
                label=label,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise HarnessError(
                "garmin_fetch_failed",
                f"Garmin request failed during `{label}`.",
                hint="Retry the sync. If this keeps failing, inspect Garmin connectivity and token health.",
                details=str(e),
            ) from e


def _call_garmin_api(label: str, fn):
    try:
        return garmin_circuit_breaker.call(lambda: _retry_garmin_call(label, fn))
    except CircuitBreakerOpenError as exc:
        log_event(
            logger,
            logging.WARNING,
            "garmin.circuit_open",
            label=label,
            retry_after_sec=round(exc.retry_after_sec, 1),
        )
        raise HarnessError(
            "garmin_temporarily_unavailable",
            "Garmin requests are temporarily paused after repeated failures.",
            hint=f"Wait about {int(round(exc.retry_after_sec))} seconds, then retry sync.",
            details=str(exc),
        ) from exc


def fetch_running_activities(client, start_date: str) -> list[dict]:
    """Fetch running activities from a watermark date onward."""
    log_event(logger, logging.INFO, "garmin.activities.fetch_started", start_date=start_date)
    activities = _call_garmin_api(
        "activity list",
        lambda: client.get_activities_by_date(
            startdate=start_date,
            activitytype="running",
        ),
    )
    log_event(logger, logging.INFO, "garmin.activities.fetch_completed", start_date=start_date, count=len(activities))
    return activities


def fetch_activity_detail(client, activity_id: int) -> dict:
    """Fetch per-sample time-series data for one activity."""
    log_event(logger, logging.DEBUG, "garmin.activity_detail.fetch_started", activity_id=activity_id)
    time.sleep(config.DETAIL_FETCH_DELAY_SEC)
    return _call_garmin_api(
        f"activity detail {activity_id}",
        lambda: client.get_activity_details(str(activity_id), maxchart=2000),
    )


def fetch_activity_splits(client, activity_id: int) -> dict:
    """Fetch lap-level split data for one activity."""
    log_event(logger, logging.DEBUG, "garmin.activity_splits.fetch_started", activity_id=activity_id)
    time.sleep(config.DETAIL_FETCH_DELAY_SEC)
    return _call_garmin_api(
        f"activity splits {activity_id}",
        lambda: client.get_activity_splits(str(activity_id)),
    )


def parse_detail_metrics(detail: dict) -> dict:
    """Parse the descriptor-indexed metric samples from a detail response.

    Returns a dict of lists, one list per metric type, with units normalized:
      cadence_samples   : full SPM (both feet)
      hr_samples        : bpm
      oscillation_samples: cm
      gct_samples       : ms
      stride_samples    : cm
    """
    descriptors = detail.get("metricDescriptors", [])
    key_to_idx = {d["key"]: d["metricsIndex"] for d in descriptors}

    result = {
        "cadence_samples": [],
        "hr_samples": [],
        "oscillation_samples": [],
        "gct_samples": [],
        "stride_samples": [],
    }

    for sample in detail.get("activityDetailMetrics", []):
        row = sample.get("metrics", [])

        def get(key):
            idx = key_to_idx.get(key)
            if idx is not None and idx < len(row) and row[idx] is not None:
                try:
                    return float(row[idx])
                except (TypeError, ValueError):
                    return None
            return None

        c = get("directCadence")
        if c is not None and c > 0:
            result["cadence_samples"].append(c * 2)  # half-cadence -> full SPM

        h = get("directHeartRate")
        if h is not None and h > 0:
            result["hr_samples"].append(h)

        o = get("directVerticalOscillation")
        if o is not None and o > 0:
            result["oscillation_samples"].append(o / 10.0)  # mm -> cm

        g = get("directGroundContactTime")
        if g is not None and g > 0:
            result["gct_samples"].append(g)

        s = get("directStrideLength")
        if s is not None and s > 0:
            result["stride_samples"].append(s)

    return result

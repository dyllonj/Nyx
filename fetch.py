import time

import config
from errors import DependencyError, HarnessError


def _rate_limit_error_type():
    try:
        from garminconnect import GarminConnectTooManyRequestsError
    except ImportError as e:
        raise DependencyError(
            "missing_garmin_dependency",
            "Garmin sync requires the `python-garminconnect` package.",
            hint="Run `pip install -r requirements.txt` to enable Garmin sync.",
            details=str(e),
        ) from e
    return GarminConnectTooManyRequestsError


def _retry_garmin_call(label: str, fn, *, attempts: int = 3):
    rate_limit_error = _rate_limit_error_type()
    delays = [15, 30, 60]
    for attempt in range(attempts):
        try:
            return fn()
        except rate_limit_error as e:
            if attempt == attempts - 1:
                raise HarnessError(
                    "garmin_rate_limited",
                    f"Garmin rate-limited the `{label}` request too many times.",
                    hint="Wait a few minutes, then retry `python cli.py sync`.",
                    details=str(e),
                ) from e
            delay = delays[min(attempt, len(delays) - 1)]
            print(f"\n  Rate limited on {label} — waiting {delay}s before retry...")
            time.sleep(delay)
        except Exception as e:
            raise HarnessError(
                "garmin_fetch_failed",
                f"Garmin request failed during `{label}`.",
                hint="Retry the sync. If this keeps failing, inspect Garmin connectivity and token health.",
                details=str(e),
            ) from e


def fetch_running_activities(client, start_date: str) -> list[dict]:
    """Fetch running activities from a watermark date onward."""
    print(f"Fetching activity list from {start_date}...", end="", flush=True)
    activities = _retry_garmin_call(
        "activity list",
        lambda: client.get_activities_by_date(
            startdate=start_date,
            activitytype="running",
        ),
    )
    print(f" {len(activities)} runs found.")
    return activities


def fetch_activity_detail(client, activity_id: int) -> dict:
    """Fetch per-sample time-series data for one activity."""
    time.sleep(config.DETAIL_FETCH_DELAY_SEC)
    return _retry_garmin_call(
        f"activity detail {activity_id}",
        lambda: client.get_activity_details(str(activity_id), maxchart=2000),
    )


def fetch_activity_splits(client, activity_id: int) -> dict:
    """Fetch lap-level split data for one activity."""
    time.sleep(config.DETAIL_FETCH_DELAY_SEC)
    return _retry_garmin_call(
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

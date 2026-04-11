import time
import config
from garminconnect import Garmin, GarminConnectTooManyRequestsError


def fetch_all_running_activities(client: Garmin) -> list[dict]:
    """Fetch all running activities from the beginning of time."""
    print("Fetching activity list...", end="", flush=True)
    activities = client.get_activities_by_date(
        startdate="2000-01-01",
        activitytype="running",
    )
    print(f" {len(activities)} runs found.")
    return activities


def fetch_activity_detail(client: Garmin, activity_id: int) -> dict:
    """Fetch per-sample time-series data for one activity."""
    time.sleep(config.DETAIL_FETCH_DELAY_SEC)
    try:
        return client.get_activity_details(str(activity_id), maxchart=2000)
    except GarminConnectTooManyRequestsError:
        print("\n  Rate limited — waiting 30s...")
        time.sleep(30)
        return client.get_activity_details(str(activity_id), maxchart=2000)


def fetch_activity_splits(client: Garmin, activity_id: int) -> dict:
    """Fetch lap-level split data for one activity."""
    time.sleep(config.DETAIL_FETCH_DELAY_SEC)
    try:
        return client.get_activity_splits(str(activity_id))
    except GarminConnectTooManyRequestsError:
        print("\n  Rate limited — waiting 30s...")
        time.sleep(30)
        return client.get_activity_splits(str(activity_id))


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

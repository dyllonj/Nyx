import datetime
import json
import math
import sqlite3
from functools import lru_cache
from typing import Optional

import config
import generate_vdot
import store


_VDOT_MIN = 30.0
_VDOT_MAX = 85.0


def _meta_float(conn: sqlite3.Connection, key: str) -> Optional[float]:
    raw = store.get_meta(conn, key)
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _meta_int(conn: sqlite3.Connection, key: str) -> Optional[int]:
    raw = store.get_meta(conn, key)
    if not raw:
        return None
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile() requires at least one value")

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]

    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


@lru_cache(maxsize=1)
def _vdot_pace_table() -> dict[int, dict]:
    path = f"{config.KNOWLEDGE_DIR}/vdot_paces.json"
    with open(path, "r", encoding="utf-8") as f:
        table = json.load(f)
    return {int(entry["vdot"]): entry for entry in table}


def _resolve_resting_hr(conn: sqlite3.Connection) -> int:
    resting_hr = _meta_int(conn, "resting_hr")
    if resting_hr is None or resting_hr <= 0:
        return 60
    return resting_hr


def _get_or_estimate_max_hr(conn: sqlite3.Connection) -> Optional[int]:
    stored_max_hr = _meta_int(conn, "max_hr_estimated")
    if stored_max_hr is not None and stored_max_hr > 0:
        return stored_max_hr

    row = conn.execute(
        "SELECT MAX(max_hr) AS max_hr FROM runs WHERE max_hr IS NOT NULL"
    ).fetchone()
    if not row or row["max_hr"] is None:
        return None

    max_hr = int(round(row["max_hr"]))
    if max_hr <= 0:
        return None

    store.set_meta(conn, "max_hr_estimated", str(max_hr))
    return max_hr


def _refresh_hr_zones(
    conn: sqlite3.Connection,
    max_hr: Optional[int] = None,
    resting_hr: Optional[int] = None,
) -> Optional[dict]:
    resolved_max_hr = max_hr if max_hr is not None else _get_or_estimate_max_hr(conn)
    if resolved_max_hr is None:
        return None

    resolved_resting_hr = resting_hr if resting_hr is not None else _resolve_resting_hr(conn)
    zones = compute_hr_zones(resolved_max_hr, resolved_resting_hr)
    store.set_meta(conn, "hr_zones_json", json.dumps(zones))
    return zones


def _qualifying_vdot_estimates(conn: sqlite3.Connection, max_hr: int) -> list[float]:
    rows = conn.execute(
        """
        SELECT distance_m, duration_sec, avg_hr
        FROM runs
        WHERE avg_hr IS NOT NULL
          AND pace_min_per_km IS NOT NULL
          AND duration_sec >= ?
          AND distance_m IS NOT NULL
          AND distance_m > 0
        ORDER BY start_time DESC
        """,
        (config.VDOT_MIN_RUN_DURATION_SEC,),
    ).fetchall()

    hr_low = max_hr * config.VDOT_HR_LOWER_FRACTION
    hr_high = max_hr * config.VDOT_HR_UPPER_FRACTION
    estimates: list[float] = []

    for row in rows:
        avg_hr = row["avg_hr"]
        duration_sec = row["duration_sec"] or 0
        distance_m = row["distance_m"] or 0

        if avg_hr is None or avg_hr < hr_low or avg_hr > hr_high:
            continue
        if duration_sec <= 0 or distance_m <= 0:
            continue

        race_equivalent = generate_vdot.vdot_from_race(distance_m, duration_sec / 60.0)
        estimates.append(race_equivalent * config.VDOT_EFFORT_CORRECTION)

    return estimates


def estimate_vdot_from_runs(conn: sqlite3.Connection) -> Optional[float]:
    max_hr = _get_or_estimate_max_hr(conn)
    if max_hr is None:
        store.set_meta(conn, "vdot_qualifying_run_count", "0")
        store.set_meta(conn, "current_vdot", "")
        store.set_meta(conn, "vdot_estimated_at", "")
        return None

    estimates = _qualifying_vdot_estimates(conn, max_hr)
    store.set_meta(conn, "vdot_qualifying_run_count", str(len(estimates)))
    if not estimates:
        store.set_meta(conn, "current_vdot", "")
        store.set_meta(conn, "vdot_estimated_at", "")
        return None

    vdot = _percentile(estimates, config.VDOT_ESTIMATE_PERCENTILE)
    vdot = max(_VDOT_MIN, min(_VDOT_MAX, vdot))

    store.set_meta(conn, "current_vdot", f"{vdot:.2f}")
    store.set_meta(conn, "vdot_estimated_at", datetime.date.today().isoformat())
    return vdot


def lookup_training_paces(vdot: float) -> dict:
    table = _vdot_pace_table()
    lookup_vdot = int(round(max(_VDOT_MIN, min(_VDOT_MAX, vdot))))
    return dict(table[lookup_vdot])


def compute_hr_zones(max_hr: int, resting_hr: int = 60) -> dict:
    if max_hr <= 0:
        raise ValueError("max_hr must be positive")
    if resting_hr <= 0:
        raise ValueError("resting_hr must be positive")
    if max_hr <= resting_hr:
        raise ValueError("max_hr must be greater than resting_hr")

    hrr = max_hr - resting_hr
    zone_specs = [
        (1, "Recovery", 0.50, 0.60),
        (2, "Easy", 0.60, 0.70),
        (3, "Aerobic", 0.70, 0.80),
        (4, "Threshold", 0.80, 0.90),
        (5, "Maximum", 0.90, 1.00),
    ]

    zones = []
    for zone_num, name, lower_frac, upper_frac in zone_specs:
        hr_low = int(round(resting_hr + hrr * lower_frac))
        hr_high = max_hr if upper_frac == 1.0 else int(round(resting_hr + hrr * upper_frac))
        zones.append({
            "zone": zone_num,
            "name": name,
            "hr_low": hr_low,
            "hr_high": hr_high,
        })

    return {
        "max_hr": max_hr,
        "resting_hr": resting_hr,
        "method": "karvonen",
        "zones": zones,
    }


def build_zones_context(conn: sqlite3.Connection) -> str:
    sections: list[str] = []

    current_vdot = _meta_float(conn, "current_vdot")
    if current_vdot is not None:
        pace_entry = lookup_training_paces(current_vdot)
        sections.extend([
            "-- Estimated VDOT & Training Paces ----------------",
            f"  Current VDOT   : {current_vdot:.1f}  (estimated from training runs, +/-3 pts)",
            f"  Easy pace      : {pace_entry['easy_pace_range_min_per_km']} /km  (conversational effort, build base)",
            f"  Marathon pace  : {pace_entry['marathon_pace_min_per_km']} /km",
            f"  Threshold pace : {pace_entry['threshold_pace_min_per_km']} /km  (comfortably hard, ~35-40 min tempo)",
            f"  Interval pace  : {pace_entry['interval_pace_min_per_km']} /km  (VO2max efforts, 3-5 min reps)",
        ])

    hr_zones_raw = store.get_meta(conn, "hr_zones_json")
    if hr_zones_raw:
        try:
            hr_zones = json.loads(hr_zones_raw)
        except json.JSONDecodeError:
            hr_zones = None

        if hr_zones:
            if sections:
                sections.append("")
            sections.extend([
                "-- Heart Rate Zones (Karvonen) -------------------",
                f"  Max HR         : {hr_zones['max_hr']} bpm   Resting HR: {hr_zones['resting_hr']} bpm",
            ])
            for zone in hr_zones.get("zones", []):
                note = "  <- most easy runs should stay here" if zone.get("zone") == 2 else ""
                sections.append(
                    f"  Zone {zone['zone']} {zone['name']:<10}: {zone['hr_low']}-{zone['hr_high']} bpm{note}"
                )

    return "\n".join(sections)

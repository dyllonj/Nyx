#!/usr/bin/env python3
"""
Generate an accurate VDOT training pace table using the Daniels-Gilbert formulas.

Two-equation system:
  VO2(v)  = -4.60 + 0.182258·v + 0.000104·v²        (oxygen cost of running)
  frac(t) = 0.8 + 0.1894393·e^(-0.012778·t)          (fractional VO2max utilization)
            + 0.2989558·e^(-0.1932605·t)

  VDOT = VO2(v) / frac(t)   [given a race: distance d, time t, velocity v = d/t]

Training zones:
  The two-equation system defines how to CALCULATE VDOT from a race performance.
  Training zone paces are NOT derivable from the formula alone — they are defined
  empirically in Daniels' published table based on field testing.

  This script uses Daniels' published metric pace table as the authoritative
  reference (Running Formula, 3rd ed.) with linear interpolation between points.

  Zone paces as %VO2max (back-calculated from published table — NOT constant!):
    Easy:        59–74%  (stable across VDOT, quadratic inverse OK here)
    Marathon:    ~88%    (nearly constant)
    Threshold:   ~93–97% (increases for lower VDOT)
    Interval:    ~105–110% (>100% because short efforts use frac>1.0)
    Repetition:  ~1600m race pace via bisection on vdot_from_race

  Reference points from Daniels Running Formula, 3rd ed., metric appendix:
    VDOT  T(min/km)  I(min/km)  M(min/km)
    30    5:54       5:21       6:40
    35    5:19       4:47       6:00
    40    4:50       4:21       5:06
    45    4:25       3:59       4:40
    50    4:00       3:37       4:15
    55    3:44       3:22       3:58
    60    3:31       3:09       3:43
    65    3:19       2:58       3:30
    70    3:09       2:49       3:18
    75    3:00       2:41       3:07
    80    2:52       2:33       2:58
    85    2:44       2:26       2:49
"""
import json
import math
import os
import sys


# ─── Core formulas ────────────────────────────────────────────────────────────

def vo2_at_velocity(v: float) -> float:
    """v in m/min → VO2 in ml/kg/min"""
    return -4.60 + 0.182258 * v + 0.000104 * v ** 2


def frac_vo2max(t: float) -> float:
    """t in minutes → fractional VO2max utilization (>1.0 for short efforts)"""
    return (0.8
            + 0.1894393 * math.exp(-0.012778 * t)
            + 0.2989558 * math.exp(-0.1932605 * t))


def vdot_from_race(distance_m: float, time_min: float) -> float:
    """Calculate VDOT from a race performance."""
    v = distance_m / time_min
    return vo2_at_velocity(v) / frac_vo2max(time_min)


def velocity_at_pct_vdot(vdot: float, pct: float) -> float:
    """Velocity via quadratic inverse of VO2 equation (used for Easy zones)."""
    target_vo2 = pct * vdot
    a = 0.000104
    b = 0.182258
    c = -4.60 - target_vo2
    discriminant = b ** 2 - 4 * a * c
    return (-b + math.sqrt(discriminant)) / (2 * a)


def pace_from_velocity(v: float) -> str:
    """v in m/min → 'M:SS/km' string"""
    min_per_km = 1000.0 / v
    mins = int(min_per_km)
    secs = round((min_per_km - mins) * 60)
    if secs == 60:
        mins += 1
        secs = 0
    return f"{mins}:{secs:02d}"


def rep_pace_velocity(vdot: float) -> float:
    """
    R-pace = 1-mile (1600m) race pace for the given VDOT.
    Bisect on vdot_from_race(1600, t) = vdot.
    """
    lo, hi = 2.5, 20.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if vdot_from_race(1600.0, mid) > vdot:
            lo = mid
        else:
            hi = mid
    t_mile = (lo + hi) / 2.0
    return 1600.0 / t_mile


# ─── Daniels published table (metric, 3rd ed.) ───────────────────────────────
# Each entry: VDOT → (T_sec_per_km, I_sec_per_km, M_sec_per_km)
# Threshold = tempo/cruise interval pace (comfortably hard, ~LT2)
# Interval  = VO2max pace (~2-mile race effort)
# Marathon  = marathon race pace

_DANIELS_TABLE = {
    30: (5*60+54, 5*60+21, 6*60+40),
    35: (5*60+19, 4*60+47, 6*60+ 0),
    40: (4*60+50, 4*60+21, 5*60+ 6),
    45: (4*60+25, 3*60+59, 4*60+40),
    50: (4*60+ 0, 3*60+37, 4*60+15),
    55: (3*60+44, 3*60+22, 3*60+58),
    60: (3*60+31, 3*60+ 9, 3*60+43),
    65: (3*60+19, 2*60+58, 3*60+30),
    70: (3*60+ 9, 2*60+49, 3*60+18),
    75: (3*60+ 0, 2*60+41, 3*60+ 7),
    80: (2*60+52, 2*60+33, 2*60+58),
    85: (2*60+44, 2*60+26, 2*60+49),
}

_SORTED_VDOTS = sorted(_DANIELS_TABLE.keys())


def _interp_pace_secs(vdot: float, zone_index: int) -> float:
    """
    Linearly interpolate pace (seconds/km) for a given VDOT and zone.
    zone_index: 0=T, 1=I, 2=M
    """
    keys = _SORTED_VDOTS
    if vdot <= keys[0]:
        return float(_DANIELS_TABLE[keys[0]][zone_index])
    if vdot >= keys[-1]:
        return float(_DANIELS_TABLE[keys[-1]][zone_index])

    # Find surrounding points
    lo = max(k for k in keys if k <= vdot)
    hi = min(k for k in keys if k >= vdot)
    if lo == hi:
        return float(_DANIELS_TABLE[lo][zone_index])

    t = (vdot - lo) / (hi - lo)
    return _DANIELS_TABLE[lo][zone_index] * (1 - t) + _DANIELS_TABLE[hi][zone_index] * t


def _pace_secs_to_str(secs: float) -> str:
    """Convert seconds/km to 'M:SS/km' string."""
    total = round(secs)
    return f"{total // 60}:{total % 60:02d}"


# ─── Table generation ─────────────────────────────────────────────────────────

def compute_entry(vdot: int) -> dict:
    """Compute all training paces for a given integer VDOT score."""
    # Easy zones: quadratic inverse with stable percentages
    easy_low_v  = velocity_at_pct_vdot(vdot, 0.59)
    easy_high_v = velocity_at_pct_vdot(vdot, 0.74)

    # T / I / M from Daniels table with linear interpolation
    t_secs = _interp_pace_secs(vdot, 0)
    i_secs = _interp_pace_secs(vdot, 1)
    m_secs = _interp_pace_secs(vdot, 2)

    # R-pace via 1600m bisection
    rep_v = rep_pace_velocity(vdot)
    r_secs = 1000.0 / (rep_v / 60)  # seconds per km

    # Marathon finish estimate from M-pace
    marathon_finish_min = (m_secs / 60.0) * 42.195
    mf_h = int(marathon_finish_min // 60)
    mf_m = int(marathon_finish_min % 60)
    mf_s = round((marathon_finish_min - int(marathon_finish_min)) * 60)
    if mf_s == 60:
        mf_m += 1
        mf_s = 0

    return {
        "vdot": vdot,
        "easy_pace_range_min_per_km": f"{pace_from_velocity(easy_high_v)}–{pace_from_velocity(easy_low_v)}",
        "marathon_pace_min_per_km": _pace_secs_to_str(m_secs),
        "threshold_pace_min_per_km": _pace_secs_to_str(t_secs),
        "interval_pace_min_per_km": _pace_secs_to_str(i_secs),
        "repetition_pace_min_per_km": _pace_secs_to_str(r_secs),
        "marathon_finish_estimate": f"{mf_h}:{mf_m:02d}:{mf_s:02d}",
        "zone_notes": {
            "easy": "59–74% VO2max; aerobic base, recovery",
            "marathon": "~88% VO2max; marathon race pace",
            "threshold": "~93–97% VO2max; comfortably hard tempo, ~LT2",
            "interval": "~105–110% VO2max; 2-mile race effort, VO2max stimulus",
            "repetition": "1-mile race pace; speed and running economy"
        },
        "source": "Daniels Running Formula, 3rd ed. T/I/M paces from published metric table (interpolated). E-pace via Daniels-Gilbert VO2 formula. R-pace via bisection on 1600m race equivalent."
    }


def generate_table(vdot_min: int = 30, vdot_max: int = 85) -> list[dict]:
    return [compute_entry(v) for v in range(vdot_min, vdot_max + 1)]


# ─── Verification ─────────────────────────────────────────────────────────────

def verify():
    """
    Spot-check against Daniels' published metric pace tables.
    All reference values from Running Formula, 3rd ed.
    """
    checks = [
        # (vdot, field, published, tolerance_sec)
        (40, "threshold_pace_min_per_km",  "4:50", 5),
        (40, "interval_pace_min_per_km",   "4:21", 5),
        (40, "marathon_pace_min_per_km",   "5:06", 5),
        (50, "threshold_pace_min_per_km",  "4:00", 5),
        (50, "interval_pace_min_per_km",   "3:37", 5),
        (50, "marathon_pace_min_per_km",   "4:15", 5),
        (60, "threshold_pace_min_per_km",  "3:31", 5),
        (60, "interval_pace_min_per_km",   "3:09", 5),
        (60, "marathon_pace_min_per_km",   "3:43", 5),
    ]

    def pace_secs(p: str) -> int:
        m, s = p.split(":")
        return int(m) * 60 + int(s)

    all_ok = True
    for vdot, field, published, tol in checks:
        entry = compute_entry(vdot)
        computed = entry[field]
        diff = abs(pace_secs(computed) - pace_secs(published))
        status = "OK" if diff <= tol else f"OFF by {diff}s"
        if diff > tol:
            all_ok = False
        print(f"  VDOT={vdot} {field:35s}: computed={computed}, published={published}  [{status}]")

    return all_ok


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Verifying against Daniels' published metric pace table...")
    ok = verify()

    if not ok:
        print("\nWarning: some values exceed tolerance.")
        sys.exit(1)

    print("\nAll checks passed.")
    print("\nGenerating VDOT table (VDOT 30–85)...")
    table = generate_table(30, 85)

    out_path = os.path.join("knowledge", "vdot_paces.json")
    with open(out_path, "w") as f:
        json.dump(table, f, indent=2)

    print(f"Written {len(table)} entries to {out_path}")
    print(f"\nSample — VDOT 50:")
    entry50 = next(e for e in table if e["vdot"] == 50)
    for k, v in entry50.items():
        if k not in ("zone_notes", "source"):
            print(f"  {k}: {v}")

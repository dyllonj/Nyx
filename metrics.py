"""
Run Efficiency Index (REI) and derived running metrics.

REI answers: "How economically did you run, accounting for effort?"
Score of 100 = hitting all physiological targets at your aerobic baseline.
Scores above 80 are strong; below 60 indicate room for improvement.

Components:
  Cadence Score      (30%) — higher cadence = less impact, better economy
  Oscillation Score  (25%) — less bounce = more forward propulsion
  Aerobic Efficiency (30%) — faster pace per heartbeat = better fitness
  Ground Contact     (15%) — shorter contact = more elastic energy return
                             (requires Running Dynamics; absent on wrist-only)
"""
import statistics
from typing import Optional
import config
from models import RunSummary


def _safe_mean(samples: list[float]) -> Optional[float]:
    return statistics.mean(samples) if samples else None


def _safe_stdev(samples: list[float]) -> Optional[float]:
    return statistics.stdev(samples) if len(samples) >= 2 else None


def apply_detail_metrics(run: RunSummary, parsed: dict) -> None:
    """Write averaged detail metrics back onto a RunSummary in-place."""
    run.avg_cadence_spm = _safe_mean(parsed["cadence_samples"])
    run.avg_vertical_osc_cm = _safe_mean(parsed["oscillation_samples"])
    run.avg_ground_contact_ms = _safe_mean(parsed["gct_samples"])
    run.avg_stride_length_cm = _safe_mean(parsed["stride_samples"])

    # Cadence consistency: coefficient of variation (%)
    mean_c = _safe_mean(parsed["cadence_samples"])
    std_c = _safe_stdev(parsed["cadence_samples"])
    if mean_c and std_c and mean_c > 0:
        run.cadence_cv = (std_c / mean_c) * 100


def apply_split_metrics(run: RunSummary, splits: dict) -> None:
    """Compute HR drift from lap data."""
    laps = splits.get("lapDTOs", [])
    if len(laps) < 3:
        return

    # Skip first and last lap (warmup/cooldown)
    middle = laps[1:-1]
    if len(middle) < 2:
        return

    # Filter to laps that have HR and speed data
    valid = [
        lap for lap in middle
        if lap.get("averageHR") and lap.get("averageSpeed")
    ]
    if len(valid) < 2:
        return

    # Compare first third vs last third by avg HR
    third = max(1, len(valid) // 3)
    first_third = valid[:third]
    last_third = valid[-third:]

    hr_start = statistics.mean(lap["averageHR"] for lap in first_third)
    hr_end = statistics.mean(lap["averageHR"] for lap in last_third)

    if hr_start > 0:
        run.hr_drift_pct = ((hr_end - hr_start) / hr_start) * 100


def compute_aerobic_efficiency(run: RunSummary) -> Optional[float]:
    """Pace (min/km) divided by avg HR. Lower = more efficient."""
    if run.pace_min_per_km and run.avg_hr and run.avg_hr > 0:
        return run.pace_min_per_km / run.avg_hr
    return None


def compute_rei(run: RunSummary, ae_baseline: Optional[float]) -> Optional[float]:
    """
    Compute the Run Efficiency Index (0-100).

    Each component is scored 0-100, then weighted. Missing components are
    dropped and the remaining weights are renormalized to sum to 1.0.
    """
    scores: dict[str, float] = {}
    weights: dict[str, float] = {}

    # --- Cadence (higher is better, target 170 SPM) ---
    if run.avg_cadence_spm is not None and run.avg_cadence_spm > 0:
        scores["cadence"] = min(run.avg_cadence_spm / config.CADENCE_TARGET_SPM, 1.0) * 100
        weights["cadence"] = config.REI_WEIGHT_CADENCE

    # --- Vertical oscillation (lower is better, target 8.0 cm) ---
    if run.avg_vertical_osc_cm is not None and run.avg_vertical_osc_cm > 0:
        scores["oscillation"] = min(config.OSCILLATION_TARGET_CM / run.avg_vertical_osc_cm, 1.0) * 100
        weights["oscillation"] = config.REI_WEIGHT_OSCILLATION

    # --- Aerobic efficiency (higher AE value = less efficient; baseline anchors score) ---
    ae = compute_aerobic_efficiency(run)
    if ae is not None and ae_baseline is not None and ae_baseline > 0:
        scores["ae"] = min(ae_baseline / ae, 1.0) * 100
        weights["ae"] = config.REI_WEIGHT_AEROBIC_EFF

    # --- Ground contact time (lower is better, target 240 ms) ---
    if run.avg_ground_contact_ms is not None and run.avg_ground_contact_ms > 0:
        scores["gct"] = min(config.GROUND_CONTACT_TARGET_MS / run.avg_ground_contact_ms, 1.0) * 100
        weights["gct"] = config.REI_WEIGHT_GROUND_CONTACT

    if not weights:
        return None

    total_weight = sum(weights.values())
    rei = sum(scores[k] * weights[k] / total_weight for k in weights)
    return round(rei, 1)


def compute_all(run: RunSummary, ae_baseline: Optional[float]) -> None:
    """Compute and store all derived metrics on a RunSummary in-place."""
    run.aerobic_efficiency = compute_aerobic_efficiency(run)
    run.rei = compute_rei(run, ae_baseline)


def rei_component_breakdown(run: RunSummary, ae_baseline: Optional[float]) -> list[dict]:
    """Return a list of component dicts for the inspect command."""
    components = []

    if run.avg_cadence_spm is not None and run.avg_cadence_spm > 0:
        score = min(run.avg_cadence_spm / config.CADENCE_TARGET_SPM, 1.0) * 100
        components.append({
            "name": "Cadence",
            "score": score,
            "detail": f"{run.avg_cadence_spm:.0f} spm / target {config.CADENCE_TARGET_SPM} spm",
            "weight": config.REI_WEIGHT_CADENCE,
        })

    if run.avg_vertical_osc_cm is not None and run.avg_vertical_osc_cm > 0:
        score = min(config.OSCILLATION_TARGET_CM / run.avg_vertical_osc_cm, 1.0) * 100
        components.append({
            "name": "Vertical Oscillation",
            "score": score,
            "detail": f"{run.avg_vertical_osc_cm:.1f} cm / target {config.OSCILLATION_TARGET_CM} cm",
            "weight": config.REI_WEIGHT_OSCILLATION,
        })

    ae = compute_aerobic_efficiency(run)
    if ae is not None and ae_baseline is not None and ae_baseline > 0:
        score = min(ae_baseline / ae, 1.0) * 100
        components.append({
            "name": "Aerobic Efficiency",
            "score": score,
            "detail": f"AE {ae:.4f} / baseline {ae_baseline:.4f}",
            "weight": config.REI_WEIGHT_AEROBIC_EFF,
        })

    if run.avg_ground_contact_ms is not None and run.avg_ground_contact_ms > 0:
        score = min(config.GROUND_CONTACT_TARGET_MS / run.avg_ground_contact_ms, 1.0) * 100
        components.append({
            "name": "Ground Contact Time",
            "score": score,
            "detail": f"{run.avg_ground_contact_ms:.0f} ms / target {config.GROUND_CONTACT_TARGET_MS} ms",
            "weight": config.REI_WEIGHT_GROUND_CONTACT,
        })

    # Annotate each component with its renormalized contribution
    total_weight = sum(c["weight"] for c in components)
    for c in components:
        c["contribution"] = c["score"] * c["weight"] / total_weight if total_weight else 0

    return components

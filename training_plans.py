import datetime
from typing import Literal

from pydantic import BaseModel, Field

import store


class TrainingWorkout(BaseModel):
    day: str
    kind: Literal["easy", "quality", "long_run", "recovery", "race", "strength"]
    title: str
    description: str


class TrainingWeek(BaseModel):
    week: int
    phase: Literal["base", "build", "specific", "recovery", "taper", "race"]
    target_distance_km: float
    focus: str
    workouts: list[TrainingWorkout]


class TrainingPlan(BaseModel):
    goal: str
    weeks: int
    days_per_week: int
    current_vdot: float | None = None
    recent_42d_distance_km: float = 0.0
    estimated_weekly_distance_km: float = 0.0
    generated_at: str
    notes: list[str]
    weeks_detail: list[TrainingWeek]


def _goal_profile(goal: str) -> tuple[str, int | None]:
    normalized = goal.strip().lower()
    if "marathon" in normalized:
        return "marathon", 42
    if "half" in normalized or "21k" in normalized:
        return "half_marathon", 21
    if "10k" in normalized or "10 km" in normalized:
        return "10k", 10
    if "5k" in normalized or "5 km" in normalized:
        return "5k", 5
    return "general", None


def _easy_pace_hint(current_vdot: float | None) -> str:
    if current_vdot is None:
        return "easy conversational effort"

    from vdot_zones import lookup_training_paces

    return lookup_training_paces(current_vdot)["easy_pace_range_min_per_km"]


def _quality_description(profile: str, current_vdot: float | None, phase: str, week: int) -> str:
    if current_vdot is not None:
        from vdot_zones import lookup_training_paces

        paces = lookup_training_paces(current_vdot)
        threshold = paces["threshold_pace_min_per_km"]
        interval = paces["interval_pace_min_per_km"]
    else:
        threshold = "comfortably hard effort"
        interval = "5k effort"

    if phase == "base":
        return f"20-30 min steady tempo at {threshold} with full control."
    if phase == "build":
        return f"5-6 x 3 min at {interval} with 2 min easy jog recoveries."
    if phase == "specific" and profile in {"half_marathon", "marathon"}:
        return f"2 x 15 min at {threshold} with 5 min easy between blocks."
    if phase == "specific":
        return f"8 x 400m at {interval} with 200m jog recoveries."
    if phase == "taper":
        return "Short sharpening session: 6 x 1 min fast with full recovery."
    return f"Threshold progression run at {threshold}."


def _focus_for_week(profile: str, phase: str, week: int, weeks: int) -> str:
    if phase == "base":
        return "Build aerobic consistency and keep easy days truly easy."
    if phase == "build":
        return "Add controlled quality without letting weekly load spike."
    if phase == "specific":
        return (
            "Practice race-specific rhythm and fueling."
            if profile in {"half_marathon", "marathon"}
            else "Sharpen top-end efficiency while preserving durability."
        )
    if phase == "recovery":
        return "Absorb prior work and arrive fresher for the next block."
    if phase == "taper":
        return "Reduce fatigue while keeping a small amount of sharpness."
    return "Stay fresh, trust the taper, and execute the goal effort."


def _phase_for_week(profile: str, week: int, weeks: int) -> str:
    if week == weeks and profile != "general":
        return "race"
    if profile != "general" and week == weeks - 1:
        return "taper"
    if week % 4 == 0:
        return "recovery"
    if week <= max(2, weeks // 3):
        return "base"
    if week >= max(3, weeks - 2):
        return "specific"
    return "build"


def _build_week(
    *,
    profile: str,
    week: int,
    weeks: int,
    days_per_week: int,
    target_distance_km: float,
    current_vdot: float | None,
) -> TrainingWeek:
    phase = _phase_for_week(profile, week, weeks)
    easy_hint = _easy_pace_hint(current_vdot)
    long_run_km = round(max(8.0, min(target_distance_km * 0.32, target_distance_km * 0.42)), 1)
    workouts = [
        TrainingWorkout(
            day="Tue",
            kind="easy",
            title="Easy aerobic run",
            description=f"45-60 min at {easy_hint}. Keep breathing smooth and relaxed.",
        ),
        TrainingWorkout(
            day="Thu",
            kind="quality" if phase != "race" else "race",
            title="Primary session" if phase != "race" else "Goal race",
            description=(
                _quality_description(profile, current_vdot, phase, week)
                if phase != "race"
                else "Race day. Start controlled and build only if form and breathing stay stable."
            ),
        ),
        TrainingWorkout(
            day="Sat",
            kind="long_run",
            title="Long run",
            description=f"{long_run_km:.1f} km at easy effort. Practice fueling if the goal is longer than 10K.",
        ),
        TrainingWorkout(
            day="Sun",
            kind="recovery",
            title="Recovery run or cross-train",
            description="30-40 min very easy, or low-stress cross-training if fatigue is lingering.",
        ),
    ]

    if days_per_week >= 5:
        workouts.insert(
            1,
            TrainingWorkout(
                day="Wed",
                kind="strength",
                title="Strength + strides",
                description="20-30 min of basic strength work, then 4-6 relaxed strides.",
            ),
        )

    return TrainingWeek(
        week=week,
        phase=phase,
        target_distance_km=round(target_distance_km, 1),
        focus=_focus_for_week(profile, phase, week, weeks),
        workouts=workouts[: max(days_per_week, 4)],
    )


def generate_plan(
    *,
    goal: str,
    weeks: int,
    current_vdot: float | None,
    recent_42d_distance_km: float,
    days_per_week: int = 4,
) -> TrainingPlan:
    weeks = max(2, min(20, weeks))
    days_per_week = max(3, min(6, days_per_week))
    profile, _ = _goal_profile(goal)

    estimated_weekly_distance = round(max(16.0, recent_42d_distance_km / 6.0), 1)
    target = estimated_weekly_distance
    weeks_detail: list[TrainingWeek] = []

    for week in range(1, weeks + 1):
        phase = _phase_for_week(profile, week, weeks)
        if phase == "race":
            target = max(10.0, target * 0.55)
        elif phase == "taper":
            target = max(12.0, target * 0.75)
        elif phase == "recovery":
            target = max(16.0, target * 0.88)
        elif phase == "base":
            target = target * 1.05
        elif phase == "build":
            target = target * 1.08
        elif phase == "specific":
            target = target * 1.03

        weeks_detail.append(
            _build_week(
                profile=profile,
                week=week,
                weeks=weeks,
                days_per_week=days_per_week,
                target_distance_km=target,
                current_vdot=current_vdot,
            )
        )

    notes = [
        "Treat the target distance as an upper bound when sleep, soreness, or life stress is compromised.",
        "If two hard weeks in a row feel unsustainably heavy, repeat the prior week instead of forcing progression.",
    ]
    if current_vdot is None:
        notes.append("VDOT was not available, so pace cues are effort-based instead of pace-specific.")
    else:
        notes.append(f"Current VDOT {current_vdot:.1f} was used to anchor easy, threshold, and interval guidance.")

    return TrainingPlan(
        goal=goal,
        weeks=weeks,
        days_per_week=days_per_week,
        current_vdot=current_vdot,
        recent_42d_distance_km=round(recent_42d_distance_km, 1),
        estimated_weekly_distance_km=estimated_weekly_distance,
        generated_at=datetime.datetime.now().isoformat(timespec="seconds"),
        notes=notes,
        weeks_detail=weeks_detail,
    )


def build_plan_from_db(
    conn,
    *,
    goal: str,
    weeks: int,
    days_per_week: int = 4,
    current_vdot: float | None = None,
) -> TrainingPlan:
    runs = store.get_all_runs(conn)
    cutoff = datetime.datetime.now() - datetime.timedelta(days=42)
    recent_distance_km = 0.0
    for row in runs:
        try:
            started = datetime.datetime.fromisoformat(row["start_time"])
        except (TypeError, ValueError):
            continue
        if started >= cutoff:
            recent_distance_km += (row["distance_m"] or 0.0) / 1000.0

    if current_vdot is None:
        raw_vdot = store.get_meta(conn, "current_vdot")
        current_vdot = float(raw_vdot) if raw_vdot else None

    return generate_plan(
        goal=goal,
        weeks=weeks,
        days_per_week=days_per_week,
        current_vdot=current_vdot,
        recent_42d_distance_km=recent_distance_km,
    )

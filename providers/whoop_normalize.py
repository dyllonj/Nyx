import datetime


PROVIDER = "whoop"


def _parse_timestamp(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _parse_timezone_offset(value: str | None) -> datetime.timezone:
    if not value:
        return datetime.timezone.utc
    try:
        sign = -1 if value.startswith("-") else 1
        hours, minutes = value.lstrip("+-").split(":")
        delta = datetime.timedelta(hours=int(hours), minutes=int(minutes))
    except (AttributeError, ValueError):
        return datetime.timezone.utc
    return datetime.timezone(sign * delta)


def _local_date(timestamp: str | None, timezone_offset: str | None) -> str | None:
    dt = _parse_timestamp(timestamp)
    if dt is None:
        return None
    return dt.astimezone(_parse_timezone_offset(timezone_offset)).date().isoformat()


def _seconds_from_milli(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return None


def _kcal_from_kj(value) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 4.184, 2)
    except (TypeError, ValueError):
        return None


def _max_timestamp(*timestamps: str | None) -> str | None:
    parsed = [dt for dt in (_parse_timestamp(item) for item in timestamps) if dt is not None]
    if not parsed:
        return None
    return max(parsed).isoformat(timespec="seconds")


def normalize_profile(profile: dict, body_measurements: dict | None = None) -> dict:
    first_name = str(profile.get("first_name") or "").strip()
    last_name = str(profile.get("last_name") or "").strip()
    display_name = " ".join(item for item in (first_name, last_name) if item).strip()
    merged_profile = dict(profile)
    if body_measurements:
        merged_profile["body_measurements"] = body_measurements
    return {
        "provider": PROVIDER,
        "external_user_id": str(profile.get("user_id") or "") or None,
        "email": str(profile.get("email") or "").strip() or None,
        "display_name": display_name or None,
        "profile": merged_profile,
    }


def normalize_workout(payload: dict) -> tuple[dict, list[dict]]:
    score = payload.get("score") or {}
    timezone_offset = payload.get("timezone_offset")
    energy_kj = score.get("kilojoule")
    activity = {
        "provider": PROVIDER,
        "source_id": str(payload["id"]),
        "external_user_id": str(payload.get("user_id") or "") or None,
        "source_type": "workout",
        "activity_type": "run" if str(payload.get("sport_name") or "").lower() == "running" else "workout",
        "sport_name": payload.get("sport_name"),
        "name": str(payload.get("sport_name") or "WHOOP workout").replace("_", " ").title(),
        "score_state": payload.get("score_state"),
        "started_at": payload.get("start"),
        "ended_at": payload.get("end"),
        "local_date": _local_date(payload.get("start"), timezone_offset),
        "timezone_offset": timezone_offset,
        "duration_sec": _duration_seconds(payload.get("start"), payload.get("end")),
        "distance_m": _coerce_float(score.get("distance_meter")),
        "energy_kj": _coerce_float(energy_kj),
        "calories_kcal": _kcal_from_kj(energy_kj),
        "strain_score": _coerce_float(score.get("strain")),
        "avg_hr": _coerce_float(score.get("average_heart_rate")),
        "max_hr": _coerce_float(score.get("max_heart_rate")),
        "percent_recorded": _coerce_float(score.get("percent_recorded")),
        "altitude_gain_m": _coerce_float(score.get("altitude_gain_meter")),
        "altitude_change_m": _coerce_float(score.get("altitude_change_meter")),
        "source_updated_at": payload.get("updated_at"),
    }
    samples: list[dict] = []
    zone_durations = score.get("zone_durations") or {}
    zone_keys = (
        "zone_zero_milli",
        "zone_one_milli",
        "zone_two_milli",
        "zone_three_milli",
        "zone_four_milli",
        "zone_five_milli",
    )
    for index, key in enumerate(zone_keys):
        value = _seconds_from_milli(zone_durations.get(key))
        if value is None:
            continue
        samples.append(
            {
                "sample_type": "heart_rate_zone_duration",
                "bucket_index": index,
                "sample_value": value,
                "sample_unit": "sec",
                "sample_start_at": None,
                "sample_end_at": None,
                "source_updated_at": payload.get("updated_at"),
            }
        )
    return activity, samples


def normalize_daily_recovery(
    *,
    cycle: dict | None,
    sleep: dict | None,
    recovery: dict | None,
) -> dict | None:
    if cycle is None and sleep is None and recovery is None:
        return None

    cycle = cycle or {}
    sleep = sleep or {}
    recovery = recovery or {}
    cycle_score = cycle.get("score") or {}
    sleep_score = sleep.get("score") or {}
    recovery_score = recovery.get("score") or {}
    stage_summary = sleep_score.get("stage_summary") or {}
    sleep_needed = sleep_score.get("sleep_needed") or {}
    timezone_offset = sleep.get("timezone_offset") or cycle.get("timezone_offset")
    recovery_date = (
        _local_date(sleep.get("end"), timezone_offset)
        or _local_date(cycle.get("end"), cycle.get("timezone_offset"))
        or _local_date(sleep.get("start"), timezone_offset)
    )
    if recovery_date is None:
        return None

    total_sleep_needed_sec = sum(
        value
        for value in (
            _seconds_from_milli(sleep_needed.get("baseline_milli")),
            _seconds_from_milli(sleep_needed.get("need_from_sleep_debt_milli")),
            _seconds_from_milli(sleep_needed.get("need_from_recent_strain_milli")),
            _seconds_from_milli(sleep_needed.get("need_from_recent_nap_milli")),
        )
        if value is not None
    ) or None

    energy_kj = _coerce_float(cycle_score.get("kilojoule"))
    return {
        "provider": PROVIDER,
        "recovery_date": recovery_date,
        "external_user_id": _first_non_empty(
            recovery.get("user_id"),
            sleep.get("user_id"),
            cycle.get("user_id"),
        ),
        "source_cycle_id": _string_or_none(recovery.get("cycle_id") or cycle.get("id")),
        "source_sleep_id": _string_or_none(recovery.get("sleep_id") or sleep.get("id")),
        "source_status": recovery.get("score_state") or sleep.get("score_state") or cycle.get("score_state"),
        "sleep_start_at": sleep.get("start"),
        "sleep_end_at": sleep.get("end"),
        "timezone_offset": timezone_offset,
        "total_in_bed_sec": _seconds_from_milli(stage_summary.get("total_in_bed_time_milli")),
        "total_awake_sec": _seconds_from_milli(stage_summary.get("total_awake_time_milli")),
        "total_no_data_sec": _seconds_from_milli(stage_summary.get("total_no_data_time_milli")),
        "total_light_sleep_sec": _seconds_from_milli(stage_summary.get("total_light_sleep_time_milli")),
        "total_slow_wave_sleep_sec": _seconds_from_milli(stage_summary.get("total_slow_wave_sleep_time_milli")),
        "total_rem_sleep_sec": _seconds_from_milli(stage_summary.get("total_rem_sleep_time_milli")),
        "sleep_cycle_count": _coerce_int(stage_summary.get("sleep_cycle_count")),
        "disturbance_count": _coerce_int(stage_summary.get("disturbance_count")),
        "sleep_needed_sec": total_sleep_needed_sec,
        "respiratory_rate": _coerce_float(sleep_score.get("respiratory_rate")),
        "sleep_performance_pct": _coerce_float(sleep_score.get("sleep_performance_percentage")),
        "sleep_consistency_pct": _coerce_float(sleep_score.get("sleep_consistency_percentage")),
        "sleep_efficiency_pct": _coerce_float(sleep_score.get("sleep_efficiency_percentage")),
        "recovery_score": _coerce_float(recovery_score.get("recovery_score")),
        "resting_hr": _coerce_float(recovery_score.get("resting_heart_rate")),
        "hrv_rmssd_ms": _coerce_float(recovery_score.get("hrv_rmssd_milli")),
        "spo2_pct": _coerce_float(recovery_score.get("spo2_percentage")),
        "skin_temp_c": _coerce_float(recovery_score.get("skin_temp_celsius")),
        "day_strain_score": _coerce_float(cycle_score.get("strain")),
        "day_energy_kj": energy_kj,
        "day_calories_kcal": _kcal_from_kj(energy_kj),
        "day_avg_hr": _coerce_float(cycle_score.get("average_heart_rate")),
        "day_max_hr": _coerce_float(cycle_score.get("max_heart_rate")),
        "source_updated_at": _max_timestamp(
            cycle.get("updated_at"),
            sleep.get("updated_at"),
            recovery.get("updated_at"),
        ),
    }


def normalize_sync_bundle(
    *,
    cycles: list[dict],
    sleeps: list[dict],
    recoveries: list[dict],
    workouts: list[dict],
) -> dict:
    activities: list[dict] = []
    activity_samples: dict[str, list[dict]] = {}
    for workout in workouts:
        activity, samples = normalize_workout(workout)
        activities.append(activity)
        activity_samples[activity["source_id"]] = samples

    cycle_by_id = {str(record["id"]): record for record in cycles if record.get("id") is not None}
    sleep_by_cycle_id = {
        str(record["cycle_id"]): record
        for record in sleeps
        if record.get("cycle_id") is not None
    }
    recovery_by_cycle_id = {
        str(record["cycle_id"]): record
        for record in recoveries
        if record.get("cycle_id") is not None
    }
    recovery_rows: list[dict] = []
    for cycle_id in sorted(set(cycle_by_id) | set(sleep_by_cycle_id) | set(recovery_by_cycle_id)):
        row = normalize_daily_recovery(
            cycle=cycle_by_id.get(cycle_id),
            sleep=sleep_by_cycle_id.get(cycle_id),
            recovery=recovery_by_cycle_id.get(cycle_id),
        )
        if row is not None:
            recovery_rows.append(row)

    return {
        "activities": activities,
        "activity_samples": activity_samples,
        "daily_recovery": recovery_rows,
    }


def _duration_seconds(started_at: str | None, ended_at: str | None) -> float | None:
    start_dt = _parse_timestamp(started_at)
    end_dt = _parse_timestamp(ended_at)
    if start_dt is None or end_dt is None:
        return None
    return max(0.0, (end_dt - start_dt).total_seconds())


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_non_empty(*values) -> str | None:
    for value in values:
        text = _string_or_none(value)
        if text is not None:
            return text
    return None

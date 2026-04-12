from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any

from providers.base import NormalizedActivity, NormalizedBatch, NormalizedDailyRecovery, ProviderRawData


def normalize_payloads(*, account_id: int, raw: ProviderRawData) -> NormalizedBatch:
    batch = NormalizedBatch()
    batch.activities.extend(_normalize_workouts(account_id=account_id, workouts=raw.activity_summaries))
    batch.daily_recovery.extend(_normalize_daily_recovery(account_id=account_id, raw=raw))
    return batch


def _normalize_workouts(*, account_id: int, workouts: list[dict[str, Any]]) -> list[NormalizedActivity]:
    normalized: list[NormalizedActivity] = []
    for workout in workouts:
        start_time = str(workout.get("start_datetime") or "")
        end_time = str(workout.get("end_datetime") or "") or None
        duration_sec = _duration_seconds(start_time, end_time)
        normalized.append(
            NormalizedActivity(
                provider="oura",
                provider_account_id=account_id,
                provider_activity_id=str(workout["id"]),
                source_type="workout",
                activity_type=_string_or_none(workout.get("activity")),
                name=_string_or_none(workout.get("label")) or _title_case(workout.get("activity")),
                start_time=start_time,
                end_time=end_time,
                day=_string_or_none(workout.get("day")),
                duration_sec=duration_sec,
                distance_m=_float_or_none(workout.get("distance")),
                calories=_float_or_none(workout.get("calories")),
                intensity=_string_or_none(workout.get("intensity")),
                source=_string_or_none(workout.get("source")),
                metadata={
                    "oura_day": workout.get("day"),
                    "raw_source_type": "workout",
                },
            )
        )
    return normalized


def _normalize_daily_recovery(*, account_id: int, raw: ProviderRawData) -> list[NormalizedDailyRecovery]:
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "daily_activity": None,
            "daily_sleep": None,
            "daily_readiness": None,
            "sleep": [],
            "heartrate": [],
        }
    )

    for payload in raw.daily_health.get("daily_activity", []):
        buckets[str(payload.get("day"))]["daily_activity"] = payload
    for payload in raw.daily_health.get("daily_sleep", []):
        buckets[str(payload.get("day"))]["daily_sleep"] = payload
    for payload in raw.daily_health.get("daily_readiness", []):
        buckets[str(payload.get("day"))]["daily_readiness"] = payload
    for payload in raw.daily_health.get("sleep", []):
        buckets[str(payload.get("day"))]["sleep"].append(payload)
    for payload in raw.daily_health.get("heartrate", []):
        timestamp = _string_or_none(payload.get("timestamp"))
        if not timestamp:
            continue
        buckets[timestamp[:10]]["heartrate"].append(payload)

    normalized: list[NormalizedDailyRecovery] = []
    for day in sorted(day for day in buckets if day and day != "None"):
        bucket = buckets[day]
        daily_activity = bucket["daily_activity"] or {}
        daily_sleep = bucket["daily_sleep"] or {}
        daily_readiness = bucket["daily_readiness"] or {}
        sleep_documents = list(bucket["sleep"])
        heartrate_samples = list(bucket["heartrate"])
        primary_sleep = _pick_primary_sleep(sleep_documents)

        metadata = {
            "document_ids": {
                "daily_activity": daily_activity.get("id"),
                "daily_sleep": daily_sleep.get("id"),
                "daily_readiness": daily_readiness.get("id"),
                "sleep": primary_sleep.get("id") if primary_sleep else None,
            },
            "oura_activity": {
                "target_calories": daily_activity.get("target_calories"),
                "target_meters": daily_activity.get("target_meters"),
                "meters_to_target": daily_activity.get("meters_to_target"),
                "non_wear_time": daily_activity.get("non_wear_time"),
                "resting_time": daily_activity.get("resting_time"),
                "inactivity_alerts": daily_activity.get("inactivity_alerts"),
            },
            "oura_sleep": {
                "sleep_type": primary_sleep.get("type") if primary_sleep else None,
                "readiness_score_delta": primary_sleep.get("readiness_score_delta") if primary_sleep else None,
                "sleep_score_delta": primary_sleep.get("sleep_score_delta") if primary_sleep else None,
            },
        }

        if heartrate_samples:
            average_daytime_hr = sum(sample.get("bpm", 0) for sample in heartrate_samples) / len(heartrate_samples)
            metadata["oura_heartrate"] = {
                "sample_count": len(heartrate_samples),
                "average_bpm": round(average_daytime_hr, 2),
            }

        contributors = {
            "activity": daily_activity.get("contributors"),
            "sleep": daily_sleep.get("contributors"),
            "readiness": daily_readiness.get("contributors"),
        }

        normalized.append(
            NormalizedDailyRecovery(
                provider="oura",
                provider_account_id=account_id,
                day=day,
                provider_day_id=_first_non_empty(
                    daily_readiness.get("id"),
                    daily_sleep.get("id"),
                    daily_activity.get("id"),
                    primary_sleep.get("id") if primary_sleep else None,
                ),
                recovery_score=_int_or_none(daily_readiness.get("score") or _nested_get(primary_sleep, "readiness", "score")),
                readiness_score=_int_or_none(daily_readiness.get("score")),
                sleep_score=_int_or_none(daily_sleep.get("score")),
                activity_score=_int_or_none(daily_activity.get("score")),
                resting_heart_rate=_float_or_none(
                    (primary_sleep or {}).get("lowest_heart_rate") or (primary_sleep or {}).get("average_heart_rate")
                ),
                average_heart_rate=_float_or_none((primary_sleep or {}).get("average_heart_rate")),
                average_hrv=_float_or_none((primary_sleep or {}).get("average_hrv")),
                body_temperature_delta_c=_float_or_none(daily_readiness.get("temperature_deviation")),
                body_temperature_trend_delta_c=_float_or_none(daily_readiness.get("temperature_trend_deviation")),
                sleep_duration_sec=_int_or_none((primary_sleep or {}).get("total_sleep_duration")),
                time_in_bed_sec=_int_or_none((primary_sleep or {}).get("time_in_bed")),
                deep_sleep_duration_sec=_int_or_none((primary_sleep or {}).get("deep_sleep_duration")),
                rem_sleep_duration_sec=_int_or_none((primary_sleep or {}).get("rem_sleep_duration")),
                light_sleep_duration_sec=_int_or_none((primary_sleep or {}).get("light_sleep_duration")),
                awake_time_sec=_int_or_none((primary_sleep or {}).get("awake_time")),
                latency_sec=_int_or_none((primary_sleep or {}).get("latency")),
                sleep_efficiency=_int_or_none((primary_sleep or {}).get("efficiency")),
                average_breath=_float_or_none((primary_sleep or {}).get("average_breath")),
                active_calories=_int_or_none(daily_activity.get("active_calories")),
                steps=_int_or_none(daily_activity.get("steps")),
                total_calories=_int_or_none(daily_activity.get("total_calories")),
                contributors=contributors,
                metadata=metadata,
            )
        )

    return normalized


def _duration_seconds(start_time: str, end_time: str | None) -> float | None:
    if not start_time or not end_time:
        return None
    try:
        start_dt = datetime.datetime.fromisoformat(start_time)
        end_dt = datetime.datetime.fromisoformat(end_time)
    except ValueError:
        return None
    return max(0.0, (end_dt - start_dt).total_seconds())


def _pick_primary_sleep(documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not documents:
        return None
    return max(
        documents,
        key=lambda item: (
            _int_or_none(item.get("time_in_bed")) or 0,
            _int_or_none(item.get("total_sleep_duration")) or 0,
        ),
    )


def _nested_get(payload: dict[str, Any] | None, *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _title_case(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.replace("_", " ").title()


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _string_or_none(value)
        if text:
            return text
    return None

#!/usr/bin/env python3
import datetime
import json
import re
import statistics
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import coach
import evals
import health
import store
import sync_engine
import vdot_zones
from errors import HarnessError


_DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
_SOURCE_RE = re.compile(r"\[Source:\s*([^\]]+)\]")
_ROOT_DIR = Path(__file__).resolve().parent
_WEB_DIST_DIR = _ROOT_DIR / "apps" / "nyx-client" / "dist"
_FEEDBACK_VERDICTS = ("helpful", "too_generic", "not_grounded", "unsafe")
_STATUS_RANK = {
    "unknown": 0,
    "on_track": 1,
    "mixed": 2,
    "at_risk": 3,
}
_SEVERE_SAFETY_FLAGS = {"rf_current_pain", "rf_stress_fracture", "rf_multiple_injuries"}
_CAUTION_SAFETY_FLAGS = {
    "rf_reds_pattern",
    "rf_rest_anxiety",
    "rf_always_pushes_through",
    "rf_overtraining",
    "rf_sleep_restoration",
    "rf_menstrual_disruption",
}


class ConversationMessage(BaseModel):
    role: str
    content: str


class CoachMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: int | None = None
    conversation: list[ConversationMessage] = Field(default_factory=list)
    model: str = "kimi-2.5"
    max_tokens: int = 1200


class CoachFeedbackRequest(BaseModel):
    thread_id: int
    message_id: int
    verdict: str = Field(pattern="^(helpful|too_generic|not_grounded|unsafe)$")


class EvalRunRequest(BaseModel):
    live: bool = False
    verbose: bool = False
    limit: int = 0
    model: str = "kimi-2.5"


class SyncStartRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    interactive: bool = False


@dataclass
class SyncJobState:
    job_id: str
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds"))
    logs: list[str] = field(default_factory=list)
    summary: dict | None = None
    error: dict | None = None

    def append_log(self, message: str) -> None:
        self.logs.append(message)
        self.updated_at = datetime.datetime.now().isoformat(timespec="seconds")


app = FastAPI(
    title="Nyx Local API",
    version="0.1.0",
    summary="Local API wrapper for the Nyx running coach harness.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_sync_jobs: dict[str, SyncJobState] = {}
_sync_jobs_lock = threading.Lock()


def _error_payload(exc: HarnessError) -> dict:
    return {
        "code": exc.code,
        "message": exc.message,
        "hint": exc.hint,
        "details": exc.details,
    }


@app.exception_handler(HarnessError)
async def handle_harness_error(_, exc: HarnessError):
    return JSONResponse(status_code=400, content={"error": _error_payload(exc)})


def _open_db():
    return store.open_db()


def _resolve_web_response_path(request_path: str) -> Path | None:
    if not _WEB_DIST_DIR.is_dir():
        return None

    relative_path = request_path.lstrip("/")
    index_file = _WEB_DIST_DIR / "index.html"
    if not relative_path:
        return index_file if index_file.is_file() else None

    candidate = (_WEB_DIST_DIR / relative_path).resolve()
    try:
        candidate.relative_to(_WEB_DIST_DIR.resolve())
    except ValueError:
        return None

    if candidate.is_file():
        return candidate

    if Path(relative_path).suffix:
        return None

    return index_file if index_file.is_file() else None


def _parse_hr_zones(conn) -> dict | None:
    raw = store.get_meta(conn, "hr_zones_json")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _current_vdot_payload(conn) -> dict | None:
    raw = store.get_meta(conn, "current_vdot")
    if not raw:
        return None

    vdot = float(raw)
    paces = vdot_zones.lookup_training_paces(vdot)
    return {
        "value": round(vdot, 2),
        "estimated_at": store.get_meta(conn, "vdot_estimated_at"),
        "qualifying_run_count": int(store.get_meta(conn, "vdot_qualifying_run_count") or 0),
        "easy_pace": paces["easy_pace_range_min_per_km"],
        "marathon_pace": paces["marathon_pace_min_per_km"],
        "threshold_pace": paces["threshold_pace_min_per_km"],
        "interval_pace": paces["interval_pace_min_per_km"],
    }


def _recent_load(runs, days: int = 42) -> tuple[int, float]:
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    selected = []
    for row in runs:
        try:
            started = datetime.datetime.fromisoformat(row["start_time"])
        except (TypeError, ValueError):
            continue
        if started >= cutoff:
            selected.append(row)
    return len(selected), sum((row["distance_m"] or 0) for row in selected) / 1000.0


def _rei_trend(runs) -> dict | None:
    rei_values = [row["rei"] for row in runs if row["rei"] is not None]
    if len(rei_values) < 10:
        return None

    recent_avg = statistics.mean(rei_values[:10])
    if len(rei_values) >= 20:
        prior_avg = statistics.mean(rei_values[10:20])
        delta = recent_avg - prior_avg
        label = "improving" if delta > 0 else "declining"
    else:
        prior_avg = None
        delta = None
        label = "stable"

    return {
        "label": label,
        "recent_avg": round(recent_avg, 2),
        "prior_avg": round(prior_avg, 2) if prior_avg is not None else None,
        "delta_vs_prior": round(delta, 2) if delta is not None else None,
    }


def _weekly_mileage(runs, weeks: int = 8) -> list[dict]:
    weekly: dict[str, float] = {}
    for row in runs:
        try:
            started = datetime.datetime.fromisoformat(row["start_time"])
        except (TypeError, ValueError):
            continue
        week_key = f"{started.isocalendar()[0]}-W{started.isocalendar()[1]:02d}"
        weekly[week_key] = weekly.get(week_key, 0.0) + (row["distance_m"] or 0) / 1000.0

    return [
        {"week": week, "distance_km": round(distance_km, 1)}
        for week, distance_km in sorted(weekly.items(), reverse=True)[:weeks]
    ]


def _feedback_counts(rows) -> dict:
    counts = {verdict: 0 for verdict in _FEEDBACK_VERDICTS}
    for row in rows:
        verdict = row["verdict"]
        if verdict in counts:
            counts[verdict] += 1
    counts["total"] = sum(counts.values())
    return counts


def _feedback_summary_payload(rows, *, window: int) -> dict:
    counts = _feedback_counts(rows)
    total = counts["total"]

    if total == 0:
        return {
            "status": "unknown",
            "summary": "No response feedback yet.",
            "counts": counts,
            "window": window,
        }

    helpful = counts["helpful"]
    generic = counts["too_generic"]
    not_grounded = counts["not_grounded"]
    unsafe = counts["unsafe"]
    helpful_ratio = helpful / total
    serious_ratio = (not_grounded + unsafe) / total

    if unsafe:
        status = "at_risk"
        summary = "A recent coach answer was marked unsafe."
    elif serious_ratio >= 0.34:
        status = "at_risk"
        summary = f"{helpful} of last {total} responses were still marked helpful."
    elif helpful == total:
        status = "on_track"
        summary = f"All {total} recent responses were rated helpful."
    elif helpful_ratio >= 0.7 and generic <= 1:
        status = "on_track"
        summary = f"{helpful} of last {total} responses were rated helpful."
    else:
        status = "mixed"
        summary = f"{helpful} of last {total} responses were rated helpful."

    return {
        "status": status,
        "summary": summary,
        "counts": counts,
        "window": window,
    }


def _coach_feedback_summary(conn, *, thread_id: int | None = None, limit: int = 10) -> dict:
    rows = store.get_coach_feedback(conn, thread_id=thread_id, limit=limit)
    return _feedback_summary_payload(rows, window=limit)


def _goal_preview(conn) -> dict | None:
    raw = store.get_meta(conn, "onboarding_goal")
    if not raw:
        return None

    text = " ".join(raw.split())
    if len(text) > 120:
        text = text[:117].rstrip() + "..."
    return {
        "text": text,
        "source": "onboarding",
    }


def _onboarding_flags(conn) -> list[str]:
    raw = store.get_meta(conn, "onboarding_red_flags") or "[]"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []
    return [str(flag) for flag in parsed]


def _latest_weekly_change(weekly_mileage: list[dict]) -> dict | None:
    if len(weekly_mileage) < 2:
        return None

    recent = weekly_mileage[0]["distance_km"]
    prior = weekly_mileage[1]["distance_km"]
    if prior <= 0:
        return None

    delta_pct = ((recent - prior) / prior) * 100.0
    return {
        "recent_km": recent,
        "prior_km": prior,
        "delta_pct": round(delta_pct, 1),
    }


def _progress_signal(
    *,
    goal_preview: dict | None,
    vdot: dict | None,
    rei_trend: dict | None,
    weekly_mileage: list[dict],
    recent_run_count: int,
    recent_distance_km: float,
) -> dict:
    if recent_run_count == 0:
        return {
            "status": "unknown",
            "summary": "Sync run data to start tracking progress.",
            "reason_codes": [],
            "reasons": ["No recent runs are available in the local harness yet."],
        }

    positives = 0
    risks = 0
    reason_codes: list[str] = []
    reasons: list[str] = []

    if vdot:
        positives += 1
        reason_codes.append("vdot_ready")
        reasons.append(f"Current VDOT {vdot['value']} gives Nyx a stable fitness anchor.")

    if rei_trend and rei_trend.get("delta_vs_prior") is not None:
        delta = float(rei_trend["delta_vs_prior"])
        if delta >= 1:
            positives += 1
            reason_codes.append("rei_up")
            reasons.append(f"Recent REI is up {delta:+.1f} versus the prior block.")
        elif delta <= -1:
            risks += 1
            reason_codes.append("rei_down")
            reasons.append(f"Recent REI is down {delta:+.1f} versus the prior block.")

    weekly_change = _latest_weekly_change(weekly_mileage)
    if weekly_change:
        delta_pct = weekly_change["delta_pct"]
        if delta_pct >= 20:
            risks += 1
            reason_codes.append("load_spike")
            reasons.append(f"Weekly mileage jumped {abs(delta_pct):.0f}% versus last week.")
        elif delta_pct <= -25:
            risks += 1
            reason_codes.append("load_drop")
            reasons.append(f"Weekly mileage dropped {abs(delta_pct):.0f}% versus last week.")
        else:
            positives += 1
            reason_codes.append("load_stable")
            reasons.append("Weekly mileage is relatively stable right now.")

    if not reasons:
        reasons.append(f"Recent 42-day load is {recent_run_count} runs / {recent_distance_km:.1f} km.")

    if positives == 0 and risks == 0:
        status = "unknown"
        summary = "Need more stable history to assess progress cleanly."
    elif risks and positives:
        status = "mixed"
        summary = (
            "Fitness signals are improving, but durability signals are mixed."
            if goal_preview
            else "Recent training signals are mixed."
        )
    elif risks:
        status = "at_risk"
        summary = "Recent training signals suggest stalled progress or elevated risk."
    else:
        status = "on_track"
        summary = (
            "Recent training signals are moving in the right direction for your stated goal."
            if goal_preview
            else "Recent training signals are moving in the right direction."
        )

    return {
        "status": status,
        "summary": summary,
        "reason_codes": reason_codes,
        "reasons": reasons[:3],
    }


def _safety_signal(
    *,
    flags: list[str],
    rei_trend: dict | None,
    weekly_mileage: list[dict],
    recent_run_count: int,
) -> dict:
    if recent_run_count == 0 and not flags:
        return {
            "status": "unknown",
            "summary": "Need run history before safety risk can be assessed.",
            "reason_codes": [],
            "reasons": ["No recent training history is available yet."],
        }

    severity = 0
    reason_codes: list[str] = []
    reasons: list[str] = []

    severe_flags = [flag for flag in flags if flag in _SEVERE_SAFETY_FLAGS]
    caution_flags = [flag for flag in flags if flag in _CAUTION_SAFETY_FLAGS]

    if severe_flags:
        severity = max(severity, 2)
        reason_codes.extend(sorted(severe_flags))
        reasons.append("Onboarding flagged current pain or significant injury history.")
    elif caution_flags:
        severity = max(severity, 1)
        reason_codes.extend(sorted(caution_flags))
        reasons.append("Onboarding surfaced recovery or injury caution flags.")

    weekly_change = _latest_weekly_change(weekly_mileage)
    if weekly_change:
        delta_pct = weekly_change["delta_pct"]
        if delta_pct >= 35:
            severity = max(severity, 2)
            reason_codes.append("load_spike_severe")
            reasons.append(f"Weekly mileage jumped {abs(delta_pct):.0f}% versus last week.")
        elif delta_pct >= 20:
            severity = max(severity, 1)
            reason_codes.append("load_spike")
            reasons.append(f"Weekly mileage jumped {abs(delta_pct):.0f}% versus last week.")

    if rei_trend and rei_trend.get("delta_vs_prior") is not None and float(rei_trend["delta_vs_prior"]) <= -2:
        severity = max(severity, 1)
        reason_codes.append("rei_decline")
        reasons.append("REI is trending down enough to warrant a recovery check.")

    if severity >= 2:
        status = "at_risk"
        summary = "Current data suggests elevated safety risk or a need for extra caution."
    elif severity == 1:
        status = "mixed"
        summary = "Recovery and safety signals need a closer look before adding stress."
    else:
        status = "on_track"
        summary = "No immediate safety warnings are showing up in current data."
        if not reasons:
            reasons.append("Recent load and recovery signals do not show an obvious warning.")

    return {
        "status": status,
        "summary": summary,
        "reason_codes": reason_codes,
        "reasons": reasons[:3],
    }


def _coach_status_next_action(progress: dict, quality: dict, safety: dict) -> dict:
    if safety["status"] == "at_risk":
        return {
            "action": "athlete",
            "label": "Review Athlete State",
            "reason": "Check load, recovery, and injury signals before making the next training call.",
        }
    if quality["status"] == "at_risk":
        return {
            "action": "diagnostics",
            "label": "Open Diagnostics",
            "reason": "Guidance quality feedback is degraded enough to compare against eval output.",
        }
    if quality["status"] == "unknown":
        return {
            "action": "coach",
            "label": "Open Coach",
            "reason": "Ask a concrete training question and rate whether the answer is grounded.",
        }
    if progress["status"] in {"mixed", "at_risk", "unknown"}:
        return {
            "action": "athlete",
            "label": "Review Athlete State",
            "reason": "Look at the recent trend details before changing training.",
        }
    return {
        "action": "coach",
        "label": "Open Coach",
        "reason": "Recent signals look stable; ask the next training question.",
    }


def _build_coach_status(
    conn,
    *,
    vdot: dict | None,
    rei_trend: dict | None,
    weekly_mileage: list[dict],
    recent_run_count: int,
    recent_distance_km: float,
) -> tuple[dict | None, dict]:
    goal_preview = _goal_preview(conn)
    quality = _coach_feedback_summary(conn, limit=10)
    progress = _progress_signal(
        goal_preview=goal_preview,
        vdot=vdot,
        rei_trend=rei_trend,
        weekly_mileage=weekly_mileage,
        recent_run_count=recent_run_count,
        recent_distance_km=recent_distance_km,
    )
    safety = _safety_signal(
        flags=_onboarding_flags(conn),
        rei_trend=rei_trend,
        weekly_mileage=weekly_mileage,
        recent_run_count=recent_run_count,
    )

    return goal_preview, {
        "progress": progress,
        "quality": quality,
        "safety": safety,
        "next_action": _coach_status_next_action(progress, quality, safety),
    }


def _next_action(status: dict) -> dict:
    if status["total_runs"] == 0:
        return {
            "action": "sync",
            "label": "Sync Garmin",
            "reason": "No run data has been loaded into the local harness yet.",
        }
    if status["last_sync_status"] == "failed":
        return {
            "action": "diagnostics",
            "label": "Open Diagnostics",
            "reason": "The last sync failed and needs attention before coaching is trustworthy.",
        }
    if not status["current_vdot"]:
        return {
            "action": "metrics",
            "label": "Refresh Training Metrics",
            "reason": "Run data is present, but VDOT has not been estimated yet.",
        }
    return {
        "action": "coach",
        "label": "Open Coach",
        "reason": "The harness is ready for a coaching session grounded in your current data.",
    }


def _serialize_run(row) -> dict:
    return {
        "activity_id": row["activity_id"],
        "name": row["name"],
        "start_time": row["start_time"],
        "duration_sec": row["duration_sec"],
        "distance_m": row["distance_m"],
        "distance_km": round((row["distance_m"] or 0) / 1000.0, 2),
        "calories": row["calories"],
        "avg_hr": row["avg_hr"],
        "max_hr": row["max_hr"],
        "avg_speed_ms": row["avg_speed_ms"],
        "pace_min_per_km": row["pace_min_per_km"],
        "avg_cadence_spm": row["avg_cadence_spm"],
        "avg_vertical_osc_cm": row["avg_vertical_osc_cm"],
        "avg_ground_contact_ms": row["avg_ground_contact_ms"],
        "avg_stride_length_cm": row["avg_stride_length_cm"],
        "aerobic_efficiency": row["aerobic_efficiency"],
        "hr_drift_pct": row["hr_drift_pct"],
        "cadence_cv": row["cadence_cv"],
        "rei": row["rei"],
        "detail_fetched": bool(row["detail_fetched"]),
    }


def _athlete_summary(conn) -> dict:
    runs = store.get_all_runs(conn)
    status = health.collect_status(conn)
    recent_run_count, recent_distance_km = _recent_load(runs, days=42)
    vdot = _current_vdot_payload(conn)
    rei_trend = _rei_trend(runs)
    weekly_mileage = _weekly_mileage(runs)
    hr_zones = _parse_hr_zones(conn)
    zone_2 = None
    if hr_zones:
        for zone in hr_zones.get("zones", []):
            if zone.get("zone") == 2:
                zone_2 = zone
                break
    goal_preview, coach_status = _build_coach_status(
        conn,
        vdot=vdot,
        rei_trend=rei_trend,
        weekly_mileage=weekly_mileage,
        recent_run_count=recent_run_count,
        recent_distance_km=recent_distance_km,
    )

    return {
        "total_runs": status["total_runs"],
        "detailed_runs": status["detailed_runs"],
        "pending_details": status["pending_details"],
        "recent_42d_runs": recent_run_count,
        "recent_42d_distance_km": round(recent_distance_km, 1),
        "ae_baseline": float(status["ae_baseline"]) if status["ae_baseline"] else None,
        "rei_trend": rei_trend,
        "weekly_mileage": weekly_mileage,
        "vdot": vdot,
        "hr_zones": hr_zones,
        "zone_2": zone_2,
        "last_sync_status": status["last_sync_status"],
        "last_sync_completed_at": status["last_sync_completed_at"],
        "goal_preview": goal_preview,
        "coach_status": coach_status,
        "next_action": _next_action(status),
    }


def _coach_context_summary(conn) -> dict:
    vdot = _current_vdot_payload(conn)
    hr_zones = _parse_hr_zones(conn)
    zone_2 = None
    if hr_zones:
        zone_2 = next((zone for zone in hr_zones.get("zones", []) if zone.get("zone") == 2), None)

    return {
        "current_vdot": vdot["value"] if vdot else None,
        "easy_pace": vdot["easy_pace"] if vdot else None,
        "threshold_pace": vdot["threshold_pace"] if vdot else None,
        "marathon_pace": vdot["marathon_pace"] if vdot else None,
        "interval_pace": vdot["interval_pace"] if vdot else None,
        "zone_2": zone_2,
        "last_sync_completed_at": store.get_meta(conn, "last_sync_completed_at"),
        "quality_summary": _coach_feedback_summary(conn, limit=10),
    }


def _parse_coach_sections(text: str) -> tuple[str, list[str], str]:
    verdict = ""
    evidence: list[str] = []
    next_step = ""
    section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("verdict:"):
            section = "verdict"
            verdict = line.split(":", 1)[1].strip()
            continue
        if lowered.startswith("evidence:"):
            section = "evidence"
            continue
        if lowered.startswith("next step:"):
            section = "next_step"
            next_step = line.split(":", 1)[1].strip()
            continue

        if section == "verdict":
            verdict = f"{verdict} {line}".strip()
        elif section == "evidence" and line[:1] in {"-", "*"}:
            evidence.append(line[1:].strip())
        elif section == "next_step":
            next_step = f"{next_step} {line}".strip()

    if not verdict:
        verdict = text.strip()
    return verdict, evidence, next_step


def _serialize_coach_thread(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"] or None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _serialize_coach_feedback(row) -> dict:
    return {
        "id": row["id"],
        "thread_id": row["thread_id"],
        "message_id": row["message_id"],
        "verdict": row["verdict"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _serialize_structured_message(conn, content: str) -> dict | None:
    verdict, evidence_lines, next_step = _parse_coach_sections(content)
    if "verdict:" not in content.lower() and not evidence_lines and not next_step:
        return None

    return {
        "verdict": verdict,
        "evidence": [_evidence_item(conn, line) for line in evidence_lines],
        "next_step": next_step,
    }


def _serialize_coach_message(conn, row, feedback_by_message_id: dict[int, object]) -> dict:
    payload = {
        "id": row["id"],
        "thread_id": row["thread_id"],
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
    }
    feedback = feedback_by_message_id.get(int(row["id"]))
    if feedback is not None:
        payload["feedback"] = _serialize_coach_feedback(feedback)
    if row["role"] == "assistant":
        structured = _serialize_structured_message(conn, row["content"])
        if structured is not None:
            payload["structured"] = structured
    return payload


def _coach_thread_payload(conn, thread) -> dict:
    messages = store.get_coach_messages(conn, thread["id"])
    feedback_by_message_id = store.get_coach_feedback_map(
        conn,
        [int(row["id"]) for row in messages if row["role"] == "assistant"],
    )
    return {
        "thread": _serialize_coach_thread(thread),
        "messages": [_serialize_coach_message(conn, row, feedback_by_message_id) for row in messages],
        "message_count": len(messages),
    }


def _resolve_coach_thread(conn, thread_id: int | None):
    if thread_id is not None:
        thread = store.get_coach_thread(conn, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Coach thread not found.")
        store.set_active_coach_thread(conn, thread_id)
        return thread
    return store.get_or_create_active_coach_thread(conn)


def _evidence_item(conn, bullet: str) -> dict:
    date_match = _DATE_RE.search(bullet)
    source_match = _SOURCE_RE.search(bullet)
    activity_id = None
    kind = "metric"
    label = "Athlete data"

    if date_match:
        started = date_match.group(0)
        row = conn.execute(
            "SELECT activity_id, name FROM runs WHERE start_time LIKE ? ORDER BY start_time DESC LIMIT 1",
            (f"{started}%",),
        ).fetchone()
        if row:
            activity_id = row["activity_id"]
            label = row["name"] or started
            kind = "run"
    elif source_match:
        label = source_match.group(1).strip()
        kind = "knowledge"
    elif "VDOT" in bullet or "Zone " in bullet or "pace" in bullet.lower():
        label = "Current training metrics"

    item = {
        "label": label,
        "kind": kind,
        "text": bullet,
    }
    if activity_id is not None:
        item["activity_id"] = activity_id
    if source_match:
        item["source"] = source_match.group(1).strip()
    return item


def _get_sync_job(job_id: str) -> SyncJobState:
    with _sync_jobs_lock:
        job = _sync_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown sync job: {job_id}")
    return job


def _sync_job_payload(job: SyncJobState) -> dict:
    return asdict(job)


def _run_sync_job(job: SyncJobState, email: str | None, password: str | None, interactive: bool) -> None:
    def log(message: str) -> None:
        job.append_log(message)

    try:
        job.status = "running"
        summary = sync_engine.run_sync(
            log=log,
            email=email,
            password=password,
            interactive=interactive,
        )
        job.summary = asdict(summary)
        job.status = "success"
    except HarnessError as exc:
        job.error = _error_payload(exc)
        job.status = "failed"
    except Exception as exc:
        job.error = {
            "code": "sync_failed",
            "message": str(exc),
            "hint": "",
            "details": "",
        }
        job.status = "failed"
    finally:
        job.updated_at = datetime.datetime.now().isoformat(timespec="seconds")


@app.get("/api")
def api_root():
    return {
        "name": "Nyx Local API",
        "version": app.version,
        "status": "ok",
    }


@app.get("/api/status")
def get_status():
    conn = _open_db()
    try:
        return health.collect_status(conn)
    finally:
        conn.close()


@app.get("/api/doctor")
def get_doctor():
    conn = _open_db()
    try:
        checks = [asdict(check) for check in health.run_doctor(conn)]
        counts = {
            "pass": sum(1 for check in checks if check["status"] == health.PASS),
            "warn": sum(1 for check in checks if check["status"] == health.WARN),
            "fail": sum(1 for check in checks if check["status"] == health.FAIL),
        }
        return {"checks": checks, "counts": counts}
    finally:
        conn.close()


@app.get("/api/athlete/summary")
def get_athlete_summary():
    conn = _open_db()
    try:
        return _athlete_summary(conn)
    finally:
        conn.close()


@app.get("/api/runs")
def get_runs(limit: int = 50):
    conn = _open_db()
    try:
        runs = store.get_all_runs(conn, limit=limit)
        return {"runs": [_serialize_run(row) for row in runs]}
    finally:
        conn.close()


@app.get("/api/runs/{activity_id}")
def get_run_detail(activity_id: int):
    conn = _open_db()
    try:
        row = store.get_run(conn, activity_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Unknown run: {activity_id}")
        laps = conn.execute(
            """
            SELECT lap_index, duration_sec, distance_m, avg_hr, avg_speed_ms, avg_cadence_spm
            FROM laps
            WHERE activity_id = ?
            ORDER BY lap_index ASC
            """,
            (activity_id,),
        ).fetchall()
        return {
            "run": _serialize_run(row),
            "laps": [
                {
                    "lap_index": lap["lap_index"],
                    "duration_sec": lap["duration_sec"],
                    "distance_m": lap["distance_m"],
                    "avg_hr": lap["avg_hr"],
                    "avg_speed_ms": lap["avg_speed_ms"],
                    "avg_cadence_spm": lap["avg_cadence_spm"],
                }
                for lap in laps
            ],
        }
    finally:
        conn.close()


@app.get("/api/vdot")
def get_vdot():
    conn = _open_db()
    try:
        return {"vdot": _current_vdot_payload(conn)}
    finally:
        conn.close()


@app.get("/api/hr-zones")
def get_hr_zones():
    conn = _open_db()
    try:
        return {"hr_zones": _parse_hr_zones(conn)}
    finally:
        conn.close()


@app.get("/api/coach/context")
def get_coach_context():
    conn = _open_db()
    try:
        return _coach_context_summary(conn)
    finally:
        conn.close()


@app.get("/api/coach/thread/current")
def get_current_coach_thread():
    conn = _open_db()
    try:
        thread = store.get_or_create_active_coach_thread(conn)
        return _coach_thread_payload(conn, thread)
    finally:
        conn.close()


@app.post("/api/coach/thread")
def create_coach_thread():
    conn = _open_db()
    try:
        thread = store.create_coach_thread(conn)
        return _coach_thread_payload(conn, thread)
    finally:
        conn.close()


@app.post("/api/vdot/recalc")
def recalc_vdot():
    conn = _open_db()
    try:
        vdot = vdot_zones.estimate_vdot_from_runs(conn)
        hr_zones = vdot_zones._refresh_hr_zones(conn)
        return {
            "vdot": _current_vdot_payload(conn),
            "hr_zones": hr_zones,
            "updated": bool(vdot or hr_zones),
        }
    finally:
        conn.close()


@app.post("/api/evals/run")
def run_evals(request: EvalRunRequest):
    conn = _open_db()
    try:
        if request.live:
            results = evals.run_live_evals(
                conn,
                model=request.model,
                limit=request.limit,
            )
        else:
            results = evals.run_offline_evals(conn)
        payload = [asdict(result) for result in results]
        counts = {
            "pass": sum(1 for result in payload if result["status"] == evals.PASS),
            "warn": sum(1 for result in payload if result["status"] == evals.WARN),
            "fail": sum(1 for result in payload if result["status"] == evals.FAIL),
        }
        counts_by_category: dict[str, dict[str, int]] = {}
        for result in payload:
            category = result.get("category", "coverage")
            bucket = counts_by_category.setdefault(category, {"pass": 0, "warn": 0, "fail": 0})
            if result["status"] == evals.PASS:
                bucket["pass"] += 1
            elif result["status"] == evals.WARN:
                bucket["warn"] += 1
            elif result["status"] == evals.FAIL:
                bucket["fail"] += 1
        response = {"results": payload, "counts": counts, "counts_by_category": counts_by_category}
        if request.verbose:
            response["report"] = evals.format_eval_report(results, verbose=True)
        return response
    finally:
        conn.close()


@app.post("/api/coach/feedback")
def post_coach_feedback(request: CoachFeedbackRequest):
    conn = _open_db()
    try:
        thread = store.get_coach_thread(conn, request.thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Coach thread not found.")

        message = store.get_coach_message(conn, request.message_id)
        if message is None:
            raise HTTPException(status_code=404, detail="Coach message not found.")
        if message["thread_id"] != request.thread_id:
            raise HTTPException(status_code=400, detail="Message does not belong to the requested thread.")
        if message["role"] != "assistant":
            raise HTTPException(status_code=400, detail="Only assistant messages can be rated.")
        if request.verdict not in _FEEDBACK_VERDICTS:
            raise HTTPException(status_code=400, detail="Unsupported feedback verdict.")

        feedback = store.set_coach_feedback(
            conn,
            thread_id=request.thread_id,
            message_id=request.message_id,
            verdict=request.verdict,
        )
        return {
            "feedback": _serialize_coach_feedback(feedback),
            "quality_summary": _coach_feedback_summary(conn, limit=10),
        }
    finally:
        conn.close()


@app.post("/api/coach/message")
def post_coach_message(request: CoachMessageRequest):
    conn = _open_db()
    try:
        thread = _resolve_coach_thread(conn, request.thread_id)
        persisted_messages = store.get_coach_messages(conn, thread["id"])
        if persisted_messages:
            conversation = [
                {"role": row["role"], "content": row["content"]}
                for row in persisted_messages
            ]
        else:
            conversation = [message.model_dump() for message in request.conversation]
            for message in conversation:
                store.append_coach_message(
                    conn,
                    thread["id"],
                    message["role"],
                    message["content"],
                )
                if message["role"] == "user":
                    store.maybe_set_coach_thread_title_from_message(
                        conn,
                        thread["id"],
                        message["content"],
                    )

        session = coach.CoachSession(conn, model=request.model, max_tokens=request.max_tokens)
        session.conversation = conversation
        existing_count = len(session.conversation)
        raw_text = session.ask(request.message)
        assistant_row = None
        for message in session.conversation[existing_count:]:
            persisted = store.append_coach_message(
                conn,
                thread["id"],
                message["role"],
                message["content"],
            )
            if message["role"] == "assistant":
                assistant_row = persisted
        store.maybe_set_coach_thread_title_from_message(conn, thread["id"], request.message)
        thread = store.get_coach_thread(conn, thread["id"])
        if thread is None:
            raise HTTPException(status_code=500, detail="Coach thread could not be reloaded.")
        verdict, evidence_lines, next_step = _parse_coach_sections(raw_text)
        evidence = [_evidence_item(conn, line) for line in evidence_lines]
        sources = sorted({match.strip() for match in _SOURCE_RE.findall(raw_text)})
        return {
            "thread": _serialize_coach_thread(thread),
            "verdict": verdict,
            "evidence": evidence,
            "next_step": next_step,
            "raw_text": raw_text,
            "assistant_message": (
                _serialize_coach_message(conn, assistant_row, {})
                if assistant_row is not None
                else None
            ),
            "conversation": session.conversation,
            "sources": sources,
        }
    finally:
        conn.close()


@app.post("/api/sync")
def start_sync(request: SyncStartRequest):
    job = SyncJobState(job_id=uuid.uuid4().hex)
    with _sync_jobs_lock:
        _sync_jobs[job.job_id] = job

    thread = threading.Thread(
        target=_run_sync_job,
        args=(job, request.email, request.password, request.interactive),
        daemon=True,
    )
    thread.start()
    return _sync_job_payload(job)


@app.get("/api/sync/{job_id}")
def get_sync_job(job_id: str):
    return _sync_job_payload(_get_sync_job(job_id))


@app.get("/", include_in_schema=False)
def serve_web_root():
    asset_path = _resolve_web_response_path("")
    if not asset_path:
        raise HTTPException(status_code=404, detail="Web app is not built yet.")
    return FileResponse(asset_path)


@app.get("/{full_path:path}", include_in_schema=False)
def serve_web_app(full_path: str):
    if full_path.startswith("api/") or full_path == "api":
        raise HTTPException(status_code=404, detail="Not Found")

    asset_path = _resolve_web_response_path(full_path)
    if not asset_path:
        raise HTTPException(status_code=404, detail="Web app asset not found.")
    return FileResponse(asset_path)

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


class ConversationMessage(BaseModel):
    role: str
    content: str


class CoachMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation: list[ConversationMessage] = Field(default_factory=list)
    model: str = "claude-opus-4-6"
    max_tokens: int = 1200


class EvalRunRequest(BaseModel):
    live: bool = False
    verbose: bool = False
    limit: int = 0
    model: str = "claude-opus-4-6"


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
    hr_zones = _parse_hr_zones(conn)
    zone_2 = None
    if hr_zones:
        for zone in hr_zones.get("zones", []):
            if zone.get("zone") == 2:
                zone_2 = zone
                break

    return {
        "total_runs": status["total_runs"],
        "detailed_runs": status["detailed_runs"],
        "pending_details": status["pending_details"],
        "recent_42d_runs": recent_run_count,
        "recent_42d_distance_km": round(recent_distance_km, 1),
        "ae_baseline": float(status["ae_baseline"]) if status["ae_baseline"] else None,
        "rei_trend": _rei_trend(runs),
        "weekly_mileage": _weekly_mileage(runs),
        "vdot": vdot,
        "hr_zones": hr_zones,
        "zone_2": zone_2,
        "last_sync_status": status["last_sync_status"],
        "last_sync_completed_at": status["last_sync_completed_at"],
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
        response = {"results": payload, "counts": counts}
        if request.verbose:
            response["report"] = evals.format_eval_report(results, verbose=True)
        return response
    finally:
        conn.close()


@app.post("/api/coach/message")
def post_coach_message(request: CoachMessageRequest):
    conn = _open_db()
    try:
        session = coach.CoachSession(conn, model=request.model, max_tokens=request.max_tokens)
        session.conversation = [message.model_dump() for message in request.conversation]
        raw_text = session.ask(request.message)
        verdict, evidence_lines, next_step = _parse_coach_sections(raw_text)
        evidence = [_evidence_item(conn, line) for line in evidence_lines]
        sources = sorted({match.strip() for match in _SOURCE_RE.findall(raw_text)})
        return {
            "verdict": verdict,
            "evidence": evidence,
            "next_step": next_step,
            "raw_text": raw_text,
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

import datetime
import importlib.util
import json
import os
import sqlite3
from dataclasses import dataclass
from urllib import error, request

import auth
import coach
import config
import fetch
import knowledge_base
import store


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class CheckResult:
    name: str
    status: str
    summary: str
    hint: str = ""


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    return store.get_meta(conn, key) or default


def _count(conn: sqlite3.Connection, query: str) -> int:
    row = conn.execute(query).fetchone()
    return int(row[0] or 0) if row else 0


def check_db_connection() -> dict:
    try:
        conn = store.open_db()
        try:
            conn.execute("SELECT 1").fetchone()
            schema_version = store.get_schema_version(conn)
        finally:
            conn.close()
    except Exception as e:
        return {
            "status": FAIL,
            "summary": "SQLite connection failed.",
            "details": str(e),
        }

    return {
        "status": PASS,
        "summary": "SQLite connection is healthy.",
        "schema_version": schema_version,
    }


def check_knowledge_base() -> dict:
    if not os.path.isdir(config.KNOWLEDGE_DB_PATH):
        return {
            "status": WARN,
            "summary": "Knowledge base directory is missing.",
            "details": "Run `python build_kb.py` to build the retrieval index.",
        }

    if not _module_available("fastembed") or not _module_available("chromadb"):
        return {
            "status": WARN,
            "summary": "Knowledge base dependencies are not installed.",
            "details": "Install `fastembed` and `chromadb` to enable retrieval checks.",
        }

    try:
        import chromadb

        client = chromadb.PersistentClient(path=config.KNOWLEDGE_DB_PATH)
        collection = client.get_or_create_collection(
            name=knowledge_base.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        count = collection.count()
    except Exception as e:
        return {
            "status": FAIL,
            "summary": "Knowledge base probe failed.",
            "details": str(e),
        }

    if count == 0:
        return {
            "status": WARN,
            "summary": "Knowledge base is empty.",
            "details": "Run `python build_kb.py` to index the knowledge files.",
            "document_count": count,
        }

    return {
        "status": PASS,
        "summary": "Knowledge base is initialized.",
        "document_count": count,
    }


def check_garmin_connectivity() -> dict:
    if not _module_available("garminconnect"):
        return {
            "status": FAIL,
            "summary": "Garmin dependency is missing.",
            "details": "Run `pip install -r requirements.txt` to enable sync.",
        }

    try:
        client = auth.get_client(interactive=False)
        today = datetime.date.today().isoformat()
        activities = fetch.fetch_running_activities(client, today)
    except Exception as e:
        status = WARN if getattr(e, "code", "") == "garmin_login_required" else FAIL
        return {
            "status": status,
            "summary": "Garmin probe failed.",
            "details": getattr(e, "message", str(e)),
        }

    return {
        "status": PASS,
        "summary": "Garmin connectivity is healthy.",
        "activity_count_today": len(activities),
    }


def check_moonshot_connectivity() -> dict:
    if not _module_available("openai"):
        return {
            "status": FAIL,
            "summary": "OpenAI SDK is missing.",
            "details": "Run `pip install -r requirements.txt` to enable coach chat.",
        }

    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        return {
            "status": WARN,
            "summary": "MOONSHOT_API_KEY is not configured.",
            "details": "Set the key before using the coach or live evals.",
        }

    req = request.Request(
        f"{coach._MOONSHOT_BASE_URL}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            status_code = response.status
    except error.HTTPError as e:
        status_code = e.code
    except Exception as e:
        return {
            "status": FAIL,
            "summary": "Moonshot probe failed.",
            "details": str(e),
        }

    if status_code in {200, 401, 403}:
        return {
            "status": PASS if status_code == 200 else WARN,
            "summary": "Moonshot endpoint is reachable." if status_code == 200 else "Moonshot endpoint is reachable, but authentication failed.",
            "http_status": status_code,
        }

    return {
        "status": FAIL,
        "summary": "Moonshot endpoint returned an unexpected response.",
        "http_status": status_code,
    }


def collect_deep_status() -> dict:
    checks = {
        "database": check_db_connection(),
        "garmin_api": check_garmin_connectivity(),
        "knowledge_base": check_knowledge_base(),
        "moonshot_api": check_moonshot_connectivity(),
    }

    statuses = {check["status"] for check in checks.values()}
    if FAIL in statuses:
        overall = FAIL
    elif WARN in statuses:
        overall = WARN
    else:
        overall = PASS

    return {
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "overall": overall,
        "checks": checks,
    }


def collect_status(conn: sqlite3.Connection) -> dict:
    total_runs = _count(conn, "SELECT COUNT(*) FROM runs")
    detailed_runs = _count(conn, "SELECT COUNT(*) FROM runs WHERE detail_fetched = 1")
    pending_details = _count(conn, "SELECT COUNT(*) FROM runs WHERE detail_fetched = 0")
    total_provider_activities = _count(conn, "SELECT COUNT(*) FROM activities")
    total_daily_recovery = _count(conn, "SELECT COUNT(*) FROM daily_recovery")

    row = conn.execute(
        """
        SELECT MIN(start_time) AS first_run, MAX(start_time) AS last_run
        FROM runs
        """
    ).fetchone()

    hr_zones_raw = store.get_meta(conn, "hr_zones_json")
    try:
        hr_zones = json.loads(hr_zones_raw) if hr_zones_raw else None
    except json.JSONDecodeError:
        hr_zones = None

    provider_status = store.get_provider_data_status(conn)

    return {
        "schema_version": store.get_schema_version(conn),
        "total_runs": total_runs,
        "detailed_runs": detailed_runs,
        "pending_details": pending_details,
        "total_provider_activities": total_provider_activities,
        "total_daily_recovery_records": total_daily_recovery,
        "first_run": row["first_run"] if row else None,
        "last_run": row["last_run"] if row else None,
        "last_sync_started_at": _meta(conn, "last_sync_started_at"),
        "last_sync_completed_at": _meta(conn, "last_sync_completed_at"),
        "last_sync_status": _meta(conn, "last_sync_status", "never"),
        "last_sync_error": _meta(conn, "last_sync_error"),
        "sync_watermark_date": _meta(conn, "sync_watermark_date"),
        "last_sync_new_runs": _meta(conn, "last_sync_new_runs", "0"),
        "last_sync_detail_failures": _meta(conn, "last_sync_detail_failures", "0"),
        "ae_baseline": _meta(conn, "ae_baseline"),
        "current_vdot": _meta(conn, "current_vdot"),
        "vdot_estimated_at": _meta(conn, "vdot_estimated_at"),
        "onboarding_completed": _meta(conn, "onboarding_completed", "0") == "1",
        "knowledge_dir_exists": os.path.isdir(config.KNOWLEDGE_DIR),
        "knowledge_db_exists": os.path.isdir(config.KNOWLEDGE_DB_PATH),
        "hr_zones": hr_zones,
        "providers": provider_status,
    }


def format_status(conn: sqlite3.Connection) -> str:
    status = collect_status(conn)
    lines = [
        "Nyx Harness Status",
        "==================",
        f"Schema version     : {status['schema_version']}",
        f"Runs               : {status['total_runs']} total, {status['detailed_runs']} detailed, {status['pending_details']} pending detail fetches",
        f"Run date range     : {status['first_run'][:10] if status['first_run'] else 'n/a'} -> {status['last_run'][:10] if status['last_run'] else 'n/a'}",
        f"Last sync          : {status['last_sync_status']}  started={status['last_sync_started_at'] or 'n/a'}  completed={status['last_sync_completed_at'] or 'n/a'}",
        f"Sync watermark     : {status['sync_watermark_date'] or '2000-01-01'}",
        f"Last sync result   : {status['last_sync_new_runs']} new runs, {status['last_sync_detail_failures']} detail failures",
        f"Provider data      : {status['total_provider_activities']} activities, {status['total_daily_recovery_records']} daily recovery records",
        f"Onboarding         : {'complete' if status['onboarding_completed'] else 'not completed'}",
        f"AE baseline        : {status['ae_baseline'] or 'not computed'}",
        f"Current VDOT       : {status['current_vdot'] or 'not estimated'}",
        f"VDOT estimated at  : {status['vdot_estimated_at'] or 'n/a'}",
        f"Knowledge base     : {'present' if status['knowledge_db_exists'] else 'not built'}",
    ]
    hr_zones = status["hr_zones"]
    if hr_zones:
        lines.append(
            f"HR zones           : Karvonen max={hr_zones['max_hr']} resting={hr_zones['resting_hr']}"
        )
    if status["last_sync_error"]:
        lines.append(f"Last sync error    : {status['last_sync_error']}")
    if status["providers"]:
        connected = ", ".join(
            f"{provider}={details['status']}"
            for provider, details in sorted(status["providers"].items())
        )
        lines.append(f"Providers          : {connected}")
    return "\n".join(lines)


def run_doctor(conn: sqlite3.Connection) -> list[CheckResult]:
    checks: list[CheckResult] = []
    schema_version = store.get_schema_version(conn)

    checks.append(CheckResult(
        name="sqlite_schema",
        status=PASS if schema_version == store.SCHEMA_VERSION else WARN,
        summary=f"Schema version is {schema_version}.",
        hint="" if schema_version == store.SCHEMA_VERSION else f"Expected schema version {store.SCHEMA_VERSION}. Open the DB through the CLI to migrate.",
    ))

    checks.append(CheckResult(
        name="garmin_dependency",
        status=PASS if _module_available("garminconnect") else FAIL,
        summary="Garmin dependency is installed." if _module_available("garminconnect") else "Garmin dependency is missing.",
        hint="" if _module_available("garminconnect") else "Run `pip install -r requirements.txt` to enable sync.",
    ))

    openai_ready = _module_available("openai")
    moonshot_key = bool(os.getenv("MOONSHOT_API_KEY"))
    checks.append(CheckResult(
        name="coach_dependency",
        status=PASS if openai_ready and moonshot_key else FAIL if openai_ready else WARN,
        summary="OpenAI SDK and Moonshot API key are ready." if openai_ready and moonshot_key else (
            "OpenAI SDK is installed but MOONSHOT_API_KEY is not set." if openai_ready else "OpenAI SDK is missing."
        ),
        hint="" if openai_ready and moonshot_key else (
            "Set `MOONSHOT_API_KEY` in your environment." if openai_ready else "Run `pip install -r requirements.txt` to enable coach chat and evals."
        ),
    ))

    kb_modules = _module_available("fastembed") and _module_available("chromadb")
    kb_built = os.path.isdir(config.KNOWLEDGE_DB_PATH)
    checks.append(CheckResult(
        name="knowledge_base",
        status=PASS if kb_modules and kb_built else WARN,
        summary="Knowledge base dependencies and index are present." if kb_modules and kb_built else "Knowledge base is not fully ready.",
        hint="" if kb_modules and kb_built else "Install `fastembed`/`chromadb` and run `python build_kb.py`.",
    ))

    total_runs = _count(conn, "SELECT COUNT(*) FROM runs")
    checks.append(CheckResult(
        name="run_data",
        status=PASS if total_runs > 0 else WARN,
        summary=f"Local DB has {total_runs} runs.",
        hint="" if total_runs > 0 else "Run `python cli.py sync` to pull Garmin history.",
    ))

    last_sync_status = _meta(conn, "last_sync_status", "never")
    last_sync_completed_at = _meta(conn, "last_sync_completed_at")
    sync_status = PASS if last_sync_status == "success" else WARN
    sync_hint = ""
    if last_sync_status == "never":
        sync_hint = "Run `python cli.py sync` to create the first local snapshot."
    elif last_sync_status == "failed":
        sync_hint = _meta(conn, "last_sync_error", "Check the sync logs.")

    if last_sync_completed_at:
        try:
            completed = datetime.datetime.fromisoformat(last_sync_completed_at)
            age_days = (datetime.datetime.now() - completed).days
            if age_days > 14:
                sync_status = WARN
                sync_hint = f"Last successful sync was {age_days} days ago."
        except ValueError:
            pass

    checks.append(CheckResult(
        name="sync_state",
        status=sync_status,
        summary=f"Last sync status is {last_sync_status}.",
        hint=sync_hint,
    ))

    onboarding_complete = _meta(conn, "onboarding_completed", "0") == "1"
    checks.append(CheckResult(
        name="onboarding",
        status=PASS if onboarding_complete else WARN,
        summary="Onboarding is complete." if onboarding_complete else "Onboarding has not been completed.",
        hint="" if onboarding_complete else "Complete onboarding in the app, or run `python cli.py onboarding`, before using the coach seriously.",
    ))

    return checks


def format_doctor(conn: sqlite3.Connection) -> str:
    lines = [
        "Nyx Harness Doctor",
        "==================",
    ]
    for check in run_doctor(conn):
        lines.append(f"[{check.status}] {check.name}: {check.summary}")
        if check.hint:
            lines.append(f"  hint: {check.hint}")
    return "\n".join(lines)

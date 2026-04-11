import datetime
import hashlib
import json
import sqlite3
import statistics
from typing import Optional
import config
from models import RunSummary


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    activity_id           INTEGER PRIMARY KEY,
    name                  TEXT,
    start_time            TEXT NOT NULL,
    duration_sec          REAL,
    distance_m            REAL,
    calories              INTEGER,
    avg_hr                REAL,
    max_hr                REAL,
    avg_speed_ms          REAL,
    pace_min_per_km       REAL,
    avg_cadence_spm       REAL,
    avg_vertical_osc_cm   REAL,
    avg_ground_contact_ms REAL,
    avg_stride_length_cm  REAL,
    aerobic_efficiency    REAL,
    hr_drift_pct          REAL,
    cadence_cv            REAL,
    rei                   REAL,
    detail_fetched        INTEGER DEFAULT 0,
    created_at            TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS laps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id     INTEGER NOT NULL REFERENCES runs(activity_id),
    lap_index       INTEGER NOT NULL,
    duration_sec    REAL,
    distance_m      REAL,
    avg_hr          REAL,
    avg_speed_ms    REAL,
    avg_cadence_spm REAL
);

CREATE TABLE IF NOT EXISTS user_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_runs_start_time ON runs(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_runs_detail_fetched ON runs(detail_fetched, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_laps_activity_id ON laps(activity_id, lap_index);
"""

COACH_SCHEMA = """
CREATE TABLE IF NOT EXISTS coach_threads (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coach_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id  INTEGER NOT NULL REFERENCES coach_threads(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coach_threads_updated_at ON coach_threads(updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_coach_messages_thread_id ON coach_messages(thread_id, id);
"""

FEEDBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS coach_feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id  INTEGER NOT NULL REFERENCES coach_threads(id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL UNIQUE REFERENCES coach_messages(id) ON DELETE CASCADE,
    verdict    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coach_feedback_thread_id ON coach_feedback(thread_id, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_coach_feedback_verdict ON coach_feedback(verdict, updated_at DESC);
"""

SYNC_JOB_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_jobs (
    job_id        TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    summary_json  TEXT,
    error_json    TEXT
);

CREATE TABLE IF NOT EXISTS sync_job_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL REFERENCES sync_jobs(job_id) ON DELETE CASCADE,
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_jobs_updated_at ON sync_jobs(updated_at DESC, job_id DESC);
CREATE INDEX IF NOT EXISTS idx_sync_job_logs_job_id ON sync_job_logs(job_id, id);
"""

SCHEMA_VERSION = 6


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _apply_schema_migrations(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]

    if current == 0:
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA user_version = 1")
        current = 1

    if current < 2:
        conn.executescript(INDEX_SCHEMA)
        conn.execute("PRAGMA user_version = 2")
        current = 2

    if current < 3:
        _backfill_run_avg_hr_from_laps(conn)
        _recompute_derived_metrics(conn)
        conn.execute("PRAGMA user_version = 3")
        current = 3

    if current < 4:
        conn.executescript(COACH_SCHEMA)
        conn.execute("PRAGMA user_version = 4")
        current = 4

    if current < 5:
        conn.executescript(FEEDBACK_SCHEMA)
        conn.execute("PRAGMA user_version = 5")
        current = 5

    if current < 6:
        conn.executescript(SYNC_JOB_SCHEMA)
        conn.execute("PRAGMA user_version = 6")
        current = 6

    conn.commit()


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    _apply_schema_migrations(conn)
    return conn


def get_schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def upsert_run(conn: sqlite3.Connection, run: RunSummary, detail_fetched: bool = False) -> None:
    conn.execute(
        """
        INSERT INTO runs (
            activity_id, name, start_time, duration_sec, distance_m, calories,
            avg_hr, max_hr, avg_speed_ms, pace_min_per_km,
            avg_cadence_spm, avg_vertical_osc_cm, avg_ground_contact_ms, avg_stride_length_cm,
            aerobic_efficiency, hr_drift_pct, cadence_cv, rei, detail_fetched
        ) VALUES (
            :activity_id, :name, :start_time, :duration_sec, :distance_m, :calories,
            :avg_hr, :max_hr, :avg_speed_ms, :pace_min_per_km,
            :avg_cadence_spm, :avg_vertical_osc_cm, :avg_ground_contact_ms, :avg_stride_length_cm,
            :aerobic_efficiency, :hr_drift_pct, :cadence_cv, :rei, :detail_fetched
        )
        ON CONFLICT(activity_id) DO UPDATE SET
            name = excluded.name,
            start_time = excluded.start_time,
            duration_sec = excluded.duration_sec,
            distance_m = excluded.distance_m,
            calories = excluded.calories,
            avg_hr = excluded.avg_hr,
            max_hr = excluded.max_hr,
            avg_speed_ms = excluded.avg_speed_ms,
            pace_min_per_km = excluded.pace_min_per_km,
            avg_cadence_spm = excluded.avg_cadence_spm,
            avg_vertical_osc_cm = excluded.avg_vertical_osc_cm,
            avg_ground_contact_ms = excluded.avg_ground_contact_ms,
            avg_stride_length_cm = excluded.avg_stride_length_cm,
            aerobic_efficiency = excluded.aerobic_efficiency,
            hr_drift_pct = excluded.hr_drift_pct,
            cadence_cv = excluded.cadence_cv,
            rei = excluded.rei,
            detail_fetched = excluded.detail_fetched
        """,
        {
            "activity_id": run.activity_id,
            "name": run.name,
            "start_time": run.start_time.isoformat(),
            "duration_sec": run.duration_sec,
            "distance_m": run.distance_m,
            "calories": run.calories,
            "avg_hr": run.avg_hr,
            "max_hr": run.max_hr,
            "avg_speed_ms": run.avg_speed_ms,
            "pace_min_per_km": run.pace_min_per_km,
            "avg_cadence_spm": run.avg_cadence_spm,
            "avg_vertical_osc_cm": run.avg_vertical_osc_cm,
            "avg_ground_contact_ms": run.avg_ground_contact_ms,
            "avg_stride_length_cm": run.avg_stride_length_cm,
            "aerobic_efficiency": run.aerobic_efficiency,
            "hr_drift_pct": run.hr_drift_pct,
            "cadence_cv": run.cadence_cv,
            "rei": run.rei,
            "detail_fetched": 1 if detail_fetched else 0,
        },
    )
    conn.commit()


def upsert_laps(conn: sqlite3.Connection, activity_id: int, laps: list[dict]) -> None:
    conn.execute("DELETE FROM laps WHERE activity_id = ?", (activity_id,))
    for i, lap in enumerate(laps):
        speed = lap.get("averageSpeed")
        conn.execute(
            """
            INSERT INTO laps (activity_id, lap_index, duration_sec, distance_m,
                              avg_hr, avg_speed_ms, avg_cadence_spm)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id, i,
                lap.get("duration"),
                lap.get("distance"),
                lap.get("averageHR"),
                speed,
                lap.get("averageCadence"),
            ),
        )
    conn.commit()


def get_runs_without_details(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        "SELECT activity_id FROM runs WHERE detail_fetched = 0 ORDER BY start_time DESC"
    ).fetchall()
    return [row["activity_id"] for row in rows]


def get_all_runs(conn: sqlite3.Connection, limit: int = 0) -> list[sqlite3.Row]:
    q = "SELECT * FROM runs ORDER BY start_time DESC"
    if limit:
        q += f" LIMIT {limit}"
    return conn.execute(q).fetchall()


def get_run(conn: sqlite3.Connection, activity_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM runs WHERE activity_id = ?", (activity_id,)
    ).fetchone()


def get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM user_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO user_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def _now_timestamp() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _coach_thread_title_from_message(message: str, max_len: int = 72) -> str:
    normalized = " ".join(message.split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 1].rstrip() + "..."


def get_coach_thread(conn: sqlite3.Connection, thread_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM coach_threads WHERE id = ?",
        (thread_id,),
    ).fetchone()


def get_coach_messages(conn: sqlite3.Connection, thread_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, thread_id, role, content, created_at
        FROM coach_messages
        WHERE thread_id = ?
        ORDER BY id ASC
        """,
        (thread_id,),
    ).fetchall()


def get_coach_message(conn: sqlite3.Connection, message_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, thread_id, role, content, created_at
        FROM coach_messages
        WHERE id = ?
        """,
        (message_id,),
    ).fetchone()


def set_active_coach_thread(conn: sqlite3.Connection, thread_id: int) -> None:
    set_meta(conn, "active_coach_thread_id", str(thread_id))


def get_active_coach_thread(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    raw_thread_id = get_meta(conn, "active_coach_thread_id")
    if raw_thread_id:
        try:
            thread_id = int(raw_thread_id)
        except ValueError:
            thread_id = 0
        if thread_id:
            thread = get_coach_thread(conn, thread_id)
            if thread is not None:
                return thread

    thread = conn.execute(
        """
        SELECT *
        FROM coach_threads
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    if thread is not None:
        set_active_coach_thread(conn, thread["id"])
    return thread


def create_coach_thread(conn: sqlite3.Connection, title: str = "") -> sqlite3.Row:
    now = _now_timestamp()
    cursor = conn.execute(
        """
        INSERT INTO coach_threads (title, created_at, updated_at)
        VALUES (?, ?, ?)
        """,
        (title, now, now),
    )
    conn.commit()
    thread = get_coach_thread(conn, cursor.lastrowid)
    if thread is None:
        raise RuntimeError("Failed to create coach thread.")
    set_active_coach_thread(conn, thread["id"])
    return thread


def get_or_create_active_coach_thread(conn: sqlite3.Connection) -> sqlite3.Row:
    thread = get_active_coach_thread(conn)
    if thread is not None:
        return thread
    return create_coach_thread(conn)


def append_coach_message(conn: sqlite3.Connection, thread_id: int, role: str, content: str) -> sqlite3.Row:
    now = _now_timestamp()
    cursor = conn.execute(
        """
        INSERT INTO coach_messages (thread_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (thread_id, role, content, now),
    )
    conn.execute(
        "UPDATE coach_threads SET updated_at = ? WHERE id = ?",
        (now, thread_id),
    )
    conn.commit()
    message = conn.execute(
        """
        SELECT id, thread_id, role, content, created_at
        FROM coach_messages
        WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    if message is None:
        raise RuntimeError("Failed to append coach message.")
    return message


def maybe_set_coach_thread_title_from_message(
    conn: sqlite3.Connection,
    thread_id: int,
    user_message: str,
) -> None:
    conn.execute(
        """
        UPDATE coach_threads
        SET title = COALESCE(NULLIF(title, ''), ?)
        WHERE id = ?
        """,
        (_coach_thread_title_from_message(user_message), thread_id),
    )
    conn.commit()


def get_coach_feedback(
    conn: sqlite3.Connection,
    *,
    thread_id: int | None = None,
    limit: int = 0,
) -> list[sqlite3.Row]:
    query = """
        SELECT cf.id, cf.thread_id, cf.message_id, cf.verdict, cf.created_at, cf.updated_at
        FROM coach_feedback AS cf
        JOIN coach_messages AS cm ON cm.id = cf.message_id
        WHERE cm.role = 'assistant'
    """
    params: list[object] = []

    if thread_id is not None:
        query += " AND cf.thread_id = ?"
        params.append(thread_id)

    query += " ORDER BY cf.updated_at DESC, cf.id DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    return conn.execute(query, tuple(params)).fetchall()


def get_coach_feedback_map(
    conn: sqlite3.Connection,
    message_ids: list[int],
) -> dict[int, sqlite3.Row]:
    if not message_ids:
        return {}

    placeholders = ", ".join("?" for _ in message_ids)
    rows = conn.execute(
        f"""
        SELECT id, thread_id, message_id, verdict, created_at, updated_at
        FROM coach_feedback
        WHERE message_id IN ({placeholders})
        """,
        tuple(message_ids),
    ).fetchall()
    return {int(row["message_id"]): row for row in rows}


def set_coach_feedback(
    conn: sqlite3.Connection,
    *,
    thread_id: int,
    message_id: int,
    verdict: str,
) -> sqlite3.Row:
    now = _now_timestamp()
    conn.execute(
        """
        INSERT INTO coach_feedback (thread_id, message_id, verdict, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(message_id) DO UPDATE SET
            thread_id = excluded.thread_id,
            verdict = excluded.verdict,
            updated_at = excluded.updated_at
        """,
        (thread_id, message_id, verdict, now, now),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT id, thread_id, message_id, verdict, created_at, updated_at
        FROM coach_feedback
        WHERE message_id = ?
        """,
        (message_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Failed to persist coach feedback.")
    return row


def create_sync_job(conn: sqlite3.Connection, job_id: str, status: str = "queued") -> None:
    now = _now_timestamp()
    conn.execute(
        """
        INSERT INTO sync_jobs (job_id, status, created_at, updated_at, summary_json, error_json)
        VALUES (?, ?, ?, ?, NULL, NULL)
        """,
        (job_id, status, now, now),
    )
    conn.commit()


def mark_sync_job_running(conn: sqlite3.Connection, job_id: str) -> None:
    now = _now_timestamp()
    conn.execute(
        """
        UPDATE sync_jobs
        SET status = ?, updated_at = ?
        WHERE job_id = ?
        """,
        ("running", now, job_id),
    )
    conn.commit()


def append_sync_job_log(conn: sqlite3.Connection, job_id: str, message: str) -> None:
    now = _now_timestamp()
    conn.execute(
        """
        INSERT INTO sync_job_logs (job_id, message, created_at)
        VALUES (?, ?, ?)
        """,
        (job_id, message, now),
    )
    conn.execute(
        """
        UPDATE sync_jobs
        SET updated_at = ?
        WHERE job_id = ?
        """,
        (now, job_id),
    )
    conn.commit()


def complete_sync_job(conn: sqlite3.Connection, job_id: str, summary: dict | None) -> None:
    now = _now_timestamp()
    conn.execute(
        """
        UPDATE sync_jobs
        SET status = ?, updated_at = ?, summary_json = ?, error_json = NULL
        WHERE job_id = ?
        """,
        ("success", now, json.dumps(summary) if summary is not None else None, job_id),
    )
    conn.commit()


def fail_sync_job(conn: sqlite3.Connection, job_id: str, error: dict | None) -> None:
    now = _now_timestamp()
    conn.execute(
        """
        UPDATE sync_jobs
        SET status = ?, updated_at = ?, summary_json = NULL, error_json = ?
        WHERE job_id = ?
        """,
        ("failed", now, json.dumps(error) if error is not None else None, job_id),
    )
    conn.commit()


def get_sync_job_state(conn: sqlite3.Connection, job_id: str) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT job_id, status, created_at, updated_at, summary_json, error_json
        FROM sync_jobs
        WHERE job_id = ?
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        return None

    logs = conn.execute(
        """
        SELECT message
        FROM sync_job_logs
        WHERE job_id = ?
        ORDER BY id ASC
        """,
        (job_id,),
    ).fetchall()

    def _parse_json(raw: str | None) -> dict | None:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "logs": [log["message"] for log in logs],
        "summary": _parse_json(row["summary_json"]),
        "error": _parse_json(row["error_json"]),
    }


def get_context_hash(conn: sqlite3.Connection) -> str:
    run_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_runs,
            MAX(start_time) AS latest_run_start,
            MAX(created_at) AS latest_run_created_at
        FROM runs
        """
    ).fetchone()

    payload = {
        "total_runs": int(run_row["total_runs"] or 0) if run_row else 0,
        "latest_run_start": run_row["latest_run_start"] if run_row else None,
        "latest_run_created_at": run_row["latest_run_created_at"] if run_row else None,
        "last_sync_completed_at": get_meta(conn, "last_sync_completed_at"),
        "ae_baseline": get_meta(conn, "ae_baseline"),
        "current_vdot": get_meta(conn, "current_vdot"),
        "hr_zones_json": get_meta(conn, "hr_zones_json"),
        "onboarding_completed": get_meta(conn, "onboarding_completed"),
        "onboarding_goal": get_meta(conn, "onboarding_goal"),
        "onboarding_red_flags": get_meta(conn, "onboarding_red_flags"),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def get_sync_start_date(conn: sqlite3.Connection) -> str:
    watermark = get_meta(conn, "sync_watermark_date")
    if not watermark:
        return "2000-01-01"

    try:
        watermark_date = datetime.date.fromisoformat(watermark)
    except ValueError:
        return "2000-01-01"

    start_date = watermark_date - datetime.timedelta(days=config.SYNC_LOOKBACK_DAYS)
    return start_date.isoformat()


def mark_sync_started(conn: sqlite3.Connection) -> None:
    now = datetime.datetime.now().isoformat(timespec="seconds")
    set_meta(conn, "last_sync_started_at", now)
    set_meta(conn, "last_sync_status", "running")
    set_meta(conn, "last_sync_error", "")


def mark_sync_failed(conn: sqlite3.Connection, error_message: str) -> None:
    set_meta(conn, "last_sync_status", "failed")
    set_meta(conn, "last_sync_error", error_message)


def mark_sync_completed(
    conn: sqlite3.Connection,
    *,
    new_runs: int,
    detail_failures: int,
) -> None:
    now = datetime.datetime.now().isoformat(timespec="seconds")
    set_meta(conn, "last_sync_completed_at", now)
    set_meta(conn, "last_sync_status", "success")
    set_meta(conn, "last_sync_error", "")
    set_meta(conn, "last_sync_new_runs", str(new_runs))
    set_meta(conn, "last_sync_detail_failures", str(detail_failures))

    row = conn.execute("SELECT MAX(date(start_time)) AS max_date FROM runs").fetchone()
    watermark = row["max_date"] if row and row["max_date"] else None
    if watermark:
        set_meta(conn, "sync_watermark_date", watermark)


def compute_and_store_ae_baseline(conn: sqlite3.Connection) -> Optional[float]:
    """Compute AE baseline from the best N% of qualifying runs and store it."""
    rows = conn.execute(
        """
        SELECT aerobic_efficiency FROM runs
        WHERE aerobic_efficiency IS NOT NULL
          AND duration_sec >= ?
          AND avg_hr IS NOT NULL
          AND pace_min_per_km IS NOT NULL
        ORDER BY aerobic_efficiency ASC
        """,
        (config.AE_BASELINE_MIN_DURATION_SEC,),
    ).fetchall()

    if not rows:
        set_meta(conn, "ae_baseline", "")
        return None

    ae_values = [row["aerobic_efficiency"] for row in rows]
    # Lower AE = more efficient; take bottom N% (most efficient runs)
    cutoff = max(1, int(len(ae_values) * config.AE_BASELINE_PERCENTILE / 100))
    baseline = statistics.mean(ae_values[:cutoff])

    set_meta(conn, "ae_baseline", str(baseline))
    return baseline


def recompute_all_rei(conn: sqlite3.Connection, ae_baseline: Optional[float]) -> int:
    """Recompute REI for all runs using the latest AE baseline, if available."""
    from metrics import compute_rei
    import datetime

    rows = conn.execute("SELECT * FROM runs").fetchall()
    updated = 0
    for row in rows:
        run = RunSummary(
            activity_id=row["activity_id"],
            name=row["name"] or "",
            start_time=datetime.datetime.fromisoformat(row["start_time"]),
            duration_sec=row["duration_sec"] or 0,
            distance_m=row["distance_m"] or 0,
            calories=row["calories"] or 0,
            avg_hr=row["avg_hr"],
            max_hr=row["max_hr"],
            avg_speed_ms=row["avg_speed_ms"],
            pace_min_per_km=row["pace_min_per_km"],
            avg_cadence_spm=row["avg_cadence_spm"],
            avg_vertical_osc_cm=row["avg_vertical_osc_cm"],
            avg_ground_contact_ms=row["avg_ground_contact_ms"],
            avg_stride_length_cm=row["avg_stride_length_cm"],
            aerobic_efficiency=row["aerobic_efficiency"],
            hr_drift_pct=row["hr_drift_pct"],
            cadence_cv=row["cadence_cv"],
        )
        new_rei = compute_rei(run, ae_baseline)
        conn.execute(
            "UPDATE runs SET rei = ? WHERE activity_id = ?",
            (new_rei, run.activity_id),
        )
        updated += 1
    conn.commit()
    return updated


def _backfill_run_avg_hr_from_laps(conn: sqlite3.Connection) -> int:
    cursor = conn.execute(
        """
        UPDATE runs
        SET avg_hr = (
            SELECT CASE
                WHEN SUM(CASE WHEN laps.duration_sec IS NOT NULL AND laps.duration_sec > 0 THEN laps.duration_sec ELSE 0 END) > 0
                    THEN SUM(laps.avg_hr * laps.duration_sec) / SUM(laps.duration_sec)
                ELSE AVG(laps.avg_hr)
            END
            FROM laps
            WHERE laps.activity_id = runs.activity_id
              AND laps.avg_hr IS NOT NULL
        )
        WHERE runs.avg_hr IS NULL
          AND EXISTS (
              SELECT 1
              FROM laps
              WHERE laps.activity_id = runs.activity_id
                AND laps.avg_hr IS NOT NULL
          )
        """
    )
    conn.commit()
    return cursor.rowcount


def _recompute_derived_metrics(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE runs
        SET aerobic_efficiency = CASE
            WHEN avg_hr IS NOT NULL AND avg_hr > 0 AND pace_min_per_km IS NOT NULL
                THEN pace_min_per_km / avg_hr
            ELSE NULL
        END
        """
    )
    conn.commit()

    ae_baseline = compute_and_store_ae_baseline(conn)
    recompute_all_rei(conn, ae_baseline)

    import vdot_zones

    vdot_zones.estimate_vdot_from_runs(conn)
    try:
        vdot_zones._refresh_hr_zones(conn)
    except ValueError:
        pass

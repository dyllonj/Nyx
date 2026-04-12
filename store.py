import datetime
import hashlib
import json
import sqlite3
import statistics
from typing import Any, Optional
import config
from models import RunSummary
from providers.base import (
    NormalizedActivity,
    NormalizedActivitySample,
    NormalizedBatch,
    NormalizedDailyRecovery,
)


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

PROVIDER_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_accounts (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    provider              TEXT NOT NULL,
    provider_user_id      TEXT NOT NULL,
    display_name          TEXT,
    status                TEXT NOT NULL DEFAULT 'connected',
    scopes_json           TEXT,
    access_token          TEXT,
    refresh_token         TEXT,
    token_type            TEXT,
    token_expires_at      TEXT,
    account_metadata_json TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    disconnected_at       TEXT,
    UNIQUE(provider, provider_user_id)
);

CREATE TABLE IF NOT EXISTS provider_sync_state (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    provider            TEXT NOT NULL,
    resource_type       TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'idle',
    cursor_json         TEXT,
    watermark           TEXT,
    last_started_at     TEXT,
    last_success_at     TEXT,
    last_error_json     TEXT,
    summary_json        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE(provider_account_id, resource_type)
);

CREATE TABLE IF NOT EXISTS activities (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    provider             TEXT NOT NULL,
    provider_account_id  INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    provider_activity_id TEXT NOT NULL,
    source_type          TEXT NOT NULL,
    activity_type        TEXT,
    name                 TEXT,
    start_time           TEXT NOT NULL,
    end_time             TEXT,
    day                  TEXT,
    timezone             TEXT,
    duration_sec         REAL,
    distance_m           REAL,
    calories             REAL,
    intensity            TEXT,
    source               TEXT,
    average_hr           REAL,
    max_hr               REAL,
    metadata_json        TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    UNIQUE(provider, provider_account_id, provider_activity_id)
);

CREATE TABLE IF NOT EXISTS activity_samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id   INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    sample_type   TEXT NOT NULL,
    recorded_at   TEXT NOT NULL,
    value         REAL,
    unit          TEXT,
    source        TEXT NOT NULL DEFAULT '',
    metadata_json TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE(activity_id, sample_type, recorded_at, source)
);

CREATE TABLE IF NOT EXISTS daily_recovery (
    id                             INTEGER PRIMARY KEY AUTOINCREMENT,
    provider                       TEXT NOT NULL,
    provider_account_id            INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    day                            TEXT NOT NULL,
    provider_day_id                TEXT,
    recovery_score                 INTEGER,
    readiness_score                INTEGER,
    sleep_score                    INTEGER,
    activity_score                 INTEGER,
    resting_heart_rate             REAL,
    average_heart_rate             REAL,
    average_hrv                    REAL,
    body_temperature_delta_c       REAL,
    body_temperature_trend_delta_c REAL,
    sleep_duration_sec             INTEGER,
    time_in_bed_sec                INTEGER,
    deep_sleep_duration_sec        INTEGER,
    rem_sleep_duration_sec         INTEGER,
    light_sleep_duration_sec       INTEGER,
    awake_time_sec                 INTEGER,
    latency_sec                    INTEGER,
    sleep_efficiency               INTEGER,
    average_breath                 REAL,
    active_calories                INTEGER,
    steps                          INTEGER,
    total_calories                 INTEGER,
    contributors_json              TEXT,
    metadata_json                  TEXT,
    created_at                     TEXT NOT NULL,
    updated_at                     TEXT NOT NULL,
    UNIQUE(provider, provider_account_id, day)
);

CREATE TABLE IF NOT EXISTS oura_raw_personal_info (
    provider_account_id INTEGER PRIMARY KEY REFERENCES provider_accounts(id) ON DELETE CASCADE,
    payload_json        TEXT NOT NULL,
    fetched_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oura_raw_workouts (
    provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    document_id         TEXT NOT NULL,
    day                 TEXT,
    start_time          TEXT,
    payload_json        TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    PRIMARY KEY (provider_account_id, document_id)
);

CREATE TABLE IF NOT EXISTS oura_raw_daily_activity (
    provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    document_id         TEXT NOT NULL,
    day                 TEXT,
    payload_json        TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    PRIMARY KEY (provider_account_id, document_id)
);

CREATE TABLE IF NOT EXISTS oura_raw_daily_sleep (
    provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    document_id         TEXT NOT NULL,
    day                 TEXT,
    payload_json        TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    PRIMARY KEY (provider_account_id, document_id)
);

CREATE TABLE IF NOT EXISTS oura_raw_daily_readiness (
    provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    document_id         TEXT NOT NULL,
    day                 TEXT,
    payload_json        TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    PRIMARY KEY (provider_account_id, document_id)
);

CREATE TABLE IF NOT EXISTS oura_raw_sleep (
    provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    document_id         TEXT NOT NULL,
    day                 TEXT,
    start_time          TEXT,
    payload_json        TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    PRIMARY KEY (provider_account_id, document_id)
);

CREATE TABLE IF NOT EXISTS oura_raw_heartrate (
    provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    sample_timestamp    TEXT NOT NULL,
    payload_json        TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    PRIMARY KEY (provider_account_id, sample_timestamp)
);

CREATE INDEX IF NOT EXISTS idx_provider_accounts_provider_status
    ON provider_accounts(provider, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_provider_sync_state_account_resource
    ON provider_sync_state(provider_account_id, resource_type);
CREATE INDEX IF NOT EXISTS idx_activities_provider_day
    ON activities(provider, day DESC, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_daily_recovery_provider_day
    ON daily_recovery(provider, day DESC);
CREATE INDEX IF NOT EXISTS idx_oura_raw_workouts_day
    ON oura_raw_workouts(provider_account_id, day DESC);
CREATE INDEX IF NOT EXISTS idx_oura_raw_daily_activity_day
    ON oura_raw_daily_activity(provider_account_id, day DESC);
CREATE INDEX IF NOT EXISTS idx_oura_raw_daily_sleep_day
    ON oura_raw_daily_sleep(provider_account_id, day DESC);
CREATE INDEX IF NOT EXISTS idx_oura_raw_daily_readiness_day
    ON oura_raw_daily_readiness(provider_account_id, day DESC);
CREATE INDEX IF NOT EXISTS idx_oura_raw_sleep_day
    ON oura_raw_sleep(provider_account_id, day DESC);
CREATE INDEX IF NOT EXISTS idx_oura_raw_heartrate_timestamp
    ON oura_raw_heartrate(provider_account_id, sample_timestamp DESC);
"""

PROVIDER_RAW_PAYLOAD_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_raw_payloads (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    provider          TEXT NOT NULL,
    provider_account_id INTEGER NOT NULL REFERENCES provider_accounts(id) ON DELETE CASCADE,
    resource          TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    payload_json      TEXT NOT NULL,
    source_updated_at TEXT,
    fetched_at        TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE(provider, provider_account_id, resource, source_id)
);

CREATE INDEX IF NOT EXISTS idx_provider_raw_payloads_provider_resource
    ON provider_raw_payloads(provider, resource, source_updated_at DESC);
"""

SCHEMA_VERSION = 9


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not _table_exists(conn, table_name):
        return False
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column["name"] == column_name for column in columns)


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

    if current < 7:
        conn.executescript(PROVIDER_SCHEMA)
        conn.execute("PRAGMA user_version = 7")
        current = 7

    if current < 8:
        if not _table_has_column(conn, "provider_accounts", "provider_user_id"):
            conn.executescript(
                """
                DROP TABLE IF EXISTS oura_raw_heartrate;
                DROP TABLE IF EXISTS oura_raw_sleep;
                DROP TABLE IF EXISTS oura_raw_daily_readiness;
                DROP TABLE IF EXISTS oura_raw_daily_sleep;
                DROP TABLE IF EXISTS oura_raw_daily_activity;
                DROP TABLE IF EXISTS oura_raw_workouts;
                DROP TABLE IF EXISTS oura_raw_personal_info;
                DROP TABLE IF EXISTS daily_recovery;
                DROP TABLE IF EXISTS activity_samples;
                DROP TABLE IF EXISTS activities;
                DROP TABLE IF EXISTS provider_sync_state;
                DROP TABLE IF EXISTS provider_accounts;
                DROP TABLE IF EXISTS provider_raw_payloads;
                """
            )
            conn.executescript(PROVIDER_SCHEMA)
        conn.execute("PRAGMA user_version = 8")
        current = 8

    if current < 9:
        conn.executescript(PROVIDER_RAW_PAYLOAD_SCHEMA)
        conn.execute("PRAGMA user_version = 9")
        current = 9

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


def delete_meta(conn: sqlite3.Connection, *keys: str) -> None:
    if not keys:
        return
    conn.executemany(
        "DELETE FROM user_meta WHERE key = ?",
        [(key,) for key in keys],
    )
    conn.commit()


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _parse_json_value(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _provider_meta_key(provider: str, suffix: str) -> str:
    return f"provider:{provider}:{suffix}"


def set_provider_oauth_state(conn: sqlite3.Connection, provider: str, state: str) -> None:
    set_meta(conn, _provider_meta_key(provider, "oauth_state"), state)


def get_provider_oauth_state(conn: sqlite3.Connection, provider: str) -> Optional[str]:
    return get_meta(conn, _provider_meta_key(provider, "oauth_state"))


def clear_provider_oauth_state(conn: sqlite3.Connection, provider: str) -> None:
    delete_meta(conn, _provider_meta_key(provider, "oauth_state"))


def _deserialize_provider_account(row: sqlite3.Row | dict | None) -> dict[str, Any] | None:
    if row is None:
        return None
    account = dict(row)
    scopes = _parse_json_value(account.get("scopes_json"))
    if not isinstance(scopes, list):
        scopes = []
    metadata = _parse_json_value(account.get("account_metadata_json"))
    if not isinstance(metadata, dict):
        metadata = {}
    account["scopes"] = scopes
    account["account_metadata"] = metadata
    account["external_user_id"] = account.get("provider_user_id")
    account["email"] = metadata.get("email")
    account["profile_json"] = _json_dumps(metadata.get("profile") or metadata)
    account["refresh_token_expires_at"] = metadata.get("refresh_token_expires_at")
    account["connected_at"] = metadata.get("connected_at") or account.get("created_at")
    account["last_refreshed_at"] = metadata.get("last_refreshed_at") or account.get("updated_at")
    return account


def get_provider_account(conn: sqlite3.Connection, provider: str) -> Optional[dict[str, Any]]:
    return get_active_provider_account(conn, provider)


def get_active_provider_account(conn: sqlite3.Connection, provider: str) -> Optional[dict[str, Any]]:
    row = conn.execute(
        """
        SELECT *
        FROM provider_accounts
        WHERE provider = ?
        ORDER BY CASE status WHEN 'connected' THEN 0 ELSE 1 END, updated_at DESC, id DESC
        LIMIT 1
        """,
        (provider,),
    ).fetchone()
    return _deserialize_provider_account(row)


def get_provider_account_by_id(conn: sqlite3.Connection, account_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        """
        SELECT *
        FROM provider_accounts
        WHERE id = ?
        """,
        (account_id,),
    ).fetchone()
    return _deserialize_provider_account(row)


def list_provider_accounts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM provider_accounts
        ORDER BY provider ASC, updated_at DESC, id DESC
        """
    ).fetchall()
    accounts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        account = _deserialize_provider_account(row)
        if account is None or str(account["provider"]) in seen:
            continue
        seen.add(str(account["provider"]))
        accounts.append(account)
    return accounts


def upsert_provider_account(
    conn: sqlite3.Connection,
    *,
    provider: str,
    provider_user_id: str,
    display_name: str | None,
    scopes: list[str] | tuple[str, ...] | None,
    access_token: str | None,
    refresh_token: str | None,
    token_type: str | None,
    token_expires_at: str | None,
    status: str,
    account_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now_timestamp()
    metadata = dict(account_metadata or {})
    metadata.setdefault("connected_at", now)
    metadata["last_refreshed_at"] = now
    conn.execute(
        """
        INSERT INTO provider_accounts (
            provider, provider_user_id, display_name, status, scopes_json,
            access_token, refresh_token, token_type, token_expires_at,
            account_metadata_json, created_at, updated_at, disconnected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, provider_user_id) DO UPDATE SET
            display_name = excluded.display_name,
            status = excluded.status,
            scopes_json = excluded.scopes_json,
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            token_type = excluded.token_type,
            token_expires_at = excluded.token_expires_at,
            account_metadata_json = excluded.account_metadata_json,
            updated_at = excluded.updated_at,
            disconnected_at = excluded.disconnected_at
        """,
        (
            provider,
            provider_user_id,
            display_name,
            status,
            _json_dumps(sorted({str(scope) for scope in (scopes or [])})),
            access_token,
            refresh_token,
            token_type,
            token_expires_at,
            _json_dumps(metadata),
            now,
            now,
            None if status == "connected" else now,
        ),
    )
    conn.commit()
    account = conn.execute(
        """
        SELECT *
        FROM provider_accounts
        WHERE provider = ? AND provider_user_id = ?
        """,
        (provider, provider_user_id),
    ).fetchone()
    parsed = _deserialize_provider_account(account)
    if parsed is None:
        raise RuntimeError("Failed to upsert provider account.")
    return parsed


def connect_provider_account(
    conn: sqlite3.Connection,
    *,
    provider: str,
    external_user_id: str | None,
    email: str | None,
    display_name: str | None,
    access_token: str,
    refresh_token: str | None,
    token_type: str | None,
    scopes: list[str],
    token_expires_at: str | None,
    refresh_token_expires_at: str | None,
    profile: dict | None,
) -> dict[str, Any]:
    metadata = {"profile": dict(profile or {})}
    if email:
        metadata["email"] = email
    if refresh_token_expires_at:
        metadata["refresh_token_expires_at"] = refresh_token_expires_at
    provider_user_id = external_user_id or email or provider
    return upsert_provider_account(
        conn,
        provider=provider,
        provider_user_id=provider_user_id,
        display_name=display_name,
        scopes=scopes,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type,
        token_expires_at=token_expires_at,
        status="connected",
        account_metadata=metadata,
    )


def update_provider_account_tokens(
    conn: sqlite3.Connection,
    *,
    account_id: int | None = None,
    provider: str | None = None,
    access_token: str,
    refresh_token: str | None,
    token_type: str | None,
    scopes: list[str] | None,
    token_expires_at: str | None,
    refresh_token_expires_at: str | None = None,
) -> None:
    target_account: dict[str, Any] | None
    if account_id is not None:
        target_account = get_provider_account_by_id(conn, account_id)
    elif provider is not None:
        target_account = get_active_provider_account(conn, provider)
    else:
        raise ValueError("Either account_id or provider is required.")
    if target_account is None:
        raise RuntimeError("Provider account does not exist.")

    metadata = dict(target_account.get("account_metadata") or {})
    metadata["last_refreshed_at"] = _now_timestamp()
    if refresh_token_expires_at is not None:
        metadata["refresh_token_expires_at"] = refresh_token_expires_at

    now = _now_timestamp()
    conn.execute(
        """
        UPDATE provider_accounts
        SET status = ?,
            access_token = ?,
            refresh_token = ?,
            token_type = ?,
            scopes_json = COALESCE(?, scopes_json),
            token_expires_at = ?,
            account_metadata_json = ?,
            updated_at = ?,
            disconnected_at = NULL
        WHERE id = ?
        """,
        (
            "connected",
            access_token,
            refresh_token,
            token_type,
            _json_dumps(sorted({str(scope) for scope in scopes})) if scopes is not None else None,
            token_expires_at,
            _json_dumps(metadata),
            now,
            int(target_account["id"]),
        ),
    )
    conn.commit()


def disconnect_provider_account(conn: sqlite3.Connection, provider_or_account_id: str | int) -> None:
    account = (
        get_provider_account_by_id(conn, int(provider_or_account_id))
        if isinstance(provider_or_account_id, int)
        else get_active_provider_account(conn, provider_or_account_id)
    )
    if account is None:
        return
    now = _now_timestamp()
    conn.execute(
        """
        UPDATE provider_accounts
        SET status = ?,
            access_token = NULL,
            refresh_token = NULL,
            token_type = NULL,
            token_expires_at = NULL,
            updated_at = ?,
            disconnected_at = ?
        WHERE id = ?
        """,
        ("disconnected", now, now, int(account["id"])),
    )
    conn.commit()


def _resolve_sync_identity(
    conn: sqlite3.Connection,
    provider_or_account_id: str | int | None = None,
    resource: str | None = None,
    *,
    account_id: int | None = None,
    provider: str | None = None,
    resource_type: str | None = None,
) -> tuple[int, str, str]:
    resolved_account_id = account_id
    resolved_provider = provider
    resolved_resource = resource_type or resource

    if resolved_account_id is None and isinstance(provider_or_account_id, int):
        resolved_account_id = provider_or_account_id
    if resolved_provider is None and isinstance(provider_or_account_id, str):
        resolved_provider = provider_or_account_id

    if resolved_account_id is None:
        if not resolved_provider:
            raise ValueError("Provider is required when account_id is not provided.")
        account = get_active_provider_account(conn, resolved_provider)
        if account is None:
            raise RuntimeError(f"No provider account found for {resolved_provider}.")
        resolved_account_id = int(account["id"])
        resolved_provider = str(account["provider"])
    elif resolved_provider is None:
        account = get_provider_account_by_id(conn, resolved_account_id)
        if account is None:
            raise RuntimeError(f"No provider account found for id {resolved_account_id}.")
        resolved_provider = str(account["provider"])

    if not resolved_resource:
        raise ValueError("resource_type is required.")

    return resolved_account_id, resolved_provider, resolved_resource


def _deserialize_sync_state(row: sqlite3.Row | dict | None) -> dict[str, Any] | None:
    if row is None:
        return None
    state = dict(row)
    state["cursor"] = _parse_json_value(state.get("cursor_json"))
    state["error"] = _parse_json_value(state.get("last_error_json"))
    state["summary"] = _parse_json_value(state.get("summary_json"))
    state["resource"] = state.get("resource_type")
    state["last_sync_started_at"] = state.get("last_started_at")
    state["last_sync_completed_at"] = state.get("last_success_at")
    state["last_sync_status"] = state.get("status")
    state["last_error"] = state.get("error")
    return state


def get_provider_sync_state(
    conn: sqlite3.Connection,
    provider_or_account_id: str | int,
    resource: str,
) -> Optional[dict[str, Any]]:
    account_id, _, resource_type = _resolve_sync_identity(conn, provider_or_account_id, resource)
    row = conn.execute(
        """
        SELECT *
        FROM provider_sync_state
        WHERE provider_account_id = ? AND resource_type = ?
        """,
        (account_id, resource_type),
    ).fetchone()
    return _deserialize_sync_state(row)


def list_provider_sync_states(
    conn: sqlite3.Connection,
    provider: str | None = None,
    *,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    query = "SELECT * FROM provider_sync_state"
    if account_id is not None:
        query += " WHERE provider_account_id = ?"
        params.append(account_id)
    elif provider is not None:
        query += " WHERE provider = ?"
        params.append(provider)
    query += " ORDER BY provider ASC, resource_type ASC"
    rows = conn.execute(query, tuple(params)).fetchall()
    return [state for state in (_deserialize_sync_state(row) for row in rows) if state is not None]


def _serialize_cursor(cursor: str | dict | list | None) -> str | None:
    if cursor is None:
        return None
    if isinstance(cursor, str):
        return cursor
    return _json_dumps(cursor)


def mark_provider_sync_running(
    conn: sqlite3.Connection,
    account_id: int,
    provider: str,
    resource_type: str,
) -> None:
    now = _now_timestamp()
    conn.execute(
        """
        INSERT INTO provider_sync_state (
            provider_account_id, provider, resource_type, status, cursor_json, watermark,
            last_started_at, last_success_at, last_error_json, summary_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, NULL, ?, ?)
        ON CONFLICT(provider_account_id, resource_type) DO UPDATE SET
            provider = excluded.provider,
            status = excluded.status,
            last_started_at = excluded.last_started_at,
            last_error_json = NULL,
            updated_at = excluded.updated_at
        """,
        (account_id, provider, resource_type, "running", now, now, now),
    )
    conn.commit()


def mark_provider_sync_started(conn: sqlite3.Connection, provider: str, resource: str) -> None:
    account_id, resolved_provider, resource_type = _resolve_sync_identity(conn, provider, resource)
    mark_provider_sync_running(conn, account_id, resolved_provider, resource_type)


def mark_provider_sync_success(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    provider: str,
    resource_type: str,
    watermark: str | None,
    cursor: str | dict | list | None = None,
    summary: dict[str, Any] | None = None,
) -> None:
    now = _now_timestamp()
    conn.execute(
        """
        INSERT INTO provider_sync_state (
            provider_account_id, provider, resource_type, status, cursor_json, watermark,
            last_started_at, last_success_at, last_error_json, summary_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?)
        ON CONFLICT(provider_account_id, resource_type) DO UPDATE SET
            provider = excluded.provider,
            status = excluded.status,
            cursor_json = COALESCE(excluded.cursor_json, provider_sync_state.cursor_json),
            watermark = COALESCE(excluded.watermark, provider_sync_state.watermark),
            last_success_at = excluded.last_success_at,
            last_error_json = NULL,
            summary_json = excluded.summary_json,
            updated_at = excluded.updated_at
        """,
        (
            account_id,
            provider,
            resource_type,
            "success",
            _serialize_cursor(cursor),
            watermark,
            now,
            _json_dumps(summary),
            now,
            now,
        ),
    )
    conn.commit()


def mark_provider_sync_completed(
    conn: sqlite3.Connection,
    provider: str,
    resource: str,
    *,
    cursor: str | dict | list | None = None,
) -> None:
    account_id, resolved_provider, resource_type = _resolve_sync_identity(conn, provider, resource)
    watermark = None
    parsed_cursor = cursor if isinstance(cursor, dict) else _parse_json_value(cursor) if isinstance(cursor, str) else None
    if isinstance(parsed_cursor, dict):
        window_end = parsed_cursor.get("window_end") or parsed_cursor.get("last_day")
        if isinstance(window_end, str):
            watermark = window_end[:10]
    mark_provider_sync_success(
        conn,
        account_id=account_id,
        provider=resolved_provider,
        resource_type=resource_type,
        watermark=watermark,
        cursor=cursor,
        summary=None,
    )


def mark_provider_sync_failed(
    conn: sqlite3.Connection,
    provider_or_account_id: str | int | None = None,
    resource: str | None = None,
    error_message: str | None = None,
    *,
    account_id: int | None = None,
    provider: str | None = None,
    resource_type: str | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    resolved_account_id, resolved_provider, resolved_resource = _resolve_sync_identity(
        conn,
        provider_or_account_id,
        resource,
        account_id=account_id,
        provider=provider,
        resource_type=resource_type,
    )
    now = _now_timestamp()
    error_payload = error or {"message": error_message or "Provider sync failed."}
    conn.execute(
        """
        INSERT INTO provider_sync_state (
            provider_account_id, provider, resource_type, status, cursor_json, watermark,
            last_started_at, last_success_at, last_error_json, summary_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, NULL, ?, ?)
        ON CONFLICT(provider_account_id, resource_type) DO UPDATE SET
            provider = excluded.provider,
            status = excluded.status,
            last_error_json = excluded.last_error_json,
            updated_at = excluded.updated_at
        """,
        (
            resolved_account_id,
            resolved_provider,
            resolved_resource,
            "failed",
            _json_dumps(error_payload),
            now,
            now,
        ),
    )
    conn.commit()


def upsert_provider_raw_payload(
    conn: sqlite3.Connection,
    *,
    provider: str,
    resource: str,
    source_id: str,
    payload: dict,
    source_updated_at: str | None = None,
) -> None:
    now = _now_timestamp()
    provider_account_id = _resolve_provider_account_id(conn, provider=provider)
    conn.execute(
        """
        INSERT INTO provider_raw_payloads (
            provider, provider_account_id, resource, source_id, payload_json, source_updated_at,
            fetched_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, provider_account_id, resource, source_id) DO UPDATE SET
            payload_json = excluded.payload_json,
            source_updated_at = excluded.source_updated_at,
            fetched_at = excluded.fetched_at,
            updated_at = excluded.updated_at
        """,
        (
            provider,
            provider_account_id,
            resource,
            source_id,
            _json_dumps(payload),
            source_updated_at,
            now,
            now,
            now,
        ),
    )
    conn.commit()


def upsert_oura_raw_payloads(
    conn: sqlite3.Connection,
    account_id: int,
    resource_type: str,
    payloads: list[dict[str, Any]],
) -> None:
    now = _now_timestamp()
    if resource_type == "personal_info":
        payload = payloads[0] if payloads else {}
        conn.execute(
            """
            INSERT INTO oura_raw_personal_info (provider_account_id, payload_json, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(provider_account_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                fetched_at = excluded.fetched_at
            """,
            (account_id, _json_dumps(payload), now),
        )
        conn.commit()
        return

    table_names = {
        "workout": "oura_raw_workouts",
        "daily_activity": "oura_raw_daily_activity",
        "daily_sleep": "oura_raw_daily_sleep",
        "daily_readiness": "oura_raw_daily_readiness",
        "sleep": "oura_raw_sleep",
        "heartrate": "oura_raw_heartrate",
    }
    table_name = table_names.get(resource_type)
    if table_name is None:
        raise ValueError(f"Unsupported Oura raw payload resource: {resource_type}")

    for payload in payloads:
        if resource_type == "heartrate":
            conn.execute(
                """
                INSERT INTO oura_raw_heartrate (provider_account_id, sample_timestamp, payload_json, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider_account_id, sample_timestamp) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    fetched_at = excluded.fetched_at
                """,
                (account_id, str(payload.get("timestamp")), _json_dumps(payload), now),
            )
            continue

        if resource_type in {"workout", "sleep"}:
            conn.execute(
                f"""
                INSERT INTO {table_name} (provider_account_id, document_id, day, start_time, payload_json, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_account_id, document_id) DO UPDATE SET
                    day = excluded.day,
                    start_time = excluded.start_time,
                    payload_json = excluded.payload_json,
                    fetched_at = excluded.fetched_at
                """,
                (
                    account_id,
                    str(payload.get("id")),
                    payload.get("day"),
                    payload.get("start_datetime") or payload.get("bedtime_start"),
                    _json_dumps(payload),
                    now,
                ),
            )
            continue

        conn.execute(
            f"""
            INSERT INTO {table_name} (provider_account_id, document_id, day, payload_json, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider_account_id, document_id) DO UPDATE SET
                day = excluded.day,
                payload_json = excluded.payload_json,
                fetched_at = excluded.fetched_at
            """,
            (
                account_id,
                str(payload.get("id")),
                payload.get("day"),
                _json_dumps(payload),
                now,
            ),
        )
    conn.commit()


def _resolve_provider_account_id(
    conn: sqlite3.Connection,
    *,
    provider: str,
    provider_account_id: int | None = None,
) -> int:
    if provider_account_id is not None:
        return provider_account_id
    account = get_active_provider_account(conn, provider)
    if account is None:
        raise RuntimeError(f"No provider account found for {provider}.")
    return int(account["id"])


def upsert_activity(conn: sqlite3.Connection, activity: NormalizedActivity | dict[str, Any]) -> int:
    if isinstance(activity, NormalizedActivity):
        normalized = activity
    else:
        provider = str(activity["provider"])
        normalized = NormalizedActivity(
            provider=provider,
            provider_account_id=_resolve_provider_account_id(
                conn,
                provider=provider,
                provider_account_id=_coerce_int(activity.get("provider_account_id")),
            ),
            provider_activity_id=str(activity.get("provider_activity_id") or activity.get("source_id")),
            source_type=str(activity.get("source_type") or "activity"),
            activity_type=_string_or_none(activity.get("activity_type")),
            name=_string_or_none(activity.get("name")),
            start_time=str(activity.get("start_time") or activity.get("started_at")),
            end_time=_string_or_none(activity.get("end_time") or activity.get("ended_at")),
            day=_string_or_none(activity.get("day") or activity.get("local_date")),
            timezone=_string_or_none(activity.get("timezone") or activity.get("timezone_offset")),
            duration_sec=_coerce_float(activity.get("duration_sec")),
            distance_m=_coerce_float(activity.get("distance_m")),
            calories=_coerce_float(activity.get("calories") or activity.get("calories_kcal")),
            intensity=_string_or_none(activity.get("intensity")),
            source=_string_or_none(activity.get("source") or activity.get("sport_name")),
            average_hr=_coerce_float(activity.get("average_hr") or activity.get("avg_hr")),
            max_hr=_coerce_float(activity.get("max_hr")),
            metadata={
                key: value
                for key, value in activity.items()
                if key
                not in {
                    "provider",
                    "provider_account_id",
                    "provider_activity_id",
                    "source_id",
                    "source_type",
                    "activity_type",
                    "name",
                    "start_time",
                    "started_at",
                    "end_time",
                    "ended_at",
                    "day",
                    "local_date",
                    "timezone",
                    "timezone_offset",
                    "duration_sec",
                    "distance_m",
                    "calories",
                    "calories_kcal",
                    "intensity",
                    "source",
                    "sport_name",
                    "average_hr",
                    "avg_hr",
                    "max_hr",
                }
            },
        )

    now = _now_timestamp()
    conn.execute(
        """
        INSERT INTO activities (
            provider, provider_account_id, provider_activity_id, source_type, activity_type,
            name, start_time, end_time, day, timezone, duration_sec, distance_m,
            calories, intensity, source, average_hr, max_hr, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, provider_account_id, provider_activity_id) DO UPDATE SET
            source_type = excluded.source_type,
            activity_type = excluded.activity_type,
            name = excluded.name,
            start_time = excluded.start_time,
            end_time = excluded.end_time,
            day = excluded.day,
            timezone = excluded.timezone,
            duration_sec = excluded.duration_sec,
            distance_m = excluded.distance_m,
            calories = excluded.calories,
            intensity = excluded.intensity,
            source = excluded.source,
            average_hr = excluded.average_hr,
            max_hr = excluded.max_hr,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (
            normalized.provider,
            normalized.provider_account_id,
            normalized.provider_activity_id,
            normalized.source_type,
            normalized.activity_type,
            normalized.name,
            normalized.start_time,
            normalized.end_time,
            normalized.day,
            normalized.timezone,
            normalized.duration_sec,
            normalized.distance_m,
            normalized.calories,
            normalized.intensity,
            normalized.source,
            normalized.average_hr,
            normalized.max_hr,
            _json_dumps(normalized.metadata),
            now,
            now,
        ),
    )
    row = conn.execute(
        """
        SELECT id
        FROM activities
        WHERE provider = ? AND provider_account_id = ? AND provider_activity_id = ?
        """,
        (normalized.provider, normalized.provider_account_id, normalized.provider_activity_id),
    ).fetchone()
    conn.commit()
    if row is None:
        raise RuntimeError("Failed to upsert activity.")
    return int(row["id"])


def replace_activity_samples(
    conn: sqlite3.Connection,
    *,
    provider: str,
    activity_source_id: str,
    samples: list[dict],
) -> None:
    row = conn.execute(
        """
        SELECT id, start_time
        FROM activities
        WHERE provider = ? AND provider_activity_id = ?
        """,
        (provider, activity_source_id),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Activity {provider}/{activity_source_id} does not exist.")
    activity_id = int(row["id"])
    default_timestamp = row["start_time"] or _now_timestamp()
    conn.execute("DELETE FROM activity_samples WHERE activity_id = ?", (activity_id,))
    now = _now_timestamp()
    for sample in samples:
        metadata = {
            key: value
            for key, value in sample.items()
            if key not in {"sample_type", "sample_value", "sample_unit", "sample_start_at", "sample_end_at", "bucket_index"}
        }
        bucket_index = sample.get("bucket_index")
        source = f"bucket:{bucket_index}" if bucket_index is not None else ""
        recorded_at = sample.get("sample_start_at") or sample.get("sample_end_at") or default_timestamp
        conn.execute(
            """
            INSERT INTO activity_samples (
                activity_id, sample_type, recorded_at, value, unit, source, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id, sample_type, recorded_at, source) DO UPDATE SET
                value = excluded.value,
                unit = excluded.unit,
                metadata_json = excluded.metadata_json
            """,
            (
                activity_id,
                sample["sample_type"],
                recorded_at,
                sample.get("sample_value"),
                sample.get("sample_unit"),
                source,
                _json_dumps(metadata),
                now,
            ),
        )
    conn.commit()


def upsert_daily_recovery(conn: sqlite3.Connection, recovery: NormalizedDailyRecovery | dict[str, Any]) -> None:
    if isinstance(recovery, NormalizedDailyRecovery):
        normalized = recovery
    else:
        provider = str(recovery["provider"])
        sleep_duration = _coerce_float(recovery.get("sleep_duration_sec"))
        if sleep_duration is None:
            sleep_duration = sum(
                value
                for value in (
                    _coerce_float(recovery.get("total_light_sleep_sec")),
                    _coerce_float(recovery.get("total_slow_wave_sleep_sec")),
                    _coerce_float(recovery.get("total_rem_sleep_sec")),
                )
                if value is not None
            ) or None
        normalized = NormalizedDailyRecovery(
            provider=provider,
            provider_account_id=_resolve_provider_account_id(
                conn,
                provider=provider,
                provider_account_id=_coerce_int(recovery.get("provider_account_id")),
            ),
            day=str(recovery.get("day") or recovery.get("recovery_date")),
            provider_day_id=_string_or_none(
                recovery.get("provider_day_id")
                or recovery.get("source_cycle_id")
                or recovery.get("source_sleep_id")
            ),
            recovery_score=_coerce_int(recovery.get("recovery_score")),
            readiness_score=_coerce_int(recovery.get("readiness_score") or recovery.get("recovery_score")),
            sleep_score=_coerce_int(recovery.get("sleep_score")),
            activity_score=_coerce_int(recovery.get("activity_score")),
            resting_heart_rate=_coerce_float(recovery.get("resting_heart_rate") or recovery.get("resting_hr")),
            average_heart_rate=_coerce_float(recovery.get("average_heart_rate") or recovery.get("day_avg_hr")),
            average_hrv=_coerce_float(recovery.get("average_hrv") or recovery.get("hrv_rmssd_ms")),
            body_temperature_delta_c=_coerce_float(
                recovery.get("body_temperature_delta_c") or recovery.get("skin_temp_c")
            ),
            body_temperature_trend_delta_c=_coerce_float(recovery.get("body_temperature_trend_delta_c")),
            sleep_duration_sec=_coerce_int(sleep_duration),
            time_in_bed_sec=_coerce_int(recovery.get("time_in_bed_sec") or recovery.get("total_in_bed_sec")),
            deep_sleep_duration_sec=_coerce_int(
                recovery.get("deep_sleep_duration_sec") or recovery.get("total_slow_wave_sleep_sec")
            ),
            rem_sleep_duration_sec=_coerce_int(
                recovery.get("rem_sleep_duration_sec") or recovery.get("total_rem_sleep_sec")
            ),
            light_sleep_duration_sec=_coerce_int(
                recovery.get("light_sleep_duration_sec") or recovery.get("total_light_sleep_sec")
            ),
            awake_time_sec=_coerce_int(recovery.get("awake_time_sec") or recovery.get("total_awake_sec")),
            latency_sec=_coerce_int(recovery.get("latency_sec")),
            sleep_efficiency=_coerce_int(
                recovery.get("sleep_efficiency") or recovery.get("sleep_efficiency_pct")
            ),
            average_breath=_coerce_float(recovery.get("average_breath") or recovery.get("respiratory_rate")),
            active_calories=_coerce_int(recovery.get("active_calories") or recovery.get("day_calories_kcal")),
            steps=_coerce_int(recovery.get("steps")),
            total_calories=_coerce_int(recovery.get("total_calories") or recovery.get("day_calories_kcal")),
            contributors=recovery.get("contributors") or {},
            metadata={
                key: value
                for key, value in recovery.items()
                if key
                not in {
                    "provider",
                    "provider_account_id",
                    "day",
                    "recovery_date",
                    "provider_day_id",
                    "source_cycle_id",
                    "source_sleep_id",
                    "recovery_score",
                    "readiness_score",
                    "sleep_score",
                    "activity_score",
                    "resting_heart_rate",
                    "resting_hr",
                    "average_heart_rate",
                    "day_avg_hr",
                    "average_hrv",
                    "hrv_rmssd_ms",
                    "body_temperature_delta_c",
                    "skin_temp_c",
                    "body_temperature_trend_delta_c",
                    "sleep_duration_sec",
                    "time_in_bed_sec",
                    "total_in_bed_sec",
                    "deep_sleep_duration_sec",
                    "total_slow_wave_sleep_sec",
                    "rem_sleep_duration_sec",
                    "total_rem_sleep_sec",
                    "light_sleep_duration_sec",
                    "total_light_sleep_sec",
                    "awake_time_sec",
                    "total_awake_sec",
                    "latency_sec",
                    "sleep_efficiency",
                    "sleep_efficiency_pct",
                    "average_breath",
                    "respiratory_rate",
                    "active_calories",
                    "steps",
                    "total_calories",
                    "day_calories_kcal",
                    "contributors",
                }
            },
        )

    now = _now_timestamp()
    conn.execute(
        """
        INSERT INTO daily_recovery (
            provider, provider_account_id, day, provider_day_id, recovery_score, readiness_score,
            sleep_score, activity_score, resting_heart_rate, average_heart_rate, average_hrv,
            body_temperature_delta_c, body_temperature_trend_delta_c, sleep_duration_sec,
            time_in_bed_sec, deep_sleep_duration_sec, rem_sleep_duration_sec,
            light_sleep_duration_sec, awake_time_sec, latency_sec, sleep_efficiency,
            average_breath, active_calories, steps, total_calories, contributors_json,
            metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, provider_account_id, day) DO UPDATE SET
            provider_day_id = excluded.provider_day_id,
            recovery_score = excluded.recovery_score,
            readiness_score = excluded.readiness_score,
            sleep_score = excluded.sleep_score,
            activity_score = excluded.activity_score,
            resting_heart_rate = excluded.resting_heart_rate,
            average_heart_rate = excluded.average_heart_rate,
            average_hrv = excluded.average_hrv,
            body_temperature_delta_c = excluded.body_temperature_delta_c,
            body_temperature_trend_delta_c = excluded.body_temperature_trend_delta_c,
            sleep_duration_sec = excluded.sleep_duration_sec,
            time_in_bed_sec = excluded.time_in_bed_sec,
            deep_sleep_duration_sec = excluded.deep_sleep_duration_sec,
            rem_sleep_duration_sec = excluded.rem_sleep_duration_sec,
            light_sleep_duration_sec = excluded.light_sleep_duration_sec,
            awake_time_sec = excluded.awake_time_sec,
            latency_sec = excluded.latency_sec,
            sleep_efficiency = excluded.sleep_efficiency,
            average_breath = excluded.average_breath,
            active_calories = excluded.active_calories,
            steps = excluded.steps,
            total_calories = excluded.total_calories,
            contributors_json = excluded.contributors_json,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (
            normalized.provider,
            normalized.provider_account_id,
            normalized.day,
            normalized.provider_day_id,
            normalized.recovery_score,
            normalized.readiness_score,
            normalized.sleep_score,
            normalized.activity_score,
            normalized.resting_heart_rate,
            normalized.average_heart_rate,
            normalized.average_hrv,
            normalized.body_temperature_delta_c,
            normalized.body_temperature_trend_delta_c,
            normalized.sleep_duration_sec,
            normalized.time_in_bed_sec,
            normalized.deep_sleep_duration_sec,
            normalized.rem_sleep_duration_sec,
            normalized.light_sleep_duration_sec,
            normalized.awake_time_sec,
            normalized.latency_sec,
            normalized.sleep_efficiency,
            normalized.average_breath,
            normalized.active_calories,
            normalized.steps,
            normalized.total_calories,
            _json_dumps(normalized.contributors),
            _json_dumps(normalized.metadata),
            now,
            now,
        ),
    )
    conn.commit()


def upsert_normalized_batch(conn: sqlite3.Connection, batch: NormalizedBatch) -> None:
    activity_id_by_provider_activity_id: dict[tuple[str, int, str], int] = {}
    for activity in batch.activities:
        local_id = upsert_activity(conn, activity)
        activity_id_by_provider_activity_id[
            (activity.provider, activity.provider_account_id, activity.provider_activity_id)
        ] = local_id

    now = _now_timestamp()
    for sample in batch.activity_samples:
        matches = [
            local_id
            for (provider, provider_account_id, provider_activity_id), local_id in activity_id_by_provider_activity_id.items()
            if provider_activity_id == sample.provider_activity_id
        ]
        if not matches:
            row = conn.execute(
                """
                SELECT id
                FROM activities
                WHERE provider_activity_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (sample.provider_activity_id,),
            ).fetchone()
            if row is None:
                continue
            matches = [int(row["id"])]
        conn.execute(
            """
            INSERT INTO activity_samples (
                activity_id, sample_type, recorded_at, value, unit, source, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id, sample_type, recorded_at, source) DO UPDATE SET
                value = excluded.value,
                unit = excluded.unit,
                metadata_json = excluded.metadata_json
            """,
            (
                matches[0],
                sample.sample_type,
                sample.recorded_at,
                sample.value,
                sample.unit,
                sample.source,
                _json_dumps(sample.metadata),
                now,
            ),
        )

    for recovery in batch.daily_recovery:
        upsert_daily_recovery(conn, recovery)

    conn.commit()


def get_provider_data_status(conn: sqlite3.Connection) -> dict[str, dict]:
    accounts = list_provider_accounts(conn)
    sync_states = list_provider_sync_states(conn)
    activity_counts = {
        row["provider"]: int(row["count"])
        for row in conn.execute(
            """
            SELECT provider, COUNT(*) AS count
            FROM activities
            GROUP BY provider
            """
        ).fetchall()
    }
    recovery_counts = {
        row["provider"]: int(row["count"])
        for row in conn.execute(
            """
            SELECT provider, COUNT(*) AS count
            FROM daily_recovery
            GROUP BY provider
            """
        ).fetchall()
    }

    providers: dict[str, dict] = {}
    for account in accounts:
        providers[account["provider"]] = {
            "provider": account["provider"],
            "status": account["status"],
            "external_user_id": account.get("external_user_id"),
            "email": account.get("email"),
            "display_name": account.get("display_name"),
            "connected_at": account.get("connected_at"),
            "disconnected_at": account.get("disconnected_at"),
            "token_expires_at": account.get("token_expires_at"),
            "last_refreshed_at": account.get("last_refreshed_at"),
            "activities": activity_counts.get(account["provider"], 0),
            "daily_recovery_records": recovery_counts.get(account["provider"], 0),
            "sync": {},
        }

    for state in sync_states:
        provider_entry = providers.setdefault(
            state["provider"],
            {
                "provider": state["provider"],
                "status": "never_connected",
                "external_user_id": None,
                "email": None,
                "display_name": None,
                "connected_at": None,
                "disconnected_at": None,
                "token_expires_at": None,
                "last_refreshed_at": None,
                "activities": activity_counts.get(state["provider"], 0),
                "daily_recovery_records": recovery_counts.get(state["provider"], 0),
                "sync": {},
            },
        )
        provider_entry["sync"][state["resource"]] = {
            "cursor": state.get("cursor"),
            "last_sync_started_at": state.get("last_sync_started_at"),
            "last_sync_completed_at": state.get("last_sync_completed_at"),
            "last_sync_status": state.get("last_sync_status"),
            "last_error": state.get("last_error"),
        }

    return providers


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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

    onboarding_rows = conn.execute(
        """
        SELECT key, value
        FROM user_meta
        WHERE key LIKE 'onboarding_%'
        ORDER BY key ASC
        """
    ).fetchall()

    payload = {
        "total_runs": int(run_row["total_runs"] or 0) if run_row else 0,
        "latest_run_start": run_row["latest_run_start"] if run_row else None,
        "latest_run_created_at": run_row["latest_run_created_at"] if run_row else None,
        "last_sync_completed_at": get_meta(conn, "last_sync_completed_at"),
        "ae_baseline": get_meta(conn, "ae_baseline"),
        "current_vdot": get_meta(conn, "current_vdot"),
        "hr_zones_json": get_meta(conn, "hr_zones_json"),
        "onboarding_meta": {row["key"]: row["value"] for row in onboarding_rows},
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

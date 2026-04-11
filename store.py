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


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


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
        return None

    ae_values = [row["aerobic_efficiency"] for row in rows]
    # Lower AE = more efficient; take bottom N% (most efficient runs)
    cutoff = max(1, int(len(ae_values) * config.AE_BASELINE_PERCENTILE / 100))
    baseline = statistics.mean(ae_values[:cutoff])

    set_meta(conn, "ae_baseline", str(baseline))
    return baseline


def recompute_all_rei(conn: sqlite3.Connection, ae_baseline: float) -> int:
    """Recompute REI for all runs using a fresh AE baseline. Returns count updated."""
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

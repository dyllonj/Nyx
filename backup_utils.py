import csv
import datetime
import json
import sqlite3
from pathlib import Path

import config


RUN_EXPORT_COLUMNS = [
    "activity_id",
    "name",
    "start_time",
    "duration_sec",
    "distance_m",
    "calories",
    "avg_hr",
    "max_hr",
    "avg_speed_ms",
    "pace_min_per_km",
    "avg_cadence_spm",
    "avg_vertical_osc_cm",
    "avg_ground_contact_ms",
    "avg_stride_length_cm",
    "aerobic_efficiency",
    "hr_drift_pct",
    "cadence_cv",
    "rei",
    "detail_fetched",
]


def _timestamp_slug(now: datetime.datetime | None = None) -> str:
    current = now or datetime.datetime.now()
    return current.strftime("%Y%m%d-%H%M%S")


def _coerce_since(since: datetime.date | datetime.datetime | None) -> str | None:
    if since is None:
        return None
    if isinstance(since, datetime.datetime):
        return since.isoformat()
    return datetime.datetime.combine(since, datetime.time.min).isoformat()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def _laps_by_activity(conn: sqlite3.Connection, activity_ids: list[int]) -> dict[int, list[dict]]:
    if not activity_ids:
        return {}

    placeholders = ", ".join("?" for _ in activity_ids)
    rows = conn.execute(
        f"""
        SELECT activity_id, lap_index, duration_sec, distance_m, avg_hr, avg_speed_ms, avg_cadence_spm
        FROM laps
        WHERE activity_id IN ({placeholders})
        ORDER BY activity_id ASC, lap_index ASC
        """,
        tuple(activity_ids),
    ).fetchall()

    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["activity_id"]), []).append(_row_to_dict(row))
    return grouped


def fetch_export_runs(
    conn: sqlite3.Connection,
    *,
    since: datetime.date | datetime.datetime | None = None,
) -> list[dict]:
    query = "SELECT * FROM runs"
    params: list[object] = []
    since_value = _coerce_since(since)
    if since_value is not None:
        query += " WHERE start_time >= ?"
        params.append(since_value)
    query += " ORDER BY start_time DESC"

    runs = conn.execute(query, tuple(params)).fetchall()
    laps = _laps_by_activity(conn, [int(row["activity_id"]) for row in runs])

    exported = []
    for row in runs:
        payload = _row_to_dict(row)
        payload["laps"] = laps.get(int(row["activity_id"]), [])
        exported.append(payload)
    return exported


def export_runs(
    conn: sqlite3.Connection,
    *,
    format_name: str,
    output_path: str | Path | None = None,
    since: datetime.date | datetime.datetime | None = None,
    now: datetime.datetime | None = None,
) -> Path:
    timestamp = _timestamp_slug(now)
    suffix = ".json" if format_name == "json" else ".csv"
    path = Path(output_path) if output_path else Path(config.EXPORT_DIR) / f"runs-export-{timestamp}{suffix}"
    _ensure_parent(path)

    runs = fetch_export_runs(conn, since=since)
    if format_name == "json":
        payload = {
            "exported_at": (now or datetime.datetime.now()).isoformat(timespec="seconds"),
            "format": "json",
            "since": _coerce_since(since),
            "run_count": len(runs),
            "runs": runs,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    if format_name == "csv":
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=RUN_EXPORT_COLUMNS)
            writer.writeheader()
            for run in runs:
                writer.writerow({column: run.get(column) for column in RUN_EXPORT_COLUMNS})
        return path

    raise ValueError(f"Unsupported export format: {format_name}")


def snapshot_database(
    *,
    output_path: str | Path | None = None,
    now: datetime.datetime | None = None,
) -> Path:
    timestamp = _timestamp_slug(now)
    path = Path(output_path) if output_path else Path(config.BACKUP_DIR) / f"nyx-backup-{timestamp}.db"
    _ensure_parent(path)

    source = sqlite3.connect(config.DB_PATH)
    destination = sqlite3.connect(path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return path


def prune_backups(directory: str | Path, *, keep: int) -> list[Path]:
    backup_dir = Path(directory)
    if keep <= 0 or not backup_dir.exists():
        return []

    backups = sorted(
        [path for path in backup_dir.glob("nyx-backup-*.db") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed: list[Path] = []
    for stale in backups[keep:]:
        stale.unlink(missing_ok=True)
        removed.append(stale)
    return removed


def auto_backup_db() -> Path | None:
    if not config.AUTO_BACKUP_ON_SYNC:
        return None

    path = snapshot_database()
    prune_backups(config.BACKUP_DIR, keep=config.BACKUP_RETENTION_COUNT)
    return path

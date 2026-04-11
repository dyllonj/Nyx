import csv
import datetime
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import backup_utils
import config
import store
from models import RunSummary


def make_run(activity_id: int, start_day: int) -> RunSummary:
    return RunSummary(
        activity_id=activity_id,
        name=f"Run {activity_id}",
        start_time=datetime.datetime(2026, 4, start_day, 7, 0, 0),
        duration_sec=3600.0,
        distance_m=10000.0,
        calories=700,
        avg_hr=150.0,
        max_hr=180.0,
        avg_speed_ms=2.8,
        pace_min_per_km=6.0,
        avg_cadence_spm=170.0,
        avg_vertical_osc_cm=8.0,
        avg_ground_contact_ms=240.0,
        avg_stride_length_cm=110.0,
    )


class BackupUtilsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.original_db_path = config.DB_PATH
        self.original_export_dir = config.EXPORT_DIR
        self.original_backup_dir = config.BACKUP_DIR
        self.original_auto_backup = config.AUTO_BACKUP_ON_SYNC
        self.original_retention = config.BACKUP_RETENTION_COUNT

        config.DB_PATH = str(base / "test_garmin_data.db")
        config.EXPORT_DIR = str(base / "exports")
        config.BACKUP_DIR = str(base / "backups")
        config.AUTO_BACKUP_ON_SYNC = True
        config.BACKUP_RETENTION_COUNT = 2

    def tearDown(self) -> None:
        config.DB_PATH = self.original_db_path
        config.EXPORT_DIR = self.original_export_dir
        config.BACKUP_DIR = self.original_backup_dir
        config.AUTO_BACKUP_ON_SYNC = self.original_auto_backup
        config.BACKUP_RETENTION_COUNT = self.original_retention
        self.temp_dir.cleanup()

    def test_export_runs_writes_json_with_laps(self) -> None:
        conn = store.open_db()
        try:
            store.upsert_run(conn, make_run(1, 1), detail_fetched=True)
            store.upsert_laps(conn, 1, [{"duration": 300, "distance": 1000, "averageHR": 145, "averageSpeed": 3.0, "averageCadence": 170}])
            path = backup_utils.export_runs(conn, format_name="json")
        finally:
            conn.close()

        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["run_count"], 1)
        self.assertEqual(payload["runs"][0]["activity_id"], 1)
        self.assertEqual(len(payload["runs"][0]["laps"]), 1)

    def test_export_runs_writes_csv_summary(self) -> None:
        conn = store.open_db()
        try:
            store.upsert_run(conn, make_run(2, 2), detail_fetched=True)
            path = backup_utils.export_runs(conn, format_name="csv")
        finally:
            conn.close()

        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["activity_id"], "2")

    def test_snapshot_database_copies_sqlite_file(self) -> None:
        conn = store.open_db()
        try:
            store.upsert_run(conn, make_run(3, 3), detail_fetched=True)
        finally:
            conn.close()

        backup_path = backup_utils.snapshot_database()
        backup_conn = sqlite3.connect(backup_path)
        try:
            count = backup_conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        finally:
            backup_conn.close()
        self.assertEqual(count, 1)

    def test_prune_backups_keeps_most_recent_files(self) -> None:
        backup_dir = Path(config.BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stale = []
        for i in range(3):
            path = backup_dir / f"nyx-backup-20260411-00000{i}.db"
            path.write_text("db", encoding="utf-8")
            stale.append(path)
        removed = backup_utils.prune_backups(backup_dir, keep=2)
        self.assertEqual(len(removed), 1)
        self.assertFalse(removed[0].exists())


if __name__ == "__main__":
    unittest.main()

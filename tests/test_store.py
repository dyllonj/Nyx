import datetime
import tempfile
import unittest
from pathlib import Path

import config
import store
from models import RunSummary


def make_run(activity_id: int, *, avg_hr: float, pace_min_per_km: float, start_day: int) -> RunSummary:
    aerobic_efficiency = pace_min_per_km / avg_hr
    return RunSummary(
        activity_id=activity_id,
        name=f"Run {activity_id}",
        start_time=datetime.datetime(2026, 4, start_day, 7, 0, 0),
        duration_sec=3600.0,
        distance_m=10000.0,
        calories=700,
        avg_hr=avg_hr,
        max_hr=180.0,
        avg_speed_ms=1000.0 / (pace_min_per_km * 60.0),
        pace_min_per_km=pace_min_per_km,
        avg_cadence_spm=170.0,
        avg_vertical_osc_cm=8.0,
        avg_ground_contact_ms=240.0,
        avg_stride_length_cm=110.0,
        aerobic_efficiency=aerobic_efficiency,
    )


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = str(Path(self.temp_dir.name) / "test_garmin_data.db")

    def tearDown(self) -> None:
        config.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_open_db_applies_schema_and_roundtrips_runs(self) -> None:
        conn = store.open_db()
        try:
            self.assertEqual(store.get_schema_version(conn), store.SCHEMA_VERSION)

            run = make_run(101, avg_hr=150.0, pace_min_per_km=6.0, start_day=1)
            store.upsert_run(conn, run, detail_fetched=True)

            stored = store.get_run(conn, 101)
            self.assertIsNotNone(stored)
            self.assertEqual(stored["activity_id"], 101)
            self.assertEqual(stored["detail_fetched"], 1)
            self.assertEqual(store.get_runs_without_details(conn), [])
        finally:
            conn.close()

    def test_compute_and_store_ae_baseline_sets_meta_and_recomputes_rei(self) -> None:
        conn = store.open_db()
        try:
            store.upsert_run(conn, make_run(201, avg_hr=150.0, pace_min_per_km=6.0, start_day=2))
            store.upsert_run(conn, make_run(202, avg_hr=148.0, pace_min_per_km=5.8, start_day=3))

            baseline = store.compute_and_store_ae_baseline(conn)
            updated = store.recompute_all_rei(conn, baseline)

            self.assertIsNotNone(baseline)
            self.assertGreater(baseline or 0.0, 0.0)
            self.assertEqual(updated, 2)
            self.assertEqual(store.get_meta(conn, "ae_baseline"), str(baseline))

            rows = store.get_all_runs(conn)
            self.assertTrue(all(row["rei"] is not None for row in rows))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

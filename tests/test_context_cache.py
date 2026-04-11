import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import coach
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
    )


class ContextCacheTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = str(Path(self.temp_dir.name) / "test_garmin_data.db")
        coach._cached_base_system_blocks = None
        coach._cached_context_hash = None

    def tearDown(self) -> None:
        config.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()
        coach._cached_base_system_blocks = None
        coach._cached_context_hash = None

    def test_context_hash_changes_when_training_metadata_changes(self) -> None:
        conn = store.open_db()
        try:
            store.upsert_run(conn, make_run(1, 1))
            initial_hash = store.get_context_hash(conn)
            store.set_meta(conn, "current_vdot", "51.2")
            updated_hash = store.get_context_hash(conn)
        finally:
            conn.close()

        self.assertNotEqual(initial_hash, updated_hash)

    def test_context_hash_changes_when_onboarding_answers_change(self) -> None:
        conn = store.open_db()
        try:
            store.upsert_run(conn, make_run(1, 1))
            initial_hash = store.get_context_hash(conn)
            store.set_meta(conn, "onboarding_injury", "Left knee pain on long runs.")
            updated_hash = store.get_context_hash(conn)
        finally:
            conn.close()

        self.assertNotEqual(initial_hash, updated_hash)

    def test_build_base_system_blocks_reuses_cache_until_hash_changes(self) -> None:
        conn = store.open_db()
        try:
            store.upsert_run(conn, make_run(1, 1))
            with (
                mock.patch.object(coach.onboarding, "build_profile_context", return_value="PROFILE"),
                mock.patch.object(coach, "build_data_context", return_value="DATA") as build_data_context,
            ):
                coach.build_base_system_blocks(conn)
                coach.build_base_system_blocks(conn)
                self.assertEqual(build_data_context.call_count, 1)

                store.set_meta(conn, "current_vdot", "52.0")
                coach.build_base_system_blocks(conn)
                self.assertEqual(build_data_context.call_count, 2)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

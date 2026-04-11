import datetime
import tempfile
import unittest
from pathlib import Path

import config
import store
import training_plans
from models import RunSummary


def make_run(activity_id: int, start_time: datetime.datetime, distance_m: float = 10000.0) -> RunSummary:
    return RunSummary(
        activity_id=activity_id,
        name=f"Run {activity_id}",
        start_time=start_time,
        duration_sec=3600.0,
        distance_m=distance_m,
        calories=700,
        avg_hr=150.0,
        max_hr=180.0,
        avg_speed_ms=2.8,
        pace_min_per_km=6.0,
    )


class TrainingPlanTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = str(Path(self.temp_dir.name) / "test_garmin_data.db")

    def tearDown(self) -> None:
        config.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_generate_plan_returns_requested_week_count(self) -> None:
        plan = training_plans.generate_plan(
            goal="half marathon",
            weeks=8,
            days_per_week=4,
            current_vdot=50.0,
            recent_42d_distance_km=180.0,
        )

        self.assertEqual(plan.weeks, 8)
        self.assertEqual(len(plan.weeks_detail), 8)
        self.assertEqual(plan.weeks_detail[-1].phase, "race")

    def test_build_plan_from_db_uses_recent_load_and_stored_vdot(self) -> None:
        conn = store.open_db()
        try:
            now = datetime.datetime.now()
            store.upsert_run(conn, make_run(1, now - datetime.timedelta(days=7), 12000.0), detail_fetched=True)
            store.upsert_run(conn, make_run(2, now - datetime.timedelta(days=20), 8000.0), detail_fetched=True)
            store.set_meta(conn, "current_vdot", "51.5")
            plan = training_plans.build_plan_from_db(conn, goal="10k", weeks=6, days_per_week=5)
        finally:
            conn.close()

        self.assertEqual(plan.current_vdot, 51.5)
        self.assertGreater(plan.recent_42d_distance_km, 0.0)
        self.assertEqual(plan.days_per_week, 5)


if __name__ == "__main__":
    unittest.main()

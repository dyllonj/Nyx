import datetime
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
import server
import store
from errors import HarnessError
from models import RunSummary


def make_run(activity_id: int) -> RunSummary:
    return RunSummary(
        activity_id=activity_id,
        name=f"Run {activity_id}",
        start_time=datetime.datetime(2026, 4, 11, 7, 0, 0),
        duration_sec=3600.0,
        distance_m=10000.0,
        calories=700,
        avg_hr=150.0,
        max_hr=180.0,
        avg_speed_ms=2.8,
        pace_min_per_km=6.0,
    )


class ServerAsyncTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = str(Path(self.temp_dir.name) / "test_garmin_data.db")

    def tearDown(self) -> None:
        config.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def test_run_db_async_executes_callback_with_managed_connection(self) -> None:
        schema_version = await server._run_db_async(store.get_schema_version)

        self.assertEqual(schema_version, store.SCHEMA_VERSION)

    async def test_status_endpoint_is_async_and_serves_status_payload(self) -> None:
        self.assertTrue(inspect.iscoroutinefunction(server.get_status))

        payload = await server.get_status()

        self.assertEqual(payload["schema_version"], store.SCHEMA_VERSION)
        self.assertEqual(payload["last_sync_status"], "never")
        self.assertEqual(payload["meta"]["source"], "local_db")
        self.assertTrue(payload["meta"]["cached"])

    async def test_training_plan_endpoint_uses_local_data(self) -> None:
        conn = store.open_db()
        try:
            store.set_meta(conn, "current_vdot", "50.0")
        finally:
            conn.close()

        payload = await server.create_training_plan(
            server.TrainingPlanRequest(goal="10k", weeks=4, days_per_week=4)
        )

        self.assertEqual(payload["plan"]["goal"], "10k")
        self.assertEqual(len(payload["plan"]["weeks_detail"]), 4)
        self.assertEqual(payload["meta"]["source"], "local_db")

    async def test_onboarding_endpoints_roundtrip_state(self) -> None:
        initial = await server.get_onboarding()
        self.assertFalse(initial["completed"])

        saved = await server.update_onboarding(
            server.OnboardingUpdateRequest(
                answers={"onboarding_goal": "Run a strong 10K"},
                current_step=1,
            )
        )
        self.assertEqual(saved["answers"]["onboarding_goal"], "Run a strong 10K")
        self.assertEqual(saved["current_step"], 1)

        completed = await server.complete_onboarding()
        self.assertTrue(completed["completed"])
        self.assertIsNotNone(completed["profile_context"])

        reset = await server.reset_onboarding()
        self.assertFalse(reset["completed"])
        self.assertEqual("", reset["answers"]["onboarding_goal"])

    async def test_coach_message_requires_completed_onboarding(self) -> None:
        with self.assertRaisesRegex(HarnessError, "Complete onboarding before starting a coaching conversation"):
            await server.post_coach_message(server.CoachMessageRequest(message="What should I do this week?"))

    async def test_athlete_summary_next_action_prefers_onboarding_when_runs_are_present(self) -> None:
        conn = store.open_db()
        try:
            store.upsert_run(conn, make_run(1), detail_fetched=True)
            store.set_meta(conn, "last_sync_status", "success")
            store.set_meta(conn, "last_sync_completed_at", "2026-04-11T07:00:00")
        finally:
            conn.close()

        with mock.patch.object(server.health, "run_doctor", return_value=[]):
            payload = await server.get_athlete_summary()

        self.assertEqual(payload["next_action"]["action"], "onboarding")


if __name__ == "__main__":
    unittest.main()

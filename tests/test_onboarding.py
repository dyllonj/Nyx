import tempfile
import unittest
from pathlib import Path

import config
import onboarding
import store


class OnboardingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = str(Path(self.temp_dir.name) / "test_garmin_data.db")

    def tearDown(self) -> None:
        config.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_partial_save_persists_progress_without_completion(self) -> None:
        conn = store.open_db()
        try:
            state = onboarding.save_onboarding_answers(
                conn,
                {"onboarding_goal": "Run a sub-20 5K"},
                current_step=2,
            )
        finally:
            conn.close()

        self.assertFalse(state["completed"])
        self.assertEqual(state["current_step"], 2)
        self.assertEqual(state["answers"]["onboarding_goal"], "Run a sub-20 5K")

    def test_complete_sets_red_flags_and_profile_context(self) -> None:
        conn = store.open_db()
        try:
            onboarding.save_onboarding_answers(
                conn,
                {
                    "onboarding_goal": "Run a healthy fall half marathon",
                    "onboarding_injury": "My ankle still has pain after long runs.",
                },
                current_step=4,
            )
            state = onboarding.complete_onboarding(conn)
            completed_flag = store.get_meta(conn, "onboarding_completed")
        finally:
            conn.close()

        self.assertTrue(state["completed"])
        self.assertEqual("1", completed_flag)
        self.assertIn("rf_current_pain", state["active_red_flags"])
        self.assertIsNotNone(state["profile_context"])
        self.assertIn("healthy fall half marathon", state["profile_context"])

    def test_reset_clears_answers_progress_and_profile_context(self) -> None:
        conn = store.open_db()
        try:
            onboarding.save_onboarding_answers(
                conn,
                {"onboarding_goal": "Break 40 in the 10K"},
                current_step=1,
            )
            onboarding.complete_onboarding(conn)
            onboarding.reset_onboarding(conn)
            state = onboarding.get_onboarding_state(conn)
            profile = onboarding.build_profile_context(conn)
            started_at = store.get_meta(conn, "onboarding_started_at")
        finally:
            conn.close()

        self.assertFalse(state["completed"])
        self.assertEqual("", state["answers"]["onboarding_goal"])
        self.assertEqual([], state["active_red_flags"])
        self.assertIsNone(started_at)
        self.assertIsNone(profile)


if __name__ == "__main__":
    unittest.main()

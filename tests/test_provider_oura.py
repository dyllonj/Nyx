import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from providers.base import ProviderPage, ProviderRawData
from providers import oura_normalize
import server
import store


class OuraProviderServerTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = str(Path(self.temp_dir.name) / "test_provider_oura.db")
        self.env_patcher = mock.patch.dict(
            os.environ,
            {
                "OURA_CLIENT_ID": "oura-client-id",
                "OURA_CLIENT_SECRET": "oura-client-secret",
            },
            clear=False,
        )
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()
        config.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def test_connect_oura_returns_authorization_url(self) -> None:
        payload = await server.connect_oura(
            server.OuraConnectRequest(redirect_uri="http://localhost:8765/api/providers/oura/callback")
        )

        self.assertEqual(payload["provider"], "oura")
        self.assertEqual(payload["status"], "authorization_required")
        self.assertIn("cloud.ouraring.com/oauth/authorize", payload["authorization_url"])
        self.assertTrue(payload["state"])
        self.assertEqual(payload["scopes"], list(config.OURA_DEFAULT_SCOPES))

        conn = store.open_db()
        try:
            raw_state = store.get_meta(conn, "oura_oauth_state")
        finally:
            conn.close()

        self.assertIsNotNone(raw_state)
        self.assertIn(payload["state"], raw_state or "")

    async def test_connect_oura_with_code_persists_account(self) -> None:
        init_payload = await server.connect_oura(
            server.OuraConnectRequest(redirect_uri="http://localhost:8765/api/providers/oura/callback")
        )

        token_payload = {
            "access_token": "oura-access-token",
            "refresh_token": "oura-refresh-token",
            "token_type": "bearer",
            "expires_at": "2026-04-12T15:00:00+00:00",
            "scopes": ["daily", "workout", "personal"],
        }
        personal_info = {
            "id": "oura-user-1",
            "email": "athlete@example.com",
            "age": 35,
            "weight": 72.5,
        }

        with (
            mock.patch("providers.oura.oura_auth.exchange_code_for_token", return_value=token_payload),
            mock.patch("providers.oura.oura_fetch.OuraApiClient.get_personal_info", return_value=personal_info),
        ):
            payload = await server.connect_oura(
                server.OuraConnectRequest(
                    redirect_uri="http://localhost:8765/api/providers/oura/callback",
                    code="oauth-code",
                    state=init_payload["state"],
                )
            )

        self.assertEqual(payload["status"], "connected")
        self.assertEqual(payload["account"]["provider"], "oura")
        self.assertEqual(payload["account"]["external_user_id"], "oura-user-1")
        self.assertEqual(payload["account"]["email"], "athlete@example.com")

        conn = store.open_db()
        try:
            account = store.get_provider_account(conn, "oura")
        finally:
            conn.close()

        self.assertIsNotNone(account)
        self.assertEqual(account["provider_user_id"], "oura-user-1")
        self.assertEqual(account["display_name"], "athlete@example.com")
        self.assertEqual(account["scopes"], ["daily", "personal", "workout"])

    async def test_sync_oura_persists_raw_and_normalized_records(self) -> None:
        conn = store.open_db()
        try:
            account = store.upsert_provider_account(
                conn,
                provider="oura",
                provider_user_id="oura-user-1",
                display_name="athlete@example.com",
                scopes=["daily", "workout", "personal"],
                access_token="oura-access-token",
                refresh_token="oura-refresh-token",
                token_type="bearer",
                token_expires_at=None,
                status="connected",
                account_metadata={"email": "athlete@example.com"},
            )
        finally:
            conn.close()

        workout_page = ProviderPage(
            resource="workout",
            items=[
                {
                    "id": "workout-1",
                    "activity": "running",
                    "day": "2026-04-10",
                    "start_datetime": "2026-04-10T07:00:00+00:00",
                    "end_datetime": "2026-04-10T07:45:00+00:00",
                    "intensity": "moderate",
                    "source": "manual",
                    "distance": 10000.0,
                    "calories": 650.0,
                    "label": "Morning Run",
                }
            ],
        )
        daily_activity_page = ProviderPage(
            resource="daily_activity",
            items=[
                {
                    "id": "daily-activity-1",
                    "day": "2026-04-10",
                    "score": 79,
                    "active_calories": 500,
                    "steps": 12000,
                    "total_calories": 2400,
                    "target_calories": 600,
                    "target_meters": 9000,
                    "meters_to_target": 0,
                    "non_wear_time": 0,
                    "resting_time": 24000,
                    "inactivity_alerts": 1,
                    "contributors": {"stay_active": 81},
                }
            ],
        )
        daily_sleep_page = ProviderPage(
            resource="daily_sleep",
            items=[
                {
                    "id": "daily-sleep-1",
                    "day": "2026-04-10",
                    "score": 83,
                    "contributors": {"total_sleep": 86},
                }
            ],
        )
        daily_readiness_page = ProviderPage(
            resource="daily_readiness",
            items=[
                {
                    "id": "daily-readiness-1",
                    "day": "2026-04-10",
                    "score": 87,
                    "temperature_deviation": -0.2,
                    "temperature_trend_deviation": 0.1,
                    "contributors": {"previous_night": 91},
                }
            ],
        )
        sleep_page = ProviderPage(
            resource="sleep",
            items=[
                {
                    "id": "sleep-1",
                    "day": "2026-04-10",
                    "bedtime_start": "2026-04-09T23:00:00+00:00",
                    "bedtime_end": "2026-04-10T07:00:00+00:00",
                    "time_in_bed": 28800,
                    "total_sleep_duration": 25200,
                    "deep_sleep_duration": 3600,
                    "rem_sleep_duration": 5400,
                    "light_sleep_duration": 16200,
                    "awake_time": 1800,
                    "latency": 600,
                    "efficiency": 88,
                    "average_heart_rate": 52.5,
                    "average_hrv": 64,
                    "lowest_heart_rate": 47,
                    "average_breath": 13.2,
                    "readiness": {"score": 86},
                    "type": "long_sleep",
                    "readiness_score_delta": 2,
                    "sleep_score_delta": 1,
                }
            ],
        )

        with (
            mock.patch("providers.oura.oura_fetch.OuraApiClient.list_workouts", return_value=workout_page),
            mock.patch("providers.oura.oura_fetch.OuraApiClient.list_daily_activity", return_value=daily_activity_page),
            mock.patch("providers.oura.oura_fetch.OuraApiClient.list_daily_sleep", return_value=daily_sleep_page),
            mock.patch("providers.oura.oura_fetch.OuraApiClient.list_daily_readiness", return_value=daily_readiness_page),
            mock.patch("providers.oura.oura_fetch.OuraApiClient.list_sleep", return_value=sleep_page),
        ):
            payload = await server.sync_oura(server.OuraSyncRequest())

        self.assertEqual(payload["provider"], "oura")
        self.assertEqual(payload["normalized"]["activities"], 1)
        self.assertEqual(payload["normalized"]["daily_recovery"], 1)
        self.assertEqual(payload["resource_counts"]["workout"], 1)

        conn = store.open_db()
        try:
            activity_count = conn.execute("SELECT COUNT(*) AS count FROM activities").fetchone()["count"]
            recovery_count = conn.execute("SELECT COUNT(*) AS count FROM daily_recovery").fetchone()["count"]
            raw_workout_count = conn.execute("SELECT COUNT(*) AS count FROM oura_raw_workouts").fetchone()["count"]
            sync_state = store.get_provider_sync_state(conn, int(account["id"]), "workout")
        finally:
            conn.close()

        self.assertEqual(activity_count, 1)
        self.assertEqual(recovery_count, 1)
        self.assertEqual(raw_workout_count, 1)
        self.assertIsNotNone(sync_state)
        self.assertEqual(sync_state["last_sync_status"], "success")


class OuraNormalizeTestCase(unittest.TestCase):
    def test_normalize_payloads_chooses_primary_sleep_and_maps_scores(self) -> None:
        raw = ProviderRawData(
            activity_summaries=[
                {
                    "id": "workout-1",
                    "activity": "running",
                    "day": "2026-04-10",
                    "start_datetime": "2026-04-10T07:00:00+00:00",
                    "end_datetime": "2026-04-10T07:35:00+00:00",
                    "distance": 8000.0,
                    "calories": 520.0,
                    "intensity": "moderate",
                    "source": "manual",
                }
            ],
            daily_health={
                "daily_activity": [{"id": "a1", "day": "2026-04-10", "score": 76, "active_calories": 450, "steps": 11000, "total_calories": 2200, "contributors": {"stay_active": 80}}],
                "daily_sleep": [{"id": "s1", "day": "2026-04-10", "score": 81, "contributors": {"total_sleep": 84}}],
                "daily_readiness": [{"id": "r1", "day": "2026-04-10", "score": 88, "temperature_deviation": -0.1, "temperature_trend_deviation": 0.2, "contributors": {"previous_night": 90}}],
                "sleep": [
                    {
                        "id": "sleep-short",
                        "day": "2026-04-10",
                        "time_in_bed": 1800,
                        "total_sleep_duration": 1200,
                        "average_hrv": 40,
                    },
                    {
                        "id": "sleep-primary",
                        "day": "2026-04-10",
                        "time_in_bed": 28800,
                        "total_sleep_duration": 25200,
                        "deep_sleep_duration": 3600,
                        "rem_sleep_duration": 5400,
                        "light_sleep_duration": 16200,
                        "awake_time": 1800,
                        "latency": 600,
                        "efficiency": 88,
                        "average_heart_rate": 51.5,
                        "average_hrv": 67,
                        "lowest_heart_rate": 46,
                        "average_breath": 12.8,
                        "readiness": {"score": 87},
                    },
                ],
            },
        )

        batch = oura_normalize.normalize_payloads(account_id=42, raw=raw)

        self.assertEqual(len(batch.activities), 1)
        self.assertEqual(len(batch.daily_recovery), 1)
        self.assertEqual(batch.activities[0].provider_activity_id, "workout-1")
        self.assertEqual(batch.daily_recovery[0].provider_day_id, "r1")
        self.assertEqual(batch.daily_recovery[0].recovery_score, 88)
        self.assertEqual(batch.daily_recovery[0].average_hrv, 67.0)
        self.assertEqual(batch.daily_recovery[0].sleep_duration_sec, 25200)


if __name__ == "__main__":
    unittest.main()

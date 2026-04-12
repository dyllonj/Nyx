import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
import server
import store


def make_connected_account(conn) -> None:
    store.connect_provider_account(
        conn,
        provider="whoop",
        external_user_id="123",
        email="athlete@example.com",
        display_name="Nyx Runner",
        access_token="access-token",
        refresh_token="refresh-token",
        token_type="Bearer",
        scopes=[
            "offline",
            "read:profile",
            "read:cycles",
            "read:sleep",
            "read:recovery",
            "read:workout",
        ],
        token_expires_at="2026-04-12T12:00:00+00:00",
        refresh_token_expires_at=None,
        profile={"user_id": 123},
    )


def make_workout_payload() -> dict:
    return {
        "id": "workout-1",
        "user_id": 123,
        "sport_name": "running",
        "score_state": "SCORED",
        "start": "2026-04-10T10:00:00+00:00",
        "end": "2026-04-10T11:00:00+00:00",
        "timezone_offset": "-04:00",
        "updated_at": "2026-04-10T11:05:00+00:00",
        "score": {
            "strain": 12.3,
            "average_heart_rate": 150,
            "max_heart_rate": 178,
            "kilojoule": 2300,
            "percent_recorded": 100,
            "distance_meter": 10000,
            "altitude_gain_meter": 120,
            "altitude_change_meter": 15,
            "zone_durations": {
                "zone_zero_milli": 1000,
                "zone_one_milli": 2000,
                "zone_two_milli": 3000,
                "zone_three_milli": 4000,
                "zone_four_milli": 5000,
                "zone_five_milli": 6000,
            },
        },
    }


def make_cycle_payload() -> dict:
    return {
        "id": 9001,
        "user_id": 123,
        "start": "2026-04-10T04:00:00+00:00",
        "end": "2026-04-11T04:00:00+00:00",
        "timezone_offset": "-04:00",
        "score_state": "SCORED",
        "updated_at": "2026-04-11T05:00:00+00:00",
        "score": {
            "strain": 9.1,
            "kilojoule": 1800,
            "average_heart_rate": 72,
            "max_heart_rate": 165,
        },
    }


def make_sleep_payload() -> dict:
    return {
        "id": "sleep-1",
        "user_id": 123,
        "cycle_id": 9001,
        "start": "2026-04-10T22:00:00+00:00",
        "end": "2026-04-11T05:30:00+00:00",
        "timezone_offset": "-04:00",
        "score_state": "SCORED",
        "updated_at": "2026-04-11T05:31:00+00:00",
        "score": {
            "respiratory_rate": 14.5,
            "sleep_performance_percentage": 92,
            "sleep_consistency_percentage": 88,
            "sleep_efficiency_percentage": 90,
            "sleep_needed": {
                "baseline_milli": 27000000,
                "need_from_sleep_debt_milli": 0,
                "need_from_recent_strain_milli": 1800000,
                "need_from_recent_nap_milli": 0,
            },
            "stage_summary": {
                "total_in_bed_time_milli": 27600000,
                "total_awake_time_milli": 1200000,
                "total_no_data_time_milli": 0,
                "total_light_sleep_time_milli": 14400000,
                "total_slow_wave_sleep_time_milli": 5400000,
                "total_rem_sleep_time_milli": 6600000,
                "sleep_cycle_count": 5,
                "disturbance_count": 1,
            },
        },
    }


def make_recovery_payload() -> dict:
    return {
        "cycle_id": 9001,
        "sleep_id": "sleep-1",
        "user_id": 123,
        "score_state": "SCORED",
        "updated_at": "2026-04-11T05:35:00+00:00",
        "score": {
            "recovery_score": 68,
            "resting_heart_rate": 49,
            "hrv_rmssd_milli": 82,
            "spo2_percentage": 97.3,
            "skin_temp_celsius": 0.2,
        },
    }


class WhoopProviderTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = str(Path(self.temp_dir.name) / "test_garmin_data.db")

    def tearDown(self) -> None:
        config.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def test_connect_whoop_returns_authorization_url_and_persists_state(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"WHOOP_CLIENT_ID": "client-123", "WHOOP_CLIENT_SECRET": "secret-123"},
            clear=False,
        ):
            payload = await server.connect_whoop(
                server.WhoopConnectRequest(redirect_uri="https://example.com/callback")
            )

        self.assertEqual(payload["status"], "authorization_required")
        self.assertIn("client_id=client-123", payload["authorization_url"])
        self.assertEqual(
            payload["state"],
            server._with_db(lambda conn: store.get_provider_oauth_state(conn, "whoop")),
        )

    async def test_connect_whoop_exchanges_code_and_persists_account(self) -> None:
        async def run_db_inline(callback):
            return server._with_db(callback)

        async def run_blocking_inline(callback):
            return callback()

        token_payload = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "Bearer",
            "scope_list": ["offline", "read:profile", "read:recovery", "read:sleep", "read:workout"],
            "token_expires_at": "2026-04-12T12:00:00+00:00",
        }
        profile = {
            "user_id": 123,
            "email": "athlete@example.com",
            "first_name": "Nyx",
            "last_name": "Runner",
        }
        body_measurements = {
            "height_meter": 1.78,
            "weight_kilogram": 70.0,
            "max_heart_rate": 190,
        }
        server._with_db(lambda conn: store.set_provider_oauth_state(conn, "whoop", "state-123"))

        with (
            mock.patch.object(server, "_run_db_async", side_effect=run_db_inline),
            mock.patch.object(server, "_run_blocking_async", side_effect=run_blocking_inline),
            mock.patch.object(server.whoop_auth, "exchange_code_for_tokens", return_value=token_payload),
            mock.patch.object(server.whoop_fetch.WhoopApiClient, "get_basic_profile", return_value=profile),
            mock.patch.object(
                server.whoop_fetch.WhoopApiClient,
                "get_body_measurements",
                return_value=body_measurements,
            ),
        ):
            payload = await server.connect_whoop(
                server.WhoopConnectRequest(
                    redirect_uri="https://example.com/callback",
                    code="auth-code",
                    state="state-123",
                )
            )

        self.assertEqual(payload["status"], "connected")
        account = server._with_db(lambda conn: store.get_provider_account(conn, "whoop"))
        self.assertIsNotNone(account)
        self.assertEqual(account["email"], "athlete@example.com")
        self.assertEqual(account["status"], "connected")
        self.assertIsNone(server._with_db(lambda conn: store.get_provider_oauth_state(conn, "whoop")))

    async def test_disconnect_whoop_clears_local_connection(self) -> None:
        server._with_db(make_connected_account)

        payload = await server.disconnect_whoop(server.WhoopDisconnectRequest(revoke_remote=False))

        self.assertEqual(payload["status"], "disconnected")
        account = server._with_db(lambda conn: store.get_provider_account(conn, "whoop"))
        self.assertIsNotNone(account)
        self.assertEqual(account["status"], "disconnected")
        self.assertIsNone(account["access_token"])

    async def test_sync_whoop_persists_job_before_background_thread_runs(self) -> None:
        server._with_db(make_connected_account)
        fake_thread = mock.Mock()

        async def run_db_inline(callback):
            return server._with_db(callback)

        with (
            mock.patch.object(server, "_run_db_async", side_effect=run_db_inline),
            mock.patch.object(server.threading, "Thread", return_value=fake_thread) as thread_ctor,
        ):
            payload = await server.sync_whoop(server.WhoopSyncRequest())

        self.assertEqual(payload["status"], "queued")
        fake_thread.start.assert_called_once()
        thread_ctor.assert_called_once()
        persisted = await server.get_sync_job(payload["job_id"])
        self.assertEqual(persisted["job_id"], payload["job_id"])

    async def test_sync_whoop_stores_canonical_activity_and_recovery_rows(self) -> None:
        server._with_db(make_connected_account)
        fake_client = mock.Mock()
        fake_client.list_workouts.return_value = [make_workout_payload()]
        fake_client.list_cycles.return_value = [make_cycle_payload()]
        fake_client.list_sleeps.return_value = [make_sleep_payload()]
        fake_client.list_recoveries.return_value = [make_recovery_payload()]

        with mock.patch.object(server.whoop_fetch, "WhoopApiClient", return_value=fake_client):
            summary = server._with_db(
                lambda conn: server._sync_whoop(
                    conn,
                    log=lambda _: None,
                    start="2026-04-10T00:00:00+00:00",
                    end="2026-04-12T00:00:00+00:00",
                    full_refresh=False,
                )
            )

        self.assertEqual(summary["activities_upserted"], 1)
        self.assertEqual(summary["daily_recovery_upserted"], 1)

        conn = store.open_db()
        try:
            activity = conn.execute("SELECT * FROM activities WHERE provider = 'whoop'").fetchone()
            recovery = conn.execute("SELECT * FROM daily_recovery WHERE provider = 'whoop'").fetchone()
            samples = conn.execute(
                """
                SELECT COUNT(*)
                FROM activity_samples AS samples
                JOIN activities AS activities ON activities.id = samples.activity_id
                WHERE activities.provider = 'whoop'
                """
            ).fetchone()[0]
            status = store.get_provider_data_status(conn)["whoop"]
        finally:
            conn.close()

        self.assertIsNotNone(activity)
        self.assertEqual(activity["activity_type"], "run")
        self.assertIsNotNone(recovery)
        self.assertEqual(samples, 6)
        self.assertEqual(status["activities"], 1)
        self.assertEqual(status["daily_recovery_records"], 1)
        self.assertEqual(status["sync"]["workout"]["last_sync_status"], "success")


if __name__ == "__main__":
    unittest.main()

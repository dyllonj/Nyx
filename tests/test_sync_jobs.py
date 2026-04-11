import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
import server
import store


class SyncJobStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = str(Path(self.temp_dir.name) / "test_garmin_data.db")

    def tearDown(self) -> None:
        config.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_sync_job_state_persists_across_connections(self) -> None:
        conn = store.open_db()
        try:
            store.create_sync_job(conn, "job-1")
            store.mark_sync_job_running(conn, "job-1")
            store.append_sync_job_log(conn, "job-1", "Started sync.")
            store.complete_sync_job(conn, "job-1", {"new_runs": 3})
        finally:
            conn.close()

        conn = store.open_db()
        try:
            job = store.get_sync_job_state(conn, "job-1")
        finally:
            conn.close()

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "success")
        self.assertEqual(job["logs"], ["Started sync."])
        self.assertEqual(job["summary"], {"new_runs": 3})
        self.assertIsNone(job["error"])


class SyncJobServerTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = config.DB_PATH
        config.DB_PATH = str(Path(self.temp_dir.name) / "test_garmin_data.db")

    def tearDown(self) -> None:
        config.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def test_start_sync_persists_job_before_background_thread_runs(self) -> None:
        fake_thread = mock.Mock()
        async def run_db_inline(callback):
            return server._with_db(callback)

        with (
            mock.patch.object(server, "_run_db_async", side_effect=run_db_inline),
            mock.patch.object(server.threading, "Thread", return_value=fake_thread) as thread_ctor,
        ):
            payload = await server.start_sync(server.SyncStartRequest(interactive=False))

        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["logs"], [])
        fake_thread.start.assert_called_once()
        thread_ctor.assert_called_once()

        persisted = await server.get_sync_job(payload["job_id"])
        self.assertEqual(persisted["job_id"], payload["job_id"])
        self.assertEqual(persisted["status"], "queued")

    async def test_get_sync_job_raises_for_unknown_job(self) -> None:
        with self.assertRaises(server.HTTPException) as ctx:
            await server.get_sync_job("missing-job")

        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

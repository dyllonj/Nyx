import inspect
import tempfile
import unittest
from pathlib import Path

import config
import server
import store


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


if __name__ == "__main__":
    unittest.main()

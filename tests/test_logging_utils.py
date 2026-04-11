import json
import logging
import unittest

from logging_utils import JsonFormatter


class LoggingUtilsTestCase(unittest.TestCase):
    def test_json_formatter_includes_event_and_fields(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="nyx.sync",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="sync.completed",
            args=(),
            exc_info=None,
        )
        record.event_name = "sync.completed"
        record.fields = {"new_runs": 4, "detail_failures": 1}

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload["logger"], "nyx.sync")
        self.assertEqual(payload["event"], "sync.completed")
        self.assertEqual(payload["new_runs"], 4)
        self.assertEqual(payload["detail_failures"], 1)


if __name__ == "__main__":
    unittest.main()

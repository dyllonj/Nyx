import datetime
import unittest

from models import RunSummary


class RunSummaryModelTestCase(unittest.TestCase):
    def test_run_summary_validates_and_computes_distance(self) -> None:
        run = RunSummary(
            activity_id=1,
            name="Easy Run",
            start_time=datetime.datetime(2026, 4, 1, 7, 0, 0),
            duration_sec=1800,
            distance_m=5000,
            calories=320,
            avg_hr=145,
            max_hr=170,
            avg_speed_ms=2.78,
        )

        self.assertEqual(run.distance_km, 5.0)
        self.assertEqual(run.duration_sec, 1800.0)


if __name__ == "__main__":
    unittest.main()

import datetime
import unittest

import metrics
from models import RunSummary


def make_run(**overrides) -> RunSummary:
    payload = {
        "activity_id": 1,
        "name": "Test Run",
        "start_time": datetime.datetime(2026, 4, 1, 7, 0, 0),
        "duration_sec": 3600.0,
        "distance_m": 10000.0,
        "calories": 700,
        "avg_hr": 150.0,
        "max_hr": 175.0,
        "avg_speed_ms": 2.7777777778,
        "pace_min_per_km": 6.0,
        "avg_cadence_spm": 172.0,
        "avg_vertical_osc_cm": 8.0,
        "avg_ground_contact_ms": 240.0,
        "avg_stride_length_cm": 110.0,
        "aerobic_efficiency": None,
        "hr_drift_pct": None,
        "cadence_cv": None,
        "rei": None,
    }
    payload.update(overrides)
    return RunSummary(**payload)


class MetricsTestCase(unittest.TestCase):
    def test_compute_rei_renormalizes_available_components(self) -> None:
        run = make_run(
            avg_cadence_spm=168.0,
            avg_vertical_osc_cm=None,
            avg_ground_contact_ms=None,
        )

        rei = metrics.compute_rei(run, ae_baseline=0.04)

        self.assertIsNotNone(rei)
        self.assertAlmostEqual(rei, 99.4, places=1)

    def test_apply_split_metrics_computes_weighted_avg_hr_and_drift(self) -> None:
        run = make_run(avg_hr=None)
        splits = {
            "lapDTOs": [
                {"duration": 300, "averageHR": 140, "averageSpeed": 2.8},
                {"duration": 600, "averageHR": 145, "averageSpeed": 2.9},
                {"duration": 600, "averageHR": 150, "averageSpeed": 2.8},
                {"duration": 600, "averageHR": 156, "averageSpeed": 2.8},
                {"duration": 300, "averageHR": 150, "averageSpeed": 2.6},
            ]
        }

        metrics.apply_split_metrics(run, splits)

        self.assertAlmostEqual(run.avg_hr or 0.0, 149.0, places=1)
        self.assertAlmostEqual(run.hr_drift_pct or 0.0, 7.5862, places=3)


if __name__ == "__main__":
    unittest.main()

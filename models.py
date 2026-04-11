import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RunSummary(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    activity_id: int
    name: str
    start_time: datetime.datetime
    duration_sec: float
    distance_m: float
    calories: int
    avg_hr: Optional[float]
    max_hr: Optional[float]
    avg_speed_ms: Optional[float]

    # Populated from detail endpoint
    avg_cadence_spm: Optional[float] = None
    avg_vertical_osc_cm: Optional[float] = None
    avg_ground_contact_ms: Optional[float] = None
    avg_stride_length_cm: Optional[float] = None

    # Computed metrics
    pace_min_per_km: Optional[float] = None
    aerobic_efficiency: Optional[float] = None  # pace / hr (min/km per bpm)
    hr_drift_pct: Optional[float] = None
    cadence_cv: Optional[float] = None          # cadence coefficient of variation %
    rei: Optional[float] = None

    @property
    def distance_km(self) -> float:
        return self.distance_m / 1000.0

    @classmethod
    def from_api_summary(cls, d: dict) -> "RunSummary":
        raw_time = d.get("startTimeLocal", "")
        try:
            start = datetime.datetime.fromisoformat(raw_time)
        except ValueError:
            start = datetime.datetime.now()

        speed_ms = d.get("averageSpeed")
        pace = None
        if speed_ms and speed_ms > 0:
            pace = (1000.0 / speed_ms) / 60.0  # min/km

        return cls(
            activity_id=d["activityId"],
            name=d.get("activityName", ""),
            start_time=start,
            duration_sec=float(d.get("duration", 0)),
            distance_m=float(d.get("distance", 0)),
            calories=int(d.get("calories", 0) or 0),
            avg_hr=d.get("avgHR"),
            max_hr=d.get("maxHR"),
            avg_speed_ms=speed_ms,
            pace_min_per_km=pace,
        )

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


ProviderSlug = Literal["garmin", "oura", "whoop", "apple_health"]


@dataclass(frozen=True)
class ProviderDescriptor:
    slug: ProviderSlug
    display_name: str
    auth_mode: str
    backend_sync: bool
    supports_daily_health: bool
    notes: str | None = None


@dataclass
class ProviderPage:
    resource: str
    items: list[dict[str, Any]]
    next_cursor: str | None = None


@dataclass
class ProviderDailyHealthPage:
    resources: dict[str, ProviderPage] = field(default_factory=dict)


@dataclass
class ProviderRawData:
    account: dict[str, Any] | None = None
    activity_summaries: list[dict[str, Any]] = field(default_factory=list)
    activity_details: dict[str, dict[str, Any]] = field(default_factory=dict)
    daily_health: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def add_daily_health_page(self, page: ProviderDailyHealthPage) -> None:
        for resource, resource_page in page.resources.items():
            self.daily_health.setdefault(resource, []).extend(resource_page.items)


@dataclass
class NormalizedActivity:
    provider: ProviderSlug
    provider_account_id: int
    provider_activity_id: str
    source_type: str
    activity_type: str | None
    name: str | None
    start_time: str
    end_time: str | None = None
    day: str | None = None
    timezone: str | None = None
    duration_sec: float | None = None
    distance_m: float | None = None
    calories: float | None = None
    intensity: str | None = None
    source: str | None = None
    average_hr: float | None = None
    max_hr: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedActivitySample:
    provider_activity_id: str
    sample_type: str
    recorded_at: str
    value: float | None
    unit: str | None = None
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedDailyRecovery:
    provider: ProviderSlug
    provider_account_id: int
    day: str
    provider_day_id: str | None = None
    recovery_score: int | None = None
    readiness_score: int | None = None
    sleep_score: int | None = None
    activity_score: int | None = None
    resting_heart_rate: float | None = None
    average_heart_rate: float | None = None
    average_hrv: float | None = None
    body_temperature_delta_c: float | None = None
    body_temperature_trend_delta_c: float | None = None
    sleep_duration_sec: int | None = None
    time_in_bed_sec: int | None = None
    deep_sleep_duration_sec: int | None = None
    rem_sleep_duration_sec: int | None = None
    light_sleep_duration_sec: int | None = None
    awake_time_sec: int | None = None
    latency_sec: int | None = None
    sleep_efficiency: int | None = None
    average_breath: float | None = None
    active_calories: int | None = None
    steps: int | None = None
    total_calories: int | None = None
    contributors: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedBatch:
    activities: list[NormalizedActivity] = field(default_factory=list)
    activity_samples: list[NormalizedActivitySample] = field(default_factory=list)
    daily_recovery: list[NormalizedDailyRecovery] = field(default_factory=list)


class ProviderBase(ABC):
    descriptor: ProviderDescriptor

    @abstractmethod
    def authenticate(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_activity_summaries(
        self,
        *,
        account: dict[str, Any],
        start: str | None = None,
        cursor: str | None = None,
    ) -> ProviderPage:
        raise NotImplementedError

    @abstractmethod
    def get_activity_detail(
        self,
        *,
        account: dict[str, Any],
        activity_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_daily_health(
        self,
        *,
        account: dict[str, Any],
        start: str | None = None,
        cursor: str | None = None,
    ) -> ProviderDailyHealthPage:
        raise NotImplementedError

    @abstractmethod
    def normalize(
        self,
        *,
        account: dict[str, Any],
        raw: ProviderRawData,
    ) -> NormalizedBatch:
        raise NotImplementedError

from __future__ import annotations

from typing import Any

from errors import HarnessError
from providers.base import ProviderBase, ProviderDailyHealthPage, ProviderDescriptor, ProviderPage, ProviderRawData, NormalizedBatch


class AppleHealthProvider(ProviderBase):
    descriptor = ProviderDescriptor(
        slug="apple_health",
        display_name="Apple Health",
        auth_mode="device_bridge",
        backend_sync=False,
        supports_daily_health=True,
        notes="Apple Health requires an app-mediated HealthKit bridge rather than backend OAuth pull sync.",
    )

    def _unsupported(self) -> HarnessError:
        return HarnessError(
            "apple_health_bridge_required",
            "Apple Health requires a device-mediated HealthKit bridge.",
            hint="Implement the iOS uploader path before calling the backend provider abstraction directly.",
        )

    def authenticate(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        raise self._unsupported()

    def list_activity_summaries(
        self,
        *,
        account: dict[str, Any],
        start: str | None = None,
        cursor: str | None = None,
    ) -> ProviderPage:
        raise self._unsupported()

    def get_activity_detail(self, *, account: dict[str, Any], activity_id: str) -> dict[str, Any]:
        raise self._unsupported()

    def list_daily_health(
        self,
        *,
        account: dict[str, Any],
        start: str | None = None,
        cursor: str | None = None,
    ) -> ProviderDailyHealthPage:
        raise self._unsupported()

    def normalize(self, *, account: dict[str, Any], raw: ProviderRawData) -> NormalizedBatch:
        raise self._unsupported()

from __future__ import annotations

from typing import Any

from errors import HarnessError
from providers.base import ProviderBase, ProviderDailyHealthPage, ProviderDescriptor, ProviderPage, ProviderRawData, NormalizedBatch


class WhoopProvider(ProviderBase):
    descriptor = ProviderDescriptor(
        slug="whoop",
        display_name="WHOOP",
        auth_mode="oauth2",
        backend_sync=True,
        supports_daily_health=True,
        notes="WHOOP is scaffolded in the provider abstraction but not yet implemented in this phase.",
    )

    def _unsupported(self) -> HarnessError:
        return HarnessError(
            "whoop_not_implemented",
            "WHOOP integration has not been implemented yet.",
            hint="Use the new provider abstraction hooks to add WHOOP in the next phase.",
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

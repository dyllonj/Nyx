from __future__ import annotations

import datetime
from typing import Any

import auth as garmin_auth
import fetch as garmin_fetch
from errors import HarnessError
from providers.base import (
    NormalizedActivity,
    NormalizedActivitySample,
    NormalizedBatch,
    ProviderBase,
    ProviderDailyHealthPage,
    ProviderDescriptor,
    ProviderPage,
    ProviderRawData,
)


class GarminProvider(ProviderBase):
    descriptor = ProviderDescriptor(
        slug="garmin",
        display_name="Garmin",
        auth_mode="credentials",
        backend_sync=True,
        supports_daily_health=False,
        notes="Garmin continues to use the legacy sync pipeline, but now has a compatible provider adapter surface.",
    )

    def authenticate(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        client = garmin_auth.get_client(
            email=payload.get("email"),
            password=payload.get("password"),
            interactive=bool(payload.get("interactive", True)),
        )
        return {"provider": self.descriptor.slug, "client": client}

    def list_activity_summaries(
        self,
        *,
        account: dict[str, Any],
        start: str | None = None,
        cursor: str | None = None,
    ) -> ProviderPage:
        client = account.get("client")
        if client is None:
            raise HarnessError("garmin_client_required", "A Garmin client session is required to list activities.")
        return ProviderPage(
            resource="workout",
            items=garmin_fetch.fetch_running_activities(client, start or "2000-01-01"),
            next_cursor=cursor,
        )

    def get_activity_detail(self, *, account: dict[str, Any], activity_id: str) -> dict[str, Any]:
        client = account.get("client")
        if client is None:
            raise HarnessError("garmin_client_required", "A Garmin client session is required to fetch activity detail.")
        detail = garmin_fetch.fetch_activity_detail(client, int(activity_id))
        detail["splits"] = garmin_fetch.fetch_activity_splits(client, int(activity_id)).get("lapDTOs", [])
        return detail

    def list_daily_health(
        self,
        *,
        account: dict[str, Any],
        start: str | None = None,
        cursor: str | None = None,
    ) -> ProviderDailyHealthPage:
        return ProviderDailyHealthPage(resources={})

    def normalize(self, *, account: dict[str, Any], raw: ProviderRawData) -> NormalizedBatch:
        provider_account_id = int(account.get("provider_account_id", 0) or 0)
        batch = NormalizedBatch()
        for summary in raw.activity_summaries:
            start_time = summary.get("startTimeLocal") or datetime.datetime.now().isoformat()
            end_time = None
            try:
                start_dt = datetime.datetime.fromisoformat(start_time)
                end_time = (start_dt + datetime.timedelta(seconds=float(summary.get("duration", 0) or 0))).isoformat()
            except ValueError:
                start_dt = datetime.datetime.now()
            activity_id = str(summary["activityId"])
            batch.activities.append(
                NormalizedActivity(
                    provider=self.descriptor.slug,
                    provider_account_id=provider_account_id,
                    provider_activity_id=activity_id,
                    source_type="run",
                    activity_type="running",
                    name=summary.get("activityName"),
                    start_time=start_dt.isoformat(),
                    end_time=end_time,
                    day=start_dt.date().isoformat(),
                    duration_sec=float(summary.get("duration", 0) or 0),
                    distance_m=float(summary.get("distance", 0) or 0),
                    calories=float(summary.get("calories", 0) or 0),
                    average_hr=summary.get("avgHR"),
                    max_hr=summary.get("maxHR"),
                    source="garmin_connect",
                    metadata={"raw_summary": summary},
                )
            )

            detail = raw.activity_details.get(activity_id)
            if not detail:
                continue
            parsed = garmin_fetch.parse_detail_metrics(detail)
            timestamps = detail.get("activityDetailMetrics", [])
            for index, value in enumerate(parsed.get("hr_samples", [])):
                metric = timestamps[index] if index < len(timestamps) else {}
                batch.activity_samples.append(
                    NormalizedActivitySample(
                        provider_activity_id=activity_id,
                        sample_type="heart_rate",
                        recorded_at=metric.get("startTimeGMT") or start_dt.isoformat(),
                        value=value,
                        unit="bpm",
                        source="garmin_connect",
                    )
                )
        return batch

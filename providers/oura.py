from __future__ import annotations

import datetime
import json
from typing import Any, Callable

import config
from errors import HarnessError
from providers.base import NormalizedBatch, ProviderBase, ProviderDailyHealthPage, ProviderDescriptor, ProviderPage, ProviderRawData
from providers import oura_auth, oura_fetch, oura_normalize
import store


class OuraProvider(ProviderBase):
    descriptor = ProviderDescriptor(
        slug="oura",
        display_name="Oura",
        auth_mode="oauth2",
        backend_sync=True,
        supports_daily_health=True,
        notes="Implements Oura OAuth2, token refresh, raw payload persistence, and normalization into Nyx canonical tables.",
    )

    def authenticate(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        code = _string_or_none(payload.get("code"))
        redirect_uri = _string_or_none(payload.get("redirect_uri")) or _string_or_none(payload.get("redirectUrl"))
        scopes = _normalize_scopes(payload.get("scopes"))

        if not code:
            state = oura_auth.generate_state()
            conn = store.open_db()
            try:
                store.set_meta(
                    conn,
                    "oura_oauth_state",
                    json.dumps(
                        {
                            "state": state,
                            "created_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                            "redirect_uri": redirect_uri,
                        }
                    ),
                )
            finally:
                conn.close()
            return {
                "mode": "authorize",
                "provider": self.descriptor.slug,
                "authorization_url": oura_auth.build_authorization_url(
                    redirect_uri=redirect_uri,
                    state=state,
                    scopes=scopes,
                ),
                "state": state,
                "scopes": scopes,
            }

        state = _string_or_none(payload.get("state"))
        if not state:
            raise HarnessError(
                "oura_state_required",
                "The Oura OAuth state is required to complete the connect flow.",
                hint="Call the connect endpoint once to get an authorization URL and state token, then send the returned state back with the code.",
            )

        conn = store.open_db()
        try:
            self._validate_oauth_state(conn, state, redirect_uri)
        finally:
            conn.close()

        token_payload = oura_auth.exchange_code_for_token(code, redirect_uri=redirect_uri)
        client = oura_fetch.OuraApiClient(access_token=str(token_payload["access_token"]))
        personal_info = client.get_personal_info()

        conn = store.open_db()
        try:
            account = store.upsert_provider_account(
                conn,
                provider=self.descriptor.slug,
                provider_user_id=str(personal_info["id"]),
                display_name=_string_or_none(personal_info.get("email")) or f"Oura {personal_info['id']}",
                scopes=token_payload.get("scopes", scopes),
                access_token=_string_or_none(token_payload.get("access_token")),
                refresh_token=_string_or_none(token_payload.get("refresh_token")),
                token_type=_string_or_none(token_payload.get("token_type")) or "bearer",
                token_expires_at=_string_or_none(token_payload.get("expires_at")),
                status="connected",
                account_metadata={
                    "email": personal_info.get("email"),
                    "age": personal_info.get("age"),
                    "weight": personal_info.get("weight"),
                    "height": personal_info.get("height"),
                    "biological_sex": personal_info.get("biological_sex"),
                },
            )
            store.upsert_oura_raw_payloads(conn, int(account["id"]), "personal_info", [personal_info])
            store.delete_meta(conn, "oura_oauth_state")
        finally:
            conn.close()

        return {
            "mode": "connected",
            "provider": self.descriptor.slug,
            "account": _public_account_payload(account),
            "scopes": token_payload.get("scopes", scopes),
        }

    def list_activity_summaries(
        self,
        *,
        account: dict[str, Any],
        start: str | None = None,
        cursor: str | None = None,
    ) -> ProviderPage:
        client = self._client_for_account(account)
        return client.list_workouts(start_date=start or "2000-01-01", end_date=_today_iso(), next_token=cursor)

    def get_activity_detail(self, *, account: dict[str, Any], activity_id: str) -> dict[str, Any]:
        client = self._client_for_account(account)
        return client.get_workout(activity_id)

    def list_daily_health(
        self,
        *,
        account: dict[str, Any],
        start: str | None = None,
        cursor: str | None = None,
    ) -> ProviderDailyHealthPage:
        cursor_map = _parse_cursor_map(cursor)
        client = self._client_for_account(account)
        end_date = _today_iso()
        return ProviderDailyHealthPage(
            resources={
                "daily_activity": client.list_daily_activity(
                    start_date=start or "2000-01-01",
                    end_date=end_date,
                    next_token=cursor_map.get("daily_activity"),
                ),
                "daily_sleep": client.list_daily_sleep(
                    start_date=start or "2000-01-01",
                    end_date=end_date,
                    next_token=cursor_map.get("daily_sleep"),
                ),
                "daily_readiness": client.list_daily_readiness(
                    start_date=start or "2000-01-01",
                    end_date=end_date,
                    next_token=cursor_map.get("daily_readiness"),
                ),
                "sleep": client.list_sleep(
                    start_date=start or "2000-01-01",
                    end_date=end_date,
                    next_token=cursor_map.get("sleep"),
                ),
            }
        )

    def normalize(self, *, account: dict[str, Any], raw: ProviderRawData) -> NormalizedBatch:
        account_id = int(account["id"])
        return oura_normalize.normalize_payloads(account_id=account_id, raw=raw)

    def disconnect(self) -> dict[str, Any]:
        conn = store.open_db()
        try:
            account = store.get_active_provider_account(conn, self.descriptor.slug)
            if account is None:
                return {"provider": self.descriptor.slug, "disconnected": False, "account": None}
            store.disconnect_provider_account(conn, int(account["id"]))
            disconnected = store.get_provider_account_by_id(conn, int(account["id"]))
        finally:
            conn.close()
        return {
            "provider": self.descriptor.slug,
            "disconnected": True,
            "account": _public_account_payload(disconnected) if disconnected is not None else None,
        }

    def sync(
        self,
        *,
        start_date: str | None = None,
        full_refresh: bool = False,
        include_heartrate: bool = False,
    ) -> dict[str, Any]:
        conn = store.open_db()
        try:
            account_row = store.get_active_provider_account(conn, self.descriptor.slug)
            if account_row is None:
                raise HarnessError(
                    "oura_not_connected",
                    "No connected Oura account is available.",
                    hint="Connect Oura first with POST /api/providers/oura/connect.",
                )
            if account_row["status"] != "connected":
                raise HarnessError(
                    "oura_not_connected",
                    "The stored Oura account is disconnected.",
                    hint="Reconnect Oura before syncing.",
                )

            account = dict(account_row)
            client = self._client_for_account(account)
            raw = ProviderRawData(account=account)
            end_date = _today_iso()
            account_id = int(account["id"])
            resource_counts: dict[str, int] = {}

            workout_start_date = self._resource_start_date(
                conn,
                account_id=account_id,
                resource_type="workout",
                requested_start_date=start_date,
                full_refresh=full_refresh,
            )
            workouts = self._sync_document_collection(
                conn,
                account=account,
                resource_type="workout",
                start_date=workout_start_date,
                end_date=end_date,
                fetch_page=lambda next_token: client.list_workouts(
                    start_date=workout_start_date,
                    end_date=end_date,
                    next_token=next_token,
                ),
            )
            raw.activity_summaries.extend(workouts)
            resource_counts["workout"] = len(workouts)

            for resource_type, fetch_fn in (
                ("daily_activity", client.list_daily_activity),
                ("daily_sleep", client.list_daily_sleep),
                ("daily_readiness", client.list_daily_readiness),
                ("sleep", client.list_sleep),
            ):
                resource_start_date = self._resource_start_date(
                    conn,
                    account_id=account_id,
                    resource_type=resource_type,
                    requested_start_date=start_date,
                    full_refresh=full_refresh,
                )
                items = self._sync_document_collection(
                    conn,
                    account=account,
                    resource_type=resource_type,
                    start_date=resource_start_date,
                    end_date=end_date,
                    fetch_page=lambda next_token, fetch_fn=fetch_fn, resource_start_date=resource_start_date: fetch_fn(
                        start_date=resource_start_date,
                        end_date=end_date,
                        next_token=next_token,
                    ),
                )
                raw.daily_health[resource_type] = items
                resource_counts[resource_type] = len(items)

            if include_heartrate:
                heartrate_start = self._heartrate_start_datetime(
                    conn,
                    account_id=account_id,
                    requested_start_date=start_date,
                    full_refresh=full_refresh,
                )
                heartrate_end = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
                heartrate_samples = self._sync_heartrate_collection(
                    conn,
                    account=account,
                    start_datetime=heartrate_start,
                    end_datetime=heartrate_end,
                    fetch_page=lambda next_token: client.list_heartrate(
                        start_datetime=heartrate_start,
                        end_datetime=heartrate_end,
                        next_token=next_token,
                    ),
                )
                raw.daily_health["heartrate"] = heartrate_samples
                resource_counts["heartrate"] = len(heartrate_samples)

            normalized = self.normalize(account=account, raw=raw)
            store.upsert_normalized_batch(conn, normalized)
            return {
                "provider": self.descriptor.slug,
                "account": _public_account_payload(account_row),
                "resource_counts": resource_counts,
                "normalized": {
                    "activities": len(normalized.activities),
                    "activity_samples": len(normalized.activity_samples),
                    "daily_recovery": len(normalized.daily_recovery),
                },
            }
        finally:
            conn.close()

    def _sync_document_collection(
        self,
        conn,
        *,
        account: dict[str, Any],
        resource_type: str,
        start_date: str,
        end_date: str,
        fetch_page: Callable[[str | None], ProviderPage],
    ) -> list[dict[str, Any]]:
        account_id = int(account["id"])
        store.mark_provider_sync_running(conn, account_id, self.descriptor.slug, resource_type)
        items: list[dict[str, Any]] = []
        next_token: str | None = None
        try:
            while True:
                page = fetch_page(next_token)
                items.extend(page.items)
                next_token = page.next_cursor
                if not next_token:
                    break
            store.upsert_oura_raw_payloads(conn, account_id, resource_type, items)
            watermark = _max_day(items) or end_date
            store.mark_provider_sync_success(
                conn,
                account_id=account_id,
                provider=self.descriptor.slug,
                resource_type=resource_type,
                watermark=watermark,
                cursor={"last_day": watermark},
                summary={
                    "fetched": len(items),
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
            return items
        except Exception as exc:
            store.mark_provider_sync_failed(
                conn,
                account_id=account_id,
                provider=self.descriptor.slug,
                resource_type=resource_type,
                error={
                    "code": getattr(exc, "code", "provider_sync_failed"),
                    "message": getattr(exc, "message", str(exc)),
                    "details": getattr(exc, "details", None),
                },
            )
            raise

    def _sync_heartrate_collection(
        self,
        conn,
        *,
        account: dict[str, Any],
        start_datetime: str,
        end_datetime: str,
        fetch_page: Callable[[str | None], ProviderPage],
    ) -> list[dict[str, Any]]:
        account_id = int(account["id"])
        resource_type = "heartrate"
        store.mark_provider_sync_running(conn, account_id, self.descriptor.slug, resource_type)
        items: list[dict[str, Any]] = []
        next_token: str | None = None
        try:
            while True:
                page = fetch_page(next_token)
                items.extend(page.items)
                next_token = page.next_cursor
                if not next_token:
                    break
            store.upsert_oura_raw_payloads(conn, account_id, resource_type, items)
            store.mark_provider_sync_success(
                conn,
                account_id=account_id,
                provider=self.descriptor.slug,
                resource_type=resource_type,
                watermark=end_datetime[:10],
                cursor={"last_datetime": end_datetime},
                summary={
                    "fetched": len(items),
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                },
            )
            return items
        except Exception as exc:
            store.mark_provider_sync_failed(
                conn,
                account_id=account_id,
                provider=self.descriptor.slug,
                resource_type=resource_type,
                error={
                    "code": getattr(exc, "code", "provider_sync_failed"),
                    "message": getattr(exc, "message", str(exc)),
                    "details": getattr(exc, "details", None),
                },
            )
            raise

    def _client_for_account(self, account: dict[str, Any]) -> oura_fetch.OuraApiClient:
        refresh_token = _string_or_none(account.get("refresh_token"))
        account_id = account.get("id")
        refresh_fn = None
        if refresh_token and account_id is not None:
            refresh_fn = lambda token: self._refresh_tokens(int(account_id), token)
        access_token = _string_or_none(account.get("access_token"))
        if not access_token:
            raise HarnessError(
                "oura_not_connected",
                "The Oura account does not have a stored access token.",
                hint="Reconnect the Oura account before syncing.",
            )
        return oura_fetch.OuraApiClient(
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=_string_or_none(account.get("token_expires_at")),
            refresh_token_fn=refresh_fn,
        )

    def _refresh_tokens(self, account_id: int, refresh_token: str) -> dict[str, Any]:
        token_payload = oura_auth.refresh_access_token(refresh_token)
        conn = store.open_db()
        try:
            store.update_provider_account_tokens(
                conn,
                account_id=account_id,
                access_token=_string_or_none(token_payload.get("access_token")),
                refresh_token=_string_or_none(token_payload.get("refresh_token")),
                token_type=_string_or_none(token_payload.get("token_type")) or "bearer",
                token_expires_at=_string_or_none(token_payload.get("expires_at")),
                scopes=token_payload.get("scopes"),
            )
        finally:
            conn.close()
        return token_payload

    def _resource_start_date(
        self,
        conn,
        *,
        account_id: int,
        resource_type: str,
        requested_start_date: str | None,
        full_refresh: bool,
    ) -> str:
        if requested_start_date:
            return requested_start_date
        if full_refresh:
            return "2000-01-01"
        state = store.get_provider_sync_state(conn, account_id, resource_type)
        last_day = _string_or_none((state or {}).get("cursor", {}).get("last_day"))
        if not last_day:
            return "2000-01-01"
        parsed_day = datetime.date.fromisoformat(last_day) - datetime.timedelta(days=config.OURA_SYNC_LOOKBACK_DAYS)
        return max(parsed_day, datetime.date(2000, 1, 1)).isoformat()

    def _heartrate_start_datetime(
        self,
        conn,
        *,
        account_id: int,
        requested_start_date: str | None,
        full_refresh: bool,
    ) -> str:
        if requested_start_date:
            return f"{requested_start_date}T00:00:00"
        if full_refresh:
            start_day = datetime.date.today() - datetime.timedelta(days=config.OURA_HEARTRATE_LOOKBACK_DAYS)
            return f"{start_day.isoformat()}T00:00:00"
        state = store.get_provider_sync_state(conn, account_id, "heartrate")
        last_datetime = _string_or_none((state or {}).get("cursor", {}).get("last_datetime"))
        if last_datetime:
            return last_datetime
        start_day = datetime.date.today() - datetime.timedelta(days=config.OURA_HEARTRATE_LOOKBACK_DAYS)
        return f"{start_day.isoformat()}T00:00:00"

    def _validate_oauth_state(self, conn, state: str, redirect_uri: str | None) -> None:
        stored_state_raw = store.get_meta(conn, "oura_oauth_state")
        if not stored_state_raw:
            raise HarnessError(
                "oura_state_missing",
                "No pending Oura OAuth state was found.",
                hint="Restart the Oura connect flow and complete the authorization promptly.",
            )
        try:
            stored_state = json.loads(stored_state_raw)
        except json.JSONDecodeError as exc:
            raise HarnessError(
                "oura_state_invalid",
                "The stored Oura OAuth state could not be parsed.",
                hint="Restart the Oura connect flow.",
                details=str(exc),
            ) from exc
        if stored_state.get("state") != state:
            raise HarnessError(
                "oura_state_mismatch",
                "The Oura OAuth state did not match the pending authorization request.",
                hint="Restart the Oura connect flow to get a fresh authorization URL.",
            )
        created_at_raw = _string_or_none(stored_state.get("created_at"))
        if created_at_raw:
            created_at = datetime.datetime.fromisoformat(created_at_raw)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.UTC)
            age = datetime.datetime.now(datetime.UTC) - created_at
            if age.total_seconds() > config.OURA_OAUTH_STATE_TTL_SEC:
                raise HarnessError(
                    "oura_state_expired",
                    "The pending Oura OAuth state has expired.",
                    hint="Restart the Oura connect flow to get a fresh authorization URL.",
                )
        stored_redirect = _string_or_none(stored_state.get("redirect_uri"))
        if stored_redirect and redirect_uri and stored_redirect != redirect_uri:
            raise HarnessError(
                "oura_redirect_mismatch",
                "The Oura redirect URI does not match the pending authorization request.",
                hint="Use the same redirect URI for both the authorization and code exchange steps.",
            )


def _today_iso() -> str:
    return datetime.date.today().isoformat()


def _max_day(items: list[dict[str, Any]]) -> str | None:
    days = sorted(str(item.get("day")) for item in items if item.get("day"))
    return days[-1] if days else None


def _normalize_scopes(scopes: Any) -> list[str]:
    if isinstance(scopes, (list, tuple)):
        values = [str(scope).strip() for scope in scopes]
    elif isinstance(scopes, str):
        values = [scope.strip() for scope in scopes.replace(",", " ").split()]
    else:
        values = list(config.OURA_DEFAULT_SCOPES)
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped or list(config.OURA_DEFAULT_SCOPES)


def _parse_cursor_map(cursor: str | None) -> dict[str, str]:
    if not cursor:
        return {}
    try:
        parsed = json.loads(cursor)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items() if value}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _public_account_payload(row: dict[str, Any] | Any) -> dict[str, Any]:
    account = dict(row)
    metadata = account.get("account_metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return {
        "id": account.get("id"),
        "provider": account.get("provider"),
        "provider_user_id": account.get("provider_user_id"),
        "display_name": account.get("display_name"),
        "status": account.get("status"),
        "scopes": account.get("scopes") if isinstance(account.get("scopes"), list) else [],
        "token_expires_at": account.get("token_expires_at"),
        "connected_at": account.get("created_at"),
        "updated_at": account.get("updated_at"),
        "disconnected_at": account.get("disconnected_at"),
        "account_metadata": metadata,
    }

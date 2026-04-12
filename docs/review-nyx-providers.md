# Nyx Provider Review

Reviewed commits: `bd25361`, `89b2051`, `9777224`

Scope:
- Oura and WHOOP integrations
- Provider abstraction consistency relative to Garmin
- OAuth/security handling
- schema and migration correctness
- API surface consistency
- test coverage

High-level assessment:
- `89b2051` is cleanup-only. I did not find a correctness issue in that commit by itself.
- The landed stack is directionally good, especially on Oura, but WHOOP still has two concrete correctness/security bugs and the provider abstraction is not yet authoritative.
- I did not find a blocking schema migration defect in the upgrade path from the pre-provider schema, but migration coverage is missing.

## Findings

### 1. High: WHOOP OAuth callback accepts unsolicited authorization codes

Files:
- `server.py:1797-1808`
- `server.py:1782-1795`

Details:
- `connect_whoop()` only checks `request.state` when a stored state already exists:
  - `expected_state = ... get_provider_oauth_state(...)`
  - `if expected_state and request.state != expected_state: ...`
- If there is no pending state in the database, the callback path still exchanges the code and connects the account.
- I reproduced this locally by calling `connect_whoop()` with a mocked valid token exchange and no stored state; the endpoint returned `status="connected"`.

Impact:
- This defeats the main CSRF/account-binding protection in the WHOOP OAuth flow.
- Any authorized local caller that can present a valid WHOOP auth code for the configured app can attach an account without first starting Nyx's stateful connect flow.

Recommendation:
- Require a pending state to exist before any WHOOP code exchange.
- Store WHOOP state as structured data `{state, redirect_uri, created_at}` like the Oura flow does, then enforce:
  - state match
  - redirect URI match
  - TTL/expiry
- Clear the pending state after success and on explicit restart.

Reference:
- WHOOP OAuth docs describe `state` as the CSRF protection for the flow: <https://developer.whoop.com/docs/developing/oauth/>

### 2. High: WHOOP refresh-on-401 path bypasses retry/error translation

Files:
- `providers/whoop_fetch.py:92-96`
- `providers/whoop_fetch.py:104-159`
- `providers/oura_fetch.py:235-266`

Details:
- In `WhoopApiClient._call_api()`, the 401 branch does:
  - `return fn(force_refresh=True)`
- If the refreshed request then fails with another `HTTPError`/`URLError`, that exception escapes the retry loop as a raw stdlib exception.
- I reproduced this locally with a mock: first request `401`, refreshed request `429`, result was raw `HTTPError 429` instead of `HarnessError`.
- Oura's retry logic does not have this problem; it refreshes and then continues through the same wrapped retry path.

Impact:
- WHOOP callers can receive uncaught low-level exceptions instead of Nyx error payloads.
- Retries and circuit-breaker semantics are inconsistent after token refresh.
- In production this can turn a handled provider failure into a 500-class server error.

Recommendation:
- Do not `return fn(force_refresh=True)` from inside the exception block.
- Instead refresh state and `continue`, or wrap the refreshed call in the same retry/error translation path so every post-refresh failure still becomes a `HarnessError`.

### 3. Medium: WHOOP incremental sync window is global, not per-resource

Files:
- `server.py:399-422`
- `server.py:1091-1178`
- `providers/oura.py:209-279`

Details:
- `_resolve_whoop_sync_window()` computes the next incremental start from `max(window_end)` across all WHOOP sync-state rows.
- `_sync_whoop()` tracks workout, cycle, sleep, and recovery as separate resources with separate sync state rows.
- I reproduced a drift case locally:
  - workout cursor at `2026-04-10`
  - recovery cursor at `2026-03-20`
  - next WHOOP sync window started at `2026-04-03`
- That means a lagging resource can lose older history once the gap exceeds the 7-day lookback.
- Oura already uses the safer per-resource pattern via `_resource_start_date()`.

Impact:
- If one WHOOP resource keeps failing while others continue to advance, Nyx can permanently miss older recovery/sleep/cycle data.

Recommendation:
- Resolve the next start independently per WHOOP resource, mirroring Oura's cursor handling.
- Keep the queued background job if desired, but move resource window calculation to the resource level.

### 4. Medium: Provider status payload can disagree with the account actually used for sync

Files:
- `store.py:604-619`
- `store.py:634-650`
- `store.py:1643-1710`
- `server.py:351-352`

Details:
- `get_provider_account()` / `get_active_provider_account()` prefer connected rows.
- `get_provider_data_status()` is built from `list_provider_accounts()`, which keeps the newest row per provider, not the active connected row.
- I reproduced this locally with two WHOOP accounts:
  - account `u1` still connected
  - account `u2` newer and disconnected
  - sync/auth APIs resolved `u1`, but status payload reported `u2` as the provider account

Impact:
- `/api/status` and provider account payloads can misreport the active connection when multiple accounts exist for the same provider.
- This is especially confusing because the schema explicitly allows multiple accounts per provider via `UNIQUE(provider, provider_user_id)`.

Recommendation:
- Make `list_provider_accounts()` use the same active-account selection rule as `get_active_provider_account()`, or
- expose both `active_account` and `historical_accounts` explicitly instead of collapsing to a single row.

### 5. Medium: Provider abstraction is not authoritative and already diverges from Garmin/Oura/WHOOP reality

Files:
- `providers/registry.py:10-15`
- `providers/whoop.py:9-50`
- `server.py:355-356`
- `server.py:1076-1195`
- `store.py:227-326`
- `providers/garmin.py:73-75`

Details:
- The registry advertises four providers, but only Oura is actually routed through a real provider object in server code.
- `WhoopProvider` is still a stub that always raises `whoop_not_implemented`, while the real WHOOP flow lives directly in `server.py` plus auth/fetch/normalize helpers.
- Oura uses provider-object sync plus Oura-specific raw tables.
- WHOOP bypasses the provider object and writes to the generic `provider_raw_payloads` table.
- Garmin has an adapter, but its `normalize()` path defaults `provider_account_id` to `0`, so it is not actually compatible with persistence through the provider tables today.

Impact:
- The codebase now has three provider patterns:
  - legacy Garmin sync engine
  - Oura provider object
  - WHOOP server-specific flow
- That drift makes `providers/registry.py` misleading and increases the cost/risk of adding the next provider.

Recommendation:
- Pick one approach and enforce it:
  - either make WHOOP and Garmin fully implement `ProviderBase` end-to-end and standardize raw payload storage, or
  - remove the registry/provider-descriptor surface until the abstraction is real.
- Given the current code, Oura's per-resource sync model is the better base to standardize on.

## Schema And Migration Assessment

Files:
- `store.py:329-414`
- parent schema before provider work: `923a374:store.py` (`SCHEMA_VERSION = 6`)

Assessment:
- The upgrade path from the pre-provider schema to the current provider schema is linear and appears mechanically correct.
- Existing Garmin tables are left intact; provider tables are additive.
- I did not find a blocking migration defect in the reviewed commits.

Risk:
- There are no migration tests that build an older DB and verify `open_db()` upgrades it correctly.
- Provider-heavy features depend on several new tables and indices, but the test suite does not validate those upgrade paths.

Recommendation:
- Add migration tests for at least:
  - schema v6 -> current
  - provider account creation after migration
  - provider raw payload writes after migration
  - sync-state reads after migration

## API Consistency Notes

Observations:
- Oura `/api/providers/oura/sync` is synchronous and returns a summary immediately.
- WHOOP `/api/providers/whoop/sync` is asynchronous and returns a generic sync job that must be polled through `/api/sync/{job_id}`.
- That asymmetry is documented in README, but it is still an inconsistent provider contract for API clients.

Recommendation:
- Either standardize provider sync endpoints on a shared queued-job contract, or expose a provider-specific status endpoint so clients do not need to special-case WHOOP.

## Test Coverage Assessment

Files reviewed:
- `tests/test_provider_oura.py:35-297`
- `tests/test_whoop_provider.py:146-290`

What is covered well:
- happy-path Oura connect
- happy-path Oura sync normalization/persistence
- happy-path WHOOP connect/disconnect
- WHOOP queued sync job creation
- happy-path WHOOP normalization/persistence

Important gaps:
- no WHOOP negative OAuth tests:
  - missing state
  - mismatched state
  - expired/replayed state
- no tests for WHOOP refresh-error behavior after a 401
- no tests for per-resource sync cursor drift / partial failure recovery
- no tests for multiple accounts per provider
- no migration tests at all

## Suggested Follow-Up Order

1. Fix WHOOP OAuth callback validation so a pending state is mandatory.
2. Fix WHOOP refresh retry handling so post-refresh failures still become `HarnessError`s.
3. Change WHOOP incremental sync to use per-resource cursors/watermarks.
4. Unify active-account selection in status/reporting code.
5. Decide whether the provider abstraction is real; then either finish it or remove the misleading stubs/registry surface.
6. Add migration and negative-path tests before expanding to the next provider.

# Review Track B - Backend/API Hardening

Date: 2026-04-12

Scope reviewed:
`server.py`, `store.py`, `sync_engine.py`, `health.py`, `auth.py`, `coach.py`, `evals.py`

## Summary

I found 9 production-readiness issues in the reviewed backend path: 4 high severity and 5 medium severity. The biggest release blockers are fail-open API authentication, destructive/non-atomic database migrations, a broken live-evals credential check, and an API-triggerable sync path that can block on stdin.

I did not find a direct SQL injection primitive in `store.py`. Most user-influenced values are bound through SQLite parameters; the main database risks are migration safety, integrity enforcement, and concurrency behavior.

## Findings

### 1. [High] API authentication is fail-open when `NYX_API_TOKEN` is unset

References: `server.py:158-171`, `server.py:179-186`, `server.py:205-224`

`_configured_api_token()` returns `None` when the env var is missing, and `_is_authorized_request()` treats that as fully authorized. That means every `/api/*` route becomes unauthenticated by default. In the same file, CORS also allows localhost plus a regex that matches Tailscale and LAN-style origins. For a pilot release, this is a bad default: a deployment mistake turns the full backend into an open API.

Recommendation: make auth fail closed outside an explicitly local/dev mode, and tie the relaxed behavior to a separate `NYX_DEV_MODE`-style flag instead of missing config.

### 2. [High] `open_db()` runs destructive, non-atomic migrations on every connection

References: `store.py:347-421`, `store.py:386-406`, `store.py:2145-2258`

Every call to `store.open_db()` applies schema migrations before returning the connection. The v7 to v8 path drops all provider-related tables if `provider_user_id` is missing, which destroys provider accounts, sync state, raw payloads, and recovery/activity history in place. The migration flow is also not atomic: migration step helpers commit internally, so a failure can leave the database partially upgraded.

This is especially risky because `open_db()` is used per request throughout the API and by health/status code paths. The first request against an older DB can mutate or destroy data.

Recommendation: move migrations to an explicit startup/admin step, wrap them in a single transaction, and replace destructive table drops with a real data-preserving migration or a mandatory backup-and-confirm flow.

### 3. [High] Live evals are wired to the wrong credential and will fail in a correctly configured Moonshot deployment

References: `evals.py:160-171`, `coach.py:294-312`

`coach.py` uses `MOONSHOT_API_KEY` and the OpenAI SDK for Moonshot requests, but `evals.run_live_evals()` blocks unless `ANTHROPIC_API_KEY` is set. In practice, live evals will fail even when coach chat is correctly configured.

Recommendation: gate live evals on the same Moonshot/OpenAI configuration used by `coach.py`, and add a regression test that exercises the live-eval preflight path.

### 4. [High] `/api/sync` allows API callers to trigger interactive stdin prompts in a background thread

References: `server.py:102-106`, `server.py:1682-1705`, `auth.py:76-99`

The API accepts `interactive: bool` and passes it straight into the background Garmin sync thread. If the token cache is missing or expired and `interactive=True`, `auth.get_client()` will call `input()` and `getpass.getpass()` on the server process. In an API deployment, that can hang the worker thread indefinitely and leave the sync job stuck.

Recommendation: reject `interactive=True` from the API entirely and keep interactive login only in CLI flows.

### 5. [Medium] Garmin detail-fetch failures are downgraded to per-run warnings, even for rate limiting and circuit-open conditions

References: `sync_engine.py:124-149`, `sync_engine.py:234-275`, `fetch.py:92-108`

`fetch.py` already converts repeated Garmin failures into `HarnessError` values such as temporary unavailability and rate limiting, but `sync_engine.run_sync()` catches all exceptions inside the per-activity detail loop and continues. If Garmin starts throttling mid-sync, Nyx will churn through the full backlog, mark many details as failed, and still mark the overall sync as successful.

That behavior hides a degraded sync behind a success status and can waste substantial time while the circuit is open.

Recommendation: treat Garmin-wide failure modes as sync-level failures and abort the remaining detail loop once rate limiting or circuit-open conditions are detected.

### 6. [Medium] Moonshot upstream failures return raw 500s until the circuit breaker opens

References: `server.py:200-202`, `server.py:1527-1559`, `server.py:1611-1679`, `coach.py:347-378`

The API only normalizes `HarnessError`. `CoachSession.ask()` converts circuit-open into `HarnessError`, but other upstream exceptions are logged and re-raised unchanged. That means network errors, auth failures, and rate limits from Moonshot propagate out of `/api/coach/message` and live evals as generic 500s until the breaker trips.

Recommendation: translate known OpenAI/Moonshot exceptions into stable `HarnessError` responses immediately, not only after repeated failures.

### 7. [Medium] SQLite foreign-key constraints and cascades are declared but never enabled

References: `store.py:41-50`, `store.py:72-95`, `store.py:108-240`, `store.py:417-421`

The schema relies heavily on foreign keys and `ON DELETE CASCADE`, but `open_db()` never executes `PRAGMA foreign_keys = ON`. In SQLite, that means the constraints are not enforced on the connection by default. The result is silent integrity drift: orphaned child rows, missing cascade cleanup, and weaker guarantees around provider, coach, and sync-job tables.

Recommendation: enable foreign keys on every connection in `open_db()` and add a regression test that verifies cascade behavior.

### 8. [Medium] `sync_engine.run_sync()` opens a SQLite connection and never closes it

References: `sync_engine.py:49-50`, `sync_engine.py:52-288`

`run_sync()` creates a DB connection once at the top of the function and never closes it on success or failure. In a long-running API process, repeated sync jobs will leak connections/file descriptors and increase the chance of `database is locked` behavior or other resource exhaustion symptoms.

Recommendation: wrap the connection in `try/finally` and always `conn.close()` after marking the sync complete or failed.

### 9. [Medium] Health checks do not cover all backend dependencies and do not verify database writeability

References: `health.py:43-62`, `health.py:111-181`, `health.py:184-204`, `server.py:1709-1935`

`collect_deep_status()` only checks SQLite, Garmin, the knowledge base, and Moonshot. The backend also exposes WHOOP and Oura provider flows, but those dependencies are not surfaced in deep health at all. The SQLite check also only runs `SELECT 1` plus schema version lookup, so it can pass while writes are failing due to permissions or lock contention.

Recommendation: add provider-specific health probes for configured integrations and make the DB check verify a lightweight write transaction or other writeability signal.

## Additional Notes

- `store.py` appears reasonably safe from classic SQL injection. Dynamic SQL is limited and mostly built from trusted constants or typed integers.
- Input validation is still loose in several API models. Examples include unbounded `max_tokens`, unconstrained conversation `role`, and unbounded list/detail limits in `server.py:76-149`. Those are not the top blockers above, but they should be tightened before exposing this service beyond a trusted local environment.
- `auth.py` stores Garmin session state in a relative `.garmin_tokens` directory (`config.py:1`, `auth.py:38-48`) without explicit permission hardening. That is acceptable for a local dev harness, but weak for a service deployment.

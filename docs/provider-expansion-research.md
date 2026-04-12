# Wearable Data Provider Expansion Research (Oura + Apple Health)

_Date: 2026-04-12_

## Why this doc exists
Nyx is currently Garmin-first. This research outlines how to add additional **consumer wearable health data providers** into the same harness with minimal architectural churn, starting with the two biggest requests:

1. **Oura** (server-to-server OAuth API)
2. **Apple Health / HealthKit** (device-mediated sync via iOS app)

## Executive recommendation
- Build a **provider abstraction layer** in the backend now so Garmin, Oura, and Apple become pluggable ingest sources.
- Integrate **Oura + WHOOP in the initial ship** because both fit Nyx's existing backend sync model (OAuth + REST pull).
- Integrate **Apple Health second** with a thin iOS collector app because Apple Health data is governed through HealthKit entitlements and user-granted on-device access rather than a general Apple cloud REST API.

---

## "Agent team" deep-research findings

### Agent 1 — API surface and feasibility

#### Oura (high feasibility, medium effort)
What we verified:
- Oura provides API access for both personal data access and third-party integrations through its developer ecosystem and API application model.
- Oura explicitly points developers to Oura API v2 docs and app registration flow.
- Oura availability constraints matter: Gen3 / Ring 4 API access can depend on active Oura Membership status.

Implication for Nyx:
- Oura can be ingested similarly to Garmin using a backend OAuth token flow + scheduled incremental pulls.
- We should capture provider capability flags (e.g., membership-gated fields) to avoid treating missing data as outages.

Primary references:
- Oura Help: The Oura API (links to new developer portal + API v2 docs).
- Oura docs/portal links exposed from official Oura surfaces.

#### Apple Health / HealthKit (high user demand, higher effort)
What we verified:
- HealthKit access is attached to Apple app capabilities and explicit user consent.
- Apple policy language for HealthKit strongly constrains data usage and third-party sharing (health/fitness purpose only, explicit consent expectations, no ad-broker style use).

Inference for Nyx architecture:
- Nyx cannot rely on a generic "Apple Health cloud pull" comparable to Garmin/Oura REST ingestion.
- Instead, Nyx needs an **iOS client-side bridge** that reads authorized HealthKit types and uploads normalized records to Nyx backend.

Primary references:
- Apple developer agreement language around HealthKit API usage.
- Apple HealthKit developer documentation ecosystem.

---

### Agent 2 — Compliance and risk

#### Oura
Key risk items:
- OAuth token lifecycle, refresh storage, scope minimization.
- Membership-dependent data access for some users.
- Rate limiting and backfill throttling.

Mitigations:
- Encrypt token material at rest.
- Build sync cursors per endpoint.
- Add provider-specific retry/circuit breaker policy (reuse current Garmin resilience pattern).

#### Apple Health
Key risk items:
- HealthKit permission UX and consent flows can be denied/revoked at any time.
- Exporting data from device to Nyx backend requires clear privacy disclosures and narrowly scoped use.
- App Store review risk if feature intent and health value are unclear.

Mitigations:
- Implement granular sample-type consent requests and clear in-app rationale.
- Ship auditable data-use policy + export controls in onboarding.
- Start with read-only ingestion of core fitness metrics before expanding domains.

---

### Agent 3 — Data-model & harness integration

Current Nyx assumptions are Garmin-centric in naming and UX, but the backend already has useful primitives:
- Background sync jobs.
- Structured sync logs.
- Local-first SQLite persistence.

This supports a provider expansion with relatively small refactors.

## Proposed target architecture

### 1) Provider interface (backend)
Introduce a simple provider contract, e.g.:
- `authenticate()`
- `list_activity_summaries(start, cursor)`
- `get_activity_detail(id)`
- `list_daily_health(start, cursor)` (sleep/readiness/recovery where available)
- `normalize()` -> canonical Nyx schema

### 2) Canonical normalized entities
Add provider-agnostic tables/records (or views) so coaching logic can consume uniform fields:
- `activities` (run/workout events)
- `activity_samples` (timeseries samples)
- `daily_recovery` (sleep, resting HR, HRV, readiness proxies)
- `provider_accounts` + `provider_sync_state`

Keep provider-specific raw payload tables for traceability/debugging.

### 3) Sync orchestration
- Keep existing job manager semantics.
- Execute provider jobs independently with per-provider watermarks.
- Merge into shared normalized tables after validation.

---

## Provider-by-provider implementation plan

## Phase 1 — Oura + WHOOP integration (initial ship)

### Scope
- OAuth connect/disconnect for both providers.
- Historical backfill + incremental sync for both providers.
- Sleep/recovery/activity endpoints mapped into normalized entities.

### Deliverables
1. `providers/oura_auth.py` + `providers/whoop_auth.py` (OAuth flow + token refresh)
2. `providers/oura_fetch.py` + `providers/whoop_fetch.py` (endpoint wrappers, retry policy)
3. `providers/oura_normalize.py` + `providers/whoop_normalize.py` (payload mapping -> Nyx canonical schema)
4. API endpoints:
   - `POST /api/providers/oura/connect`
   - `POST /api/providers/oura/disconnect`
   - `POST /api/providers/oura/sync`
   - `POST /api/providers/whoop/connect`
   - `POST /api/providers/whoop/disconnect`
   - `POST /api/providers/whoop/sync`
5. Diagnostics updates showing provider-specific health and last successful sync.

### Acceptance criteria
- New Oura account can connect and backfill without blocking Garmin sync.
- Provider outage does not fail unrelated providers.
- Canonical metrics render in existing dashboard/coach paths.

## Phase 2 — Apple Health bridge (iOS)

### Scope
- Minimal iOS companion app with HealthKit read permissions.
- On-device extraction + batching uploader to Nyx backend.
- Background delivery for selected sample types.

### Deliverables
1. iOS module/app:
   - HealthKit authorization flow.
   - Query + delta-upload pipeline.
   - Local queue for offline uploads.
2. Backend ingestion endpoint:
   - `POST /api/providers/apple-health/ingest`
   - Idempotency keys + signature verification.
3. Privacy controls:
   - Per-type toggles.
   - Revoke/delete provider data path.

### Acceptance criteria
- User can authorize selected types and sync at least daily summaries + workouts.
- Revoked permissions are handled gracefully.
- Data lineage is preserved from source sample to normalized record.

---

## Expanded wearable landscape (beyond Oura + Apple)

You asked for the bigger field — agreed. There are many viable providers and connector surfaces. The practical question is not only “who exists,” but “how do we get reliable access with acceptable compliance risk?”

### Priority longlist for Nyx

| Provider / Platform | Access model | What matters for Nyx |
|---|---|---|
| **Fitbit** | OAuth + Web API + subscriptions/webhooks | Strong breadth of health endpoints. **Important timing:** Fitbit’s legacy Web API page currently flags deprecation in **September 2026** and points to migration guidance, so connector work should be planned with migration in mind. |
| **WHOOP** | OAuth + API docs (v2), app approval flow | WHOOP has an active developer platform. Migration and webhook lifecycle changes have happened (v1 webhook removal), so versioning discipline is required. |
| **Withings** | Partner Hub + Public API + SDK options | Explicit healthcare/RPM framing; multiple integration modes (public API, SDK, advanced plans). Good fit for sleep/biometrics expansion. |
| **Polar** | AccessLink API (OAuth2 + webhook events) | Mature OAuth2 flow + signed webhook delivery. Good if we want training + sleep from Polar users. |
| **Samsung Health** | Android SDK integration into Samsung Health app data store | Rich health data via mobile SDK (including read/write types). This is app-mediated, not pure backend cloud pull. |
| **Google Health Connect** | Android on-device health data hub (app-mediated) | Very useful as a “fan-in” path from many Android apps/wearables; supports background read/sync patterns. |
| **COROS** | Partner/API-application model | COROS confirms an API application path for developers in support docs; treat as partner-approval gated. |
| **Eight Sleep** | First-party app + explicit Apple Health / Google Health Connect integration mentions in legal docs | Eight Sleep is strategically useful for sleep/recovery. Most robust near-term ingestion path is via Apple Health / Health Connect fan-in, with direct API access treated as partner/enterprise exploration. |
| **Dexcom (CGM)** | Official developer/partner API program | Medical-grade glucose stream potential; higher compliance burden but valuable for metabolic + training correlation use-cases. |

### Suggested next-wave order after initial ship (Oura + WHOOP + Apple)

1. **Fitbit** (large installed base, but build with migration-proofing from day 1)  
2. **Withings** (strong biomarker coverage)  
3. **Polar** (solid sports physiology data + webhooks)  
4. **Samsung Health + Health Connect** (Android ecosystem multiplier)  
5. **Eight Sleep** (sleep enrichment via Apple Health/Health Connect first, direct path later)

---

## Suggested rollout sequence (8–12 weeks)

1. Week 1-2: provider abstraction + schema migration groundwork.
2. Week 3-5: Oura + WHOOP OAuth, pull sync, normalization, diagnostics.
3. Week 6: hardening (retry, cursors, reprocessing, observability) across Garmin/Oura/WHOOP.
4. Week 7-10: Apple Health iOS bridge MVP + backend ingest.
5. Week 11-12: QA, data validation against known athlete baselines, onboarding UX.

---

## Open questions to resolve before build

1. Do we want "fitness-only" first (workouts/sleep/recovery) or broader medical-style HealthKit types later?
2. Should provider credentials be stored only locally (current Nyx posture) or in a managed secret store for multi-user hosted deployments?
3. Is Apple Health ingestion limited to iOS only for v1, with Android parity via Health Connect later?
4. Do we expose provider conflict resolution (same workout from Garmin + Apple) with deterministic precedence rules?

---

## Source notes (official references used)
- Oura Help Center — **The Oura API**: official guidance on app registration, API v2 docs, and membership-linked availability.
  - https://support.ouraring.com/hc/en-us/articles/4415266939155-The-Oura-API
- Oura Cloud / Developer portal entrypoints (linked from Oura support page).
  - https://cloud.ouraring.com
  - https://developer.ouraring.com
- Apple Developer Program information PDF containing HealthKit API usage constraints (health/fitness purpose + consent/sharing restrictions).
  - https://developer.apple.com/programs/information/Apple_Developer_Program_Information_8_12_15.pdf
- Apple Developer documentation hub for HealthKit APIs.
  - https://developer.apple.com/documentation/healthkit
- Apple Developer Program License Agreement (current support page; includes HealthKit-use restriction language).
  - https://developer.apple.com/programs/apple-developer-program-license-agreement/
- Fitbit Web API reference page (includes legacy API deprecation notice and endpoint taxonomy).
  - https://dev.fitbit.com/build/reference/web-api/
- WHOOP developer docs (v2 platform and migration context).
  - https://developer.whoop.com/docs/introduction/
- Withings Partner Hub (Public API, plans, API reference, SDK positioning).
  - https://developer.withings.com/
- Polar AccessLink API (OAuth2 flow + webhook delivery/signature model).
  - https://www.polar.com/accesslink-api/
- Samsung Health Data SDK overview (data access model, supported types, restrictions).
  - https://developer.samsung.com/health/data/overview.html
- Google Health Connect developer docs (Android compatibility + sync/read patterns).
  - https://developer.android.com/health-and-fitness/health-connect
- COROS support page confirming developer API application route.
  - https://support.coros.com/hc/en-us/articles/360040256531-Supported-3rd-Party-Apps
- Eight Sleep legal pages referencing Apple Health and Google Health Connect integrations.
  - https://www.eightsleep.com/mx-en/legal/consumer-health-data-privacy-policy/
  - https://www.eightsleep.com/mx-en/app-terms-conditions/
- Dexcom developer API overview.
  - https://developer.dexcom.com/docs

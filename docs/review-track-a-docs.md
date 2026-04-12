# Review Track A: Documentation and Release Framing

Date: 2026-04-12

## Executive Summary

Nyx is not documentation-ready for a pilot release yet.

- `README.md` is directionally correct on architecture, but it is not a reliable operator guide for the current web/deploy path.
- `docs/web-app-build-spec.md` still works as an origin spec, but several sections are now aspirational rather than descriptive.
- `docs/provider-expansion-research.md` is useful as roadmap research, but it overstates what provider work is user-visible today.
- `docs/web-onboarding-plan.md` is obsolete as a plan; most of the described work already shipped.

The biggest pilot-release risks are setup confusion, stale onboarding framing, and provider language that implies broader product support than the current UI and coach flows actually provide.

## Verification Method

- Reviewed the target docs plus the current implementation in `server.py`, `onboarding.py`, `health.py`, `coach.py`, `evals.py`, `providers/*`, `scripts/*`, `deploy/*`, and `apps/nyx-client/*`.
- Verified shipped behavior with:
  - `.venv/bin/python -m unittest tests.test_onboarding tests.test_server_async tests.test_provider_oura tests.test_whoop_provider`
  - `PATH="/home/deck/Work/Nyx/.runtime/node/bin:$PATH" /home/deck/Work/Nyx/.runtime/node/bin/npm run typecheck`

## Document Status Matrix

| Document | Status | Assessment | Recommended action |
|---|---|---|---|
| `README.md` | Partial | Accurate on core stack, incomplete and internally inconsistent for setup/deploy | Rewrite as operator guide |
| `docs/web-app-build-spec.md` | Partial / historical | Directionally right, but not a faithful description of the shipped UI | Update or split into implemented-vs-future |
| `docs/provider-expansion-research.md` | Roadmap, not status | Useful research, but not accurate as current integration framing | Reframe as roadmap / backend groundwork |
| `docs/web-onboarding-plan.md` | Obsolete | Most proposed work is already implemented | Replace with current-state doc or mark historical |

## Findings

### 1. High: `README.md` is not sufficient as a pilot operator guide

What is accurate:

- Core architecture is correct: FastAPI backend, Expo web client, TanStack Query, local-first SQLite.
- The documented Oura and WHOOP API endpoints exist.

What is missing or misleading:

- The README does not document the pilot-style single-origin web path that already exists:
  - `scripts/build-web.sh`
  - `scripts/run-nyx-dual.sh`
  - `deploy/systemd/nyx.service`
  - FastAPI serving `apps/nyx-client/dist`
- `Setup` step 6 says “Install and start the web client” but only shows `npm install`; it never actually tells the user to run `npm run web`.
- The README hardcodes the web client talking to `http://127.0.0.1:8000`, but the repo also supports:
  - Tailscale/LAN hosts
  - same-origin production serving
  - default deploy port `8765`
- The API list omits shipped endpoints that matter for the current app:
  - `/api/onboarding`
  - `/api/onboarding/complete`
  - `/api/onboarding/reset`
  - `/api/coach/thread/current`
  - `/api/coach/thread`
  - `/api/coach/feedback`
- The CLI reference omits the implemented `python3 cli.py onboarding` flow.
- The Garmin token story is internally inconsistent:
  - setup says tokens live in `~/.garminconnect`
  - file map says `.garmin_tokens/`
  - runtime checks both, with `.garmin_tokens` as the config default
- Troubleshooting says “Anthropic dependency missing,” but the coach stack uses the OpenAI SDK with Moonshot.
- The live eval story is inconsistent with code:
  - README says live evals need `MOONSHOT_API_KEY`
  - `evals.py` still requires `ANTHROPIC_API_KEY`

Why this matters:

- A pilot user or operator can follow the README and still miss the real deploy path, the actual frontend start command, or the credential required for live evals.

Recommended action:

- Rewrite the README as the primary operator doc.
- Split it into `Local dev` and `Pilot deploy`.
- Document `scripts/build-web.sh`, `scripts/run-nyx-dual.sh`, `NYX_PORT`, `NYX_LOCAL_HOST`, `NYX_TAILSCALE_HOST`, and the same-origin production path.
- Fix the Garmin token explanation and resolve or explicitly call out the live-eval env var mismatch.

### 2. High: `docs/web-onboarding-plan.md` is obsolete as a “plan”

The document says these do not exist yet:

- FastAPI onboarding endpoints
- Expo onboarding route logic
- fixed reset semantics

All three are already implemented:

- `server.py` exposes:
  - `GET /api/onboarding`
  - `PUT /api/onboarding`
  - `POST /api/onboarding/complete`
  - `POST /api/onboarding/reset`
- `apps/nyx-client/app/onboarding.tsx` is shipped
- `onboarding.reset_onboarding()` now clears answers and progress metadata
- Home routes into onboarding when incomplete
- Coach is gated behind onboarding both in the API and in the web UI

The shared helpers proposed by the doc also already exist:

- `get_onboarding_questions`
- `get_onboarding_state`
- `save_onboarding_answers`
- `complete_onboarding`
- `reset_onboarding`

One important mismatch remains:

- The doc says `POST /api/onboarding/complete` validates that the active flow is sufficiently answered.
- The implementation does not require non-empty answers; it fills missing answers with empty strings and still marks onboarding complete.

Additional gap:

- The doc’s frontend test expectations are not met. I did not find app-level frontend tests for the onboarding flow; only backend tests and a passing frontend typecheck.

Why this matters:

- Anyone reading this file as current status will come away with the wrong picture of what already shipped and what still needs work.

Recommended action:

- Replace this file with a current-state onboarding behavior doc, or add a strong “historical plan / implemented” banner and update it.
- Document the real completion semantics.
- Note the current testing reality: backend coverage exists, frontend behavior is not yet covered by dedicated UI tests.

### 3. High: `docs/provider-expansion-research.md` overstates current provider readiness

What is true today:

- The backend has real provider groundwork:
  - provider tables in SQLite
  - Oura auth/sync/normalization
  - WHOOP auth/sync/normalization
  - Apple Health placeholder provider
  - provider-related backend tests

What the doc overstates:

- The doc treats provider expansion as if it already feeds the existing product experience.
- That is not true today:
  - Home, Athlete, Coach, and training plans still read Garmin-centric `runs` and metadata
  - coach prompt construction in `coach.py` still serializes Garmin run history from `runs`
  - `daily_recovery` and normalized provider `activities` are not surfaced in current web screens
- The doc presents a provider abstraction as the active integration layer, but:
  - `providers/whoop.py` is still a stub that says WHOOP is not implemented
  - real WHOOP sync logic lives directly in `server.py`
  - Garmin still uses the legacy sync pipeline
- The doc says diagnostics should show provider-specific health and last successful sync.
  - Provider status exists in `health.collect_status()`
  - the current web Diagnostics screen does not render provider-specific status or controls
- Apple Health Phase 2 is not started in product terms:
  - no iOS bridge
  - no ingest endpoint
  - no user-facing controls

Why this matters:

- The document currently reads like present capability when it is closer to roadmap plus partial backend implementation.

Recommended action:

- Reframe the file as `research + backend groundwork`.
- Explicitly state:
  - Oura and WHOOP are backend/API integrations
  - Apple Health is not implemented
  - current UI and coach remain Garmin-first
- Link to `docs/review-nyx-providers.md` for implementation caveats.

### 4. Medium: `docs/web-app-build-spec.md` is directionally right but no longer describes the shipped UI closely

What still matches:

- Stack choice
- Monochrome visual direction
- Four primary destinations
- Data-first framing
- Structured coach responses with evidence

What no longer matches implementation well:

- The spec omits the shipped onboarding route and onboarding gating.
- Home CTA logic is outdated. Actual backend next-action order is:
  - diagnostics failures
  - no runs
  - onboarding incomplete
  - no VDOT
  - coach
- The spec assumes settings entry points and sheet-based secondary actions; those do not exist.
- Athlete is supposed to emphasize weekly mileage trend and provide run-detail access from recent runs.
  - weekly mileage is computed in the backend
  - the Athlete screen does not render it
  - the Athlete recent runs list is not tappable
- Coach thread persistence, “New chat,” and response feedback ratings are implemented but not described.
- The coach context strip and composer are not sticky/pinned in the current implementation.
- Diagnostics does not provide:
  - `Run sync`
  - `Run doctor`
  - environment details
  - current sync job state/logs
- Diagnostics does provide a feedback summary that the spec does not mention.
- The backend contract section hardcodes `http://127.0.0.1:8000`, which is only one dev mode and not the deploy path.

Why this matters:

- The file is still useful as a design-source document, but it is not reliable as an implementation spec.

Recommended action:

- Update it to reflect the shipped app, or split it into:
  - `implemented UI`
  - `future UX ideas`
- Add onboarding, persisted coach threads, and feedback flows.
- Mark unshipped items as aspirational instead of implied current behavior.

### 5. Medium: Cross-document contradictions will confuse setup and release framing

- README and build spec frame the web app as talking to `127.0.0.1:8000`, while deploy scripts and systemd default to `8765`, and the production client uses same-origin.
- Build spec says Home should go from sync/diagnostics straight to coach, while onboarding doc says Home should prioritize onboarding when incomplete. The backend now follows the onboarding doc.
- README does not mention onboarding as a web surface, while the onboarding plan says it does not exist yet, even though it now exists and blocks coach usage.
- The provider research title says “Oura + Apple Health,” while the content and current backend work also include WHOOP.

## Implemented But Underdocumented

- Web onboarding flow with autosave, skip, reset, resume, and coach intercept
- Onboarding API endpoints
- Persisted coach threads and `New chat`
- Coach feedback capture and Diagnostics feedback summary
- FastAPI static serving of built web assets
- Provider status in `GET /api/status`

## Documented Or Implied But Not Actually Shipped

- Apple Health ingest bridge and endpoint
- User-visible provider management UI in the web app
- Provider-specific diagnostics in the web app
- Settings UI / overflow menu / sheet interactions
- Sticky coach composer
- Run-detail navigation from Athlete recent runs
- Dedicated frontend onboarding test coverage
- A documentation-consistent live-eval auth story

## Recommendations For Pilot Release Readiness

1. Update `README.md` first. It is the main entry point and currently carries the most setup risk.
2. Replace `docs/web-onboarding-plan.md` with a current-state doc, or mark it historical.
3. Reframe `docs/provider-expansion-research.md` as roadmap/research, not current product capability.
4. Refresh `docs/web-app-build-spec.md` so it describes the app that actually ships today.
5. Resolve the live-eval credential mismatch before using the docs as release material.
6. Add a short “Current release scope” section somewhere central:
   - Garmin-first user experience
   - Oura and WHOOP backend groundwork
   - Apple Health not implemented yet

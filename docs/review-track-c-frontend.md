# Track C Frontend Review

Date: 2026-04-12
Scope: `apps/nyx-client/`
Verdict: Not ready for pilot release.

## What I Checked

- `app/` structure and required screens
- shared components under `components/`
- API wrapper in `lib/api/client.ts`
- design tokens in `lib/theme/tokens.ts`
- dependency manifest and lockfile
- frontend endpoint usage against `README.md` and `server.py`

## Findings

### High

1. `/api/athlete/summary` contract drift causes incorrect sync/cache UI on successful loads.
   - The client reads `athlete.meta.cached` and `athlete.meta.last_sync` in `apps/nyx-client/app/(tabs)/index.tsx:125-141` and `apps/nyx-client/app/(tabs)/athlete.tsx:37-39`.
   - The backend summary payload does not return a `meta` object; it returns `last_sync_status` and `last_sync_completed_at` instead in `server.py:879-896`.
   - Impact: Home shows `data = live` even though Nyx is explicitly local-cache backed, and both Home/Athlete fall back to "no successful sync yet" copy even when sync metadata exists.
   - Why this slipped: every API method is typed as `any` in `apps/nyx-client/lib/api/client.ts:49-130`, so TypeScript cannot catch response-shape drift.

### Medium

2. There is no production error boundary around the app/query tree.
   - `apps/nyx-client/app/_layout.tsx:41-50` mounts `QueryClientProvider` and `Stack`, but no route-level or app-level error boundary.
   - Impact: a render exception on any screen has no branded recovery path and will fall back to default runtime behavior.

3. Core screens hide auth/network/CORS failures behind placeholder copy instead of explicit error states.
   - Home (`apps/nyx-client/app/(tabs)/index.tsx:28-39,69-230`), Athlete (`apps/nyx-client/app/(tabs)/athlete.tsx:13-136`), Diagnostics (`apps/nyx-client/app/(tabs)/diagnostics.tsx:15-165`), and Run Detail (`apps/nyx-client/app/run/[activityId].tsx:14-64`) do not render query error states.
   - The backend enforces bearer auth on `/api/*` when `NYX_API_TOKEN` is set and applies CORS policy to those routes (`server.py:158-185,205-220`; `README.md:157-171`).
   - Impact: missing token, wrong origin, or backend outage often degrades into `Loading`, `unknown`, `n/a`, or empty sections instead of an actionable failure message.
   - Concrete example: the Home screen's metrics refresh path awaits `apiRequestRefresh()` without a local `try/catch` (`apps/nyx-client/app/(tabs)/index.tsx:92-95,236-239`).

4. Coach send can fail before its own error handling runs.
   - `submit()` calls `ensureThreadId()` before entering the `try/catch` in `apps/nyx-client/app/(tabs)/coach.tsx:156-173`.
   - Impact: first-send and prompt-click flows can produce an unhandled rejection if current-thread lookup fails.

5. The API client has no timeout, abort wiring, or explicit retry/backoff strategy, and mutation paths are single-shot.
   - `apps/nyx-client/lib/api/client.ts:27-46` wraps `fetch` directly with no timeout and no `AbortSignal`.
   - React Query covers read queries with library defaults, but imperative actions such as sync start, metric recalculation, onboarding updates, coach messaging, eval runs, and feedback posts all fail immediately on a transient network issue.
   - `Content-Type: application/json` is sent on every request, including GETs (`apps/nyx-client/lib/api/client.ts:28-34`), which forces unnecessary CORS preflights for cross-origin/LAN use.

6. The documented backend API surface and the frontend's actual integration surface diverge.
   - `README.md:35-55` documents endpoints the client never calls directly: `/api/health/deep`, `/api/vdot`, `/api/hr-zones`, all Oura/WHOOP connect/disconnect/sync endpoints, and `/api/training-plan`.
   - The client depends on undocumented routes in `apps/nyx-client/lib/api/client.ts:53-80,113-120`: `/api/onboarding`, `/api/onboarding/complete`, `/api/onboarding/reset`, `/api/coach/thread/current`, `/api/coach/thread`, and `/api/coach/feedback`.
   - `generateTrainingPlan()` exists in the client (`apps/nyx-client/lib/api/client.ts:103-112`) but has no caller.
   - Impact: the README overstates client coverage, while some client-critical routes are absent from the published API contract.

7. The design system is only partially tokenized.
   - `apps/nyx-client/lib/theme/tokens.ts:3-49` defines only base palette, spacing, radius, fonts, and a `none` shadow.
   - Semantic status styling and many layout/typography values are still hardcoded inside components such as `apps/nyx-client/components/StatusBadge.tsx:26-63` and `apps/nyx-client/components/AppFrame.tsx:136-258`.
   - Impact: consistency depends on per-component constants rather than a reusable token contract, which makes future theming and maintenance harder.

## Screens And Components

- Required screens are present:
  - Home: `apps/nyx-client/app/(tabs)/index.tsx`
  - Athlete: `apps/nyx-client/app/(tabs)/athlete.tsx`
  - Coach: `apps/nyx-client/app/(tabs)/coach.tsx`
  - Diagnostics: `apps/nyx-client/app/(tabs)/diagnostics.tsx`
  - Run Detail: `apps/nyx-client/app/run/[activityId].tsx`
- `app/onboarding.tsx` is also present and is integrated into the Coach gate and Home next-action flow.
- Shared components are small and generally correct. I did not find a release-blocking logic bug inside `Surface`, `MetricPill`, `SignalRow`, `FeedbackRow`, or `EvidenceChip`.

## API Coverage

### Used By The Client

- `/api/status`
- `/api/doctor`
- `/api/athlete/summary`
- `/api/runs?limit=N`
- `/api/runs/{activity_id}`
- `/api/coach/context`
- `/api/sync`
- `/api/sync/{job_id}`
- `/api/vdot/recalc`
- `/api/coach/message`
- `/api/evals/run`

### Not Used Directly From The README Contract

- `/api/health/deep`
- `/api/vdot`
- `/api/hr-zones`
- `/api/providers/oura/connect`
- `/api/providers/oura/disconnect`
- `/api/providers/oura/sync`
- `/api/providers/whoop/connect`
- `/api/providers/whoop/disconnect`
- `/api/providers/whoop/sync`
- `/api/training-plan`

### Used By The Client But Missing From `README.md`

- `/api/onboarding`
- `/api/onboarding/complete`
- `/api/onboarding/reset`
- `/api/coach/thread/current`
- `/api/coach/thread`
- `/api/coach/feedback`

## Package Review

- `apps/nyx-client/package.json:14-32` includes the runtime packages imported by the current client.
- I could not run `npm audit` locally because `node`, `npm`, and `npx` are not installed in this environment.
- I audited `apps/nyx-client/package-lock.json` against OSV on 2026-04-12 instead. Result: 0 known vulnerabilities across 661 unique npm package/version pairs in the lockfile.

## Verification Gaps

- I could not run `npm run typecheck` or `npm run build:web` because there is no JavaScript toolchain on `PATH` in this environment.
- No automated test files were found under `apps/nyx-client/`.

## Recommendation

Do not call the web client pilot-ready until findings 1 through 4 are fixed and a real `typecheck` plus `build:web` pass is captured in a Node-enabled environment.

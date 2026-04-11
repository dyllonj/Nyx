# Nyx Web App Build Spec

## Purpose

This document defines the first real product UI for Nyx.

The goal is a local-first web app that feels sleek, severe, and calm rather than like a generic AI dashboard. It should be simple to build now, mobile-friendly from day one, and architected so the same frontend can later ship as a native mobile app with minimal rewrite.

## Product Goals

- Replace the current command-heavy dev flow with a single app surface.
- Keep the visual language monochrome: whites and greys on black only.
- Make the default UX data-first, not chat-first.
- Preserve the existing Python harness as the source of truth for sync, metrics, evals, and coach logic.
- Use a frontend stack that can target web now and native mobile later.

## Non-Goals

- Multi-user auth
- Cloud deployment
- Social features
- A polished consumer onboarding funnel
- A marketing site

## Guiding UX Principles

1. Calm control surface, not AI toy.
   The landing screen should answer: what is my state, what changed, what should I do next.

2. Data first, AI second.
   Chat is one tab, not the whole product.

3. One primary action per screen.
   Every page should have a clear next move.

4. Evidence is part of the UI.
   Coach responses should always show supporting run data, zones, paces, and retrieved source labels.

5. Monochrome hierarchy through type, spacing, and borders.
   No gradients, glow, glassmorphism, or decorative color accents.

6. Mobile-first structure.
   The web layout should work on a phone-width viewport without feeling like a desktop page shrunk down.

## Anti-Patterns To Avoid

- Giant hero gradients
- Purple or blue AI-brand color palettes
- Equal-weight metric cards with no information hierarchy
- Empty “Ask Nyx anything” landing pages
- Fake terminal styling everywhere
- Dense desktop tables as the primary mobile presentation
- Over-rounded generic SaaS cards

## Recommended Stack

### Frontend

- Expo Router with the latest stable Expo SDK at implementation time
- React Native + React Native Web
- TypeScript
- TanStack Query for server-state fetching and invalidation
- `expo-font` for bundled typography

### Backend

- FastAPI as a thin local API wrapper around the current Python modules
- Uvicorn for local development
- Pydantic response models

### Why This Stack

- Expo Router gives one navigation model across web, iOS, and Android.
- React Native Web keeps layout logic portable to mobile later.
- FastAPI lets us keep `sync_engine.py`, `coach.py`, `health.py`, `evals.py`, and `vdot_zones.py` intact instead of rewriting business logic.
- TanStack Query keeps async state simple without adding a heavy client-side state framework.

## Information Architecture

Top-level navigation:

- Home
- Athlete
- Coach
- Diagnostics

Secondary access:

- Settings from a top-right icon or sheet
- Run details from Athlete and Coach evidence chips

Compact screens:

- Bottom tab bar with 4 destinations

Wide screens:

- Left navigation rail
- Secondary content panes where useful

## App Shell

### Layout Rules

- Use a centered content column with max width on desktop
- Use safe-area-aware padding on mobile
- Use sticky bottom navigation on compact screens
- Use sticky coach composer in the Coach screen
- Use sheets for transient actions instead of full-screen modals when possible

### Primary Header

Each screen gets:

- Screen title
- One-line status or subtitle
- One primary action max
- Optional overflow menu for secondary actions

## Screen Specs

### 1. Home

Purpose:

- Show current athlete state
- Surface the next action
- Make sync and coaching feel one tap away

Content order:

1. Hero status panel
2. Next action row
3. Current fitness strip
4. Recent runs
5. System state

Hero status panel should show:

- Last sync status
- Last sync freshness
- Current VDOT
- Easy pace
- Zone 2 range

Primary CTA logic:

- If sync has never run: `Sync Garmin`
- If doctor has failures: `Open Diagnostics`
- Otherwise: `Open Coach`

### 2. Athlete

Purpose:

- Be the factual source of athlete state
- Make metrics legible without looking like a spreadsheet

Sections:

- Training load summary
- VDOT and training paces
- HR zones
- Recent runs list
- Run detail drawer or detail page

The default emphasis should be:

- Recent 42-day load
- Weekly mileage trend
- REI trend
- Current VDOT
- Easy pace and threshold pace

### 3. Coach

Purpose:

- Hold the coaching conversation
- Make the evidence behind each answer visible and tappable

Structure:

- Pinned athlete context strip
- Scrollable thread
- Response cards with `Verdict`, `Evidence`, `Next step`
- Sticky composer

Evidence UI:

- Each evidence bullet becomes a chip or row that links to a run detail or metric definition
- Retrieved knowledge references show exact source labels such as `recovery` or `training_load`

Default prompts above the composer:

- What should my easy pace be?
- Am I running easy too hard?
- What should I do this week?
- Why did my last run feel harder?

### 4. Diagnostics

Purpose:

- Keep all dev-facing state in one place
- Make failures legible without dropping to the terminal

Sections:

- Setup readiness
- Last sync log and current sync job state
- Doctor checks
- Eval results
- Environment details

Primary actions:

- Run sync
- Run doctor
- Run offline evals
- Run live evals

## First-Pass Wireframes

### Home

```text
+--------------------------------------------------+
| NYX                                              |
| Local-first running intelligence                 |
|                                                  |
| [ Synced 2h ago ] [ VDOT 48 ] [ Z2 131-144 bpm ] |
| Easy pace 5:22-6:24/km                           |
|                                                  |
| Primary action: Open Coach                       |
+--------------------------------------------------+

+--------------------+  +-------------------------+
| Next action        |  | System state            |
| Ask about easy day |  | Doctor: 1 warning       |
| Threshold update   |  | KB: ready               |
+--------------------+  +-------------------------+

+--------------------------------------------------+
| Recent runs                                       |
| 2026-04-08  9.6 km  5:39/km  138 bpm  REI 78      |
| 2026-04-06  12.1km  5:21/km  145 bpm  REI 74      |
| 2026-04-03  7.8 km  4:58/km  156 bpm  REI 72      |
+--------------------------------------------------+
```

### Athlete

```text
+--------------------------------------------------+
| Athlete                                           |
| Recent fitness and training metrics               |
+--------------------------------------------------+

+--------------------+  +-------------------------+
| 42d load           |  | REI trend               |
| 18 runs / 146 km   |  | 76.8 avg, +2.1 vs prior |
+--------------------+  +-------------------------+

+--------------------------------------------------+
| VDOT 48                                           |
| Easy 5:22-6:24/km                                |
| Marathon 4:20/km                                 |
| Threshold 4:08/km                                |
| Interval 3:45/km                                 |
+--------------------------------------------------+

+--------------------------------------------------+
| HR zones                                          |
| Z1 119-131  Z2 131-144  Z3 144-157               |
| Z4 157-170  Z5 170-185                           |
+--------------------------------------------------+

+--------------------------------------------------+
| Recent runs                                       |
| [cards/list, tap for detail]                      |
+--------------------------------------------------+
```

### Coach

```text
+--------------------------------------------------+
| Coach                                             |
| VDOT 48  |  Easy 5:22-6:24/km  |  Z2 131-144 bpm |
+--------------------------------------------------+

| User: Am I running my easy runs too hard?         |

+--------------------------------------------------+
| Verdict                                           |
| Your easy days are trending slightly hard.        |
|                                                  |
| Evidence                                          |
| - 2026-04-06: 12.1 km at 145 bpm sat above Z2    |
| - 2026-04-08: 9.6 km at 138 bpm stayed in range  |
| - Current easy pace is 5:22-6:24/km from VDOT 48 |
|                                                  |
| Next step                                         |
| Cap the next two easy runs at 144 bpm.           |
+--------------------------------------------------+

| [ What should my easy pace be? ] [ Why fatigue? ]|
| ------------------------------------------------ |
| Ask Nyx...                               [Send]  |
```

### Diagnostics

```text
+--------------------------------------------------+
| Diagnostics                                       |
| Harness state, sync, evals, and readiness         |
+--------------------------------------------------+

+--------------------+  +-------------------------+
| Doctor             |  | Last sync               |
| 6 pass / 1 warn    |  | success, 2h ago         |
+--------------------+  +-------------------------+

+--------------------------------------------------+
| Checks                                             |
| [PASS] sqlite_schema                              |
| [PASS] garmin_dependency                          |
| [WARN] anthropic_dependency                       |
| [PASS] knowledge_base                             |
+--------------------------------------------------+

+--------------------------------------------------+
| Evals                                              |
| easy_pace      PASS                                |
| easy_hr_zone   PASS                                |
| easy_too_hard  WARN                                |
+--------------------------------------------------+
```

## Visual Design System

### Color Tokens

- `bg-app`: `#050505`
- `bg-surface-1`: `#0b0b0b`
- `bg-surface-2`: `#121212`
- `bg-surface-3`: `#1a1a1a`
- `border-subtle`: `#202020`
- `border-strong`: `#2b2b2b`
- `text-primary`: `#f5f5f5`
- `text-secondary`: `#b8b8b8`
- `text-tertiary`: `#7a7a7a`
- `text-inverse`: `#050505`
- `action-primary-bg`: `#f5f5f5`
- `action-primary-text`: `#050505`

### Typography

- Headings: `Space Grotesk`
- Body: `IBM Plex Sans`
- Metrics and run data: `IBM Plex Mono`

Type scale:

- Display: 40/44
- H1: 28/32
- H2: 22/28
- H3: 18/24
- Body: 15/22
- Small: 13/18
- Mono stat: 13/18

Rules:

- Use all-caps sparingly for section labels only
- Use monospaced numerals for pace, HR, distance, and dates
- Avoid centering text except in empty states

### Spacing

- Base unit: 4
- Common spacing: 8, 12, 16, 20, 24, 32
- Screen padding compact: 16
- Screen padding regular: 24

### Corners and Borders

- Card radius: 18
- Pill radius: 999
- Border width: 1
- Use borders instead of shadows

### Motion

- Screen enter: 140ms fade + slight upward translate
- Card reveal: 120ms stagger
- Bottom sheet: spring
- Avoid decorative looping animation

## Core Component Inventory

App shell:

- `AppFrame`
- `TopBar`
- `BottomTabs`
- `SideRail`
- `PrimaryActionButton`
- `StatusPill`

Data display:

- `MetricPanel`
- `MetricStrip`
- `SectionHeader`
- `RunList`
- `RunRow`
- `RunDetailSheet`
- `TrendSparkline`

Coach:

- `CoachThread`
- `CoachMessageCard`
- `EvidenceList`
- `EvidenceChip`
- `PromptChipRow`
- `CoachComposer`

Diagnostics:

- `DoctorCheckList`
- `EvalResultsList`
- `SyncProgressCard`
- `LogPanel`

## Route Map

```text
app/
  _layout.tsx
  (tabs)/
    _layout.tsx
    index.tsx           # Home
    athlete.tsx         # Athlete
    coach.tsx           # Coach
    diagnostics.tsx     # Diagnostics
  run/
    [activityId].tsx    # Run detail
  settings.tsx
```

## Suggested Frontend Folder Structure

```text
app/
components/
  app-shell/
  coach/
  diagnostics/
  athlete/
  home/
lib/
  api/
  theme/
  format/
  hooks/
assets/
```

## Backend API Contract

The web app should talk only to a local FastAPI service on `http://127.0.0.1:8000`.

### Read APIs

- `GET /api/status`
  - wraps `health.collect_status`

- `GET /api/doctor`
  - returns doctor checks and summary

- `GET /api/athlete/summary`
  - returns core summary for Home and Athlete
  - includes total runs, recent load, REI trend, current VDOT, easy pace, threshold pace, HR zones

- `GET /api/runs?limit=50`
  - recent runs list

- `GET /api/runs/{activity_id}`
  - run detail including splits and computed metrics

- `GET /api/vdot`
  - current VDOT, paces, estimate date, qualifying run count

- `GET /api/hr-zones`
  - parsed HR zone payload

- `GET /api/evals`
  - latest stored eval results if available

- `GET /api/coach/context`
  - compact athlete context summary for UI strips

### Mutating APIs

- `POST /api/sync`
  - starts a sync job
  - returns `job_id`

- `GET /api/sync/{job_id}`
  - polling endpoint for job status and progress messages

- `POST /api/vdot/recalc`
  - forces VDOT recompute and HR zone refresh

- `POST /api/onboarding/start`
  - optional later if onboarding moves fully into the app

- `POST /api/coach/message`
  - request body: conversation history plus user message
  - response: structured coach reply with `verdict`, `evidence`, `next_step`, `raw_text`, `sources`

- `POST /api/evals/run`
  - request body: `{ "live": false }` or `{ "live": true }`

### Example Response Shapes

`GET /api/athlete/summary`

```json
{
  "total_runs": 84,
  "recent_42d_runs": 18,
  "recent_42d_distance_km": 146.2,
  "ae_baseline": 0.0314,
  "rei_trend": {
    "label": "improving",
    "recent_avg": 76.8,
    "delta_vs_prior": 2.1
  },
  "vdot": {
    "value": 48.0,
    "estimated_at": "2026-04-10",
    "easy_pace": "5:22-6:24",
    "threshold_pace": "4:08",
    "marathon_pace": "4:20",
    "interval_pace": "3:45"
  },
  "hr_zones": {
    "max_hr": 185,
    "resting_hr": 52,
    "zones": [
      {"zone": 1, "name": "Recovery", "hr_low": 119, "hr_high": 131},
      {"zone": 2, "name": "Easy", "hr_low": 131, "hr_high": 144}
    ]
  }
}
```

`POST /api/coach/message`

```json
{
  "verdict": "Your easy days are slightly drifting high.",
  "evidence": [
    {
      "label": "2026-04-06 run",
      "kind": "run",
      "activity_id": 123456789,
      "text": "12.1 km at 145 bpm sat just above Zone 2."
    },
    {
      "label": "Current VDOT",
      "kind": "metric",
      "text": "VDOT 48 gives an easy range of 5:22-6:24/km."
    },
    {
      "label": "training_load",
      "kind": "knowledge",
      "source": "training_load",
      "text": "Accumulated fatigue can push easy-day HR upward."
    }
  ],
  "next_step": "Hold the next two easy runs at 144 bpm or below.",
  "raw_text": "Full formatted coach response..."
}
```

## Data Flow

### Sync

1. User taps `Sync Garmin`
2. Frontend `POST /api/sync`
3. Backend starts a background job wrapping `sync_engine.run_sync`
4. Frontend polls `GET /api/sync/{job_id}` every second
5. UI updates the Home and Athlete queries on completion

### Coach

1. User submits message
2. Frontend appends optimistic user bubble
3. Backend calls existing coach pipeline
4. Response is normalized into `verdict`, `evidence`, and `next_step`
5. Evidence chips link to run detail or source metadata

## State Management Rules

- Use TanStack Query for all API-backed state
- Use local component state for composer input and transient UI
- Avoid Redux
- Avoid a large client-side domain store until mobile offline needs are real

## Accessibility Requirements

- Minimum 48x48 tap targets
- At least 8px spacing between adjacent targets
- Strong luminance contrast in monochrome palette
- Keyboard-navigable on web
- No hover-only affordances
- Respect system font scaling
- Declare dark support with `color-scheme: dark`

## Implementation Plan

### Phase 0: API Shell

- Add `server.py` with FastAPI app
- Expose `status`, `doctor`, `athlete summary`, `runs`, `vdot`, `sync`, and `coach message`
- Add background sync job manager with polling endpoint

### Phase 1: App Shell

- Scaffold Expo Router app
- Implement theme tokens and font loading
- Build Home, Athlete, Coach, Diagnostics tabs
- Build mobile bottom tabs and desktop rail

### Phase 2: Data and Coach

- Wire athlete summary, recent runs, VDOT, and HR zones
- Add run detail screen
- Add structured coach response rendering
- Add diagnostics and eval screens

### Phase 3: Hardening

- Add loading, empty, and failure states for every route
- Add API error boundary and retry behavior
- Add web smoke tests and API tests

## Acceptance Criteria

- App runs locally with one frontend command and one backend command
- The Home screen makes sense on a 390px-wide viewport
- A first-time user can find sync, current VDOT, and coach chat without reading docs
- Coach responses always show evidence rows when data exists
- Diagnostics exposes doctor state and last sync result without terminal usage
- No page depends on color alone to communicate status

## Implementation Notes For This Repo

- Keep current metric logic in Python
- Do not duplicate VDOT or HR-zone logic in the frontend
- Normalize backend payloads for the frontend rather than sending raw DB rows everywhere
- Reuse the existing coach evidence contract rather than inventing a second response format

## Research References

- Expo Router introduction: https://docs.expo.dev/router/introduction/
- Expo web publishing guide: https://docs.expo.dev/guides/publishing-websites/
- Android adaptive layout and navigation guidance: https://developer.android.com/design/ui/mobile/guides/layout-and-content/layout-and-nav-patterns
- Android adaptive navigation patterns: https://developer.android.com/develop/ui/compose/layouts/adaptive/build-adaptive-navigation
- Responsive design guidance: https://web.dev/articles/accessible-responsive-design
- Tap target guidance: https://web.dev/articles/accessible-tap-targets
- CSS `color-scheme`: https://developer.mozilla.org/docs/Web/CSS/color-scheme
- Android dark theme guidance: https://developer.android.com/develop/ui/views/theming/darktheme

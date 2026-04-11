# Nyx

Nyx is a local-first running intelligence system. It syncs Garmin run history, computes training metrics (REI, VDOT, HR zones), builds a coaching knowledge base, and exposes everything through a web UI and CLI.

## Architecture

Nyx has two layers:

- **Python backend** — FastAPI server wrapping the harness modules (`server.py`). Handles sync, metrics, coach chat, evals, and health checks. All business logic stays in Python.
- **Expo web client** — React Native + React Native Web app in `apps/nyx-client/`. Talks to the backend over `http://127.0.0.1:8000`. Four screens: Home, Athlete, Coach, Diagnostics, plus a run detail page.

The design spec is in [docs/web-app-build-spec.md](docs/web-app-build-spec.md).

### Frontend stack

- Expo SDK 54, Expo Router 6, React 19, React Native Web
- TanStack Query for data fetching
- Monochrome dark design system (Space Grotesk / IBM Plex Sans / IBM Plex Mono)
- Custom `AppFrame` shell with bottom tabs (compact) and left rail (wide)

### Known issue: CSSStyleDeclaration error on web

The Expo web client currently crashes on launch with:

```
Failed to set an indexed property [0] on 'CSSStyleDeclaration': Indexed property setter is not supported.
```

This is a compatibility issue between `react-native-web@0.21` and React 19. React 19's style reconciler iterates style objects with `for...in` and tries to set numeric keys (like `"0"`) on `CSSStyleDeclaration`, which browsers reject. The root cause is in how `react-native-web` resolves `StyleSheet` objects into DOM props — under React 19, inline style values that previously worked now trigger the browser's indexed property setter guard.

Downgrading to React 18 is not viable because `expo-router@6` uses `React.use()`, which requires React 19.

Potential fixes:
- Upgrade `react-native-web` when a release ships with React 19 style reconciliation support
- Patch `react-native-web` locally to filter numeric keys from inline style objects before they reach React DOM
- Pin to an Expo SDK / react-native-web combination where this is resolved upstream

### Backend API

The FastAPI server (`server.py`) exposes:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/status` | GET | Harness status |
| `/api/doctor` | GET | Doctor checks |
| `/api/athlete/summary` | GET | Core athlete state for Home and Athlete screens |
| `/api/runs?limit=N` | GET | Recent runs list |
| `/api/runs/{activity_id}` | GET | Run detail with laps |
| `/api/vdot` | GET | Current VDOT and paces |
| `/api/hr-zones` | GET | HR zones |
| `/api/coach/context` | GET | Compact context for coach UI strip |
| `/api/sync` | POST | Start background sync job |
| `/api/sync/{job_id}` | GET | Poll sync job progress |
| `/api/vdot/recalc` | POST | Force VDOT and HR zone refresh |
| `/api/coach/message` | POST | Send message to coach, get structured response |
| `/api/evals/run` | POST | Run offline or live evals |

## Quick Start

### Web app (preferred)

```bash
# Terminal 1: backend
source .venv/bin/activate
uvicorn server:app --reload

# Terminal 2: frontend
cd apps/nyx-client
npm install
npm run web
```

### Textual TUI

```bash
python3 nyx.py
```

### Raw CLI

```bash
python3 cli.py doctor
python3 cli.py sync
python3 cli.py report --n 20
python3 coach.py
```

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the web client)
- A Garmin Connect account for sync
- An Anthropic API key for coach chat and live evals

## Setup

1. Create a virtual environment and install Python dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create your Garmin token.

Run this once. It prompts for your Garmin Connect email and password, handles MFA if your account uses it, and saves tokens to `~/.garminconnect/`. Nyx reuses them automatically on every subsequent sync — you won't need to log in again unless your tokens expire.

```bash
python3 scripts/create-garmin-token.py
```

Tokens are saved to `~/.garminconnect/garmin_tokens.json` by default. To use a custom location, pass `--tokenstore <path>` and set `GARMINTOKENS=<path>` in your environment.

3. Set your Anthropic API key.

```bash
export ANTHROPIC_API_KEY=your_key_here
```

4. Build the local knowledge base.

```bash
python3 build_kb.py
```

5. Run a health check.

```bash
python3 cli.py doctor
```

6. Install and start the web client.

```bash
cd apps/nyx-client
npm install
```

## What Nyx Computes

- REI (Run Efficiency Index)
- Aerobic efficiency baseline
- Estimated VDOT from training runs
- Daniels training paces (easy, marathon, threshold, interval)
- Karvonen HR zones

## Files and Directories

### Backend

- `server.py`: FastAPI local API
- `cli.py`: CLI command surface
- `nyx.py`: Textual TUI launcher
- `coach.py`: coach runtime and prompt assembly
- `store.py`: SQLite schema, migrations, metadata
- `vdot_zones.py`: VDOT estimation and HR zones
- `evals.py`: offline and live harness evals
- `health.py`: status and doctor checks
- `sync_engine.py`: Garmin sync pipeline
- `knowledge/`: source coaching knowledge
- `garmin_data.db`: local athlete data (SQLite)
- `chroma_db/`: local retrieval index
- `.garmin_tokens/`: Garmin auth token cache

### Frontend

- `apps/nyx-client/app/`: Expo Router pages (Home, Athlete, Coach, Diagnostics, Run Detail)
- `apps/nyx-client/components/`: Shared components (AppFrame, Surface, MetricPill, SectionHeader)
- `apps/nyx-client/lib/api/client.ts`: API client
- `apps/nyx-client/lib/theme/tokens.ts`: Design tokens

## CLI Reference

| Command | Purpose |
|---|---|
| `python3 cli.py sync` | Incremental Garmin sync |
| `python3 cli.py status` | Show harness state |
| `python3 cli.py doctor` | Check environment readiness |
| `python3 cli.py report --n 20` | Print recent runs |
| `python3 cli.py inspect <id>` | Inspect a single run |
| `python3 cli.py vdot` | Show current VDOT |
| `python3 cli.py vdot --recalc` | Recompute VDOT |
| `python3 cli.py eval` | Run offline evals |
| `python3 cli.py eval --live` | Run live evals (needs API key) |
| `python3 coach.py` | Interactive coach chat |

## Troubleshooting

### Garmin or Anthropic dependency missing

```bash
pip install -r requirements.txt
```

### Garmin rate limiting / "all strategies failed"

Garmin's SSO endpoints aggressively rate-limit login attempts on a per-account basis — changing your IP or user-agent does not help. If `create-garmin-token.py` prints "rate-limited" or "all strategies failed":

1. **Wait 15–30 minutes** before retrying. Repeated attempts extend the block.
2. Retry: `python3 scripts/create-garmin-token.py`

Nyx ships with a patched version of `python-garminconnect` that adds a widget-based login strategy (`/sso/embed`) which bypasses the rate-limited endpoints. If you consistently can't authenticate, it's a temporary Garmin server-side block — patience is the fix.

### Coach or live evals need an API key

```bash
export ANTHROPIC_API_KEY=your_key_here
```

### Knowledge base missing

```bash
python3 build_kb.py
python3 cli.py doctor
```

### Web client custom backend URL

```bash
export EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

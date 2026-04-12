# Nyx

Nyx is a local-first running intelligence system. It syncs Garmin run history, computes training metrics (REI, VDOT, HR zones), builds a coaching knowledge base, and exposes everything through a web UI and CLI.

Current implementation assumptions:

- SQLite remains the only persistence layer.
- FastAPI is the first async target; CLI and Textual flows remain synchronous for now.
- The API is intended for `localhost` or Tailscale/LAN use, not direct internet exposure.
- A single bearer token is sufficient for API authentication in this deployment model.

## Architecture

Nyx has two layers:

- **Python backend** — FastAPI server wrapping the harness modules (`server.py`). Handles sync, metrics, coach chat, evals, and health checks. All business logic stays in Python.
- **Expo web client** — React Native + React Native Web app in `apps/nyx-client/`. Talks to the backend over `http://127.0.0.1:8000`. Four screens: Home, Athlete, Coach, Diagnostics, plus a run detail page.

The design spec is in [docs/web-app-build-spec.md](docs/web-app-build-spec.md).
Provider expansion research (Oura + Apple Health) is in [docs/provider-expansion-research.md](docs/provider-expansion-research.md).

### Frontend stack

- Expo SDK 54, Expo Router 6, React 19, React Native Web
- TanStack Query for data fetching
- Monochrome dark design system (Space Grotesk / IBM Plex Sans / IBM Plex Mono)
- Custom `AppFrame` shell with bottom tabs (compact) and left rail (wide)

### Backend API

The FastAPI server (`server.py`) exposes:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/status` | GET | Harness status |
| `/api/doctor` | GET | Doctor checks |
| `/api/health/deep` | GET | On-demand deep probes for DB, Garmin, knowledge base, and Moonshot |
| `/api/athlete/summary` | GET | Core athlete state for Home and Athlete screens |
| `/api/runs?limit=N` | GET | Recent runs list |
| `/api/runs/{activity_id}` | GET | Run detail with laps |
| `/api/vdot` | GET | Current VDOT and paces |
| `/api/hr-zones` | GET | HR zones |
| `/api/coach/context` | GET | Compact context for coach UI strip |
| `/api/sync` | POST | Start background sync job |
| `/api/sync/{job_id}` | GET | Poll sync job progress |
| `/api/vdot/recalc` | POST | Force VDOT and HR zone refresh |
| `/api/training-plan` | POST | Generate a structured training plan from local data |
| `/api/coach/message` | POST | Send message to coach, get structured response |
| `/api/evals/run` | POST | Run offline or live evals |

## Quick Start

### Web app via tmux (persistent — survives SSH disconnect)

Start both services in named tmux sessions so they keep running after you close your terminal:

```bash
# Backend — binds to all interfaces so Tailscale can reach it
tmux new-session -d -s nyx-backend
tmux send-keys -t nyx-backend \
  "cd ~/Work/Nyx && MOONSHOT_API_KEY=<your-key> .venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000" Enter

# Frontend — set API base URL to backend's Tailscale/LAN IP
tmux new-session -d -s nyx-frontend
tmux send-keys -t nyx-frontend \
  "cd ~/Work/Nyx/apps/nyx-client && EXPO_PUBLIC_API_BASE_URL=http://<tailscale-ip>:8000 npx expo start --web --port 8081 --host lan" Enter
```

Access at `http://<tailscale-ip>:8081`. To reattach: `tmux attach -t nyx-backend` or `tmux attach -t nyx-frontend`.

### Web app (local dev, two terminals)

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
- A Moonshot API key for coach chat and live evals (get one at platform.moonshot.ai)

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

3. Set your Moonshot API key.

```bash
export MOONSHOT_API_KEY=your_key_here
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

Optional API auth:

```bash
export NYX_API_TOKEN=replace-me
export EXPO_PUBLIC_API_TOKEN=replace-me
```

If `NYX_API_TOKEN` is set, Nyx requires `Authorization: Bearer <token>` on `/api/*` requests. CORS is restricted to localhost by default, plus Tailscale/LAN-style origins via regex. Override explicit origins with `NYX_CORS_ORIGINS=origin1,origin2`.

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
| `python3 cli.py export --format json` | Export local run data to JSON |
| `python3 cli.py export --format csv --since 2026-04-01` | Export recent run summaries to CSV |
| `python3 cli.py backup` | Snapshot the local SQLite database |
| `python3 cli.py plan --goal "half marathon" --weeks 8` | Generate a structured week-by-week training plan |
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
export MOONSHOT_API_KEY=your_key_here
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

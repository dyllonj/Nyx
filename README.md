# Nyx

Nyx is the local harness for this running coach system.

It pulls Garmin run history into a local SQLite database, computes training metrics like REI, VDOT, and HR zones, builds a lightweight running knowledge base, and gives you a CLI plus a coach chat loop for development and evaluation.

This is a developer harness, not the final user-facing product UI.

The planned web/mobile product direction is documented in [docs/web-app-build-spec.md](docs/web-app-build-spec.md).

If you want the friendly launcher instead of the raw CLI, start with:

```bash
python3 nyx.py
```

## What Nyx Does

- Syncs Garmin running activities into `garmin_data.db`
- Fetches detail metrics and lap splits for each run
- Computes:
  - REI (Run Efficiency Index)
  - Aerobic efficiency baseline
  - Estimated VDOT from training runs
  - Daniels training paces
  - Karvonen HR zones
- Builds a retrieval-backed running knowledge base from `knowledge/`
- Runs a coach chat session grounded in athlete data plus retrieved coaching knowledge
- Exposes dev-facing health and evaluation commands

## Prerequisites

- Python 3.11+ recommended
- A Garmin Connect account for `sync`
- An Anthropic API key for `coach.py` and live evals

## Setup

1. Create a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Set your Anthropic API key if you want coach chat or live evals.

```bash
export ANTHROPIC_API_KEY=your_key_here
```

4. Build the local knowledge base.

```bash
python3 build_kb.py
```

5. Run a harness health check.

```bash
python3 cli.py doctor
```

If Garmin or Anthropic dependencies are missing, `doctor` will tell you exactly what is not ready.

## First Run

Recommended first-run flow:

```bash
python3 nyx.py
```

What to expect:

- Nyx opens a Textual app with Home, Athlete, Coach, Diagnostics, and About tabs.
- You can sync Garmin, run onboarding, refresh VDOT/HR zones, and run diagnostics from the app.
- The first `sync` will prompt you for Garmin credentials if there is no token cache yet.
- Garmin tokens are stored locally in `.garmin_tokens/`.
- Your local athlete data is stored in `garmin_data.db`.
- `build_kb.py` creates the local knowledge index in `chroma_db/`.

If you prefer the raw terminal flow, the older CLI commands still work.

## Core Commands

### Data and Metrics

```bash
python3 nyx.py
python3 cli.py sync
python3 cli.py report --n 20
python3 cli.py inspect <activity_id>
python3 cli.py plot
python3 cli.py vdot
python3 cli.py vdot --recalc
python3 cli.py vdot --resting 52 --maxhr 185
```

### Harness Health

```bash
python3 cli.py status
python3 cli.py doctor
```

### Evaluation

```bash
python3 cli.py eval
python3 cli.py eval --live
python3 cli.py eval --live --verbose
```

### Onboarding and Chat

```bash
python3 cli.py onboarding --full
python3 coach.py
```

## Command Guide

`python3 cli.py sync`

- Incrementally syncs Garmin runs into the local DB
- Uses a stored watermark date plus a short lookback window
- Persists sync state, success/failure, and last error

`python3 cli.py status`

- Shows schema version, run counts, sync state, VDOT state, onboarding state, and knowledge-base presence

`python3 cli.py doctor`

- Checks whether the local environment is ready
- Verifies Garmin dependency, Anthropic dependency, sync state, knowledge base, onboarding, and DB schema

`python3 cli.py eval`

- Runs offline harness checks without calling the model
- Useful before live testing

`python3 cli.py eval --live`

- Runs golden questions against the actual coach harness
- Requires `ANTHROPIC_API_KEY`

`python3 coach.py`

- Starts the interactive coach session
- Uses athlete profile context, compacted run history, VDOT/HR-zone context, and retrieval from the knowledge base

## Files and Directories

- `cli.py`: main command surface
- `nyx.py`: Textual launcher and friendly harness UI
- `nyx.tcss`: Nyx UI styling
- `coach.py`: coach runtime and prompt assembly
- `store.py`: SQLite schema, migrations, and metadata persistence
- `vdot_zones.py`: VDOT estimation and HR zones
- `evals.py`: offline and live harness evals
- `health.py`: `status` and `doctor`
- `knowledge/`: source coaching knowledge
- `garmin_data.db`: local athlete data
- `chroma_db/`: local retrieval index
- `.garmin_tokens/`: Garmin auth token cache

## Troubleshooting

### `python3 cli.py sync` says Garmin dependency is missing

Install requirements:

```bash
pip install -r requirements.txt
```

### `python3 coach.py` says Anthropic dependency is missing

Install requirements:

```bash
pip install -r requirements.txt
```

### `python3 coach.py` or `python3 cli.py eval --live` needs an API key

Set:

```bash
export ANTHROPIC_API_KEY=your_key_here
```

### The knowledge base is empty or unavailable

Rebuild it:

```bash
python3 build_kb.py
```

Then re-run:

```bash
python3 cli.py doctor
```

### I want to inspect current harness state quickly

Use:

```bash
python3 cli.py status
python3 cli.py doctor
```

## Current Scope

Nyx is optimized for local development, productization, and harness hardening. The CLI and chat flow are intentionally utilitarian; they exist to support evaluation and iteration on the coaching system, not to represent the final shipped UX.

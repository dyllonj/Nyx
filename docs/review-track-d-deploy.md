# Review Track D - Deployment and Operations

Date: 2026-04-12

## Verdict

Nyx is close to a single-user pilot on the current machine, but it is not yet pilot-release ready for repeatable deployment or unattended operations. The repo already has useful health checks, backup primitives, deployment scripts, and a passing local test suite, but there are still material gaps in deployment documentation, migration safety, environment documentation, CI automation, and restore/logging procedures.

## Findings

### 1. High: The deployment path is still implicit and partially manual

- `deploy/systemd/nyx.service:6-15` and `deploy/autostart/nyx.desktop:1-6` show the intended runtime targets, but there is no tracked deployment runbook explaining how to install, enable, verify, or operate them.
- `server.py:261-280` and `server.py:1938-1953` only serve the web app when `apps/nyx-client/dist/` exists.
- `scripts/build-web.sh:1-15` builds that static bundle, but README only documents tmux/dev workflows (`README.md:57-88`) and never documents the production web build step or service bootstrap.
- `deploy/autostart/nyx.desktop:5` and `scripts/start-nyx-background.sh:9` also assume `/home/deck/...`, which makes the current deployment artifacts machine-specific.

Impact: a fresh operator cannot reproduce the intended deployment from repo docs alone, and the backend can come up while `/` still returns `404 Web app is not built yet`.

Recommendation: add a deployment runbook covering env file placement, web build, service install/enable, log access, and smoke-test steps; parameterize hard-coded home-directory paths.

### 2. High: Schema migrations auto-run on DB open and include a destructive branch, but there is no documented restore path

- `store.open_db()` always applies migrations on connect (`store.py:417-420`).
- `_apply_schema_migrations()` includes a version-8 branch that drops and recreates provider tables if `provider_user_id` is missing (`store.py:386-406`).
- Backup support exists (`backup_utils.py:135-177`, `sync_engine.py:234-253`, `cli.py:338-340`), but there is no `restore` command or restore procedure documented anywhere in `README.md`, `cli.py`, or `backup_utils.py`.
- Existing store tests only validate a new database path and normal writes (`tests/test_store.py:42-74`); they do not exercise upgrades from older schema versions.

Impact: opening an older DB can mutate it immediately, and one migration path can discard provider data. Recovery currently depends on manual SQLite file replacement.

Recommendation: add a pre-migration backup guard, a documented restore workflow, and migration tests using historical DB fixtures.

### 3. Medium: The environment variable contract is incomplete and internally inconsistent

- `deploy/nyx.env.example:1-8` covers only part of the runtime surface.
- README documents Garmin, Moonshot, API token, CORS, Oura, and Expo vars (`README.md:130-171`, `README.md:255-259`), but code also depends on `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `NYX_LOG_LEVEL`, and deployment vars such as `NYX_LOCAL_HOST`, `NYX_PORT`, `NYX_TAILSCALE_HOST`, and `NYX_ENV_FILE` (`providers/whoop_auth.py:47-53`, `logging_utils.py:27-36`, `scripts/run-nyx-dual.sh:5-7`, `scripts/start-nyx-background.sh:9`).
- There is also a doc/code mismatch for live evals: README says Moonshot is needed for coach chat and live evals (`README.md:105-110`, `README.md:242-246`), while `evals.py:160-171` blocks live evals on `ANTHROPIC_API_KEY`.

Impact: pilot operators can follow README and still miss required vars or fail optional provider/eval features unexpectedly.

Recommendation: publish a single env matrix in README and sync `deploy/nyx.env.example` to it.

### 4. Medium: Tests are healthy locally, but there is no CI/CD pipeline or release automation

- `tests/` contains 41 `unittest`-based tests across storage, backup, auth, health, async server flows, Oura, and WHOOP.
- Local verification succeeded with `python -m unittest discover -s tests -v` on 2026-04-12: 41 tests passed in 5.675s.
- No `.github/workflows/`, `pytest.ini`, `pyproject.toml`, `tox.ini`, or release pipeline files were present in the repo.

Impact: quality gates exist only when a human remembers to run them. There is no automated signal on merge, release, or deploy.

Recommendation: add at least one CI workflow for dependency install, unit tests, and the web build/export step.

### 5. Medium: Monitoring and log management are basic, but not productionized

- Health/status surfaces exist: `/api/status`, `/api/doctor`, and `/api/health/deep` (`server.py:1333-1359`, `health.py:43-205`, `health.py:290-372`).
- Structured JSON logs exist (`logging_utils.py:7-46`).
- In background mode, logs are appended to a single repo-local file with no rotation or retention (`scripts/start-nyx-background.sh:5-28`).
- There is no metrics endpoint, no alerting integration, no documented dashboarding, and no explicit liveness/readiness split for external probes.

Impact: troubleshooting is possible, but unattended pilot operations will rely on manual log inspection and ad hoc health polling.

Recommendation: define log retention, expose a lightweight liveness/readiness strategy, and document probe/alert expectations.

### 6. Medium: Containerization is not ready

- No `Dockerfile`, `.dockerignore`, `docker-compose.yml`, or `compose.yaml` were present.

Impact: deployment is tied to a repo-local virtualenv and shell/systemd bootstrap instead of a reproducible container image.

Recommendation: add a backend `Dockerfile` plus a documented image build/run path if container deployment is in scope.

### 7. Low: Git hooks are present but limited in scope and not self-bootstrapped

- `.githooks/pre-commit:1-26` blocks env files, keys, and obvious secrets.
- The hook does not run tests, linting, or web builds.
- README does not document hook setup, so new clones still depend on local git configuration to activate it.

Impact: secret-leak protection is better than nothing, but this is not a reliable release gate.

Recommendation: document hook activation and keep hooks complementary to CI, not a substitute.

## Audit Notes

| Area | Status | Notes |
| --- | --- | --- |
| `deploy/` | Partial | systemd/autostart artifacts exist, but install and operations docs are missing |
| `requirements.txt` | Partial | installable in the current `.venv`; `pip check` was clean; dependencies are not fully locked and include a GitHub install (`requirements.txt:1-8`) |
| Docker | Missing | no container build files present |
| `scripts/` | Partial | useful runtime/build helpers, but host-specific assumptions remain |
| `tests/` | Partial | 41 passing local tests; no CI |
| DB migrations | Partial | versioned migration path exists, but one branch is destructive and undocumented from an ops perspective |
| `.githooks/` | Partial | secret-scan hook only |
| Env docs | Partial | README and env example do not cover all runtime variables |

## Strengths

- `backup_utils.py:135-177` plus `sync_engine.py:234-253` provide automatic SQLite snapshots with retention on successful syncs.
- Health and doctor endpoints already surface DB, Garmin, knowledge base, and Moonshot readiness.
- Logging is structured JSON instead of ad hoc prints.
- `pip check` returned clean in the current `.venv`.
- The local unit suite passed end-to-end.

## Recommended Release Blockers Before Pilot

1. Write a real deployment runbook and include systemd/autostart install, env file creation, web build, log access, and smoke-test steps.
2. Add pre-migration backup/restore procedures and test migrations against older DB fixtures.
3. Normalize the environment variable contract across README, `deploy/nyx.env.example`, and code.
4. Add CI for backend tests and web build.
5. Define log retention and a simple health-check/monitoring procedure.

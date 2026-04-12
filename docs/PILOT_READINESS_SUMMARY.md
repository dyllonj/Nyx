# Nyx Pilot Release Readiness - Executive Summary

**Date:** 2026-04-12  
**Review Scope:** Four-track pilot readiness assessment for Nyx running intelligence platform

---

## 🎯 Overall Verdict

**NOT READY** for pilot release without addressing blocking issues.

Nyx has a solid core implementation but has significant gaps in documentation accuracy, API security, frontend contract alignment, and deployment repeatability that must be resolved before external pilot users can safely onboard.

---

## 📊 Track-by-Track Status

### Track A: Documentation & Release Framing 🔴 NEEDS REWRITE
**Status:** Major gaps - README is misleading

**Key Issues:**
1. **HIGH:** README omits production deployment path (`scripts/build-web.sh`, `scripts/run-nyx-dual.sh`)
2. **HIGH:** README shows `npm install` but never says to run `npm run web`
3. **HIGH:** `docs/web-onboarding-plan.md` is obsolete - work it describes is already shipped
4. **MEDIUM:** API list in README omits shipped endpoints (`/api/onboarding`, `/api/coach/thread`)
5. **MEDIUM:** Live evals claim to need `MOONSHOT_API_KEY` but actually check `ANTHROPIC_API_KEY`
6. **LOW:** Garmin token location inconsistent between docs and code

**Impact:** Users following README will fail to deploy or run the app correctly.

---

### Track B: Backend/API Hardening 🔴 BLOCKING
**Status:** Security and reliability issues must be fixed

**🚨 BLOCKING Issues:**

**1. HIGH: API authentication is FAIL-OPEN**
- When `NYX_API_TOKEN` is unset, all `/api/*` routes become unauthenticated
- Default deployment mistake = completely open API
- **Fix:** Make auth fail-closed; require explicit `NYX_DEV_MODE` to disable auth

**2. HIGH: Database migrations are destructive and run on every connection**
- `open_db()` applies migrations on every API request
- v7→v8 migration drops all provider tables if column missing
- Non-atomic: partial failures leave DB partially upgraded
- **Fix:** Move migrations to explicit admin step; add backup guard

**3. HIGH: Live evals check wrong API key**
- README says `MOONSHOT_API_KEY` for coach + evals
- `evals.py` blocks on `ANTHROPIC_API_KEY`
- Coach uses Moonshot; evals will fail even when coach works
- **Fix:** Gate evals on same credential as coach

**4. HIGH: API allows interactive stdin prompts in background threads**
- `/api/sync` accepts `interactive: bool` and passes to sync thread
- If token missing, `auth.get_client()` calls `input()` and `getpass()`
- Can hang API worker indefinitely
- **Fix:** Reject `interactive=True` from API entirely

**Other Issues:**
- Garmin failures downgraded to warnings (hides rate limiting)
- Moonshot failures return raw 500s until circuit breaker opens
- SQLite foreign keys never enabled (declared but not enforced)
- Sync engine never closes DB connection (resource leak)
- Health checks don't verify DB writeability or provider health

---

### Track C: Frontend/Client 🟡 NEEDS FIXES
**Status:** Contract drift and missing error handling

**HIGH Issue:**
- `/api/athlete/summary` contract drift - client reads `athlete.meta.cached`, backend returns `last_sync_status`
- All API methods typed as `any` - no TypeScript catch of response drift
- Impact: Home shows "data = live" when cache-backed; shows "no sync" when sync exists

**Medium Issues:**
- No production error boundary
- Auth/network/CORS failures hidden behind placeholder copy instead of error states
- Coach send can fail before error handling runs
- No timeout, abort, or retry strategy in API client
- Client depends on undocumented routes (`/api/onboarding`, `/api/coach/thread`)
- Design system partially tokenized (many hardcoded values)

---

### Track D: Deployment & Operations 🔴 BLOCKING
**Status:** Not repeatable or unattended-ready

**🚨 BLOCKING Issues:**

**1. HIGH: Deployment path is implicit and manual**
- `deploy/systemd/nyx.service` exists but no runbook explains install/enable/verify
- `scripts/build-web.sh` builds static bundle but README never mentions it
- Hard-coded `/home/deck/` paths make artifacts machine-specific
- Backend can start while `/` returns `404 Web app is not built yet`
- **Fix:** Add deployment runbook; parameterize paths

**2. HIGH: Destructive migrations with no restore path**
- Migrations auto-run on DB open (destructive v7→v8 branch)
- Backup exists but no `restore` command or procedure documented
- No migration tests using historical DB fixtures
- **Fix:** Add pre-migration backup guard; document restore workflow

**3. MEDIUM: Environment variable contract incomplete**
- `deploy/nyx.env.example` covers only part of runtime surface
- Missing: `WHOOP_CLIENT_ID`, `NYX_LOG_LEVEL`, `NYX_LOCAL_HOST`, `NYX_PORT`, etc.
- **Fix:** Publish complete env matrix; sync example file

**Other Issues:**
- No CI/CD pipeline (41 tests exist but not automated)
- No containerization (no Dockerfile or compose)
- Log management basic (single file, no rotation)
- No metrics endpoint or alerting integration
- Git hooks not documented/self-bootstrapped

---

## 🎯 Critical Path to Pilot Release

### Phase 1: Fix Blocking Security Issues (Week 1)
1. **Track B:** Fix fail-open auth (require explicit dev mode)
2. **Track B:** Move migrations to admin step with backup guard
3. **Track B:** Fix evals credential check
4. **Track B:** Block interactive mode from API

### Phase 2: Fix Deployment & Documentation (Week 2)
5. **Track D:** Add deployment runbook with web build step
6. **Track A:** Rewrite README as operator guide (dev vs deploy paths)
7. **Track D:** Document restore procedure
8. **Track A:** Mark obsolete docs as historical

### Phase 3: Fix Frontend Contract & Error Handling (Week 3)
9. **Track C:** Fix athlete/summary contract drift
10. **Track C:** Add error boundaries and error states
11. **Track C:** Add API client timeout/retry

### Phase 4: Automation & Hardening (Week 4)
12. **Track D:** Add CI/CD pipeline for tests and web build
13. **Track B:** Enable SQLite foreign keys
14. **Track B:** Add provider health checks
15. **Track B:** Fix sync engine connection leak

---

## ✅ What's Working Well

- Core architecture (FastAPI + Expo) is solid
- 41 unit tests passing locally
- Garmin sync pipeline operational
- Coach chat with Moonshot working
- Oura and WHOOP provider integrations implemented
- Onboarding flow shipped and functional
- Web UI with all 5 screens operational
- Health checks exist (status, doctor, deep)
- Backup primitives exist
- Systemd service file exists

---

## 📋 Detailed Reports

- `docs/review-track-a-docs.md` (12KB) - Documentation gaps
- `docs/review-track-b-backend.md` (8KB) - Security/reliability issues
- `docs/review-track-c-frontend.md` (7KB) - Frontend contract drift
- `docs/review-track-d-deploy.md` (8KB) - Deployment gaps

---

## 🚀 Exit Criteria for Pilot Release

Ready when:

1. ✅ API auth is fail-closed by default
2. ✅ Migrations are explicit (not on every request) with backup guard
3. ✅ README accurately describes dev setup AND production deployment
4. ✅ Frontend contract matches backend (athlete/summary fixed)
5. ✅ Error states visible for auth/network failures
6. ✅ Deployment runbook exists and works on fresh machine
7. ✅ CI/CD runs tests automatically
8. ✅ Environment variable contract documented completely

---

**Bottom Line:** The implementation is solid but the "last mile" of documentation, security defaults, and deployment repeatability needs work before external pilots can succeed. Focus on Tracks B and D first (security + deployment), then A and C (docs + frontend polish).

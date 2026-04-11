# Web Onboarding Plan

## Goal

Add onboarding to the web app with a different UI, while keeping the same persisted answers and completion state the CLI already uses.

This should stay local-first and single-user for now. In the current architecture, "the user" is the single athlete represented by the local SQLite database.

## Current State

- CLI onboarding lives in `onboarding.py`.
- Answers are stored in `user_meta` under keys like:
  - `onboarding_motivation`
  - `onboarding_goal`
  - `onboarding_injury`
  - `onboarding_lifestyle`
  - `onboarding_easy_effort`
  - additional full-flow keys for the longer intake
- Completion is stored as `onboarding_completed = "1"`.
- Red flags are stored as `onboarding_red_flags` JSON.
- Coach/profile logic already reads these saved values.
- The FastAPI server has no onboarding endpoints yet.
- The Expo app has no onboarding screen or route logic yet.

## Important Existing Gaps

- `cli.py onboarding --reset` says it clears answers, but today it only sets `onboarding_completed = "0"`.
- `build_profile_context()` will still read old answers even after that reset.
- `onboarding_questions.json` exists but is not the active source for the CLI flow today.

The web work should fix these semantics instead of copying them.

## Recommended Product Behavior

Use a soft gate, not a full-app lock.

- Home should surface onboarding as the primary next action when incomplete.
- Coach should require onboarding before sending messages.
- Athlete and Diagnostics can remain accessible without onboarding.
- After completion, onboarding should remain editable from a secondary entry point later.

This matches the current CLI behavior better than blocking the whole app at launch.

## Source Of Truth

Backend should own onboarding definition and persistence.

Do not make the web app hardcode question text or storage keys.

### Phase 1 recommendation

Keep the current CLI question set as the source of truth and expose it through `onboarding.py`.

Add helpers such as:

- `get_onboarding_questions(full: bool = False)`
- `get_onboarding_state(conn)`
- `save_onboarding_answers(conn, answers, *, current_step=None, full=False)`
- `complete_onboarding(conn)`
- `reset_onboarding(conn, clear_answers=True)`

Then have both CLI and web use those helpers.

### Why not switch to `onboarding_questions.json` yet

That file is richer than the live CLI flow and would turn this into a content-model rewrite. For this feature, parity with the current onboarding matters more than expanding the questionnaire.

## Persistence Model

Keep using the existing answer keys so coach/profile behavior stays unchanged.

Add a small amount of progress metadata in `user_meta`:

- `onboarding_mode`: `mvp` or `full`
- `onboarding_current_step`: zero-based step index
- `onboarding_started_at`
- `onboarding_updated_at`
- `onboarding_version`: question-set version for future migrations

Keep:

- `onboarding_completed`
- `onboarding_red_flags`

Behavior:

- Save each answer as the user advances.
- Do not set `onboarding_completed = "1"` until the final submit.
- Recompute red flags whenever answers change.
- A real reset must clear all onboarding answer keys and progress metadata.

## API Shape

Add dedicated onboarding endpoints rather than overloading `/api/status`.

### `GET /api/onboarding`

Returns:

- `completed`
- `mode`
- `current_step`
- `steps`: ordered question metadata for the active flow
- `answers`: current saved answers
- `active_red_flags`

### `PUT /api/onboarding`

Request body:

```json
{
  "answers": {
    "onboarding_goal": "Run a sub-20 5K"
  },
  "current_step": 2,
  "mode": "mvp"
}
```

Behavior:

- saves partial progress
- recomputes red flags
- returns updated state plus any newly-triggered flag messages

### `POST /api/onboarding/complete`

Behavior:

- validates the active flow is sufficiently answered
- writes `onboarding_completed = "1"`
- persists final red flags
- returns stored profile preview if useful for the UI

### `POST /api/onboarding/reset`

Behavior:

- clears all onboarding answers
- clears red flags and progress metadata
- sets `onboarding_completed = "0"`

## Web UX Plan

Add a dedicated `/onboarding` route and use it in two ways:

1. Home CTA
   - If onboarding is incomplete, primary CTA becomes `Finish Onboarding`.

2. Coach intercept
   - If onboarding is incomplete, the Coach screen shows an onboarding intercept instead of the chat composer.

### Screen behavior

- One question per step
- Same wording as CLI
- Progress indicator
- Back / Next controls
- Optional skip for individual questions
- Auto-save on next step
- Resume from last saved step after refresh

### Immediate coaching notes

The CLI prints red-flag notes immediately after relevant answers.

Web should mirror that with an inline callout after a flagged response, using the same backend-generated message text.

## Backend Alignment For Home

Update server next-action logic to match the CLI/TUI ordering:

1. diagnostics failures
2. no runs synced
3. onboarding incomplete
4. no VDOT
5. coach

That allows Home to naturally drive users into onboarding without frontend-only business logic.

## Editing After Completion

Support a later "Edit onboarding" entry point using the same route.

- Existing answers prefill the flow
- Updating answers recomputes red flags
- `onboarding_completed` stays complete unless the user explicitly resets

## Implementation Order

1. Refactor `onboarding.py` so CLI and API share save/reset/complete helpers.
2. Add FastAPI onboarding endpoints.
3. Fix reset semantics so answers are actually cleared.
4. Update backend next-action logic to account for incomplete onboarding.
5. Add Expo `/onboarding` route and client API methods.
6. Gate Home CTA and Coach behavior off onboarding state.
7. Add an edit/restart entry point later.

## Tests

Backend:

- saving partial answers persists values without marking complete
- completion sets `onboarding_completed`
- red flags recompute correctly
- reset clears answers and flags
- athlete summary next action becomes onboarding when appropriate

Frontend:

- incomplete onboarding routes user into the flow from Home/Coach
- saved progress resumes correctly
- completing onboarding returns Coach/Home to normal behavior

## Non-Goal For This Pass

Do not introduce multi-user scoping yet.

If Nyx later supports multiple athletes or remote auth, onboarding data will need to move from global `user_meta` keys to user-scoped records.

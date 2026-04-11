#!/usr/bin/env python3
"""
AI Running Coach — powered by Claude Opus 4.6

Loads your full Garmin run history from the local DB and starts a
conversational coaching session. The coach has access to all your
metrics and can reason over them with full context.

Usage:
    python coach.py

Commands during chat:
    quit / exit / q    — end the session
    clear              — reset conversation history (keep data context)
    summary            — ask coach to summarize your current fitness state
"""
import datetime
import sqlite3
import sys

import config
import knowledge_base
import onboarding
import store
import vdot_zones
from errors import DependencyError, HarnessError, format_error

# ─── Data context builder ────────────────────────────────────────────────────

def _fmt_pace(pace):
    if pace is None:
        return "n/a"
    mins = int(pace)
    secs = int((pace - mins) * 60)
    return f"{mins}:{secs:02d}/km"


def _fmt_opt(val, fmt=".1f", suffix=""):
    if val is None:
        return "n/a"
    return f"{val:{fmt}}{suffix}"


def build_data_context(conn: sqlite3.Connection) -> str:
    """
    Serialize all run data into a structured text context for the coach.
    Uses prompt caching — this large block is stable across turns.
    """
    runs = store.get_all_runs(conn)
    ae_baseline = store.get_meta(conn, "ae_baseline")
    total_runs = len(runs)

    if total_runs == 0:
        return "No run data available yet. The user needs to run 'python cli.py sync' first."

    # Aggregate stats
    runs_with_rei = [r for r in runs if r["rei"] is not None]
    total_distance_km = sum((r["distance_m"] or 0) for r in runs) / 1000.0
    avg_rei = sum(r["rei"] for r in runs_with_rei) / len(runs_with_rei) if runs_with_rei else None
    zones_context = vdot_zones.build_zones_context(conn)
    recent_runs = runs[:config.COACH_RECENT_RUN_LIMIT]
    omitted_runs = max(0, total_runs - len(recent_runs))

    recent_window_start = datetime.datetime.now() - datetime.timedelta(days=42)
    recent_window_runs = []
    for r in runs:
        try:
            dt = datetime.datetime.fromisoformat(r["start_time"])
        except (ValueError, TypeError):
            continue
        if dt >= recent_window_start:
            recent_window_runs.append(r)
    recent_window_distance_km = sum((r["distance_m"] or 0) for r in recent_window_runs) / 1000.0

    # REI trend: last 10 vs prior 10
    rei_vals = [r["rei"] for r in runs_with_rei]
    rei_trend_str = "insufficient data"
    if len(rei_vals) >= 10:
        import statistics
        recent_rei = statistics.mean(rei_vals[:10])
        if len(rei_vals) >= 20:
            prior_rei = statistics.mean(rei_vals[10:20])
            delta = recent_rei - prior_rei
            direction = "improving" if delta > 0 else "declining"
            rei_trend_str = f"{recent_rei:.1f} avg (last 10), {delta:+.1f} vs prior 10 [{direction}]"
        else:
            rei_trend_str = f"{recent_rei:.1f} avg (last 10 runs)"

    # Weekly mileage (last 8 weeks)
    weekly_km: dict[str, float] = {}
    for r in runs:
        try:
            dt = datetime.datetime.fromisoformat(r["start_time"])
            # ISO week key e.g. "2026-W14"
            week_key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
            weekly_km[week_key] = weekly_km.get(week_key, 0) + (r["distance_m"] or 0) / 1000.0
        except (ValueError, TypeError):
            pass

    sorted_weeks = sorted(weekly_km.items(), reverse=True)[:config.COACH_WEEKLY_MILEAGE_WEEKS]

    # Build the full context string
    lines = [
        "═══════════════════════════════════════════════",
        "ATHLETE GARMIN DATA SUMMARY",
        "═══════════════════════════════════════════════",
        f"Total runs logged   : {total_runs}",
        f"Total distance      : {total_distance_km:.1f} km",
        f"Recent 42d load     : {len(recent_window_runs)} runs / {recent_window_distance_km:.1f} km",
        f"AE baseline         : {ae_baseline if ae_baseline else 'not computed yet'}",
        f"Average REI         : {_fmt_opt(avg_rei)} / 100",
        f"REI trend           : {rei_trend_str}",
    ]
    if zones_context:
        lines += [
            "",
            zones_context,
        ]

    lines += [
        "",
        f"── Weekly Mileage (recent {config.COACH_WEEKLY_MILEAGE_WEEKS} weeks) ──────────",
    ]
    for week, km in sorted_weeks:
        lines.append(f"  {week}: {km:.1f} km")

    lines += [
        "",
        f"── Run History (most recent {len(recent_runs)} of {total_runs}) ──────────",
        f"{'Date':<12} {'Dist':>7} {'Pace':>9} {'HR':>5} {'Cad':>5} {'VOsc':>6} {'HRD':>6} {'CadCV':>6} {'REI':>5}",
        "─" * 72,
    ]
    if omitted_runs:
        lines.append(f"Older runs omitted from prompt: {omitted_runs}")

    for r in recent_runs:
        dist_km = (r["distance_m"] or 0) / 1000.0
        lines.append(
            f"{r['start_time'][:10]:<12} "
            f"{dist_km:>6.1f}km "
            f"{_fmt_pace(r['pace_min_per_km']):>9} "
            f"{_fmt_opt(r['avg_hr'], '.0f'):>5} "
            f"{_fmt_opt(r['avg_cadence_spm'], '.0f'):>5} "
            f"{_fmt_opt(r['avg_vertical_osc_cm'], '.1f'):>6} "
            f"{_fmt_opt(r['hr_drift_pct'], '+.1f'):>6} "
            f"{_fmt_opt(r['cadence_cv'], '.1f'):>6} "
            f"{_fmt_opt(r['rei'], '.1f'):>5}"
        )

    lines += [
        "",
        "═══════════════════════════════════════════════",
        "METRIC DEFINITIONS",
        "═══════════════════════════════════════════════",
        "REI              — 0-100 composite of cadence, vertical oscillation, aerobic efficiency, and ground contact time",
        f"Cadence target   — {config.CADENCE_TARGET_SPM} spm (higher usually means better economy)",
        f"VOsc target      — {config.OSCILLATION_TARGET_CM} cm (lower means less wasted bounce)",
        f"GCT target       — {config.GROUND_CONTACT_TARGET_MS} ms (lower means faster elastic return)",
        "Aerobic Eff      — pace / HR, lower is fitter",
        "HRD              — heart-rate drift %, >5 means notable fatigue or heat load",
        "CadCV            — cadence variation %, lower means more stable form",
        "AE baseline      — athlete's personal aerobic-efficiency benchmark from best runs",
    ]

    return "\n".join(lines)


# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an elite AI running coach with deep expertise in exercise physiology, biomechanics, and training periodization. You have access to this athlete's complete Garmin run history below.

Your coaching philosophy:
- Data-driven but human-centered: every recommendation connects back to the numbers
- Specific over generic: reference actual values from their data, not platitudes
- Progressive: build on what's working, address what's limiting performance
- Injury-aware: flag concerning patterns (HR drift spikes, REI drops, cadence crashes) proactively
- Honest: if the data is ambiguous, say so rather than inventing trends

When analyzing runs:
- Always cite specific dates, REI scores, and metric values when making observations
- Distinguish between noise (single-run variation) and signal (multi-run trends)
- Consider context: hot weather degrades AE, fatigue shows as HR drift, illness appears as REI crash
- Connect metrics: e.g. low cadence + high V.Osc often appear together and fix together
- If the prompt includes VDOT, training paces, or HR zones, use those exact values rather than generic ranges

When giving training recommendations:
- Tie advice to specific upcoming runs, not abstract principles
- Suggest what to watch on the NEXT run given recent trends
- Flag if mileage increases are outpacing recovery (check Body Battery trends if available)
- For form coaching, explain the biomechanical reason, not just the target number

Evidence and citation requirements:
- For any non-trivial answer, include a short `Evidence:` section with 2-4 bullets
- Every evidence bullet must cite exact athlete data: dates, run metrics, current VDOT, pace ranges, or HR zone boundaries
- If you use retrieved coaching knowledge, cite the source label exactly as provided, e.g. `[Source: recovery]`
- If the data is missing or ambiguous, say that explicitly instead of guessing

Default response shape for substantial answers:
Verdict: one concise paragraph
Evidence:
- bullet with exact evidence
- bullet with exact evidence
Next step: one concise paragraph

Tone: direct, informed, encouraging but not sycophantic. You're a coach who knows this athlete's data cold."""


def build_base_system_blocks(conn: sqlite3.Connection) -> list[dict]:
    profile_context = onboarding.build_profile_context(conn)
    data_context = build_data_context(conn)

    base_system_blocks = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
        },
    ]

    if profile_context:
        base_system_blocks.append({
            "type": "text",
            "text": "\n\n" + profile_context,
        })

    base_system_blocks.append({
        "type": "text",
        "text": "\n\nATHLETE DATA:\n\n" + data_context,
        "cache_control": {"type": "ephemeral"},
    })
    return base_system_blocks


def build_turn_system_blocks(
    base_system_blocks: list[dict],
    user_input: str,
) -> list[dict]:
    knowledge_base.init()
    retrieved_text = knowledge_base.retrieve(user_input)
    if not retrieved_text:
        return base_system_blocks

    return base_system_blocks + [
        {
            "type": "text",
            "text": "\n\nRELEVANT COACHING KNOWLEDGE:\n\n" + retrieved_text,
        }
    ]


def _active_conversation(conversation: list[dict]) -> list[dict]:
    return conversation[-config.COACH_MAX_CONVERSATION_MESSAGES:]


def ask_coach_once(
    conn: sqlite3.Connection,
    user_input: str,
    *,
    model: str = "claude-opus-4-6",
    max_tokens: int = 1200,
) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise DependencyError(
            "missing_anthropic_dependency",
            "Coach responses require the `anthropic` package.",
            hint="Run `pip install -r requirements.txt` to enable coach chat and evals.",
            details=str(e),
        ) from e

    client = anthropic.Anthropic()
    system_blocks = build_turn_system_blocks(build_base_system_blocks(conn), user_input)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=[{"role": "user", "content": user_input}],
    )
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "".join(parts).strip()


# ─── Conversation loop ────────────────────────────────────────────────────────

def run_coach():
    try:
        import anthropic
    except ImportError as e:
        raise DependencyError(
            "missing_anthropic_dependency",
            "Coach chat requires the `anthropic` package.",
            hint="Run `pip install -r requirements.txt` to enable coach chat.",
            details=str(e),
        ) from e

    conn = store.open_db()

    total_runs = len(store.get_all_runs(conn))
    if total_runs == 0:
        print("\nNo run data found. Run `python cli.py sync` first to pull your Garmin data.\n")
        return

    # Run onboarding if this is the first launch
    if onboarding.needs_onboarding(conn):
        onboarding.run_onboarding(conn)

    client = anthropic.Anthropic()
    conversation: list[dict] = []

    print("\n" + "═" * 60)
    print("  AI RUNNING COACH")
    print("  Powered by Claude Opus 4.6 + your Garmin data")
    print("═" * 60)
    print(f"  {total_runs} runs loaded. Ask me anything about your training.")
    print("  Type 'quit' to exit, 'clear' to reset conversation.\n")

    base_system_blocks = build_base_system_blocks(conn)

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("Good luck on your next run.")
            break

        if user_input.lower() == "clear":
            conversation.clear()
            print("[Conversation cleared — data context preserved]\n")
            continue

        if user_input.lower() == "summary":
            user_input = (
                "Give me a concise but complete summary of my current fitness state: "
                "REI trend, aerobic efficiency trend, weekly mileage, and the 2-3 most "
                "important things I should focus on right now."
            )
            print(f"You: {user_input}")

        system_blocks = build_turn_system_blocks(base_system_blocks, user_input)

        conversation.append({"role": "user", "content": user_input})

        print("\nCoach: ", end="", flush=True)

        # Stream the response
        full_response = ""
        try:
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=2048,
                thinking={"type": "adaptive"},
                system=system_blocks,
                messages=_active_conversation(conversation),
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            print(event.delta.text, end="", flush=True)
                            full_response += event.delta.text

                final = stream.get_final_message()

            # Show cache stats on first turn so user knows it's working
            if len(conversation) == 1:
                usage = final.usage
                cached = getattr(usage, "cache_read_input_tokens", 0) or 0
                created = getattr(usage, "cache_creation_input_tokens", 0) or 0
                if created > 0:
                    print(f"\n  [Cache: {created:,} tokens written]", flush=True)
                elif cached > 0:
                    print(f"\n  [Cache: {cached:,} tokens read (saved ~90% on data context)]", flush=True)

        except anthropic.APIConnectionError:
            print("\n[Connection error — check your internet and ANTHROPIC_API_KEY]")
            conversation.pop()
            continue
        except anthropic.AuthenticationError:
            print("\n[Authentication error — is ANTHROPIC_API_KEY set correctly?]")
            break
        except anthropic.RateLimitError:
            print("\n[Rate limited — wait a moment and try again]")
            conversation.pop()
            continue

        print("\n", flush=True)
        conversation.append({"role": "assistant", "content": full_response})


if __name__ == "__main__":
    try:
        run_coach()
    except HarnessError as e:
        print(format_error(e), file=sys.stderr)
        raise SystemExit(1)

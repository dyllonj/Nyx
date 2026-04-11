#!/usr/bin/env python3
"""
Onboarding module — conversational intake for the AI running coach.

Runs a guided question flow on first launch, stores answers in user_meta,
and builds a structured profile context block for the coach system prompt.

Key design:
- MVP flow (5 questions) by default; full flow available via FULL_ONBOARDING=1
- Answers stored in user_meta under individual keys
- Red flags surface immediately with brief coaching note
- Profile context built from stored answers on every coach launch
"""

import datetime
import json
from typing import Optional

import store


# ─── Red flag definitions ─────────────────────────────────────────────────────

_RED_FLAG_MESSAGES = {
    "rf_current_pain": (
        "⚠️  You mentioned current pain. Before we get into training, "
        "please check in with a physio or sports doctor — I'll factor this "
        "into every recommendation I make."
    ),
    "rf_stress_fracture": (
        "⚠️  Stress fracture history is significant. I'll keep load increases "
        "very conservative and flag any bone-stress warning signs early."
    ),
    "rf_multiple_injuries": (
        "⚠️  Multiple recurring injuries often signal a systemic issue — "
        "overtraining, load spikes, or a biomechanical pattern worth investigating."
    ),
    "rf_reds_pattern": (
        "⚠️  The pattern you've described — high training, low food — is a "
        "real performance risk. I'll watch your metrics closely for RED-S signs."
    ),
    "rf_rest_anxiety": (
        "⚠️  Anxiety around rest days can lead to under-recovery. "
        "I'll explain the physiological reason for every rest I prescribe."
    ),
    "rf_always_pushes_through": (
        "⚠️  Pushing through pain is one of the top injury risk factors. "
        "I'll help you distinguish productive discomfort from warning signals."
    ),
    "rf_unrealistic_goal": (
        "Note: Your goal timeline is ambitious. Let's run the numbers together "
        "— I'd rather give you an honest projection now than a surprise later."
    ),
    "rf_overtraining": (
        "⚠️  Overtraining symptoms can look identical to other issues. "
        "Your Garmin data will help us track whether you're recovering properly."
    ),
    "rf_sleep_restoration": (
        "Note: Sleep is when adaptation happens. I'll factor sleep quality "
        "into my recommendations — hard sessions need hard recovery."
    ),
    "rf_menstrual_disruption": (
        "⚠️  Training-related menstrual disruption is a medical signal, not a "
        "badge of hard work. Please discuss with your doctor; I'll keep load "
        "conservative until we understand what's happening."
    ),
    "rf_goal_gap": (
        "Note: There's a gap between how important this goal is to you and "
        "your current confidence. That's useful information — we'll build "
        "the confidence through small, trackable wins."
    ),
}

_RED_FLAG_TRIGGERS = {
    "rf_current_pain": [
        "pain", "hurts", "hurting", "aching", "sore knee", "sore hip",
        "sore ankle", "sharp", "swollen", "limping",
    ],
    "rf_stress_fracture": ["stress fracture", "stress fx", "bone stress"],
    "rf_multiple_injuries": [],
    "rf_reds_pattern": [
        "don't eat enough", "not eating enough", "restrict", "low cal",
        "diet", "lose weight while training",
    ],
    "rf_rest_anxiety": [
        "can't take rest", "feel guilty", "anxious on rest",
        "hate rest days", "can't stop",
    ],
    "rf_always_pushes_through": [
        "always push through", "push through pain", "run through injury",
        "never stop",
    ],
    "rf_sleep_restoration": [
        "bad sleep", "can't sleep", "poor sleep", "5 hours", "4 hours",
        "3 hours", "insomnia",
    ],
}


def _detect_red_flags(text: str) -> list[str]:
    flags = []
    lower = text.lower()
    for flag_id, keywords in _RED_FLAG_TRIGGERS.items():
        for keyword in keywords:
            if keyword in lower:
                flags.append(flag_id)
                break
    return flags


# ─── Question flow ────────────────────────────────────────────────────────────

_MVP_QUESTIONS = [
    {
        "key": "onboarding_motivation",
        "text": (
            "Before I dig into your data — what made you decide to get "
            "coaching support right now? What's the thing you actually want to change?"
        ),
    },
    {
        "key": "onboarding_goal",
        "text": (
            "If we got to the end of a season together and you looked back "
            "and felt like it was completely worth it — what would have happened? "
            "What would be different?"
        ),
    },
    {
        "key": "onboarding_injury",
        "text": (
            "Any injuries, surgeries, or body parts that have given you recurring "
            "trouble? Doesn't need to be dramatic — even 'my left knee gets grumpy "
            "on long runs' counts."
        ),
    },
    {
        "key": "onboarding_lifestyle",
        "text": (
            "On a normal week, what does life look like outside of running — "
            "work stress, sleep, family demands? I'm asking because that context "
            "shapes everything about how I'll coach you."
        ),
    },
    {
        "key": "onboarding_easy_effort",
        "text": (
            "When you go out for what you'd call an easy run, what does it "
            "actually feel like? Could you hold a full phone conversation the "
            "whole time?"
        ),
    },
]

_FULL_QUESTIONS = _MVP_QUESTIONS + [
    {
        "key": "onboarding_experience",
        "text": (
            "How long have you been running, and roughly how much training have "
            "you done? I can see your recent Garmin history but I don't know "
            "what came before."
        ),
    },
    {
        "key": "onboarding_race_history",
        "text": (
            "Have you raced before? If so, what distances, and what was your "
            "best result you're proud of?"
        ),
    },
    {
        "key": "onboarding_strength",
        "text": (
            "Do you do any strength training or cross-training alongside "
            "your running? If yes, what does that look like?"
        ),
    },
    {
        "key": "onboarding_importance_confidence",
        "text": (
            "On a scale of 1-10, how important is hitting your running goal "
            "to you right now? And separately — how confident are you that "
            "you'll actually achieve it?"
        ),
    },
    {
        "key": "onboarding_training_vibe",
        "text": (
            "What kind of training do you actually enjoy? Some people love "
            "interval sessions; others dread them. Some love long slow runs; "
            "others find them boring. What feels good to you?"
        ),
    },
]

_ONBOARDING_VERSION = "1"
_ONBOARDING_MODE_KEY = "onboarding_mode"
_ONBOARDING_CURRENT_STEP_KEY = "onboarding_current_step"
_ONBOARDING_STARTED_AT_KEY = "onboarding_started_at"
_ONBOARDING_UPDATED_AT_KEY = "onboarding_updated_at"
_ONBOARDING_VERSION_KEY = "onboarding_version"
_ONBOARDING_PROGRESS_KEYS = (
    _ONBOARDING_MODE_KEY,
    _ONBOARDING_CURRENT_STEP_KEY,
    _ONBOARDING_STARTED_AT_KEY,
    _ONBOARDING_UPDATED_AT_KEY,
    _ONBOARDING_VERSION_KEY,
    "onboarding_red_flags",
)
_VALID_MODES = {"mvp", "full"}
_ALL_QUESTIONS = tuple(_FULL_QUESTIONS)
_QUESTION_KEYS = tuple(question["key"] for question in _ALL_QUESTIONS)
_QUESTION_BY_KEY = {question["key"]: question for question in _ALL_QUESTIONS}


# ─── Shared state helpers ─────────────────────────────────────────────────────

def _now_timestamp() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _normalize_mode(mode: str | None) -> str:
    normalized = (mode or "").strip().lower()
    if normalized in _VALID_MODES:
        return normalized
    return "mvp"


def _questions_for_mode(mode: str | None) -> list[dict]:
    normalized = _normalize_mode(mode)
    if normalized == "full":
        return [dict(question) for question in _FULL_QUESTIONS]
    return [dict(question) for question in _MVP_QUESTIONS]


def _current_mode(conn, mode: str | None = None) -> str:
    if mode is not None:
        return _normalize_mode(mode)
    return _normalize_mode(store.get_meta(conn, _ONBOARDING_MODE_KEY))


def _all_answers(conn) -> dict[str, str]:
    return {key: store.get_meta(conn, key) or "" for key in _QUESTION_KEYS}


def _active_red_flags_from_answers(answers: dict[str, str]) -> list[str]:
    flags: list[str] = []
    for key in _QUESTION_KEYS:
        answer = answers.get(key, "")
        if not answer:
            continue
        for flag in _detect_red_flags(answer):
            if flag not in flags:
                flags.append(flag)
    return flags


def _flag_messages(flag_ids: list[str]) -> list[dict]:
    return [
        {"id": flag_id, "message": _RED_FLAG_MESSAGES[flag_id]}
        for flag_id in flag_ids
        if flag_id in _RED_FLAG_MESSAGES
    ]


# ─── Public API ───────────────────────────────────────────────────────────────

def get_onboarding_questions(full: bool = False) -> list[dict]:
    return _questions_for_mode("full" if full else "mvp")


def get_onboarding_state(conn, mode: str | None = None) -> dict:
    active_mode = _current_mode(conn, mode)
    questions = _questions_for_mode(active_mode)
    answers = _all_answers(conn)
    active_answers = {question["key"]: answers.get(question["key"], "") for question in questions}
    active_red_flags = _active_red_flags_from_answers(answers)
    current_step_raw = store.get_meta(conn, _ONBOARDING_CURRENT_STEP_KEY)
    try:
        current_step = int(current_step_raw) if current_step_raw is not None else 0
    except ValueError:
        current_step = 0
    if questions:
        current_step = max(0, min(current_step, len(questions) - 1))
    else:
        current_step = 0

    return {
        "completed": store.get_meta(conn, "onboarding_completed") == "1",
        "mode": active_mode,
        "current_step": current_step,
        "steps": questions,
        "answers": active_answers,
        "active_red_flags": active_red_flags,
        "active_flag_messages": _flag_messages(active_red_flags),
        "started_at": store.get_meta(conn, _ONBOARDING_STARTED_AT_KEY),
        "updated_at": store.get_meta(conn, _ONBOARDING_UPDATED_AT_KEY),
        "version": store.get_meta(conn, _ONBOARDING_VERSION_KEY) or _ONBOARDING_VERSION,
    }


def save_onboarding_answers(
    conn,
    answers: dict[str, str],
    *,
    current_step: int | None = None,
    mode: str | None = None,
) -> dict:
    active_mode = _current_mode(conn, mode)
    now = _now_timestamp()
    previous_flags = _active_red_flags_from_answers(_all_answers(conn))

    if store.get_meta(conn, _ONBOARDING_STARTED_AT_KEY) is None:
        store.set_meta(conn, _ONBOARDING_STARTED_AT_KEY, now)
    store.set_meta(conn, _ONBOARDING_UPDATED_AT_KEY, now)
    store.set_meta(conn, _ONBOARDING_MODE_KEY, active_mode)
    store.set_meta(conn, _ONBOARDING_VERSION_KEY, _ONBOARDING_VERSION)

    if current_step is not None:
        store.set_meta(conn, _ONBOARDING_CURRENT_STEP_KEY, str(max(0, current_step)))

    for key, value in answers.items():
        if key not in _QUESTION_BY_KEY:
            raise ValueError(f"Unknown onboarding answer key: {key}")
        store.set_meta(conn, key, (value or "").strip())

    active_red_flags = _active_red_flags_from_answers(_all_answers(conn))
    store.set_meta(conn, "onboarding_red_flags", json.dumps(active_red_flags))

    state = get_onboarding_state(conn, mode=active_mode)
    state["new_flag_messages"] = _flag_messages(
        [flag for flag in active_red_flags if flag not in previous_flags]
    )
    return state


def complete_onboarding(conn, *, mode: str | None = None) -> dict:
    active_mode = _current_mode(conn, mode)
    questions = _questions_for_mode(active_mode)
    missing_answers = {
        question["key"]: ""
        for question in questions
        if store.get_meta(conn, question["key"]) is None
    }
    save_onboarding_answers(
        conn,
        missing_answers,
        current_step=max(0, len(questions) - 1),
        mode=active_mode,
    )
    store.set_meta(conn, "onboarding_completed", "1")
    state = get_onboarding_state(conn, mode=active_mode)
    state["profile_context"] = build_profile_context(conn)
    return state


def reset_onboarding(conn, *, clear_answers: bool = True) -> None:
    keys_to_clear = list(_ONBOARDING_PROGRESS_KEYS)
    if clear_answers:
        keys_to_clear.extend(_QUESTION_KEYS)
    store.delete_meta(conn, *keys_to_clear)
    store.set_meta(conn, "onboarding_completed", "0")
    store.set_meta(conn, "onboarding_red_flags", "[]")


def needs_onboarding(conn) -> bool:
    return store.get_meta(conn, "onboarding_completed") != "1"


def run_onboarding(conn, full: bool = False) -> None:
    mode = "full" if full else "mvp"
    questions = get_onboarding_questions(full=full)

    print("\n" + "═" * 60)
    print("  GETTING TO KNOW YOU")
    print("─" * 60)
    print(
        "  Before I dig into your Garmin data, I want to understand\n"
        "  the person behind the numbers. Just a few questions —\n"
        "  answer as much or as little as you like.\n"
        "  (Type 'skip' on any question to skip it.)"
    )
    print("═" * 60 + "\n")

    save_onboarding_answers(conn, {}, current_step=0, mode=mode)

    for i, question in enumerate(questions):
        print(f"  ({i+1}/{len(questions)}) {question['text']}\n")
        try:
            answer = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Onboarding interrupted — you can complete it later]\n")
            return

        stored_answer = "" if answer.lower() == "skip" or not answer else answer
        save_result = save_onboarding_answers(
            conn,
            {question["key"]: stored_answer},
            current_step=min(i + 1, len(questions) - 1),
            mode=mode,
        )

        for flag in save_result["new_flag_messages"]:
            print(f"\n  {flag['message']}\n")
        print()

    complete_onboarding(conn, mode=mode)

    print("─" * 60)
    print("  Got it. Let's look at your data.\n")


def build_profile_context(conn) -> Optional[str]:
    answers = {key: store.get_meta(conn, key) for key in _QUESTION_KEYS}
    filled = {key: value for key, value in answers.items() if value}
    if not filled:
        return None

    red_flags_raw = store.get_meta(conn, "onboarding_red_flags") or "[]"
    try:
        red_flags = json.loads(red_flags_raw)
    except json.JSONDecodeError:
        red_flags = []

    label_map = {
        "onboarding_motivation": "Why they sought coaching",
        "onboarding_goal": "Success vision / goal",
        "onboarding_injury": "Injury / pain history",
        "onboarding_lifestyle": "Life context (stress, sleep, demands)",
        "onboarding_easy_effort": "Easy run effort calibration",
        "onboarding_experience": "Running background",
        "onboarding_race_history": "Race history / best results",
        "onboarding_strength": "Strength / cross-training",
        "onboarding_importance_confidence": "Importance / confidence (1-10)",
        "onboarding_training_vibe": "Training preferences / enjoyment",
    }

    lines = [
        "═══════════════════════════════════════════════",
        "ATHLETE PROFILE (from onboarding)",
        "═══════════════════════════════════════════════",
    ]

    for key, label in label_map.items():
        value = filled.get(key)
        if value:
            lines.append(f"{label}:")
            lines.append(f"  {value}")
            lines.append("")

    if red_flags:
        lines.append("Active coaching flags:")
        for flag in red_flags:
            lines.append(f"  • {flag}")
        lines.append("")

    lines.append(
        "Coaching instruction: Reference the athlete's stated goals and "
        "context when making recommendations. Acknowledge injury history "
        "before suggesting load increases. Active flags require extra care."
    )

    return "\n".join(lines)

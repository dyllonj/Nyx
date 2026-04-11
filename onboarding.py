#!/usr/bin/env python3
"""
Onboarding module — conversational intake for the AI running coach.

Runs a guided question flow on first launch, stores answers in user_meta,
and builds a structured profile context block for the coach system prompt.

Key design:
- MVP flow (5 questions) by default; full flow available via FULL_ONBOARDING=1
- Answers stored as JSON in user_meta under individual keys
- Red flags surface immediately with brief coaching note
- Profile context built from stored answers on every coach launch
"""

import json
import sys
from typing import Optional

import store

# ─── Question loading ─────────────────────────────────────────────────────────

_QUESTIONS_PATH = "onboarding_questions.json"

def _load_questions() -> dict:
    try:
        with open(_QUESTIONS_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


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

# Simple keyword triggers for red flag detection from free-text answers
_RED_FLAG_TRIGGERS = {
    "rf_current_pain": [
        "pain", "hurts", "hurting", "aching", "sore knee", "sore hip",
        "sore ankle", "sharp", "swollen", "limping",
    ],
    "rf_stress_fracture": ["stress fracture", "stress fx", "bone stress"],
    "rf_multiple_injuries": [],  # handled by follow-up logic
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
    """Scan free-text answer for red flag keywords. Returns list of flag IDs."""
    flags = []
    lower = text.lower()
    for flag_id, keywords in _RED_FLAG_TRIGGERS.items():
        for kw in keywords:
            if kw in lower:
                flags.append(flag_id)
                break
    return flags


# ─── MVP question flow ────────────────────────────────────────────────────────

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

# Additional questions for full onboarding flow
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


# ─── Public API ───────────────────────────────────────────────────────────────

def needs_onboarding(conn) -> bool:
    """True if the user hasn't completed onboarding yet."""
    return store.get_meta(conn, "onboarding_completed") != "1"


def run_onboarding(conn, full: bool = False) -> None:
    """
    Run the conversational onboarding flow.
    Stores all answers in user_meta and sets onboarding_completed=1 when done.
    """
    questions = _FULL_QUESTIONS if full else _MVP_QUESTIONS

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

    active_red_flags = []

    for i, q in enumerate(questions):
        print(f"  ({i+1}/{len(questions)}) {q['text']}\n")
        try:
            answer = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Onboarding interrupted — you can complete it later]\n")
            return

        if answer.lower() == "skip" or not answer:
            store.set_meta(conn, q["key"], "")
            print()
            continue

        store.set_meta(conn, q["key"], answer)

        # Check for red flags in the answer
        flags = _detect_red_flags(answer)
        for flag in flags:
            if flag not in active_red_flags:
                active_red_flags.append(flag)
                msg = _RED_FLAG_MESSAGES.get(flag)
                if msg:
                    print(f"\n  {msg}\n")

        print()

    # Mark onboarding complete
    store.set_meta(conn, "onboarding_completed", "1")
    store.set_meta(conn, "onboarding_red_flags", json.dumps(active_red_flags))

    print("─" * 60)
    print("  Got it. Let's look at your data.\n")


def build_profile_context(conn) -> Optional[str]:
    """
    Build a structured profile text block from stored onboarding answers.
    Returns None if no answers are stored yet.
    Called by coach.py to inject user context into the system prompt.
    """
    keys = [q["key"] for q in _FULL_QUESTIONS]
    answers = {k: store.get_meta(conn, k) for k in keys}

    # Filter to answered questions only
    filled = {k: v for k, v in answers.items() if v}
    if not filled:
        return None

    red_flags_raw = store.get_meta(conn, "onboarding_red_flags") or "[]"
    try:
        red_flags = json.loads(red_flags_raw)
    except json.JSONDecodeError:
        red_flags = []

    label_map = {
        "onboarding_motivation":           "Why they sought coaching",
        "onboarding_goal":                 "Success vision / goal",
        "onboarding_injury":               "Injury / pain history",
        "onboarding_lifestyle":            "Life context (stress, sleep, demands)",
        "onboarding_easy_effort":          "Easy run effort calibration",
        "onboarding_experience":           "Running background",
        "onboarding_race_history":         "Race history / best results",
        "onboarding_strength":             "Strength / cross-training",
        "onboarding_importance_confidence":"Importance / confidence (1-10)",
        "onboarding_training_vibe":        "Training preferences / enjoyment",
    }

    lines = [
        "═══════════════════════════════════════════════",
        "ATHLETE PROFILE (from onboarding)",
        "═══════════════════════════════════════════════",
    ]

    for key, label in label_map.items():
        val = filled.get(key)
        if val:
            lines.append(f"{label}:")
            lines.append(f"  {val}")
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

import os
import re
import sqlite3
from dataclasses import dataclass

from errors import DependencyError


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class EvalResult:
    eval_id: str
    status: str
    summary: str
    response: str = ""


_DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
_PACE_RANGE_RE = re.compile(r"\b\d+:\d{2}\s*[–-]\s*\d+:\d{2}\s*/km\b")
_PACE_RE = re.compile(r"\b\d+:\d{2}\s*/km\b")
_BPM_RANGE_RE = re.compile(r"\b\d{2,3}\s*[–-]\s*\d{2,3}\s*bpm\b", re.IGNORECASE)


GOLDEN_QUESTIONS = [
    {
        "eval_id": "easy_pace",
        "question": "What pace should my easy runs be right now?",
        "needs_vdot": True,
        "checks": [
            ("pace guidance", lambda text: bool(_PACE_RANGE_RE.search(text)) or "can't estimate" in text.lower()),
            ("evidence section", lambda text: "Evidence:" in text),
            ("vdot mention", lambda text: "VDOT" in text or "easy pace" in text.lower()),
        ],
    },
    {
        "eval_id": "threshold_pace",
        "question": "What's my tempo or threshold pace?",
        "needs_vdot": True,
        "checks": [
            ("threshold pace", lambda text: bool(_PACE_RE.search(text)) or "can't estimate" in text.lower()),
            ("evidence section", lambda text: "Evidence:" in text),
            ("vdot mention", lambda text: "VDOT" in text or "threshold" in text.lower()),
        ],
    },
    {
        "eval_id": "easy_too_hard",
        "question": "Am I running my easy runs too hard?",
        "needs_runs": True,
        "checks": [
            ("evidence section", lambda text: "Evidence:" in text),
            ("specific evidence", lambda text: bool(_DATE_RE.search(text)) or "Zone 2" in text or "easy pace" in text.lower()),
            ("next step", lambda text: "Next step:" in text),
        ],
    },
    {
        "eval_id": "easy_hr_zone",
        "question": "What heart rate zone should my easy runs be in?",
        "needs_hr_zones": True,
        "checks": [
            ("zone mention", lambda text: "Zone 2" in text or "easy" in text.lower()),
            ("bpm range", lambda text: bool(_BPM_RANGE_RE.search(text)) or "can't estimate" in text.lower()),
            ("evidence section", lambda text: "Evidence:" in text),
        ],
    },
]


def _has_meta(conn: sqlite3.Connection, key: str) -> bool:
    from store import get_meta

    return bool(get_meta(conn, key))


def run_offline_evals(conn: sqlite3.Connection) -> list[EvalResult]:
    import coach

    context = coach.build_data_context(conn)
    row = conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()
    total_runs = int(row["n"] or 0) if row else 0
    results = [
        EvalResult(
            eval_id="context_present",
            status=PASS if bool(context.strip()) else FAIL,
            summary="Coach data context builds successfully." if context.strip() else "Coach data context is empty.",
        ),
        EvalResult(
            eval_id="evidence_contract",
            status=PASS if "Evidence and citation requirements" in coach.SYSTEM_PROMPT else FAIL,
            summary="System prompt includes evidence/citation expectations." if "Evidence and citation requirements" in coach.SYSTEM_PROMPT else "System prompt lacks explicit evidence/citation expectations.",
        ),
    ]

    if total_runs == 0:
        results.insert(1, EvalResult(
            eval_id="context_compaction",
            status=WARN,
            summary="Skipped: there is no run data yet, so prompt compaction cannot be evaluated meaningfully.",
        ))
    else:
        results.insert(1, EvalResult(
            eval_id="context_compaction",
            status=PASS if "Run History (most recent" in context else WARN,
            summary="Prompt context uses a compact recent-run table." if "Run History (most recent" in context else "Prompt context is not obviously compacted.",
        ))

    if _has_meta(conn, "current_vdot"):
        if total_runs == 0:
            results.append(EvalResult(
                eval_id="vdot_context",
                status=WARN,
                summary="Skipped: VDOT metadata exists, but there is no run history in the local DB.",
            ))
        else:
            results.append(EvalResult(
                eval_id="vdot_context",
                status=PASS if "Easy pace" in context and "Threshold pace" in context else FAIL,
                summary="VDOT training paces are available in coach context." if "Easy pace" in context and "Threshold pace" in context else "VDOT context is missing training pace lines.",
            ))

    if _has_meta(conn, "hr_zones_json"):
        if total_runs == 0:
            results.append(EvalResult(
                eval_id="hr_zone_context",
                status=WARN,
                summary="Skipped: HR zones exist, but there is no run history in the local DB.",
            ))
        else:
            results.append(EvalResult(
                eval_id="hr_zone_context",
                status=PASS if "Zone 2" in context and "Heart Rate Zones" in context else FAIL,
                summary="HR zones are available in coach context." if "Zone 2" in context and "Heart Rate Zones" in context else "HR zones are missing from coach context.",
            ))

    return results


def run_live_evals(
    conn: sqlite3.Connection,
    *,
    model: str = "kimi-2.5",
    limit: int = 0,
) -> list[EvalResult]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise DependencyError(
            "missing_anthropic_key",
            "Live evals require `ANTHROPIC_API_KEY`.",
            hint="Export `ANTHROPIC_API_KEY` and retry `python cli.py eval --live`.",
        )

    import coach

    selected = GOLDEN_QUESTIONS[:limit] if limit else GOLDEN_QUESTIONS
    results: list[EvalResult] = []

    for case in selected:
        if case.get("needs_vdot") and not _has_meta(conn, "current_vdot"):
            results.append(EvalResult(case["eval_id"], WARN, "Skipped: current VDOT is not available."))
            continue
        if case.get("needs_hr_zones") and not _has_meta(conn, "hr_zones_json"):
            results.append(EvalResult(case["eval_id"], WARN, "Skipped: HR zones are not available."))
            continue
        if case.get("needs_runs"):
            row = conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()
            if not row or not row["n"]:
                results.append(EvalResult(case["eval_id"], WARN, "Skipped: no run history is available."))
                continue

        response = coach.ask_coach_once(conn, case["question"], model=model)
        failing_checks = [label for label, predicate in case["checks"] if not predicate(response)]
        status = PASS if not failing_checks else FAIL
        summary = "All checks passed." if not failing_checks else f"Failed checks: {', '.join(failing_checks)}"
        results.append(EvalResult(case["eval_id"], status, summary, response=response))

    return results


def format_eval_report(results: list[EvalResult], *, verbose: bool = False) -> str:
    lines = [
        "Nyx Harness Evals",
        "=================",
    ]
    for result in results:
        lines.append(f"[{result.status}] {result.eval_id}: {result.summary}")
        if verbose and result.response:
            lines.append(result.response)
            lines.append("")
    return "\n".join(lines)

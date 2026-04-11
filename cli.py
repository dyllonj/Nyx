#!/usr/bin/env python3
"""
Garmin Run Efficiency Tracker

Commands:
  sync              Pull all running data and compute metrics
  export            Export local run data to JSON or CSV
  backup            Snapshot the local SQLite database
  report [--n N]    Show recent runs with REI and trends
  inspect <id>      Full REI breakdown for one activity
  plot              Plot REI over time (requires matplotlib)
  vdot              Show or recalculate VDOT estimate and HR zones
  status            Show harness/data status
  doctor            Run dependency and environment checks
  eval              Run offline or live golden-question evals
"""
import argparse
import datetime
import sys

import backup_utils
import evals
import health
import metrics
import models
import onboarding
import store
import sync_engine
import training_plans
import vdot_zones
from errors import HarnessError, format_error


# ─── sync ────────────────────────────────────────────────────────────────────

def cmd_sync(args):
    try:
        sync_engine.run_sync(log=print, interactive=True)
    except HarnessError:
        raise
    except Exception as e:
        raise HarnessError(
            "sync_failed",
            "Sync failed unexpectedly.",
            hint="Run `python cli.py doctor` to inspect local dependencies and sync state.",
            details=str(e),
        ) from e


# ─── report ──────────────────────────────────────────────────────────────────

def _fmt_pace(pace_min_per_km):
    if pace_min_per_km is None:
        return "—"
    mins = int(pace_min_per_km)
    secs = int((pace_min_per_km - mins) * 60)
    return f"{mins}:{secs:02d}/km"


def _fmt_optional(val, fmt=".1f", suffix=""):
    if val is None:
        return "n/a"
    return f"{val:{fmt}}{suffix}"


def _meta_float(conn, key):
    raw = store.get_meta(conn, key)
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def cmd_report(args):
    conn = store.open_db()
    runs = store.get_all_runs(conn, limit=args.n)

    if not runs:
        print("No runs found. Run 'python cli.py sync' first.")
        return

    zones_context = vdot_zones.build_zones_context(conn)
    if zones_context:
        print(zones_context)
        print()

    header = (
        f"{'Date':<12} {'Dist':>7} {'Pace':>9} {'AvgHR':>6} "
        f"{'Cadence':>8} {'V.Osc':>6} {'HR Drift':>9} {'REI':>6}"
    )
    print(header)
    print("-" * len(header))

    for row in runs:
        dist_km = (row["distance_m"] or 0) / 1000.0
        date_str = row["start_time"][:10]
        print(
            f"{date_str:<12} "
            f"{dist_km:>6.1f}km "
            f"{_fmt_pace(row['pace_min_per_km']):>9} "
            f"{_fmt_optional(row['avg_hr'], '.0f', ' bpm'):>10} "
            f"{_fmt_optional(row['avg_cadence_spm'], '.0f', ' spm'):>10} "
            f"{_fmt_optional(row['avg_vertical_osc_cm'], '.1f', 'cm'):>7} "
            f"{_fmt_optional(row['hr_drift_pct'], '+.1f', '%'):>9} "
            f"{_fmt_optional(row['rei'], '.1f'):>6}"
        )

    # REI trend: compare last 10 vs prior 10
    all_runs = store.get_all_runs(conn)
    rei_vals = [r["rei"] for r in all_runs if r["rei"] is not None]
    if len(rei_vals) >= 10:
        import statistics
        recent = statistics.mean(rei_vals[:10])
        prior = statistics.mean(rei_vals[10:20]) if len(rei_vals) >= 20 else None
        print()
        if prior:
            delta = recent - prior
            direction = "improving" if delta > 0 else "declining"
            print(f"REI trend (last 10 vs prior 10): {delta:+.1f} pts  [{direction}]")
        print(f"Average REI (last 10 runs): {recent:.1f}")


# ─── inspect ─────────────────────────────────────────────────────────────────

def cmd_inspect(args):
    conn = store.open_db()
    row = store.get_run(conn, args.id)
    if not row:
        print(f"Activity {args.id} not found. Run 'python cli.py sync' first.")
        return

    ae_baseline_str = store.get_meta(conn, "ae_baseline")
    ae_baseline = float(ae_baseline_str) if ae_baseline_str else None

    import datetime
    run = models.RunSummary(
        activity_id=row["activity_id"],
        name=row["name"] or "",
        start_time=datetime.datetime.fromisoformat(row["start_time"]),
        duration_sec=row["duration_sec"] or 0,
        distance_m=row["distance_m"] or 0,
        calories=row["calories"] or 0,
        avg_hr=row["avg_hr"],
        max_hr=row["max_hr"],
        avg_speed_ms=row["avg_speed_ms"],
        pace_min_per_km=row["pace_min_per_km"],
        avg_cadence_spm=row["avg_cadence_spm"],
        avg_vertical_osc_cm=row["avg_vertical_osc_cm"],
        avg_ground_contact_ms=row["avg_ground_contact_ms"],
        avg_stride_length_cm=row["avg_stride_length_cm"],
        aerobic_efficiency=row["aerobic_efficiency"],
        hr_drift_pct=row["hr_drift_pct"],
        cadence_cv=row["cadence_cv"],
        rei=row["rei"],
    )

    dist_km = run.distance_m / 1000.0
    dur_min = run.duration_sec / 60.0

    print(f"\nActivity: {run.name}")
    print(f"Date    : {run.start_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"Distance: {dist_km:.2f} km   Duration: {dur_min:.0f} min")
    print(f"Pace    : {_fmt_pace(run.pace_min_per_km)}   Avg HR: {_fmt_optional(run.avg_hr, '.0f')} bpm")
    print()

    rei = row["rei"]
    if rei is not None:
        print(f"REI: {rei:.1f} / 100")
        print()
        components = metrics.rei_component_breakdown(run, ae_baseline)
        total_weight = sum(c["weight"] for c in components)
        print(f"{'Component':<22} {'Score':>6}  {'Detail':<38}  {'Weight':>7}  {'Points':>7}")
        print("-" * 90)
        for c in components:
            norm_weight = c["weight"] / total_weight if total_weight else 0
            print(
                f"  {c['name']:<20} {c['score']:>5.1f}  {c['detail']:<38}  "
                f"{norm_weight*100:>5.0f}%   {c['contribution']:>6.1f}"
            )
        print("-" * 90)
        print(f"  {'REI':<48} {rei:>6.1f}")
    else:
        print("REI not computed yet. Run 'python cli.py sync' first.")

    print()
    print(f"Additional metrics:")
    print(f"  Aerobic Efficiency : {_fmt_optional(run.aerobic_efficiency, '.4f')} min/km/bpm")
    if ae_baseline:
        print(f"  AE Baseline        : {ae_baseline:.4f}")
    print(f"  HR Drift           : {_fmt_optional(run.hr_drift_pct, '+.1f', '%')}")
    print(f"  Cadence CV         : {_fmt_optional(run.cadence_cv, '.1f', '%')} (lower = more consistent)")
    if run.avg_stride_length_cm:
        print(f"  Avg Stride Length  : {run.avg_stride_length_cm:.1f} cm")
    print(f"  Calories           : {run.calories}")


# ─── plot ────────────────────────────────────────────────────────────────────

def cmd_plot(args):
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import datetime
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib")
        return

    conn = store.open_db()
    all_runs = store.get_all_runs(conn)
    runs_with_rei = [(r["start_time"][:10], r["rei"]) for r in all_runs if r["rei"] is not None]

    if not runs_with_rei:
        print("No REI data to plot yet.")
        return

    runs_with_rei.reverse()  # oldest first
    dates = [datetime.date.fromisoformat(d) for d, _ in runs_with_rei]
    reis = [r for _, r in runs_with_rei]

    # Rolling 5-run average
    import statistics
    window = 5
    rolling = []
    for i in range(len(reis)):
        start = max(0, i - window + 1)
        rolling.append(statistics.mean(reis[start:i+1]))

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.scatter(dates, reis, alpha=0.5, s=30, color="#4C9BE8", label="REI per run", zorder=3)
    ax.plot(dates, rolling, color="#E84C4C", linewidth=2, label=f"{window}-run rolling avg")
    ax.axhline(y=70, color="gray", linestyle="--", linewidth=0.8, alpha=0.6, label="70 (target)")

    ax.set_title("Run Efficiency Index (REI) Over Time", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date")
    ax.set_ylabel("REI (0–100)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate()
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("rei_plot.png", dpi=150)
    print("Saved rei_plot.png")
    plt.show()


def cmd_vdot(args):
    conn = store.open_db()

    if args.resting is not None:
        if args.resting <= 0:
            print("Resting HR must be positive.")
            return
        store.set_meta(conn, "resting_hr", str(args.resting))

    if args.maxhr is not None:
        if args.maxhr <= 0:
            print("Max HR must be positive.")
            return
        store.set_meta(conn, "max_hr_estimated", str(args.maxhr))

    current_vdot = _meta_float(conn, "current_vdot")
    if args.recalc or current_vdot is None:
        print("Estimating VDOT from run data...")
        current_vdot = vdot_zones.estimate_vdot_from_runs(conn)
        qualifying_runs = store.get_meta(conn, "vdot_qualifying_run_count") or "0"
        if current_vdot is None:
            print("No qualifying runs yet for VDOT estimation.")
        else:
            print(f"Estimated VDOT: {current_vdot:.1f} (from {qualifying_runs} qualifying runs)")
    else:
        print(f"Current VDOT: {current_vdot:.1f}")

    try:
        hr_zones = vdot_zones._refresh_hr_zones(conn)
    except ValueError as e:
        print(f"Unable to compute HR zones: {e}")
        return

    context = vdot_zones.build_zones_context(conn)
    if context:
        print()
        print(context)
        return

    if hr_zones:
        print()
        print(f"Heart rate zones computed from max HR {hr_zones['max_hr']} bpm, but no VDOT estimate is available yet.")
        return

    print("No VDOT estimate or HR zone data available yet. Run `python cli.py sync` after more qualifying runs.")


def cmd_status(args):
    conn = store.open_db()
    print(health.format_status(conn))


def cmd_doctor(args):
    conn = store.open_db()
    print(health.format_doctor(conn))


def _parse_since_arg(value: str | None):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.date.fromisoformat(value)
        except ValueError as e:
            raise HarnessError(
                "invalid_since",
                "The `--since` value must be an ISO date or datetime.",
                hint="Use a value like `2026-04-01` or `2026-04-01T07:00:00`.",
                details=str(e),
            ) from e


def cmd_export(args):
    conn = store.open_db()
    try:
        output_path = backup_utils.export_runs(
            conn,
            format_name=args.format,
            output_path=args.output,
            since=_parse_since_arg(args.since),
        )
    finally:
        conn.close()

    print(f"Exported {args.format.upper()} data to {output_path}")


def cmd_backup(args):
    output_path = backup_utils.snapshot_database(output_path=args.output)
    print(f"Backed up local DB to {output_path}")


def cmd_plan(args):
    conn = store.open_db()
    try:
        plan = training_plans.build_plan_from_db(
            conn,
            goal=args.goal,
            weeks=args.weeks,
            days_per_week=args.days_per_week,
            current_vdot=args.vdot,
        )
    finally:
        conn.close()

    print(f"Goal: {plan.goal}")
    print(f"Weeks: {plan.weeks}  Days/week: {plan.days_per_week}")
    print(f"Recent 42d load: {plan.recent_42d_distance_km:.1f} km")
    print(f"Current VDOT: {plan.current_vdot:.1f}" if plan.current_vdot is not None else "Current VDOT: n/a")
    print()
    for week in plan.weeks_detail:
        print(f"Week {week.week} [{week.phase}] — target {week.target_distance_km:.1f} km")
        print(f"  Focus: {week.focus}")
        for workout in week.workouts:
            print(f"  {workout.day} · {workout.title}: {workout.description}")
        print()
    print("Notes:")
    for note in plan.notes:
        print(f"- {note}")


def cmd_eval(args):
    conn = store.open_db()
    offline_results = evals.run_offline_evals(conn)
    print(evals.format_eval_report(offline_results, verbose=args.verbose))

    if not args.live:
        return

    print()
    live_results = evals.run_live_evals(conn, model=args.model, limit=args.limit)
    print(evals.format_eval_report(live_results, verbose=args.verbose))


# ─── onboarding ──────────────────────────────────────────────────────────────

def cmd_onboarding(args):
    conn = store.open_db()
    if args.reset:
        # Clear all onboarding-related keys
        store.set_meta(conn, "onboarding_completed", "0")
        print("[Onboarding reset — answers cleared]\n")

    onboarding.run_onboarding(conn, full=args.full)

    # Show the resulting profile context
    profile = onboarding.build_profile_context(conn)
    if profile:
        print("\n" + "─" * 60)
        print("Profile stored. Here's what the coach will see:\n")
        print(profile)


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Garmin Run Efficiency Tracker")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("sync", help="Pull all running data and compute metrics")

    exp = sub.add_parser("export", help="Export local run data to JSON or CSV")
    exp.add_argument("--format", choices=["json", "csv"], default="json", help="Export format (default: json)")
    exp.add_argument("--since", help="Only export runs on or after this ISO date/datetime")
    exp.add_argument("--output", help="Output file path")

    bak = sub.add_parser("backup", help="Snapshot the local SQLite database")
    bak.add_argument("--output", help="Output backup file path")

    rep = sub.add_parser("report", help="Show recent runs with REI")
    rep.add_argument("--n", type=int, default=20, help="Number of runs to show (default 20)")

    ins = sub.add_parser("inspect", help="Full REI breakdown for one activity")
    ins.add_argument("id", type=int, help="Activity ID")

    sub.add_parser("plot", help="Plot REI over time")

    vdot = sub.add_parser("vdot", help="Show or recalculate VDOT estimate and training zones")
    vdot.add_argument("--recalc", action="store_true", help="Recalculate VDOT from qualifying run data")
    vdot.add_argument("--resting", type=int, help="Set resting HR for Karvonen zone computation")
    vdot.add_argument("--maxhr", type=int, help="Override max HR used for estimation and zones")

    sub.add_parser("status", help="Show local harness and data status")
    sub.add_parser("doctor", help="Run dependency and environment checks")

    ev = sub.add_parser("eval", help="Run offline or live golden-question evals")
    ev.add_argument("--live", action="store_true", help="Run live model evals in addition to offline checks")
    ev.add_argument("--model", default="kimi-2.5", help="Model to use for live evals")
    ev.add_argument("--limit", type=int, default=0, help="Limit live evals to the first N golden questions")
    ev.add_argument("--verbose", action="store_true", help="Print full model responses in the eval report")

    ob = sub.add_parser("onboarding", help="Re-run onboarding questions")
    ob.add_argument("--reset", action="store_true", help="Clear existing answers and start over")
    ob.add_argument("--full", action="store_true", help="Run full question set (default: MVP 5 questions)")

    plan = sub.add_parser("plan", help="Generate a structured training plan from current local data")
    plan.add_argument("--goal", required=True, help="Goal race or focus, e.g. 'half marathon' or '5k'")
    plan.add_argument("--weeks", type=int, default=8, help="Plan length in weeks (default 8)")
    plan.add_argument("--days-per-week", type=int, default=4, help="Planned run days per week (default 4)")
    plan.add_argument("--vdot", type=float, help="Override current VDOT")

    args = parser.parse_args()

    if args.command == "sync":
        cmd_sync(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "backup":
        cmd_backup(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "inspect":
        cmd_inspect(args)
    elif args.command == "plot":
        cmd_plot(args)
    elif args.command == "vdot":
        cmd_vdot(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "eval":
        cmd_eval(args)
    elif args.command == "onboarding":
        cmd_onboarding(args)
    elif args.command == "plan":
        cmd_plan(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except HarnessError as e:
        print(format_error(e), file=sys.stderr)
        sys.exit(1)

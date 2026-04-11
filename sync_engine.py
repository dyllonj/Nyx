import datetime
from dataclasses import dataclass
from typing import Callable

import auth
import fetch
import metrics
import models
import store
import vdot_zones


LogFn = Callable[[str], None]


@dataclass
class SyncSummary:
    new_runs: int
    activities_seen: int
    pending_details: int
    detail_failures: int
    ae_baseline: float | None
    current_vdot: float | None
    hr_max: int | None


def _noop_log(_: str) -> None:
    return None


def run_sync(
    *,
    log: LogFn | None = None,
    email: str | None = None,
    password: str | None = None,
    interactive: bool = True,
) -> SyncSummary:
    log = log or _noop_log

    conn = store.open_db()
    store.mark_sync_started(conn)

    try:
        client = auth.get_client(email=email, password=password, interactive=interactive)
        start_date = store.get_sync_start_date(conn)

        activities = fetch.fetch_running_activities(client, start_date)
        new_count = 0
        for act in activities:
            existing_row = store.get_run(conn, act["activityId"])
            already_present = existing_row is not None
            run = models.RunSummary.from_api_summary(act)
            store.upsert_run(
                conn,
                run,
                detail_fetched=bool(existing_row["detail_fetched"]) if existing_row else False,
            )
            if not already_present:
                new_count += 1

        log(f"Stored {new_count} new runs ({len(activities)} activities seen since watermark).")

        pending = store.get_runs_without_details(conn)
        detail_failures = 0
        if not pending:
            log("All runs already have detailed metrics.")
        else:
            log(f"Fetching details for {len(pending)} runs (this may take a while)...")

        for i, activity_id in enumerate(pending, 1):
            row = store.get_run(conn, activity_id)
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
            )

            log(f"[{i}/{len(pending)}] {run.start_time.date()} - {run.name[:60]}")

            detail_fetched_ok = False
            try:
                detail = fetch.fetch_activity_detail(client, activity_id)
                parsed = fetch.parse_detail_metrics(detail)
                metrics.apply_detail_metrics(run, parsed)

                splits = fetch.fetch_activity_splits(client, activity_id)
                metrics.apply_split_metrics(run, splits)
                store.upsert_laps(conn, activity_id, splits.get("lapDTOs", []))
                detail_fetched_ok = True
            except Exception as e:
                detail_failures += 1
                log(f"Warning: could not fetch details for {activity_id}: {e}")

            ae_baseline_str = store.get_meta(conn, "ae_baseline")
            ae_baseline = float(ae_baseline_str) if ae_baseline_str else None
            metrics.compute_all(run, ae_baseline)
            store.upsert_run(conn, run, detail_fetched=detail_fetched_ok)

        log("Computing aerobic efficiency baseline...")
        ae_baseline = store.compute_and_store_ae_baseline(conn)
        if ae_baseline:
            updated = store.recompute_all_rei(conn, ae_baseline)
            log(f"AE baseline: {ae_baseline:.4f} ({updated} REI scores updated)")
        else:
            log("Not enough qualifying runs to compute AE baseline yet.")

        log("Estimating VDOT from run data...")
        current_vdot = store.get_meta(conn, "current_vdot")
        parsed_vdot = float(current_vdot) if current_vdot else None
        if parsed_vdot is None:
            parsed_vdot = vdot_zones.estimate_vdot_from_runs(conn)
            qualifying_runs = store.get_meta(conn, "vdot_qualifying_run_count") or "0"
            if parsed_vdot is None:
                log("No qualifying runs yet for VDOT estimation.")
            else:
                log(f"Estimated VDOT: {parsed_vdot:.1f} (from {qualifying_runs} qualifying runs)")
        else:
            log(f"Current VDOT: {parsed_vdot:.1f} (existing estimate)")

        try:
            hr_zones = vdot_zones._refresh_hr_zones(conn)
        except ValueError as e:
            hr_zones = None
            log(f"Unable to compute HR zones: {e}")

        if parsed_vdot is not None and hr_zones:
            log(f"Training paces computed. HR zones computed from max HR {hr_zones['max_hr']} bpm.")
        elif parsed_vdot is not None:
            log("Training paces computed.")
        elif hr_zones:
            log(f"HR zones computed from max HR {hr_zones['max_hr']} bpm.")

        store.mark_sync_completed(conn, new_runs=new_count, detail_failures=detail_failures)
        log("Sync complete.")

        return SyncSummary(
            new_runs=new_count,
            activities_seen=len(activities),
            pending_details=len(pending),
            detail_failures=detail_failures,
            ae_baseline=ae_baseline,
            current_vdot=parsed_vdot,
            hr_max=hr_zones["max_hr"] if hr_zones else None,
        )
    except Exception as e:
        if getattr(e, "code", None) and getattr(e, "message", None):
            store.mark_sync_failed(conn, f"{e.code}: {e.message}")
        else:
            store.mark_sync_failed(conn, str(e))
        raise

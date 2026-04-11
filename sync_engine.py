import datetime
import logging
from dataclasses import dataclass
from typing import Callable

import auth
import backup_utils
import fetch
from logging_utils import get_logger, log_event
import metrics
import models
import store
import vdot_zones


LogFn = Callable[[str], None]
logger = get_logger("sync_engine")


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


def _emit_log(log: LogFn, level: int, event: str, message: str, **fields) -> None:
    log_event(logger, level, event, **fields)
    log(message)


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

        _emit_log(
            log,
            logging.INFO,
            "sync.activities.fetch_started",
            f"Fetching Garmin activities from {start_date}.",
            start_date=start_date,
        )
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

        _emit_log(
            log,
            logging.INFO,
            "sync.activities.stored",
            f"Stored {new_count} new runs ({len(activities)} activities seen since watermark).",
            new_runs=new_count,
            activities_seen=len(activities),
        )

        pending = store.get_runs_without_details(conn)
        detail_failures = 0
        if not pending:
            _emit_log(log, logging.INFO, "sync.details.none_pending", "All runs already have detailed metrics.")
        else:
            _emit_log(
                log,
                logging.INFO,
                "sync.details.fetch_started",
                f"Fetching details for {len(pending)} runs (this may take a while)...",
                pending_runs=len(pending),
            )

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

            _emit_log(
                log,
                logging.INFO,
                "sync.detail.run_started",
                f"[{i}/{len(pending)}] {run.start_time.date()} - {run.name[:60]}",
                activity_id=activity_id,
                detail_index=i,
                pending_runs=len(pending),
            )

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
                _emit_log(
                    log,
                    logging.WARNING,
                    "sync.detail.fetch_failed",
                    f"Warning: could not fetch details for {activity_id}: {e}",
                    activity_id=activity_id,
                    error=str(e),
                )

            ae_baseline_str = store.get_meta(conn, "ae_baseline")
            ae_baseline = float(ae_baseline_str) if ae_baseline_str else None
            metrics.compute_all(run, ae_baseline)
            store.upsert_run(conn, run, detail_fetched=detail_fetched_ok)

        _emit_log(log, logging.INFO, "sync.ae_baseline.started", "Computing aerobic efficiency baseline...")
        ae_baseline = store.compute_and_store_ae_baseline(conn)
        if ae_baseline:
            updated = store.recompute_all_rei(conn, ae_baseline)
            _emit_log(
                log,
                logging.INFO,
                "sync.ae_baseline.completed",
                f"AE baseline: {ae_baseline:.4f} ({updated} REI scores updated)",
                ae_baseline=round(ae_baseline, 4),
                rei_scores_updated=updated,
            )
        else:
            _emit_log(
                log,
                logging.INFO,
                "sync.ae_baseline.unavailable",
                "Not enough qualifying runs to compute AE baseline yet.",
            )

        _emit_log(log, logging.INFO, "sync.vdot.started", "Estimating VDOT from run data...")
        current_vdot = store.get_meta(conn, "current_vdot")
        parsed_vdot = float(current_vdot) if current_vdot else None
        if parsed_vdot is None:
            parsed_vdot = vdot_zones.estimate_vdot_from_runs(conn)
            qualifying_runs = store.get_meta(conn, "vdot_qualifying_run_count") or "0"
            if parsed_vdot is None:
                _emit_log(
                    log,
                    logging.INFO,
                    "sync.vdot.unavailable",
                    "No qualifying runs yet for VDOT estimation.",
                    qualifying_runs=int(qualifying_runs),
                )
            else:
                _emit_log(
                    log,
                    logging.INFO,
                    "sync.vdot.estimated",
                    f"Estimated VDOT: {parsed_vdot:.1f} (from {qualifying_runs} qualifying runs)",
                    vdot=round(parsed_vdot, 1),
                    qualifying_runs=int(qualifying_runs),
                )
        else:
            _emit_log(
                log,
                logging.INFO,
                "sync.vdot.reused",
                f"Current VDOT: {parsed_vdot:.1f} (existing estimate)",
                vdot=round(parsed_vdot, 1),
            )

        try:
            hr_zones = vdot_zones._refresh_hr_zones(conn)
        except ValueError as e:
            hr_zones = None
            _emit_log(
                log,
                logging.WARNING,
                "sync.hr_zones.failed",
                f"Unable to compute HR zones: {e}",
                error=str(e),
            )

        if parsed_vdot is not None and hr_zones:
            _emit_log(
                log,
                logging.INFO,
                "sync.training_metrics.completed",
                f"Training paces computed. HR zones computed from max HR {hr_zones['max_hr']} bpm.",
                max_hr=hr_zones["max_hr"],
                has_vdot=True,
            )
        elif parsed_vdot is not None:
            _emit_log(log, logging.INFO, "sync.training_paces.completed", "Training paces computed.")
        elif hr_zones:
            _emit_log(
                log,
                logging.INFO,
                "sync.hr_zones.completed",
                f"HR zones computed from max HR {hr_zones['max_hr']} bpm.",
                max_hr=hr_zones["max_hr"],
            )

        store.mark_sync_completed(conn, new_runs=new_count, detail_failures=detail_failures)
        try:
            backup_path = backup_utils.auto_backup_db()
        except Exception as e:
            _emit_log(
                log,
                logging.WARNING,
                "sync.backup.failed",
                f"Warning: automatic backup failed: {e}",
                error=str(e),
            )
        else:
            if backup_path is not None:
                _emit_log(
                    log,
                    logging.INFO,
                    "sync.backup.completed",
                    f"Automatic backup saved to {backup_path}",
                    backup_path=str(backup_path),
                )
        _emit_log(
            log,
            logging.INFO,
            "sync.completed",
            "Sync complete.",
            new_runs=new_count,
            activities_seen=len(activities),
            pending_details=len(pending),
            detail_failures=detail_failures,
            current_vdot=round(parsed_vdot, 1) if parsed_vdot is not None else None,
            hr_max=hr_zones["max_hr"] if hr_zones else None,
        )

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
        log_event(
            logger,
            logging.ERROR,
            "sync.failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        if getattr(e, "code", None) and getattr(e, "message", None):
            store.mark_sync_failed(conn, f"{e.code}: {e.message}")
        else:
            store.mark_sync_failed(conn, str(e))
        raise

from __future__ import annotations

import os
from pathlib import Path

from rich.align import Align
from rich.box import HEAVY, ROUNDED, SIMPLE_HEAVY
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, RichLog, Static, TabbedContent, TabPane

import coach
import evals
import health
import onboarding
import store
import sync_engine
import vdot_zones
from errors import DependencyError, HarnessError, format_error


def _fmt_pace(pace_min_per_km):
    if pace_min_per_km is None:
        return "-"
    mins = int(pace_min_per_km)
    secs = int((pace_min_per_km - mins) * 60)
    return f"{mins}:{secs:02d}/km"


def _fmt_status(status: str) -> str:
    color = {
        "PASS": "bold green",
        "WARN": "bold yellow",
        "FAIL": "bold red",
    }.get(status, "white")
    return f"[{color}]{status}[/]"


class GarminCredentialsScreen(ModalScreen[tuple[str, str] | None]):
    CSS = """
    GarminCredentialsScreen {
        align: center middle;
        background: #02060d 80%;
    }

    #garmin-modal {
        width: 72;
        height: auto;
        border: round #5b7cff;
        background: #0c1321;
        padding: 1 2;
    }

    #garmin-actions {
        height: auto;
        margin-top: 1;
    }

    #garmin-actions Button {
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="garmin-modal"):
            yield Static("Garmin login is required before Nyx can sync your runs.", classes="modal-copy")
            yield Input(placeholder="Garmin email", id="garmin_email")
            yield Input(placeholder="Garmin password", password=True, id="garmin_password")
            with Horizontal(id="garmin-actions"):
                yield Button("Connect", id="garmin_connect", variant="primary")
                yield Button("Cancel", id="garmin_cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "garmin_cancel":
            self.dismiss(None)
            return

        email = self.query_one("#garmin_email", Input).value.strip()
        password = self.query_one("#garmin_password", Input).value
        if email and password:
            self.dismiss((email, password))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "garmin_password":
            email = self.query_one("#garmin_email", Input).value.strip()
            password = self.query_one("#garmin_password", Input).value
            if email and password:
                self.dismiss((email, password))


class NyxApp(App):
    TITLE = "Nyx"
    SUB_TITLE = "Moonlit running coach harness"
    CSS_PATH = "nyx.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "sync", "Sync"),
        Binding("o", "onboarding", "Onboarding"),
        Binding("v", "refresh_metrics", "Metrics"),
        Binding("d", "doctor", "Doctor"),
        Binding("e", "offline_eval", "Eval"),
        Binding("l", "live_eval", "Live Eval"),
        Binding("c", "focus_chat", "Coach"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._chat_base_blocks: list[dict] | None = None
        self._chat_thread_id: int | None = None
        self._chat_conversation: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="home"):
            with TabPane("Home", id="home"):
                with VerticalScroll():
                    yield Static(id="hero", classes="hero")
                    with Horizontal(id="home-actions"):
                        yield Button("Sync Garmin", id="home_sync", classes="action", variant="primary")
                        yield Button("Run Onboarding", id="home_onboarding", classes="action")
                        yield Button("Refresh Metrics", id="home_metrics", classes="action")
                        yield Button("Run Doctor", id="home_doctor", classes="action")
                        yield Button("Offline Evals", id="home_eval", classes="action")
                    with Horizontal(id="home-panels"):
                        yield Static(id="overview-panel", classes="panel")
                        yield Static(id="setup-panel", classes="panel")
            with TabPane("Athlete", id="athlete"):
                with VerticalScroll():
                    yield Static(id="athlete-summary", classes="panel")
                    yield Static(id="athlete-runs", classes="panel")
            with TabPane("Coach", id="coach"):
                yield Static(id="coach-help", classes="panel")
                yield RichLog(id="chat-log", wrap=True, markup=True, highlight=True)
                with Horizontal(id="chat-input-row"):
                    yield Input(
                        placeholder="Ask Nyx about easy pace, tempo pace, fatigue, or what to do next...",
                        id="chat_prompt",
                    )
                    yield Button("Send", id="send_chat", variant="primary")
                    yield Button("Clear", id="clear_chat")
            with TabPane("Diagnostics", id="diagnostics"):
                with VerticalScroll():
                    with Horizontal(id="diag-actions"):
                        yield Button("Sync Garmin", id="diag_sync", classes="action", variant="primary")
                        yield Button("Run Doctor", id="diag_doctor", classes="action")
                        yield Button("Offline Evals", id="diag_eval", classes="action")
                        yield Button("Live Evals", id="diag_live_eval", classes="action")
                        yield Button("Refresh Metrics", id="diag_metrics", classes="action")
                    yield Static(id="doctor-panel", classes="panel")
                    yield RichLog(id="diag-log", wrap=True, markup=True, highlight=True)
            with TabPane("About", id="about"):
                with VerticalScroll():
                    yield Static(id="about-panel", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        self._load_chat_state()
        self._reset_chat_log()
        self._log_diag("[bold cyan]Nyx online.[/] Press [bold]s[/] to sync, [bold]d[/] for doctor, [bold]c[/] for coach.")
        self.refresh_views()

    def action_refresh(self) -> None:
        self.refresh_views()
        self.notify("Nyx refreshed.", title="Nyx")

    def action_sync(self) -> None:
        self._start_sync()

    def action_onboarding(self) -> None:
        self._run_onboarding()

    def action_refresh_metrics(self) -> None:
        self._start_metrics_refresh()

    def action_doctor(self) -> None:
        self._run_doctor()

    def action_offline_eval(self) -> None:
        self._start_eval(live=False)

    def action_live_eval(self) -> None:
        self._start_eval(live=True)

    def action_focus_chat(self) -> None:
        self.query_one(TabbedContent).active = "coach"
        self.query_one("#chat_prompt", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id in {"home_sync", "diag_sync"}:
            self._start_sync()
        elif button_id == "home_onboarding":
            self._run_onboarding()
        elif button_id in {"home_metrics", "diag_metrics"}:
            self._start_metrics_refresh()
        elif button_id in {"home_doctor", "diag_doctor"}:
            self._run_doctor()
        elif button_id in {"home_eval", "diag_eval"}:
            self._start_eval(live=False)
        elif button_id == "diag_live_eval":
            self._start_eval(live=True)
        elif button_id == "send_chat":
            self._submit_chat()
        elif button_id == "clear_chat":
            self._clear_chat()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chat_prompt":
            self._submit_chat()

    def refresh_views(self) -> None:
        conn = store.open_db()
        try:
            self.query_one("#hero", Static).update(self._render_hero())
            self.query_one("#overview-panel", Static).update(self._render_overview(conn))
            self.query_one("#setup-panel", Static).update(self._render_setup(conn))
            self.query_one("#athlete-summary", Static).update(self._render_athlete_summary(conn))
            self.query_one("#athlete-runs", Static).update(self._render_recent_runs(conn))
            self.query_one("#doctor-panel", Static).update(self._render_doctor(conn))
            self.query_one("#coach-help", Static).update(self._render_coach_help())
            self.query_one("#about-panel", Static).update(self._render_about())
        finally:
            conn.close()

    def _render_hero(self):
        title_lines = [
            " _   _ __   ____  __",
            "| \\ | |\\ \\ / /\\ \\/ /",
            "|  \\| | \\ V /  \\  / ",
            "| |\\  |  > <   /  \\ ",
            "|_| \\_| /_/\\_\\/_/\\_\\",
        ]
        title = Text()
        palette = ["#9fd0ff", "#7fb9ff", "#5b7cff", "#7f5cff", "#b781ff"]
        for i, line in enumerate(title_lines):
            title.append(line + "\n", style=f"bold {palette[i]}")

        subtitle = Text("Moonlit running intelligence for hard training blocks.", style="bold #d7e6ff")
        strap = Text("Garmin grounded. Evidence first. Quietly brutal.", style="#8ca3c7")
        keys = Text("Keys: [s] sync   [o] onboarding   [v] metrics   [d] doctor   [e] eval   [c] coach", style="#6e84a8")

        return Panel(
            Align.center(Group(title, subtitle, strap, Text(""), keys)),
            title="[bold #5b7cff]Nyx[/]",
            subtitle="running coach harness",
            box=HEAVY,
            border_style="#3f5fc4",
        )

    def _render_overview(self, conn):
        status = health.collect_status(conn)
        doctor_checks = health.run_doctor(conn)
        failing = [c for c in doctor_checks if c.status == health.FAIL]
        warning = [c for c in doctor_checks if c.status == health.WARN]

        next_action = "Open Coach"
        if failing:
            next_action = "Fix diagnostics in the Diagnostics tab"
        elif status["total_runs"] == 0:
            next_action = "Sync Garmin data"
        elif not status["onboarding_completed"]:
            next_action = "Run onboarding"
        elif not status["current_vdot"]:
            next_action = "Refresh VDOT / HR zones"

        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(style="bold #7fb9ff", width=19)
        grid.add_column(style="#dce8ff")
        grid.add_row("Runs", f"{status['total_runs']} total / {status['detailed_runs']} detailed")
        grid.add_row("Last sync", status["last_sync_status"])
        grid.add_row("Current VDOT", status["current_vdot"] or "not estimated yet")
        grid.add_row("Knowledge base", "ready" if status["knowledge_db_exists"] else "not built")
        grid.add_row("Open warnings", f"{len(failing)} fail / {len(warning)} warn")
        grid.add_row("Next action", next_action)

        return Panel(grid, title="Overview", box=ROUNDED, border_style="#29415f")

    def _render_setup(self, conn):
        table = Table(expand=True, box=SIMPLE_HEAVY)
        table.add_column("Status", width=8)
        table.add_column("Check", style="bold #dce8ff")
        table.add_column("Summary", style="#9fb3d1")
        for check in health.run_doctor(conn):
            table.add_row(_fmt_status(check.status), check.name, check.summary)
        return Panel(table, title="Setup Checklist", box=ROUNDED, border_style="#29415f")

    def _render_athlete_summary(self, conn):
        status = health.collect_status(conn)
        if status["total_runs"] == 0:
            return Panel(
                "No local run data yet.\n\nUse Sync Garmin from Home or Diagnostics to pull your athlete history into Nyx.",
                title="Athlete Snapshot",
                box=ROUNDED,
                border_style="#29415f",
            )

        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(style="bold #7fb9ff", width=19)
        grid.add_column(style="#dce8ff")
        grid.add_row("Run range", f"{status['first_run'][:10]} -> {status['last_run'][:10]}")
        grid.add_row("Current VDOT", status["current_vdot"] or "not estimated yet")
        if status["hr_zones"]:
            grid.add_row(
                "Easy HR zone",
                f"Zone 2: {status['hr_zones']['zones'][1]['hr_low']}-{status['hr_zones']['zones'][1]['hr_high']} bpm",
            )
        zones_context = vdot_zones.build_zones_context(conn) or "No VDOT / HR zones available yet."
        return Panel(Group(grid, Text(""), Text(zones_context, style="#a8bbd8")), title="Athlete Snapshot", box=ROUNDED, border_style="#29415f")

    def _render_recent_runs(self, conn):
        runs = store.get_all_runs(conn, limit=12)
        if not runs:
            return Panel("No recent runs yet.", title="Recent Runs", box=ROUNDED, border_style="#29415f")

        table = Table(expand=True, box=SIMPLE_HEAVY)
        table.add_column("Date", style="bold #dce8ff")
        table.add_column("Dist", justify="right")
        table.add_column("Pace", justify="right")
        table.add_column("HR", justify="right")
        table.add_column("REI", justify="right")
        for row in runs:
            dist_km = (row["distance_m"] or 0) / 1000.0
            table.add_row(
                row["start_time"][:10],
                f"{dist_km:.1f} km",
                _fmt_pace(row["pace_min_per_km"]),
                f"{row['avg_hr']:.0f}" if row["avg_hr"] is not None else "-",
                f"{row['rei']:.1f}" if row["rei"] is not None else "-",
            )
        return Panel(table, title="Recent Runs", box=ROUNDED, border_style="#29415f")

    def _render_doctor(self, conn):
        checks = health.run_doctor(conn)
        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(width=8)
        grid.add_column(style="bold #dce8ff")
        grid.add_column(style="#9fb3d1")
        for check in checks:
            grid.add_row(_fmt_status(check.status), check.name, check.hint or check.summary)
        return Panel(grid, title="Diagnostics Snapshot", box=ROUNDED, border_style="#29415f")

    def _render_coach_help(self):
        return Panel(
            "Ask Nyx direct coaching questions.\n\nBest prompts:\n- What pace should my easy runs be?\n- Am I running my easy days too hard?\n- What should I do on my next run?\n- What does my recent trend say about fatigue?",
            title="Coach",
            box=ROUNDED,
            border_style="#29415f",
        )

    def _render_about(self):
        readme = Path("README.md").read_text(encoding="utf-8")
        lines = readme.splitlines()
        preview = "\n".join(lines[:36])
        return Panel(preview, title="About Nyx", box=ROUNDED, border_style="#29415f")

    def _log_diag(self, message: str) -> None:
        self.query_one("#diag-log", RichLog).write(message)

    def _load_chat_state(self) -> None:
        conn = store.open_db()
        try:
            thread = store.get_or_create_active_coach_thread(conn)
            self._chat_thread_id = thread["id"]
            self._chat_conversation = [
                {"role": row["role"], "content": row["content"]}
                for row in store.get_coach_messages(conn, thread["id"])
            ]
        finally:
            conn.close()

    def _reset_chat_log(self) -> None:
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.clear()
        if not self._chat_conversation:
            chat_log.write("[bold #7fb9ff]Nyx[/] is ready. Ask about training, pacing, fatigue, readiness, or form.")
            return

        chat_log.write(f"[bold #7fb9ff]Nyx[/] restored {len(self._chat_conversation)} saved messages.")
        for message in self._chat_conversation:
            if message["role"] == "user":
                chat_log.write(f"[bold #7fb9ff]You:[/] {message['content']}")
            else:
                chat_log.write(f"[bold #b781ff]Nyx:[/]\n{message['content']}")

    def _clear_chat(self) -> None:
        self._chat_base_blocks = None
        conn = store.open_db()
        try:
            thread = store.create_coach_thread(conn)
            self._chat_thread_id = thread["id"]
        finally:
            conn.close()
        self._chat_conversation.clear()
        self._reset_chat_log()
        self.notify("Started a new saved coach conversation.", title="Nyx")

    def _after_data_change(self, message: str) -> None:
        self._chat_base_blocks = None
        self._reset_chat_log()
        self.refresh_views()
        self._log_diag(message)
        self.notify(message, title="Nyx")

    def _run_doctor(self) -> None:
        conn = store.open_db()
        try:
            report = health.format_doctor(conn)
        finally:
            conn.close()
        self.query_one(TabbedContent).active = "diagnostics"
        self._log_diag(report)
        self.refresh_views()

    def _run_onboarding(self) -> None:
        self.query_one(TabbedContent).active = "home"
        with self.suspend():
            conn = store.open_db()
            try:
                onboarding.run_onboarding(conn, full=True)
            finally:
                conn.close()
        self._after_data_change("Onboarding updated.")

    def _start_sync(self, email: str | None = None, password: str | None = None) -> None:
        self.query_one(TabbedContent).active = "diagnostics"
        self._log_diag("[bold #7fb9ff]Starting Garmin sync...[/]")
        self.run_sync_worker(email=email, password=password)

    @work(thread=True, exclusive=True, group="sync")
    def run_sync_worker(self, email: str | None = None, password: str | None = None) -> None:
        def log(message: str) -> None:
            self.call_from_thread(self._log_diag, message)

        try:
            summary = sync_engine.run_sync(
                log=log,
                email=email,
                password=password,
                interactive=False,
            )
        except HarnessError as e:
            if e.code == "garmin_login_required" and not email and not password:
                self.call_from_thread(self._log_diag, "Garmin token cache missing. Opening login form...")
                self.call_from_thread(self._prompt_for_garmin_credentials)
                return
            self.call_from_thread(self._log_diag, format_error(e))
            self.call_from_thread(self.notify, e.message, title="Nyx", severity="error")
            self.call_from_thread(self.refresh_views)
            return
        except Exception as e:
            self.call_from_thread(self._log_diag, f"Unexpected sync failure: {e}")
            self.call_from_thread(self.notify, "Sync failed unexpectedly.", title="Nyx", severity="error")
            self.call_from_thread(self.refresh_views)
            return

        summary_text = f"Sync finished: {summary.new_runs} new runs, {summary.detail_failures} detail failures."
        self.call_from_thread(self._after_data_change, summary_text)

    def _prompt_for_garmin_credentials(self) -> None:
        self.push_screen(GarminCredentialsScreen(), self._handle_garmin_credentials)

    def _handle_garmin_credentials(self, result: tuple[str, str] | None) -> None:
        if not result:
            self._log_diag("Sync canceled before Garmin credentials were provided.")
            return
        email, password = result
        self._start_sync(email=email, password=password)

    def _start_metrics_refresh(self) -> None:
        self.query_one(TabbedContent).active = "diagnostics"
        self._log_diag("[bold #7fb9ff]Refreshing VDOT and HR zones...[/]")
        self.run_metrics_worker()

    @work(thread=True, exclusive=True, group="metrics")
    def run_metrics_worker(self) -> None:
        conn = store.open_db()
        try:
            current_vdot = vdot_zones.estimate_vdot_from_runs(conn)
            hr_zones = vdot_zones._refresh_hr_zones(conn)
            if current_vdot is None:
                message = "Metrics refresh complete: no qualifying runs for VDOT yet."
            elif hr_zones:
                message = f"Metrics refresh complete: VDOT {current_vdot:.1f}, easy zone {hr_zones['zones'][1]['hr_low']}-{hr_zones['zones'][1]['hr_high']} bpm."
            else:
                message = f"Metrics refresh complete: VDOT {current_vdot:.1f}."
        finally:
            conn.close()
        self.call_from_thread(self._after_data_change, message)

    def _start_eval(self, *, live: bool) -> None:
        self.query_one(TabbedContent).active = "diagnostics"
        if live:
            self._log_diag("[bold #7fb9ff]Running live golden-question evals...[/]")
        else:
            self._log_diag("[bold #7fb9ff]Running offline harness evals...[/]")
        self.run_eval_worker(live=live)

    @work(thread=True, exclusive=True, group="eval")
    def run_eval_worker(self, *, live: bool) -> None:
        conn = store.open_db()
        try:
            offline = evals.run_offline_evals(conn)
            self.call_from_thread(self._log_diag, evals.format_eval_report(offline, verbose=False))
            if live:
                live_results = evals.run_live_evals(conn)
                self.call_from_thread(self._log_diag, "")
                self.call_from_thread(self._log_diag, evals.format_eval_report(live_results, verbose=False))
        except HarnessError as e:
            self.call_from_thread(self._log_diag, format_error(e))
            self.call_from_thread(self.notify, e.message, title="Nyx", severity="error")
        except Exception as e:
            self.call_from_thread(self._log_diag, f"Eval failure: {e}")
            self.call_from_thread(self.notify, "Eval run failed unexpectedly.", title="Nyx", severity="error")
        finally:
            conn.close()
        self.call_from_thread(self.refresh_views)

    def _submit_chat(self) -> None:
        prompt_input = self.query_one("#chat_prompt", Input)
        prompt = prompt_input.value.strip()
        if not prompt:
            return

        if self._chat_base_blocks is None:
            conn = store.open_db()
            try:
                self._chat_base_blocks = coach.build_base_system_blocks(conn)
            finally:
                conn.close()

        self.query_one(TabbedContent).active = "coach"
        self.query_one("#chat-log", RichLog).write(f"[bold #7fb9ff]You:[/] {prompt}")
        self._chat_conversation.append({"role": "user", "content": prompt})
        prompt_input.value = ""
        prompt_input.disabled = True
        self.query_one("#send_chat", Button).disabled = True
        self.query_one("#clear_chat", Button).disabled = True
        self.notify("Nyx is thinking...", title="Coach")
        self.run_chat_worker(prompt=prompt, base_blocks=self._chat_base_blocks, conversation_snapshot=list(self._chat_conversation))

    @work(thread=True, exclusive=True, group="chat")
    def run_chat_worker(
        self,
        *,
        prompt: str,
        base_blocks: list[dict],
        conversation_snapshot: list[dict],
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            err = DependencyError(
                "missing_openai_dependency",
                "Coach chat requires the `openai` package.",
                hint="Run `pip install -r requirements.txt` to enable coach chat.",
                details=str(e),
            )
            self.call_from_thread(self._chat_failed, prompt, err)
            return

        if not os.getenv("MOONSHOT_API_KEY"):
            err = HarnessError(
                "missing_moonshot_key",
                "Coach chat requires `MOONSHOT_API_KEY`.",
                hint="Export your Moonshot API key before using the Coach tab.",
            )
            self.call_from_thread(self._chat_failed, prompt, err)
            return

        try:
            client = OpenAI(base_url="https://api.moonshot.cn/v1", api_key=os.getenv("MOONSHOT_API_KEY"))
            system_blocks = coach.build_turn_system_blocks(base_blocks, prompt)
            system_text = coach._flatten_system(system_blocks)
            messages = [{"role": "system", "content": system_text}] + coach._active_conversation(conversation_snapshot)
            response = client.chat.completions.create(
                model="kimi-2.5",
                max_tokens=1400,
                messages=messages,
            )
            text = (response.choices[0].message.content or "").strip()
            self.call_from_thread(self._chat_completed, text)
        except Exception as e:
            err = HarnessError(
                "coach_request_failed",
                "Coach request failed.",
                hint="Check network, API key, or Moonshot service health.",
                details=str(e),
            )
            self.call_from_thread(self._chat_failed, prompt, err)

    def _chat_completed(self, response_text: str) -> None:
        self._chat_conversation.append({"role": "assistant", "content": response_text})
        user_prompt = self._chat_conversation[-2]["content"] if len(self._chat_conversation) >= 2 else ""
        conn = store.open_db()
        try:
            thread = (
                store.get_coach_thread(conn, self._chat_thread_id)
                if self._chat_thread_id is not None
                else None
            )
            if thread is None:
                thread = store.get_or_create_active_coach_thread(conn)
                self._chat_thread_id = thread["id"]
            if user_prompt:
                store.append_coach_message(conn, thread["id"], "user", user_prompt)
                store.maybe_set_coach_thread_title_from_message(conn, thread["id"], user_prompt)
            store.append_coach_message(conn, thread["id"], "assistant", response_text)
        finally:
            conn.close()
        self.query_one("#chat-log", RichLog).write(f"[bold #b781ff]Nyx:[/]\n{response_text}")
        self._set_chat_ready()

    def _chat_failed(self, prompt: str, err: HarnessError) -> None:
        if self._chat_conversation and self._chat_conversation[-1]["role"] == "user" and self._chat_conversation[-1]["content"] == prompt:
            self._chat_conversation.pop()
        self.query_one("#chat-log", RichLog).write(f"[bold red]System:[/]\n{format_error(err)}")
        self.notify(err.message, title="Coach", severity="error")
        self._set_chat_ready()

    def _set_chat_ready(self) -> None:
        self.query_one("#chat_prompt", Input).disabled = False
        self.query_one("#send_chat", Button).disabled = False
        self.query_one("#clear_chat", Button).disabled = False
        self.query_one("#chat_prompt", Input).focus()


if __name__ == "__main__":
    NyxApp().run()

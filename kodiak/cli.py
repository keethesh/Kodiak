"""
Kodiak CLI - AI-Powered Penetration Testing Suite
"""

import os
import sys
import asyncio
import subprocess
import shlex
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.table import Table
from rich import box
from loguru import logger

console = Console()

# Severity color styles for Rich markup
SEVERITY_STYLES: dict = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "cyan",
    "info": "white",
}
# Phase display order
SCAN_PHASES = ["RECON", "ENUMERATION", "VULN_SCAN", "EXPLOITATION", "REPORTING"]

# Check for optional dependencies
HAS_DATABASE = True
HAS_BROWSER = True
HAS_API = True

try:
    import sqlalchemy
    import sqlmodel
except ImportError:
    HAS_DATABASE = False

try:
    import playwright
except ImportError:
    HAS_BROWSER = False

try:
    import uvicorn
    import fastapi
except ImportError:
    HAS_API = False


def check_docker_available() -> bool:
    """Check if Docker is available."""
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=15)
        return True
    except Exception:
        return False


def run_check(command: list[str], timeout: int = 20) -> tuple[bool, str]:
    """Run a command and return (success, stderr/stdout detail)."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, f"Command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout}s"
    except Exception as e:
        return False, str(e)
    
    if result.returncode == 0:
        return True, result.stdout.strip()
    
    detail = (result.stderr or result.stdout or "").strip()
    return False, detail or f"Command exited with code {result.returncode}"


def run_docker_compose(args: list[str]) -> tuple[bool, str]:
    """Run docker compose with fallback between `docker compose` and `docker-compose`."""
    commands = [
        ["docker", "compose", *args],
        ["docker-compose", *args],
    ]
    errors: list[str] = []
    for cmd in commands:
        ok, detail = run_check(cmd, timeout=60)
        if ok:
            return True, detail
        errors.append(f"{' '.join(cmd)} -> {detail}")
    return False, " | ".join(errors)


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version information")
@click.option("--target", "-t", help="Target to scan (launches TUI)")
@click.pass_context
def main(ctx, version: bool, target: Optional[str]):
    """Kodiak - AI-Powered Penetration Testing Suite"""
    if version:
        console.print("Kodiak v1.1.0 (Refactor)")
        return
    
    if target:
        ctx.invoke(tui, target=target)
        return
    
    if ctx.invoked_subcommand is None:
        console.print(Panel.fit(
            Text("Kodiak - AI-Powered Penetration Testing Suite", style="bold blue"),
            border_style="blue"
        ))
        console.print("Launching TUI interface...\n")
        ctx.invoke(tui)


@main.command()
@click.argument("target")
@click.option("--instructions", "-i", help="Custom scan instructions", default="Conduct a security assessment")
@click.option("--model", "-m", help="LLM model to use")
@click.option("--max-iterations", "-n", default=100, help="Total manager iteration budget")
@click.option("--project", "-p", default=None, help="Project name — reuse across scans to load prior knowledge")
@click.option("--agents", "-a", type=int, default=None, hidden=True)
@click.option("--force-agents", is_flag=True, help="Allow agent count above KODIAK_MAX_AGENTS")
@click.option(
    "--event-scheduler/--no-event-scheduler",
    default=True,
    help="Enable non-blocking event-driven scheduling (default: enabled).",
)
@click.option(
    "--report-format",
    type=click.Choice(["json", "json+md"], case_sensitive=False),
    default="json+md",
    help="Scan report output format",
)
@click.option("--report-path", type=str, default=None, help="Directory for scan report artifacts")
@click.option(
    "--role-strategy",
    type=click.Choice(["role-hinted", "generic"], case_sensitive=False),
    default="role-hinted",
    hidden=True,
)
@click.option("--verbose", "-v", is_flag=True, help="Show verbose real-time logging output")
def scan(
    target: str,
    instructions: str,
    model: Optional[str],
    max_iterations: int,
    project: Optional[str],
    agents: Optional[int],
    force_agents: bool,
    event_scheduler: bool,
    report_format: str,
    report_path: Optional[str],
    role_strategy: str,
    verbose: bool,
):
    """Run a security scan on the target."""
    if not HAS_DATABASE:
        console.print("[red]Database dependencies not installed! Please install sqlalchemy and sqlmodel.[/red]")
        return
        
    # Auto-initialize database if it's missing or empty
    from kodiak.core.config import settings
    import os
    
    needs_init = False
    if settings.is_sqlite:
        db_path = os.path.expanduser(settings.sqlite_path or "~/.kodiak/kodiak.db")
        if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
            needs_init = True
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
    if needs_init:
        console.print("[yellow]Database not found or empty. Initializing...[/yellow]")
        from kodiak.database.engine import init_db
        asyncio.run(init_db())
        console.print("[green]Database initialized![/green]")

    async def run_scan_internal() -> int:
        from kodiak.core.interface import CoreInterface
        from kodiak.core.config import settings
        from kodiak.services import llm
        
        # If not verbose, silence loguru so messages don't break the Rich Live display
        if not verbose:
            logger.remove()
            
        log_file = Path.home() / ".kodiak" / "logs" / "scan.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(log_file, level="DEBUG", rotation="10 MB")
        
        if model:
            settings.llm_model = llm.normalize_model_name(model)

        console.print(f"\n🎯 [bold]Target:[/bold] {target}")
        console.print(f"🧠 [bold]Model:[/bold] {settings.llm_model}")
        console.print(f"📋 [bold]Instructions:[/bold] {instructions}")
        if project:
            console.print(f"📁 [bold]Project:[/bold] {project} [dim](prior knowledge will be loaded if project exists)[/dim]")
        console.print(f"👤 [bold]Architecture:[/bold] Manager-Worker (single brain, parallel tools)")
        scheduler_mode = bool(event_scheduler)
        console.print(f"📡 [bold]Event Scheduler:[/bold] {'enabled' if scheduler_mode else 'disabled'}")
        if agents is not None:
            console.print("[yellow]Note: --agents is ignored in Manager-Worker mode.[/yellow]")
        if role_strategy != "role-hinted":
            console.print("[yellow]Note: --role-strategy is ignored in Manager-Worker mode.[/yellow]")
        console.print(f"📝 [bold]Report:[/bold] format={report_format} path={report_path or settings.report_output_path}")
        console.print("")
        
        interface = CoreInterface()
        run_id = await interface.start_scan(
            target=target,
            instructions=instructions,
            model=model,
            max_iterations=max_iterations,
            agent_count=1,
            role_strategy="role_hinted",
            force_agents=force_agents,
            event_scheduler=scheduler_mode,
            report_format=report_format.lower(),
            report_path=report_path,
            project_name=project,
        )
        
        # If verbose, bypass the TUI overlay and just let logs stream freely
        if verbose:
            console.print("[yellow]Verbose mode enabled. Streaming real-time execution logs...[/yellow]\n")
            try:
                async for event in interface.subscribe_events(run_id):
                    payload = event.payload or {}
                    if event.type == "agent_thinking":
                        console.print(
                            f"[blue][agent:thinking][/blue] {payload.get('agent_id', 'unknown')} -> "
                            f"{payload.get('message', 'Thinking...')}"
                        )
                    elif event.type == "agent_thought":
                        thought = str(payload.get("thought", "") or "").strip()
                        if thought:
                            if len(thought) > 1200:
                                thought = thought[:1197] + "..."
                            console.print(
                                f"[blue][agent:thought][/blue] {payload.get('agent_id', 'unknown')}\n"
                                f"{thought}"
                            )
                    elif event.type == "tool_start":
                        console.print(
                            f"[cyan][tool:start][/cyan] {payload.get('tool_name', 'unknown')} -> {payload.get('target', '')}"
                        )
                    elif event.type == "tool_complete":
                        success = payload.get("success")
                        symbol = "[green]ok[/green]" if success else "[red]fail[/red]"
                        console.print(
                            f"[cyan][tool:end][/cyan] {payload.get('tool_name', 'unknown')} {symbol}"
                        )
                    elif event.type == "finding_discovered":
                        finding = payload.get("finding", {})
                        title = finding.get("title", "Unnamed finding")
                        sev = finding.get("severity", "info").upper()
                        sev_style = SEVERITY_STYLES.get(sev.lower(), "white")
                        console.print(f"[magenta][finding][/magenta] [{sev_style}]{sev}[/{sev_style}] {title}")
                    elif event.type == "note_saved":
                        cat = payload.get("category", "general")
                        tgt = payload.get("target", "*")
                        prev = payload.get("preview", "")[:80]
                        console.print(f"[green][memory:note][/green] [{cat}] ({tgt}) {prev}")
                    elif event.type == "finding_saved":
                        sev = payload.get("severity", "info").upper()
                        sev_style = SEVERITY_STYLES.get(sev.lower(), "white")
                        title = payload.get("title", "Untitled")
                        tgt = payload.get("target", "")
                        console.print(f"[green][memory:finding][/green] [{sev_style}]{sev}[/{sev_style}] {title} @ {tgt}")
                    elif event.type == "phase_advanced":
                        old = payload.get("old_phase", "?").upper()
                        new = payload.get("new_phase", "?").upper()
                        console.print(f"[bold cyan][phase][/bold cyan] {old} → {new}")
                    elif event.type == "prior_knowledge_loaded":
                        n = payload.get("notes_count", 0)
                        f_ = payload.get("findings_count", 0)
                        console.print(f"[blue][memory][/blue] 🧠 Prior knowledge loaded: {n} notes, {f_} findings")
                    elif event.type == "scan_failed":
                        console.print(f"[red][scan][/red] failed: {payload.get('error', 'unknown error')}")

                result = await interface.get_scan_result(run_id)
                if result:
                    console.print(f"\n[green]Scan {result.status}![/green]")
                    console.print(
                        f"[bold]Summary:[/bold] nodes={result.nodes_discovered} findings={result.findings_count} "
                        f"iterations={result.iterations} duration={int(result.duration_seconds)}s"
                    )
                    return 0 if result.status == "completed" else 1
                else:
                    console.print("\n[yellow]Scan finished without a result object.[/yellow]")
                    return 1
            except KeyboardInterrupt:
                console.print("\n[yellow]Scan interrupted.[/yellow]")
                await interface.stop_scan(run_id)
                return 130
            except Exception as e:
                console.print(f"\n[red]Scan failed: {e}[/red]")
                return 1

        # State for live display (Non-Verbose Mode)
        state = {
            "status": "Initializing...",
            "tools": [],
            "findings": [],
            "start_time": datetime.utcnow(),
            "tool_count": 0,
            "tool_failures": 0,
            "failed_tools": [],
            "last_error": "",
            "scan_id": "",
            "scan_name": "",
            "active_tool": "",
            "active_tool_started_at": None,
            "raw_findings": 0,
            "deduped_findings": 0,
            "duplicate_findings_filtered": 0,
            "report_paths": {},
            # New state fields
            "phase": "RECON",
            "iteration": 0,
            "prior_knowledge": "",
            "last_thought": "",
            "last_memory_event": "",
            "project_name": project or "",
        }

        def severity_breakdown(findings: List[Dict[str, Any]]) -> Dict[str, int]:
            counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
            for finding in findings:
                sev = str(finding.get("severity", "info")).lower()
                if sev in counts:
                    counts[sev] += 1
                else:
                    counts["info"] += 1
            return counts

        def _sev_markup(sev: str) -> str:
            style = SEVERITY_STYLES.get(sev.lower(), "white")
            return f"[{style}]{sev}[/{style}]"

        def create_view():
            elapsed = (datetime.utcnow() - state["start_time"]).total_seconds()

            # Phase tracker
            current_phase = state["phase"].upper()
            try:
                current_idx = SCAN_PHASES.index(current_phase)
            except ValueError:
                current_idx = 0
            phase_parts = []
            for i, p in enumerate(SCAN_PHASES):
                if i < current_idx:
                    phase_parts.append(f"[dim green]✓ {p}[/dim green]")
                elif i == current_idx:
                    phase_parts.append(f"[bold cyan]▶ {p}[/bold cyan]")
                else:
                    phase_parts.append(f"[dim]{p}[/dim]")
            phase_str = "  →  ".join(phase_parts)

            # Header
            header_lines = [
                f"[bold cyan]🔍 Kodiak Scan: {target}[/bold cyan]  |  {int(elapsed)}s elapsed",
            ]
            if state["project_name"]:
                header_lines.append(f"📁 Project: [bold]{state['project_name']}[/bold]")
            if state["prior_knowledge"]:
                header_lines.append(f"🧠 {state['prior_knowledge']}")
            header_lines.append(phase_str)
            header = Panel("\n".join(header_lines), box=box.DOUBLE, style="cyan")

            # Activity
            activity = Table(show_header=False, box=box.SIMPLE)
            activity.add_row("🤖 Status:", state["status"])
            if state["scan_id"]:
                activity.add_row("🧾 Scan ID:", state["scan_id"])
            if state["iteration"]:
                activity.add_row("🔄 Iteration:", f"{state['iteration']}/{max_iterations}")
            if state["active_tool"]:
                active_for = (
                    int((datetime.utcnow() - state["active_tool_started_at"]).total_seconds())
                    if state["active_tool_started_at"]
                    else 0
                )
                activity.add_row("🛠️ Active Tool:", f"{state['active_tool']} ({active_for}s)")
            activity.add_row("📈 Tools:", f"{state['tool_count']} total / {state['tool_failures']} failed")
            if state["last_memory_event"]:
                activity.add_row("💾 Saved:", state["last_memory_event"])
            if state["last_thought"]:
                thought_lines = [ln.strip() for ln in state["last_thought"].split("\n") if ln.strip()][:2]
                if thought_lines:
                    activity.add_row("💭 Thinking:", thought_lines[0][:100])
                    if len(thought_lines) > 1:
                        activity.add_row("", thought_lines[1][:100])
            if state["last_error"]:
                activity.add_row("❗ Last Error:", state["last_error"][:140])

            # Tools
            tools_table = Table(title="🔧 Recent Tools", box=box.SIMPLE)
            tools_table.add_column("Tool")
            tools_table.add_column("Target")
            tools_table.add_column("Result")
            for t in state["tools"][-7:]:
                res = "✅" if t["success"] else "❌" if t["success"] is False else "⏳"
                tools_table.add_row(t["name"], t["target"], res)

            # Findings (color-coded severity)
            findings_table = Table(title="⚠️ Findings", box=box.SIMPLE)
            findings_table.add_column("Sev")
            findings_table.add_column("Target")
            findings_table.add_column("Title")
            for f in state["findings"][-10:]:
                sev_str = str(f.get("severity", "info")).upper()
                findings_table.add_row(
                    _sev_markup(sev_str),
                    str(f.get("target", ""))[:36],
                    str(f.get("title", "Untitled"))[:72],
                )

            from rich.console import Group
            return Group(header, activity, tools_table, findings_table)

        result = None
        try:
            with Live(create_view(), refresh_per_second=2, console=console) as live:
                async for event in interface.subscribe_events(run_id):
                    payload = event.payload
                    if event.type == "agent_thinking":
                        msg = payload.get("message", "Thinking...")
                        state["status"] = msg
                        # Extract iteration number from "Iteration N" message
                        if msg.startswith("Iteration "):
                            try:
                                state["iteration"] = int(msg.split()[1])
                            except (ValueError, IndexError):
                                pass
                    elif event.type == "agent_thought":
                        state["status"] = "Generating plan..."
                        thought = str(payload.get("thought", "") or "").strip()
                        if thought:
                            state["last_thought"] = thought
                    elif event.type == "tool_start":
                        tool_name = payload.get("tool_name", "unknown")
                        state["status"] = f"Running {tool_name}"
                        state["active_tool"] = tool_name
                        state["active_tool_started_at"] = datetime.utcnow()
                        state["tool_count"] += 1
                        state["tools"].append(
                            {"name": tool_name, "target": payload.get("target", ""), "success": None}
                        )
                    elif event.type == "tool_complete":
                        if state["tools"]:
                            success = payload.get("success", True)
                            state["tools"][-1]["success"] = success
                            if success is False:
                                tool_name = str(payload.get("tool_name", "unknown"))
                                error_text = str(payload.get("error") or payload.get("output") or "Tool failed")
                                short_error = " ".join(error_text.split())[:220]
                                state["tool_failures"] += 1
                                state["last_error"] = short_error
                                state["failed_tools"].append({"tool": tool_name, "error": short_error})
                        state["active_tool"] = ""
                        state["active_tool_started_at"] = None
                    elif event.type == "finding_discovered":
                        finding = payload.get("finding", {})
                        if finding:
                            state["findings"].append(finding)
                    elif event.type == "scan_started":
                        state["scan_id"] = str(payload.get("scan_id", ""))
                        state["scan_name"] = str(payload.get("scan_name", ""))
                    elif event.type == "scan_completed":
                        state["status"] = "Scan completed"
                        summary = payload.get("summary", {}) or {}
                        state["raw_findings"] = int(summary.get("raw_findings", 0) or 0)
                        state["deduped_findings"] = int(summary.get("deduped_findings", 0) or 0)
                        state["duplicate_findings_filtered"] = int(summary.get("duplicate_findings_filtered", 0) or 0)
                        state["report_paths"] = summary.get("report_paths") or {}
                    elif event.type == "scan_failed":
                        state["status"] = "Scan failed"
                        state["last_error"] = str(payload.get("error", "Scan failed"))
                    elif event.type == "phase_advanced":
                        new_phase = str(payload.get("new_phase", "")).upper()
                        if new_phase:
                            state["phase"] = new_phase
                            state["status"] = f"Phase: {new_phase}"
                    elif event.type == "note_saved":
                        cat = payload.get("category", "general")
                        prev = (payload.get("preview") or "")[:60]
                        state["last_memory_event"] = f"📝 Note [{cat}]: {prev}"
                    elif event.type == "finding_saved":
                        sev = str(payload.get("severity", "info")).upper()
                        title = payload.get("title", "Untitled")[:50]
                        state["last_memory_event"] = f"🎯 Finding [{_sev_markup(sev)}] {title}"
                    elif event.type == "prior_knowledge_loaded":
                        n = payload.get("notes_count", 0)
                        f_ = payload.get("findings_count", 0)
                        state["prior_knowledge"] = f"Prior knowledge: {n} notes, {f_} findings loaded"

                    live.update(create_view())

                result = await interface.get_scan_result(run_id)
                state["status"] = f"Scan {result.status}!" if result else "Scan finished"
                live.update(create_view())
        except KeyboardInterrupt:
            console.print("\n[yellow]Scan interrupted.[/yellow]")
            await interface.stop_scan(run_id)
            return 130
        except Exception as e:
            console.print(f"\n[red]Scan failed: {e}[/red]")
            logger.exception("CLI Scan failure")
            return 1

        # --- Final Summary (Rich Table) ---
        console.print("")
        if result:
            sev = severity_breakdown(state["findings"])

            summary_table = Table(
                box=box.ROUNDED,
                title="📊 Scan Summary",
                title_style="bold green",
                show_header=True,
            )
            summary_table.add_column("Metric", style="dim", min_width=22)
            summary_table.add_column("Value", style="bold")

            status_style = "green" if result.status == "completed" else "red"
            summary_table.add_row("Status", f"[{status_style}]{result.status.upper()}[/{status_style}]")
            summary_table.add_row("Target", target)
            if state["project_name"]:
                summary_table.add_row("Project", state["project_name"])
            if state["scan_id"]:
                summary_table.add_row("Scan ID", state["scan_id"])
            summary_table.add_row("Nodes Discovered", str(result.nodes_discovered))
            summary_table.add_row("Findings (DB)", str(result.findings_count))
            summary_table.add_row("Iterations", str(result.iterations))
            summary_table.add_row("Duration", f"{int(result.duration_seconds)}s")
            summary_table.add_row("Tools Run", str(state["tool_count"]))
            summary_table.add_row("Tool Failures", str(state["tool_failures"]))
            summary_table.add_section()
            for sev_name in ("critical", "high", "medium", "low", "info"):
                count = sev[sev_name]
                if count > 0:
                    summary_table.add_row(
                        f"Severity: {sev_name.upper()}",
                        _sev_markup(f"{count}"),
                    )

            if state["raw_findings"] > 0:
                summary_table.add_section()
                summary_table.add_row("Raw Findings", str(state["raw_findings"]))
                summary_table.add_row("Unique Findings", str(state["deduped_findings"]))

            if state["report_paths"]:
                summary_table.add_section()
                for label, rpath in state["report_paths"].items():
                    summary_table.add_row(f"Report ({label})", rpath)

            db_path = os.path.expanduser(settings.sqlite_path or "~/.kodiak/kodiak.db")
            log_path = str(Path.home() / ".kodiak" / "logs" / "scan.log")
            summary_table.add_section()
            summary_table.add_row("Database", db_path)
            summary_table.add_row("Logs", log_path)

            console.print(summary_table)

            if state["last_error"]:
                console.print(f"[dim]Last Error: {state['last_error'][:220]}[/dim]")
            if state["failed_tools"]:
                console.print("[dim]Top Failed Tools:[/dim]")
                for item in state["failed_tools"][-3:]:
                    console.print(f"  [dim]- {item['tool']}: {item['error'][:180]}[/dim]")
            console.print("[dim]Re-run with [bold]--verbose[/bold] for detailed event stream.[/dim]")
            return 0 if result.status == "completed" else 1

        console.print(
            f"Status: unknown | Findings (observed): {len(state['findings'])} | "
            f"Tools Run: {state['tool_count']}"
        )
        return 1
        
    exit_code = asyncio.run(run_scan_internal())
    if exit_code != 0:
        raise click.exceptions.Exit(exit_code)


@main.command()
def migrate():
    """Reset and initialize the database tables (MVP simple migration)."""
    from kodiak.database.engine import init_db
    console.print("🔄 [bold]Recreating database tables...[/bold]")
    asyncio.run(init_db())
    console.print("[green]✅ Database initialized.[/green]")


@main.command()
@click.option("--target", "-t", help="Initial target to scan")
def tui(target: Optional[str]):
    """Launch the Kodiak TUI."""
    # Prevent logs from breaking TUI
    logger.remove()
    log_file = Path.home() / ".kodiak" / "logs" / "tui.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(log_file, level="INFO")
    
    try:
        from kodiak.tui.app import KodiakApp
        app = KodiakApp()
        if target:
            app.initial_target = target
        app.run()
    except Exception as e:
        console.print(f"[red]Failed to launch TUI: {e}[/red]")


@main.command()
@click.option("--action", type=click.Choice(['start', 'stop', 'restart', 'status', 'logs']), default='status')
def docker(action: str):
    """Manage Docker backend."""
    kodiak_dir = Path.home() / ".kodiak"
    kodiak_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(kodiak_dir)

    cmd_ok = True
    detail = ""
    if action == "start":
        cmd_ok, detail = run_docker_compose(["up", "-d"])
    elif action == "stop":
        cmd_ok, detail = run_docker_compose(["down"])
    elif action == "restart":
        stop_ok, stop_detail = run_docker_compose(["down"])
        start_ok, start_detail = run_docker_compose(["up", "-d"])
        cmd_ok = stop_ok and start_ok
        detail = f"down={stop_detail}; up={start_detail}"
    elif action == "status":
        cmd_ok, detail = run_docker_compose(["ps"])
    elif action == "logs":
        cmd_ok, detail = run_docker_compose(["logs", "-f"])

    if not cmd_ok:
        console.print(f"[red]Docker command failed:[/red] {detail}")
        raise click.exceptions.Exit(1)


@main.command()
def doctor():
    """Check installation status."""
    from kodiak.core.config import settings

    def status_label(ok: bool) -> str:
        return "[green]OK[/green]" if ok else "[red]FAIL[/red]"

    console.print("[bold]Kodiak Doctor[/bold]\n")
    console.print(f"Python: {sys.version.split()[0]}")
    console.print(f"Database: {status_label(HAS_DATABASE)}")
    
    docker_ok = check_docker_available()
    console.print(f"Docker: {status_label(docker_ok)}")
    console.print(f"Toolbox Image: {settings.toolbox_image}")

    if not docker_ok:
        console.print("[red]Docker is required for tool execution in this build.[/red]")
        console.print("[yellow]Start Docker and re-run `kodiak doctor`.[/yellow]")
        return

    image_ok, image_detail = run_check(["docker", "image", "inspect", settings.toolbox_image], timeout=20)
    console.print(f"Toolbox Image Available: {status_label(image_ok)}")
    if not image_ok:
        console.print(f"[yellow]Image inspect failed: {image_detail}[/yellow]")
        console.print(f"[yellow]Try: docker pull {settings.toolbox_image}[/yellow]")
        return

    # Probe all docker-backed Kodiak tools in one container run.
    docker_tool_map = {
        "nmap": "nmap",
        "nuclei": "nuclei",
        "subfinder": "subfinder",
        "httpx": "httpx",
        "katana": "katana",
        "ffuf": "ffuf",
        "whatweb": "whatweb",
        "sqlmap": "sqlmap",
        "commix": "commix",
        "searchsploit": "searchsploit",
    }
    probe_pairs = [f"{tool}:{binary}" for tool, binary in docker_tool_map.items()]
    probe_wordlist = " ".join(shlex.quote(pair) for pair in probe_pairs)
    probe_script = (
        f"for pair in {probe_wordlist}; do\n"
        "  tool=${pair%%:*}\n"
        "  bin=${pair##*:}\n"
        "  if command -v \"$bin\" >/dev/null 2>&1; then\n"
        "    echo \"$tool=1\"\n"
        "  else\n"
        "    echo \"$tool=0\"\n"
        "  fi\n"
        "done"
    )

    probe_ok, probe_detail = run_check(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            settings.toolbox_image,
            "-lc",
            probe_script,
        ],
        timeout=45,
    )

    status_map: Dict[str, bool] = {}
    if probe_ok:
        for line in (probe_detail or "").splitlines():
            cleaned = line.strip()
            if "=" not in cleaned:
                continue
            name, value = cleaned.split("=", 1)
            name = name.strip()
            if name in docker_tool_map:
                status_map[name] = value.strip() == "1"
    else:
        console.print(f"[yellow]Tool probe failed: {probe_detail}[/yellow]")
        console.print("[yellow]Falling back to per-tool checks...[/yellow]")
        for tool_name, binary_name in docker_tool_map.items():
            tool_ok, _ = run_check(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--entrypoint",
                    "/bin/sh",
                    settings.toolbox_image,
                    "-lc",
                    f"command -v {binary_name}",
                ],
                timeout=30,
            )
            status_map[tool_name] = tool_ok

    console.print("\n[bold]Docker Tool Availability[/bold]")
    missing_tools: List[str] = []
    for tool_name in sorted(docker_tool_map.keys()):
        tool_ok = status_map.get(tool_name, False)
        console.print(f"{tool_name}: {status_label(tool_ok)}")
        if not tool_ok:
            missing_tools.append(tool_name)

    console.print(
        f"Summary: {len(docker_tool_map) - len(missing_tools)}/{len(docker_tool_map)} available"
    )
    if missing_tools:
        console.print(
            "[yellow]Unavailable tools may be auto-disabled during scans: "
            + ", ".join(missing_tools)
            + "[/yellow]"
        )

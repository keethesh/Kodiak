"""
Kodiak CLI - AI-Powered Penetration Testing Suite
"""

import os
import sys
import asyncio
import subprocess
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
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        return True
    except Exception:
        return False


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
@click.option("--max-iterations", "-n", default=25, help="Maximum agent iterations")
@click.option("--verbose", "-v", is_flag=True, help="Show verbose real-time logging output")
def scan(target: str, instructions: str, model: Optional[str], max_iterations: int, verbose: bool):
    """Run a security scan on the target."""
    if not HAS_DATABASE:
        console.print("[red]Database support required for scans![/red]")
        return

    async def run_scan_internal():
        from kodiak.core.scan_runner import ScanRunner
        from kodiak.api.events import event_manager
        from kodiak.core.config import settings
        
        # If not verbose, silence loguru so messages don't break the Rich Live display
        if not verbose:
            logger.remove()
            
        log_file = Path.home() / ".kodiak" / "logs" / "scan.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(log_file, level="DEBUG", rotation="10 MB")
        
        if model:
            settings.llm_model = model
            
        console.print(f"\n🎯 [bold]Target:[/bold] {target}")
        console.print(f"🧠 [bold]Model:[/bold] {settings.llm_model}")
        console.print(f"📋 [bold]Instructions:[/bold] {instructions}\n")
        
        runner = ScanRunner(event_manager)
        
        # If verbose, bypass the TUI overlay and just let logs stream freely
        if verbose:
            console.print("[yellow]Verbose mode enabled. Streaming real-time execution logs...[/yellow]\n")
            try:
                result = await runner.run(
                    target=target,
                    instructions=instructions,
                    max_iterations=max_iterations
                )
                console.print(f"\n[green]Scan {result.status}![/green]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Scan interrupted.[/yellow]")
            except Exception as e:
                console.print(f"\n[red]Scan failed: {e}[/red]")
            return

        # State for live display (Non-Verbose Mode)
        state = {
            "status": "Initializing...",
            "tools": [],
            "findings": [],
            "start_time": datetime.utcnow()
        }
        
        def create_view():
            elapsed = (datetime.utcnow() - state["start_time"]).total_seconds()
            
            # Header
            header = Panel(
                f"[bold cyan]🔍 Kodiak Scan: {target}[/bold cyan] | {int(elapsed)}s elapsed",
                box=box.DOUBLE, style="cyan"
            )
            
            # Activity
            activity = Table(show_header=False, box=box.SIMPLE)
            activity.add_row("🤖 Status:", state["status"])
            
            # Tools
            tools_table = Table(title="🔧 Recent Tools", box=box.SIMPLE)
            tools_table.add_column("Tool")
            tools_table.add_column("Target")
            tools_table.add_column("Result")
            for t in state["tools"][-5:]:
                res = "✅" if t['success'] else "❌" if t['success'] is False else "⏳"
                tools_table.add_row(t['name'], t['target'], res)
            
            # Findings
            findings_table = Table(title="⚠️ Findings", box=box.SIMPLE)
            findings_table.add_column("Sev", style="red")
            findings_table.add_column("Title")
            for f in state["findings"][-5:]:
                findings_table.add_row(f['severity'].upper(), f['title'])
            
            from rich.console import Group
            return Group(header, activity, tools_table, findings_table)

        # Event Handlers
        async def on_thinking(ev): state["status"] = ev.data.get("message", "Thinking...")
        async def on_tool_start(ev):
            state["status"] = f"Running {ev.data['tool_name']}"
            state["tools"].append({"name": ev.data['tool_name'], "target": ev.data.get("target", ""), "success": None})
        async def on_tool_complete(ev):
            if state["tools"]:
                state["tools"][-1]["success"] = ev.data.get("success", True)
        async def on_finding(ev):
            state["findings"].append(ev.data.get("finding", {}))

        event_manager.subscribe("agent_thinking", on_thinking)
        event_manager.subscribe("tool_start", on_tool_start)
        event_manager.subscribe("tool_complete", on_tool_complete)
        event_manager.subscribe("finding_discovered", on_finding)
        
        try:
            with Live(create_view(), refresh_per_second=2, console=console) as live:
                result = await runner.run(
                    target=target,
                    instructions=instructions,
                    max_iterations=max_iterations
                )
                state["status"] = f"Scan {result.status}!"
                live.update(create_view())
        except KeyboardInterrupt:
            console.print("\n[yellow]Scan interrupted.[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Scan failed: {e}[/red]")
            logger.exception("CLI Scan failure")

        console.print("\n" + "="*50)
        console.print("[bold green]📊 Final Results[/bold green]")
        console.print("="*50)
        console.print(f"Nodes: {len(state['tools'])} | Findings: {len(state['findings'])}")
        
    asyncio.run(run_scan_internal())


@main.command()
def migrate():
    """Reset and initialize the database tables (MVP simple migration)."""
    import asyncio
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
    os.chdir(kodiak_dir)
    
    if action == "start":
        subprocess.run(["docker-compose", "up", "-d"])
    elif action == "stop":
        subprocess.run(["docker-compose", "down"])
    elif action == "status":
        subprocess.run(["docker-compose", "ps"])
    elif action == "logs":
        subprocess.run(["docker-compose", "logs", "-f"])


@main.command()
def doctor():
    """Check installation status."""
    console.print("🔍 [bold]Kodiak Doctor[/bold]\n")
    console.print(f"Python: {sys.version.split()[0]}")
    console.print(f"Database: {'✅' if HAS_DATABASE else '❌'}")
    console.print(f"Docker: {'✅' if check_docker_available() else '❌'}")
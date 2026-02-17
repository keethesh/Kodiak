"""
Kodiak CLI - AI-Powered Penetration Testing Suite

This module provides the command-line interface for Kodiak, supporting both
local installations and containerized deployments.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

# Check for optional dependencies
HAS_DATABASE = True
HAS_BROWSER = True
HAS_API = True

try:
    import sqlalchemy
    import sqlmodel
    import alembic
except ImportError:
    HAS_DATABASE = False

try:
    import playwright
except ImportError:
    HAS_BROWSER = False

try:
    import fastapi
    import uvicorn
except ImportError:
    HAS_API = False


def check_docker_available() -> bool:
    """Check if Docker is available for containerized tools."""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def show_installation_help():
    """Show help for installing optional dependencies."""
    console.print("\n[bold yellow]Optional Dependencies Available:[/bold yellow]")
    
    if not HAS_DATABASE:
        console.print("📊 Database support: [dim]uv tool install kodiak-pentest[database][/dim]")
    
    if not HAS_BROWSER:
        console.print("🌐 Browser automation: [dim]uv tool install kodiak-pentest[browser][/dim]")
        
    if not HAS_API:
        console.print("🔌 API server mode: [dim]uv tool install kodiak-pentest[api][/dim]")
    
    console.print("🚀 Full installation: [dim]uv tool install kodiak-pentest[full][/dim]")
    console.print("📦 Or use pip: [dim]pip install kodiak-pentest[full][/dim]")
    console.print()


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version information")
@click.option("--target", "-t", help="Target to scan (launches TUI)")
@click.pass_context
def main(ctx, version: bool, target: Optional[str]):
    """
    Kodiak - AI-Powered Penetration Testing Suite
    
    A modern terminal-based security testing platform that uses AI agents
    to coordinate intelligent vulnerability discovery and validation.
    """
    if version:
        try:
            from kodiak import __version__
            console.print(f"Kodiak v{__version__}")
        except ImportError:
            console.print("Kodiak v0.1.0")
        return
    
    if target:
        # Quick scan mode - launch TUI with target
        ctx.invoke(tui, target=target)
        return
    
    if ctx.invoked_subcommand is None:
        # No command specified, show help and launch TUI
        console.print(Panel.fit(
            Text("Kodiak - AI-Powered Penetration Testing Suite", style="bold blue"),
            border_style="blue"
        ))
        console.print("Use [bold]kodiak --help[/bold] for available commands")
        console.print("Launching TUI interface...\n")
        ctx.invoke(tui)


@main.command()
@click.option("--force", is_flag=True, help="Force reinitialize database")
@click.option("--docker", is_flag=True, help="Use Docker for database")
def init(force: bool, docker: bool):
    """Initialize Kodiak database and configuration."""
    
    # Auto-detect if we should use Docker
    if not docker and not HAS_DATABASE:
        console.print("Database dependencies not available locally, using Docker...")
        docker = True
    
    if docker:
        console.print("🐳 Using Docker for database initialization...")
        
        # Check if Docker is available
        if not check_docker_available():
            console.print("[red]Docker is not available![/red]")
            console.print("Install Docker or use: [dim]uv tool install kodiak-pentest[database][/dim]")
            sys.exit(1)
        
        # Ensure docker-compose.yml exists
        kodiak_dir = Path.home() / ".kodiak"
        compose_file = kodiak_dir / "docker-compose.yml"
        
        if not compose_file.exists():
            console.print("Creating Docker Compose configuration...")
            setup_docker_compose(kodiak_dir)
        
        # Start database container
        os.chdir(kodiak_dir)
        result = os.system("docker-compose up -d db")
        if result != 0:
            console.print("[red]Failed to start database container[/red]")
            sys.exit(1)
        
        # Initialize database using Docker
        result = os.system("docker-compose run --rm kodiak kodiak init")
        if result == 0:
            console.print("[green]✅ Database initialized successfully![/green]")
        else:
            console.print("[red]❌ Database initialization failed[/red]")
            sys.exit(1)
        return
    
    # Local database initialization
    try:
        import asyncio
        from kodiak.database.engine import init_db
        from kodiak.core.config import settings
        
        console.print(f"🔧 Initializing database at {settings.database_url}")
        
        if force:
            console.print("[yellow]Force mode: Dropping existing data[/yellow]")
        
        asyncio.run(init_db())
        console.print("[green]✅ Database initialized successfully![/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Database initialization failed: {e}[/red]")
        console.print("Try using Docker: [dim]kodiak init --docker[/dim]")
        sys.exit(1)


def setup_docker_compose(kodiak_dir: Path):
    """Create Docker Compose configuration for Kodiak."""
    compose_content = """services:
  # PostgreSQL Database
  db:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: kodiak
      POSTGRES_PASSWORD: kodiak_password
      POSTGRES_DB: kodiak_db
    ports:
      - "5432:5432"
    volumes:
      - kodiak_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U kodiak -d kodiak_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Kodiak Security Tools Container
  kodiak-tools:
    image: ghcr.io/keethesh/kodiak:latest
    restart: unless-stopped
    environment:
      - POSTGRES_SERVER=db
      - POSTGRES_USER=kodiak
      - POSTGRES_PASSWORD=kodiak_password
      - POSTGRES_DB=kodiak_db
      - POSTGRES_PORT=5432
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./scans:/app/scans
      - ./results:/app/results
      - /var/run/docker.sock:/var/run/docker.sock
    working_dir: /app
    ports:
      - "8000:8000"  # API port for tool execution
    command: ["python", "-m", "kodiak", "api", "--host", "0.0.0.0"]

  # Optional: Nuclei Templates Update Service
  nuclei-updater:
    image: projectdiscovery/nuclei:latest
    volumes:
      - nuclei_templates:/root/nuclei-templates
    command: ["nuclei", "-update-templates"]
    restart: "no"

volumes:
  kodiak_postgres_data:
  nuclei_templates:
"""
    
    compose_file = kodiak_dir / "docker-compose.yml"
    compose_file.write_text(compose_content.strip())
    
    # Create .env template if it doesn't exist
    env_file = kodiak_dir / ".env"
    if not env_file.exists():
        env_content = """# Kodiak Configuration
# LLM Configuration (choose one)
KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
GOOGLE_API_KEY=your_google_api_key_here

# Alternative LLM Providers
# KODIAK_LLM_MODEL=openai/gpt-4
# OPENAI_API_KEY=your_openai_api_key_here
# KODIAK_LLM_MODEL=anthropic/claude-3-5-sonnet-20241022
# ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Application Settings
KODIAK_DEBUG=false
KODIAK_LOG_LEVEL=INFO
KODIAK_ENABLE_SAFETY=true
KODIAK_MAX_AGENTS=5
KODIAK_TOOL_TIMEOUT=300
KODIAK_ENABLE_HIVE_MIND=true

# TUI Settings
KODIAK_TUI_COLOR_THEME=dark
KODIAK_TUI_REFRESH_RATE=10
"""
        env_file.write_text(env_content.strip())


@main.command()
@click.option("--interactive", "-i", is_flag=True, help="Force interactive TUI mode")
@click.option("--basic", "-b", is_flag=True, help="Use basic CLI prompts instead of TUI")
@click.pass_context
def config(ctx, interactive: bool, basic: bool):
    """Configure Kodiak settings and API keys.
    
    By default, launches a TUI wizard for guided configuration.
    Use --basic for simple CLI prompts (useful for scripts/SSH).
    """
    # Default to TUI wizard unless --basic is specified
    if basic:
        # Basic CLI mode (legacy behavior)
        console.print("🔧 [bold]Kodiak Configuration (Basic Mode)[/bold]")
        console.print()
        
        # LLM Provider selection
        console.print("Select LLM Provider:")
        console.print("1. Google Gemini (Recommended)")
        console.print("2. OpenAI GPT")
        console.print("3. Anthropic Claude")
        console.print("4. Local Ollama")
        
        choice = click.prompt("Choice", type=int, default=1)
        
        config_file = Path.home() / ".kodiak" / "config.env"
        config_file.parent.mkdir(exist_ok=True)
        
        config_lines = [
            "# Kodiak Configuration",
            "# Generated by 'kodiak config --basic'",
            "",
            "# Database: SQLite by default (zero-config)",
            "KODIAK_DB_TYPE=sqlite",
            ""
        ]
        
        if choice == 1:
            api_key = click.prompt("Google API Key", hide_input=True)
            config_lines.extend([
                "KODIAK_LLM_MODEL=gemini/gemini-1.5-pro",
                f"GOOGLE_API_KEY={api_key}"
            ])
        elif choice == 2:
            api_key = click.prompt("OpenAI API Key", hide_input=True)
            config_lines.extend([
                "KODIAK_LLM_MODEL=openai/gpt-4",
                f"OPENAI_API_KEY={api_key}"
            ])
        elif choice == 3:
            api_key = click.prompt("Anthropic API Key", hide_input=True)
            config_lines.extend([
                "KODIAK_LLM_MODEL=anthropic/claude-3-5-sonnet-20241022",
                f"ANTHROPIC_API_KEY={api_key}"
            ])
        elif choice == 4:
            config_lines.append("KODIAK_LLM_MODEL=ollama/llama3.1:70b")
            console.print("Make sure Ollama is running locally")
        
        # Write configuration
        with open(config_file, "w") as f:
            f.write("\n".join(config_lines) + "\n")
        
        # Set restrictive permissions
        try:
            config_file.chmod(0o600)
        except Exception:
            pass
        
        console.print(f"[green]✅ Configuration saved to {config_file}[/green]")
        console.print("\nTo apply configuration, run:")
        console.print(f"[dim]  export $(cat {config_file} | xargs)[/dim]")
        console.print("\nOr source it in your shell profile.")
    else:
        # TUI Wizard mode (default)
        try:
            from kodiak.tui.config_wizard import run_config_wizard
            
            console.print("🔧 Launching configuration wizard...\n")
            result = run_config_wizard()
            
            if result and result.get("launch_tui"):
                console.print("\n[green]✅ Configuration and initialization complete![/green]")
                # Launch TUI
                ctx.invoke(tui)
            elif result:
                console.print("\n[green]✅ Configuration complete![/green]")
                console.print("\nNext steps:")
                console.print("  [dim]kodiak init[/dim]    Initialize database")
                console.print("  [dim]kodiak[/dim]         Launch TUI")
            else:
                console.print("\n[yellow]Configuration cancelled.[/yellow]")
                
        except ImportError as e:
            console.print(f"[red]TUI dependencies not available: {e}[/red]")
            console.print("Falling back to basic mode...\n")
            # Recursively call with basic mode
            import subprocess
            subprocess.run([sys.executable, "-m", "kodiak", "config", "--basic"])
        except Exception as e:
            console.print(f"[red]Error launching wizard: {e}[/red]")
            console.print("Try using: [dim]kodiak config --basic[/dim]")


@main.command()
@click.option("--target", "-t", help="Initial target to scan")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--docker", is_flag=True, default=True, help="Use Docker for security tools (default)")
def tui(target: Optional[str], debug: bool, docker: bool):
    """Launch the Kodiak Terminal User Interface."""
    
    # Configure loguru to write to file instead of stderr to prevent TUI interference
    from loguru import logger
    import sys as _sys
    
    # Remove default stderr handler to prevent log messages from breaking TUI
    logger.remove()
    
    # Create log directory
    log_dir = Path.home() / ".kodiak" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tui.log"
    
    # Add file handler
    log_level = "DEBUG" if debug else "INFO"
    logger.add(
        log_file,
        rotation="10 MB",
        retention="7 days",
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )
    
    logger.info("Starting Kodiak TUI...")
    
    # Ensure Docker backend is ready if using Docker mode
    if docker:
        if not check_docker_available():
            console.print("[red]❌ Docker is not available![/red]")
            console.print("Install Docker or run: [dim]kodiak tui --no-docker[/dim]")
            sys.exit(1)
        
        # Ensure Docker services are running
        setup_docker_backend()
    
    try:
        from kodiak.tui.app import KodiakApp
        
        console.print("🚀 Launching Kodiak TUI...")
        
        app = KodiakApp()
        if target:
            app.initial_target = target
        
        # Configure app to use Docker backend
        if docker:
            app.use_docker_backend = True
        
        app.run()
        
    except ImportError as e:
        console.print(f"[red]❌ TUI dependencies missing: {e}[/red]")
        console.print("Install with: [dim]uv tool install kodiak-pentest[full][/dim]")
        sys.exit(1)
    except Exception as e:
        logger.exception("Failed to launch TUI")
        console.print(f"[red]❌ Failed to launch TUI: {e}[/red]")
        if debug:
            raise
        sys.exit(1)


def setup_docker_backend():
    """Ensure Docker backend services are running."""
    kodiak_dir = Path.home() / ".kodiak"
    kodiak_dir.mkdir(exist_ok=True)
    
    compose_file = kodiak_dir / "docker-compose.yml"
    
    # Create docker-compose.yml if it doesn't exist
    if not compose_file.exists():
        console.print("🐳 Setting up Docker backend...")
        setup_docker_compose(kodiak_dir)
    
    # Start services
    os.chdir(kodiak_dir)
    
    # Check if services are already running
    result = os.system("docker-compose ps --services --filter status=running | grep -q db")
    if result != 0:
        console.print("🐳 Starting Docker services...")
        result = os.system("docker-compose up -d")
        if result != 0:
            console.print("[red]❌ Failed to start Docker services[/red]")
            sys.exit(1)
        console.print("[green]✅ Docker services started[/green]")
    else:
        console.print("[green]✅ Docker services already running[/green]")


@main.command()
@click.option("--port", "-p", default=8000, help="Port to run API server")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind server")
def api(port: int, host: str):
    """Launch Kodiak API server (requires api extras)."""
    if not HAS_API:
        console.print("[red]API dependencies not installed![/red]")
        console.print("Install with: [dim]uv tool install kodiak-pentest[api][/dim]")
        show_installation_help()
        sys.exit(1)
    
    try:
        import uvicorn
        from kodiak.api.main import app
        
        console.print(f"🌐 Starting Kodiak API server on {host}:{port}")
        uvicorn.run(app, host=host, port=port)
        
    except Exception as e:
        console.print(f"[red]❌ Failed to start API server: {e}[/red]")
        sys.exit(1)


@main.command()
@click.option("--action", type=click.Choice(['start', 'stop', 'restart', 'status', 'logs']), default='status', help="Docker backend action")
@click.option("--service", help="Specific service to target")
def docker(action: str, service: Optional[str]):
    """Manage Kodiak Docker backend services."""
    if not check_docker_available():
        console.print("[red]❌ Docker is not available![/red]")
        console.print("Please install Docker to use backend services")
        sys.exit(1)
    
    kodiak_dir = Path.home() / ".kodiak"
    compose_file = kodiak_dir / "docker-compose.yml"
    
    if not compose_file.exists():
        console.print("🐳 Setting up Docker backend...")
        setup_docker_compose(kodiak_dir)
    
    os.chdir(kodiak_dir)
    
    service_arg = f" {service}" if service else ""
    
    if action == "start":
        console.print("🐳 Starting Kodiak backend services...")
        result = os.system(f"docker-compose up -d{service_arg}")
        if result == 0:
            console.print("[green]✅ Backend services started[/green]")
        else:
            console.print("[red]❌ Failed to start services[/red]")
    
    elif action == "stop":
        console.print("🛑 Stopping Kodiak backend services...")
        result = os.system(f"docker-compose down{service_arg}")
        if result == 0:
            console.print("[green]✅ Backend services stopped[/green]")
        else:
            console.print("[red]❌ Failed to stop services[/red]")
    
    elif action == "restart":
        console.print("🔄 Restarting Kodiak backend services...")
        os.system(f"docker-compose restart{service_arg}")
    
    elif action == "status":
        console.print("📊 Kodiak backend status:")
        os.system("docker-compose ps")
    
    elif action == "logs":
        if service:
            os.system(f"docker-compose logs -f {service}")
        else:
            os.system("docker-compose logs -f")



@main.command()
def doctor():
    """Check Kodiak installation status and dependencies."""
    console.print("🔍 [bold]Kodiak Installation Check[/bold]\n")
    
    # Check Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        console.print(f"✅ Python {py_version}")
    else:
        console.print(f"❌ Python {py_version} (Required: 3.11+)")

    # Check Core CLI
    console.print("✅ Core CLI: Available")
    
    # Check Optional Dependencies
    if HAS_DATABASE:
        console.print("✅ Database support: Available")
    else:
        console.print("❌ Database support: Missing (Install with [dim]uv tool install kodiak-pentest[database][/dim])")
        
    if HAS_BROWSER:
        console.print("✅ Browser automation: Available")
    else:
        console.print("❌ Browser automation: Missing (Install with [dim]uv tool install kodiak-pentest[browser][/dim])")
        
    if HAS_API:
        console.print("✅ API server: Available")
    else:
        console.print("❌ API server: Missing (Install with [dim]uv tool install kodiak-pentest[api][/dim])")
        
    # Check Docker
    if check_docker_available():
        console.print("✅ Docker: Available")
    else:
        console.print("❌ Docker: Missing or Not Running")
        
    console.print("\n🛠️  [bold]System Tools:[/bold]")
    import shutil
    
    # Check host tools
    for tool in ["curl", "wget", "git"]:
        if shutil.which(tool):
            console.print(f"✅ {tool}: Available")
        else:
            console.print(f"❌ {tool}: Missing")

    console.print("\n🧰 [bold]Security Tools (Docker Toolbox):[/bold]")
    docker_available = check_docker_available()
    
    # Check security tools
    security_tools = ["nmap", "nuclei", "sqlmap", "ffuf", "nikto"]
    
    if docker_available:
        # If Docker is available, these are available via the toolbox container
        for tool in security_tools:
            console.print(f"✅ {tool}: Available (via Docker)")
    else:
        # If Docker is missing, check locally
        for tool in security_tools:
            if shutil.which(tool):
                console.print(f"✅ {tool}: Available (Local)")
            else:
                console.print(f"❌ {tool}: Missing (Docker not running & not found locally)")

    console.print("\n[dim]Run 'kodiak config' to configure settings[/dim]")


@main.command()
@click.argument("target")
@click.option("--instructions", "-i", help="Custom scan instructions", default="Conduct a security assessment")
@click.option("--model", "-m", help="LLM model to use")
@click.option("--project", "-p", help="Project name (creates if not exists)", default=None)
def scan(target: str, instructions: str, model: Optional[str], project: Optional[str]):
    """Run a security scan on the target.
    
    Examples:
        kodiak scan example.com
        kodiak scan 192.168.1.1 --instructions "Focus on web vulnerabilities"
    """
    import asyncio
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    from datetime import datetime
    from uuid import UUID
    
    if not HAS_DATABASE:
        console.print("[red]Database support required for scans![/red]")
        console.print("Install with: [dim]poetry install --extras database[/dim]")
        return
    
    async def run_scan():
        """Async inner function that runs the scan"""
        try:
            from kodiak.database.engine import get_session, init_db
            from kodiak.database.models import Project, ScanJob, Node, Finding
            from kodiak.database.crud import project as crud_project, scan_job as crud_scan, node as crud_node
            from kodiak.core.orchestrator import Orchestrator
            from kodiak.core.tools.inventory import inventory
            from kodiak.api.events import TUIEventManager
            from kodiak.core.config import settings
            
            # Override model if specified
            if model:
                settings.llm_model = model
            
            console.print(f"\n🎯 [bold]Target:[/bold] {target}")
            console.print(f"🧠 [bold]Model:[/bold] {settings.llm_model}")
            console.print(f"📋 [bold]Instructions:[/bold] {instructions}\n")
            
            # Initialize database if needed
            try:
                await init_db()
            except Exception as e:
                # Database might already be initialized, continue
                pass
            
            # Live output data
            scan_data = {
                "start_time": datetime.utcnow(),
                "agent_status": "Initializing...",
                "tools_run": [],
                "findings": [],
                "nodes": []
            }
            
            def create_status_table():
                """Create the live status display"""
                elapsed = (datetime.utcnow() - scan_data["start_time"]).total_seconds()
                
                # Header panel
                header = Panel(
                    f"[bold cyan]🔍 Kodiak Security Scan[/bold cyan]\n"
                    f"Target: {target} | Elapsed: {int(elapsed)}s",
                    box=box.DOUBLE,
                    style="cyan"
                )
                
                # Status table
                status_table = Table(title="Agent Activity", box=box.SIMPLE, show_header=False)
                status_table.add_row("🤖 Status:", scan_data["agent_status"])
                
                # Tools table
                if scan_data["tools_run"]:
                    tools_table = Table(title="\n🔧 Tools Executed", box=box.SIMPLE)
                    tools_table.add_column("Tool", style="yellow")
                    tools_table.add_column("Target", style="cyan")
                    tools_table.add_column("Status", style="green")
                    
                    for tool in scan_data["tools_run"][-5:]:  # Show last 5
                        status_icon = "✅" if tool.get("success") else "❌"
                        tools_table.add_row(
                            tool["name"],
                            tool.get("target", "N/A"),
                            f"{status_icon} {tool.get('status', 'Unknown')}"
                        )
                else:
                    tools_table = Panel("[dim]No tools executed yet[/dim]", title="🔧 Tools Executed")
                
                # Findings table
                if scan_data["findings"]:
                    findings_table = Table(title="\n⚠️ Findings", box=box.SIMPLE)
                    findings_table.add_column("Severity", style="red")
                    findings_table.add_column("Title", style="white")
                    
                    for finding in scan_data["findings"][-5:]:  # Show last 5
                        findings_table.add_row(
                            finding.get("severity", "UNKNOWN").upper(),
                            finding.get("title", "Unknown finding")
                        )
                else:
                    findings_table = Panel("[dim]No findings yet[/dim]", title="⚠️ Findings")
                
                # Combine all elements
                from rich.console import Group
                return Group(header, status_table, tools_table, findings_table)
            
            # Use the global event manager that orchestrator and agents emit to
            from kodiak.api.events import event_manager
            
            async def handle_agent_thinking(event):
                scan_data["agent_status"] = event.data.get("message", "Thinking...")
            
            async def handle_tool_start(event):
                scan_data["agent_status"] = f"Running {event.data['tool_name']}..."
                scan_data["tools_run"].append({
                    "name": event.data["tool_name"],
                    "target": event.data.get("target", "N/A"),
                    "status": "Running...",
                    "success": None
                })
            
            async def handle_tool_complete(event):
                tool_name = event.data["tool_name"]
                success = event.data.get("success", False)
                # Update the last tool entry
                if scan_data["tools_run"]:
                    scan_data["tools_run"][-1]["status"] = "Completed" if success else "Failed"
                    scan_data["tools_run"][-1]["success"] = success
                scan_data["agent_status"] = "Analyzing results..."
            
            async def handle_finding_discovered(event):
                scan_data["findings"].append(event.data.get("finding", {}))
                scan_data["agent_status"] = f"Found: {event.data.get('finding', {}).get('title', 'Unknown')}"
            
            # Subscribe to events
            event_manager.subscribe("agent_thinking", handle_agent_thinking)
            event_manager.subscribe("tool_start", handle_tool_start)
            event_manager.subscribe("tool_complete", handle_tool_complete)
            event_manager.subscribe("finding_discovered", handle_finding_discovered)
            
            # Run the scan with live output
            with Live(create_status_table(), refresh_per_second=2, console=console) as live:
                try:
                    # Create or get project
                    # Phase 1: Initialize Project and Scan
                    async def initialize_scan():
                        async for session in get_session():
                            project_name = project or f"CLI Scan - {target}"
                            
                            # Try to find existing project
                            from sqlmodel import select
                            stmt = select(Project).where(Project.name == project_name)
                            result = await session.execute(stmt)
                            proj = result.scalar_one_or_none()
                            
                            if not proj:
                                proj = Project(name=project_name, description=f"CLI scan of {target}")
                                proj = await crud_project.create(session, proj)
                            
                            # Create scan job
                            scan_job = ScanJob(
                                project_id=proj.id,
                                name=f"Scan - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                                config={
                                    "target": target,
                                    "instructions": instructions
                                }
                            )
                            scan_job = await crud_scan.create(session, scan_job)
                            return proj, scan_job

                    proj, scan_job = await initialize_scan()
                    
                    # Phase 2: Start Orchestrator and Scan
                    orchestrator = Orchestrator(tool_inventory=inventory)
                    await orchestrator.start()
                    console.print(f"[dim]✓ Orchestrator started, scheduler is running[/dim]")
                    
                    await orchestrator.start_scan(scan_job.id)
                    console.print(f"[dim]✓ Root task created for scan {scan_job.id}[/dim]")
                    
                    # Monitor scan progress
                    scan_data["agent_status"] = "Scan started..."
                    
                    # Wait for the scan to complete (with timeout)
                    timeout = 600  # Increased to 10 minutes
                    start_time = datetime.utcnow()
                    
                    while (datetime.utcnow() - start_time).total_seconds() < timeout:
                        live.update(create_status_table())
                        await asyncio.sleep(2)
                        
                        # Check if scan is complete using a fresh session
                        async for session in get_session():
                            scan_job_updated = await crud_scan.get(session, scan_job.id)
                            if scan_job_updated and scan_job_updated.status in ["completed", "failed"]:
                                scan_data["agent_status"] = f"Scan {scan_job_updated.status}!"
                                break
                        else:
                            # Inner loop didn't break, continue while loop
                            continue
                        # Inner loop broke, exit while loop
                        break
                    
                    # Phase 3: Cleanup and Final Results
                    await orchestrator.stop()
                    
                    # Final update
                    live.update(create_status_table())
                    
                    # Get final stats
                    async for session in get_session():
                        nodes = await crud_node.get_nodes_by_project(session, proj.id)
                        scan_data["nodes"] = nodes
                        
                except KeyboardInterrupt:
                    console.print("\n[yellow]Scan interrupted by user[/yellow]")
                    if 'orchestrator' in locals():
                        await orchestrator.stop()
                except Exception as e:
                    console.print(f"\n[red]Scan failed: {e}[/red]")
                    import traceback
                    traceback.print_exc()
            
            # Print final summary
            console.print("\n" + "="*60)
            console.print("[bold green]📊 Scan Complete[/bold green]")
            console.print("="*60)
            
            duration = (datetime.utcnow() - scan_data["start_time"]).total_seconds()
            console.print(f"⏱️  Duration: {int(duration)}s")
            console.print(f"🔧 Tools executed: {len(scan_data['tools_run'])}")
            console.print(f"🌐 Nodes discovered: {len(scan_data['nodes'])}")
            console.print(f"⚠️  Findings: {len(scan_data['findings'])}")
            
            if scan_data['findings']:
                console.print("\n[bold]Top Findings:[/bold]")
                for finding in scan_data['findings'][:5]:
                    severity = finding.get('severity', 'UNKNOWN').upper()
                    title = finding.get('title', 'Unknown')
                    console.print(f"  [{severity}] {title}")
            
            console.print("\n[dim]Launch TUI for detailed analysis: kodiak tui[/dim]\n")
            
        except ImportError as e:
            console.print(f"[red]Missing dependencies: {e}[/red]")
            console.print("Install with: [dim]poetry install --extras database[/dim]")
        except Exception as e:
            console.print(f"[red]Scan error: {e}[/red]")
            import traceback
            traceback.print_exc()
    
    # Run the async function
    asyncio.run(run_scan())


@main.command()
def migrate():
    """Migrate database schema to latest version."""
    import asyncio
    
    if not HAS_DATABASE:
        console.print("[red]Database support required for migrations![/red]")
        return
    
    async def run_migration():
        try:
            from kodiak.database.engine import get_session, engine
            from sqlalchemy import text
            
            console.print("🔄 [bold]Migrating database schema...[/bold]\n")
            
            # Check if using SQLite or PostgreSQL
            async for session in get_session():
                # Check if task.properties exists
                try:
                    result = await session.execute(text("SELECT properties FROM task LIMIT 1"))
                    console.print("✅ Database schema is up to date!")
                    return
                except Exception:
                    # Column doesn't exist, need to add it
                    pass
                
                # Add missing columns
                console.print("📝 Adding missing columns...")
                
                try:
                    # Add task.properties column
                    await session.execute(text("ALTER TABLE task ADD COLUMN properties TEXT DEFAULT '{}'"))
                    await session.commit()
                    console.print("✅ Added task.properties column")
                except Exception as e:
                    console.print(f"❌ Failed to add task.properties: {e}")
                    await session.rollback()
                
                console.print("\n✅ [bold green]Migration complete![/bold green]")
                
        except Exception as e:
            console.print(f"[red]Migration failed: {e}[/red]")
            import traceback
            traceback.print_exc()
    
    asyncio.run(run_migration())




@main.command()
def services():
    """Show status of all Kodiak services."""
    console.print("🔍 [bold]Kodiak Services Status[/bold]\n")
    
    # Check global CLI
    console.print("📱 [bold]Global CLI:[/bold]")
    try:
        from kodiak import __version__
        console.print(f"  ✅ Kodiak CLI v{__version__} (global)")
    except ImportError:
        console.print("  ❌ Kodiak CLI not available")
    
    # Check Docker backend
    console.print("\n🐳 [bold]Docker Backend:[/bold]")
    if not check_docker_available():
        console.print("  ❌ Docker not available")
        return
    
    kodiak_dir = Path.home() / ".kodiak"
    compose_file = kodiak_dir / "docker-compose.yml"
    
    if not compose_file.exists():
        console.print("  ⚠️  Docker backend not configured")
        console.print("  Run: [dim]kodiak docker start[/dim] to set up")
        return
    
    os.chdir(kodiak_dir)
    
    # Check service status
    result = os.system("docker-compose ps --format table")
    
    console.print("\n📋 [bold]Quick Commands:[/bold]")
    console.print("  [dim]kodiak docker start[/dim]     Start backend services")
    console.print("  [dim]kodiak docker stop[/dim]      Stop backend services")
    console.print("  [dim]kodiak docker logs[/dim]      View service logs")
    console.print("  [dim]kodiak init --docker[/dim]    Initialize database")


if __name__ == "__main__":
    main()
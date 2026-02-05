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
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
        console.print("📊 Database support: [dim]pip install kodiak-pentest[database][/dim]")
    
    if not HAS_BROWSER:
        console.print("🌐 Browser automation: [dim]pip install kodiak-pentest[browser][/dim]")
        
    if not HAS_API:
        console.print("🔌 API server mode: [dim]pip install kodiak-pentest[api][/dim]")
    
    console.print("🚀 Full installation: [dim]pip install kodiak-pentest[full][/dim]")
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
    if not HAS_DATABASE and not docker:
        console.print("[red]Database dependencies not installed![/red]")
        console.print("Install with: [dim]pip install kodiak-pentest[database][/dim]")
        console.print("Or use Docker: [dim]kodiak init --docker[/dim]")
        show_installation_help()
        sys.exit(1)
    
    if docker or not HAS_DATABASE:
        console.print("🐳 Using Docker for database initialization...")
        # Use Docker Compose for database setup
        kodiak_dir = Path.home() / ".kodiak"
        kodiak_dir.mkdir(exist_ok=True)
        
        # Create minimal docker-compose.yml if it doesn't exist
        compose_file = kodiak_dir / "docker-compose.yml"
        if not compose_file.exists():
            compose_content = """
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: kodiak
      POSTGRES_PASSWORD: kodiak_password
      POSTGRES_DB: kodiak_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
"""
            compose_file.write_text(compose_content.strip())
        
        os.system(f"docker-compose -f {compose_file} up -d db")
        console.print("[green]✅ Database container started![/green]")
        return
    
    # Local database initialization
    try:
        import asyncio
        from kodiak.database.engine import init_database
        from kodiak.core.config import get_settings
        
        settings = get_settings()
        console.print(f"🔧 Initializing database at {settings.database_url}")
        
        if force:
            console.print("[yellow]Force mode: Dropping existing data[/yellow]")
        
        asyncio.run(init_database(force=force))
        console.print("[green]✅ Database initialized successfully![/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Database initialization failed: {e}[/red]")
        console.print("Try using Docker: [dim]kodiak init --docker[/dim]")
        sys.exit(1)


@main.command()
@click.option("--interactive", "-i", is_flag=True, help="Interactive configuration")
def config(interactive: bool):
    """Configure Kodiak settings and API keys."""
    if interactive:
        console.print("🔧 [bold]Kodiak Configuration[/bold]")
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
        
        config_lines = []
        
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
            f.write("\n".join(config_lines))
        
        console.print(f"[green]✅ Configuration saved to {config_file}[/green]")
        console.print("Add this to your shell profile:")
        console.print(f"[dim]export $(cat {config_file} | xargs)[/dim]")
    else:
        # Show current configuration
        try:
            from kodiak.core.config import get_settings
            settings = get_settings()
            console.print("📋 [bold]Current Configuration:[/bold]")
            console.print(f"LLM Model: {settings.llm_model}")
            console.print(f"Database: {settings.database_url}")
            console.print(f"Debug Mode: {settings.debug}")
        except ImportError:
            console.print("[yellow]Configuration module not available[/yellow]")
            console.print("Install database dependencies: [dim]pip install kodiak-pentest[database][/dim]")


@main.command()
@click.option("--target", "-t", help="Initial target to scan")
@click.option("--debug", is_flag=True, help="Enable debug mode")
def tui(target: Optional[str], debug: bool):
    """Launch the Kodiak Terminal User Interface."""
    try:
        from kodiak.tui.app import KodiakApp
        
        console.print("🚀 Launching Kodiak TUI...")
        
        app = KodiakApp()
        if target:
            app.initial_target = target
        
        app.run()
        
    except ImportError as e:
        console.print(f"[red]❌ TUI dependencies missing: {e}[/red]")
        console.print("Install with: [dim]pip install kodiak-pentest[full][/dim]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Failed to launch TUI: {e}[/red]")
        if debug:
            raise
        sys.exit(1)


@main.command()
@click.option("--port", "-p", default=8000, help="Port to run API server")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind server")
def api(port: int, host: str):
    """Launch Kodiak API server (requires api extras)."""
    if not HAS_API:
        console.print("[red]API dependencies not installed![/red]")
        console.print("Install with: [dim]pip install kodiak-pentest[api][/dim]")
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
def doctor():
    """Check Kodiak installation and dependencies."""
    console.print("🔍 [bold]Kodiak Installation Check[/bold]\n")
    
    # Check Python version
    python_version = sys.version_info
    if python_version >= (3, 11):
        console.print(f"✅ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
    else:
        console.print(f"❌ Python {python_version.major}.{python_version.minor} (requires 3.11+)")
    
    # Check core dependencies
    console.print(f"✅ Core CLI: Available")
    
    # Check optional dependencies
    console.print(f"{'✅' if HAS_DATABASE else '❌'} Database support: {'Available' if HAS_DATABASE else 'Missing'}")
    console.print(f"{'✅' if HAS_BROWSER else '❌'} Browser automation: {'Available' if HAS_BROWSER else 'Missing'}")
    console.print(f"{'✅' if HAS_API else '❌'} API server: {'Available' if HAS_API else 'Missing'}")
    
    # Check Docker
    docker_available = check_docker_available()
    console.print(f"{'✅' if docker_available else '❌'} Docker: {'Available' if docker_available else 'Missing'}")
    
    # Check external tools
    console.print("\n🛠️  [bold]External Tools:[/bold]")
    tools = ["nmap", "curl", "wget"]
    for tool in tools:
        available = os.system(f"which {tool} > /dev/null 2>&1") == 0
        console.print(f"{'✅' if available else '❌'} {tool}: {'Available' if available else 'Missing'}")
    
    if not (HAS_DATABASE and HAS_BROWSER and HAS_API):
        console.print()
        show_installation_help()


if __name__ == "__main__":
    main()
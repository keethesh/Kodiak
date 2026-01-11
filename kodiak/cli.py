#!/usr/bin/env python3
"""
Kodiak CLI interface

Provides command-line interface for Kodiak TUI application.
"""

import asyncio
import sys
from typing import Optional
import argparse
from pathlib import Path

def main() -> int:
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Kodiak - LLM Penetration Testing Suite with TUI",
        prog="kodiak"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # TUI command (default)
    tui_parser = subparsers.add_parser("tui", help="Launch TUI interface (default)")
    tui_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize database schema")
    init_parser.add_argument("--force", action="store_true", help="Force reinitialize")
    
    # Config command
    config_parser = subparsers.add_parser("config", help="Configure LLM settings")
    config_parser.add_argument("--interactive", action="store_true", default=True, 
                              help="Interactive configuration (default)")
    
    # Version command
    version_parser = subparsers.add_parser("version", help="Show version information")
    
    args = parser.parse_args()
    
    # Default to TUI if no command specified
    if args.command is None:
        args.command = "tui"
        args.debug = False
    
    try:
        if args.command == "tui":
            return run_tui(debug=getattr(args, 'debug', False))
        elif args.command == "init":
            return asyncio.run(run_init(force=getattr(args, 'force', False)))
        elif args.command == "config":
            return run_config(interactive=getattr(args, 'interactive', True))
        elif args.command == "version":
            return show_version()
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_tui(debug: bool = False) -> int:
    """Launch the TUI interface"""
    try:
        # Import here to avoid circular imports and ensure textual is available
        from kodiak.tui.app import KodiakApp
        
        app = KodiakApp(debug=debug)
        app.run()
        return 0
    except ImportError as e:
        print(f"Error: Failed to import TUI components: {e}", file=sys.stderr)
        print("Make sure Textual is installed: pip install textual", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error launching TUI: {e}", file=sys.stderr)
        return 1


async def run_init(force: bool = False) -> int:
    """Initialize database schema"""
    try:
        from kodiak.database.engine import init_db
        
        print("Initializing Kodiak database...")
        await init_db()
        print("✅ Database initialized successfully")
        return 0
    except ImportError as e:
        print(f"Error: Failed to import database components: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        return 1


def run_config(interactive: bool = True) -> int:
    """Configure LLM settings"""
    try:
        # For now, just point to the existing configure script
        print("LLM Configuration")
        print("=================")
        print("Please run: python configure_llm.py")
        print("This will be integrated into the CLI in a future update.")
        return 0
    except Exception as e:
        print(f"Error configuring LLM: {e}", file=sys.stderr)
        return 1


def show_version() -> int:
    """Show version information"""
    try:
        from kodiak import __version__
        print(f"Kodiak {__version__}")
        return 0
    except ImportError:
        print("Kodiak 0.1.0")
        return 0


if __name__ == "__main__":
    sys.exit(main())
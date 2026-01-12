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
        from kodiak.database.engine import init_db, verify_database_connectivity
        from kodiak.core.config import settings
        from sqlalchemy.exc import SQLAlchemyError
        import asyncpg
        
        print("Kodiak Database Initialization")
        print("=" * 30)
        
        # Display database configuration
        print(f"Database Server: {settings.postgres_server}:{settings.postgres_port}")
        print(f"Database Name: {settings.postgres_db}")
        print(f"Database User: {settings.postgres_user}")
        print()
        
        if force:
            print("⚠️  Force mode enabled - will recreate existing tables")
        
        print("Initializing database schema...")
        
        try:
            # Test basic connectivity first
            print("🔍 Testing database connectivity...")
            await verify_database_connectivity()
            print("✅ Database connection successful")
            
            # Initialize the database
            print("📋 Creating database tables...")
            await init_db()
            print("✅ Database tables created successfully")
            
            # Verify initialization
            print("🔍 Verifying database initialization...")
            from kodiak.database.models import Project, Scan, Node, Finding, AgentLog, Task
            from kodiak.database.engine import get_session
            
            async for session in get_session():
                # Try to query each main table to verify they exist
                from sqlalchemy import text
                tables_to_check = ['projects', 'scans', 'nodes', 'findings', 'agent_logs', 'tasks']
                
                for table in tables_to_check:
                    try:
                        result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        count = result.scalar()
                        print(f"  ✅ Table '{table}' exists (contains {count} records)")
                    except Exception as e:
                        print(f"  ❌ Table '{table}' check failed: {e}")
                        return 1
                break
            
            print()
            print("🎉 Database initialization completed successfully!")
            print()
            print("Next steps:")
            print("  1. Configure your LLM settings: kodiak config")
            print("  2. Launch the TUI interface: kodiak")
            print()
            
            return 0
            
        except asyncpg.InvalidCatalogNameError:
            print(f"❌ Database '{settings.postgres_db}' does not exist")
            print(f"Please create the database first:")
            print(f"  createdb -h {settings.postgres_server} -p {settings.postgres_port} -U {settings.postgres_user} {settings.postgres_db}")
            return 1
            
        except asyncpg.InvalidPasswordError:
            print("❌ Invalid database credentials")
            print("Please check your database configuration:")
            print("  - POSTGRES_USER")
            print("  - POSTGRES_PASSWORD")
            return 1
            
        except asyncpg.ConnectionDoesNotExistError:
            print(f"❌ Cannot connect to database server at {settings.postgres_server}:{settings.postgres_port}")
            print("Please ensure PostgreSQL is running and accessible")
            print("If using Docker: docker-compose up -d db")
            return 1
            
    except ImportError as e:
        print(f"❌ Failed to import required components: {e}", file=sys.stderr)
        print("Make sure all dependencies are installed: poetry install", file=sys.stderr)
        return 1
    except SQLAlchemyError as e:
        print(f"❌ Database error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


def run_config(interactive: bool = True) -> int:
    """Configure LLM settings"""
    try:
        from kodiak.core.config import (
            infer_provider_from_model, 
            get_required_api_key_env_var,
            ERROR_MESSAGES,
            settings
        )
        from pathlib import Path
        import os
        
        print("Kodiak LLM Configuration")
        print("=" * 25)
        print()
        
        if not interactive:
            print("Non-interactive mode not yet implemented.")
            print("Please run: kodiak config --interactive")
            return 1
        
        # Check if .env file exists
        env_file = Path(".env")
        env_exists = env_file.exists()
        
        if env_exists:
            print(f"📄 Found existing .env file")
            response = input("Do you want to update the existing configuration? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                print("Configuration cancelled.")
                return 0
        else:
            print("📄 No .env file found. Creating new configuration...")
        
        print()
        print("🤖 LLM Model Configuration")
        print("-" * 30)
        print()
        print("Enter your LLM model in LiteLLM format:")
        print("Examples:")
        print("  • gemini/gemini-3-pro-preview")
        print("  • openai/gpt-5")
        print("  • anthropic/claude-4.5-sonnet")
        print("  • ollama/llama2")
        print()
        print("For more models, see: https://docs.litellm.ai/docs/providers")
        print()
        
        # Get model string with validation
        while True:
            model_string = input("Model string: ").strip()
            
            if not model_string:
                print("❌ Model string is required. Please try again.")
                continue
            
            try:
                # Test provider inference
                provider = infer_provider_from_model(model_string)
                print(f"✅ Detected provider: {provider}")
                break
            except ValueError as e:
                print(f"❌ {e}")
                print("Please use format 'provider/model' or a recognized model name.")
                continue
        
        print()
        
        # Get API key based on inferred provider
        if provider == "ollama":
            print("🏠 Local model detected - no API key required")
            api_key = None
            api_key_env = None
        else:
            api_key_env = get_required_api_key_env_var(provider)
            
            # Provider-specific help
            api_key_help_map = {
                "gemini": "Get your API key from: https://makersuite.google.com/app/apikey",
                "openai": "Get your API key from: https://platform.openai.com/api-keys",
                "anthropic": "Get your API key from: https://console.anthropic.com/",
                "azure": "Get your API key from Azure OpenAI Service",
                "vertex_ai": "Configure Google Cloud credentials for Vertex AI"
            }
            
            api_key_help = api_key_help_map.get(provider, "Check your provider's documentation for API key instructions")
            
            print(f"🔑 {api_key_env} Required")
            print(f"   {api_key_help}")
            print()
            
            # Check if API key already exists in environment
            existing_key = os.getenv(api_key_env)
            if existing_key:
                masked_key = existing_key[:8] + "..." + existing_key[-4:] if len(existing_key) > 12 else "***"
                print(f"Found existing API key: {masked_key}")
                use_existing = input("Use existing API key? (Y/n): ").strip().lower()
                if use_existing in ['', 'y', 'yes']:
                    api_key = existing_key
                else:
                    api_key = input(f"Enter your {api_key_env}: ").strip()
            else:
                api_key = input(f"Enter your {api_key_env}: ").strip()
            
            if not api_key:
                print("❌ API key is required. Configuration cancelled.")
                return 1
        
        print()
        
        # Test LiteLLM connection
        print("🔍 Testing LLM connection...")
        try:
            # Import LiteLLM and test the configuration
            import litellm
            
            # Set up the API key for testing
            if api_key and api_key_env:
                os.environ[api_key_env] = api_key
            
            # Test with a simple completion
            test_messages = [{"role": "user", "content": "Hello"}]
            
            # Use a short timeout for testing
            response = litellm.completion(
                model=model_string,
                messages=test_messages,
                max_tokens=10,
                timeout=30
            )
            
            print("✅ LLM connection successful!")
            
        except Exception as e:
            print(f"⚠️  LLM connection test failed: {e}")
            print("Configuration will be saved, but please verify your API key and model string.")
            
            continue_anyway = input("Continue with configuration? (y/N): ").strip().lower()
            if continue_anyway not in ['y', 'yes']:
                print("Configuration cancelled.")
                return 1
        
        print()
        
        # Get database configuration
        print("🗄️  Database Configuration")
        print("-" * 25)
        
        # Use current settings as defaults
        db_server = input(f"Database server [{settings.postgres_server}]: ").strip() or settings.postgres_server
        db_port = input(f"Database port [{settings.postgres_port}]: ").strip() or str(settings.postgres_port)
        db_name = input(f"Database name [{settings.postgres_db}]: ").strip() or settings.postgres_db
        db_user = input(f"Database user [{settings.postgres_user}]: ").strip() or settings.postgres_user
        
        # Only ask for password if not already set or if user wants to change it
        existing_password = os.getenv("POSTGRES_PASSWORD")
        if existing_password:
            change_password = input("Change database password? (y/N): ").strip().lower()
            if change_password in ['y', 'yes']:
                db_password = input("Database password: ").strip()
            else:
                db_password = existing_password
        else:
            db_password = input("Database password: ").strip()
        
        print()
        
        # Optional advanced settings
        print("⚙️  Advanced Settings (optional)")
        print("-" * 30)
        
        temperature = input(f"Temperature (0.0-2.0) [{settings.llm_temperature}]: ").strip()
        if temperature:
            try:
                temperature = float(temperature)
                if not 0.0 <= temperature <= 2.0:
                    print("Warning: Temperature should be between 0.0 and 2.0")
            except ValueError:
                print("Warning: Invalid temperature value, using default")
                temperature = settings.llm_temperature
        else:
            temperature = settings.llm_temperature
        
        max_tokens = input(f"Max tokens [{settings.llm_max_tokens}]: ").strip()
        if max_tokens:
            try:
                max_tokens = int(max_tokens)
                if max_tokens <= 0:
                    print("Warning: Max tokens should be positive")
                    max_tokens = settings.llm_max_tokens
            except ValueError:
                print("Warning: Invalid max tokens value, using default")
                max_tokens = settings.llm_max_tokens
        else:
            max_tokens = settings.llm_max_tokens
        
        print()
        
        # Generate .env content
        env_content = []
        
        # Add header
        env_content.append("# Kodiak Configuration")
        env_content.append("# Generated by 'kodiak config'")
        env_content.append("")
        
        # LLM Configuration
        env_content.append("# LLM Configuration")
        env_content.append(f"KODIAK_LLM_MODEL={model_string}")
        if api_key and api_key_env:
            env_content.append(f"{api_key_env}={api_key}")
        env_content.append(f"KODIAK_LLM_TEMPERATURE={temperature}")
        env_content.append(f"KODIAK_LLM_MAX_TOKENS={max_tokens}")
        env_content.append("")
        
        # Database Configuration
        env_content.append("# Database Configuration")
        env_content.append(f"POSTGRES_SERVER={db_server}")
        env_content.append(f"POSTGRES_PORT={db_port}")
        env_content.append(f"POSTGRES_DB={db_name}")
        env_content.append(f"POSTGRES_USER={db_user}")
        env_content.append(f"POSTGRES_PASSWORD={db_password}")
        env_content.append("")
        
        # Application Configuration
        env_content.append("# Application Configuration")
        env_content.append("KODIAK_DEBUG=false")
        env_content.append("KODIAK_LOG_LEVEL=INFO")
        env_content.append("KODIAK_ENABLE_SAFETY=true")
        env_content.append("KODIAK_MAX_AGENTS=5")
        env_content.append("KODIAK_TOOL_TIMEOUT=300")
        env_content.append("KODIAK_ENABLE_HIVE_MIND=true")
        env_content.append("")
        
        # TUI Configuration
        env_content.append("# TUI Configuration")
        env_content.append("KODIAK_TUI_COLOR_THEME=dark")
        env_content.append("KODIAK_TUI_REFRESH_RATE=10")
        
        # Show configuration summary
        print("📋 Configuration Summary")
        print("-" * 20)
        print(f"LLM Model: {model_string}")
        print(f"LLM Provider: {provider} (inferred)")
        if api_key:
            masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
            print(f"API Key: {masked_key}")
        else:
            print("API Key: Not required (local model)")
        print(f"Database: {db_user}@{db_server}:{db_port}/{db_name}")
        print(f"Temperature: {temperature}")
        print(f"Max Tokens: {max_tokens}")
        print()
        
        # Confirm before writing
        confirm = input("Save this configuration? (Y/n): ").strip().lower()
        if confirm in ['', 'y', 'yes']:
            # Write .env file
            with open(".env", "w") as f:
                f.write("\n".join(env_content))
            
            print()
            print("✅ Configuration saved to .env file")
            print()
            print("Next steps:")
            print("  1. Initialize the database: kodiak init")
            print("  2. Launch Kodiak: kodiak")
            print()
            
            return 0
        else:
            print("Configuration cancelled.")
            return 0
            
    except KeyboardInterrupt:
        print("\nConfiguration cancelled by user.")
        return 130
    except Exception as e:
        print(f"❌ Configuration error: {e}", file=sys.stderr)
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
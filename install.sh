#!/bin/bash
set -Eeuo pipefail

# Kodiak Installation Script
# Robust installation using UV (modern Python package manager)

KODIAK_VERSION="${KODIAK_VERSION:-latest}"
INSTALL_DIR="$HOME/.kodiak"
BIN_DIR="$HOME/.local/bin"
UV_VERSION="0.5.11"
FORCE_INSTALL="${FORCE_INSTALL:-false}"
UPDATE_INSTALL="${UPDATE_INSTALL:-false}"
SKIP_DOCKER="${SKIP_DOCKER:-false}"
RESET_DB="${RESET_DB:-false}"
DRY_RUN="${DRY_RUN:-false}"
VERBOSE="${VERBOSE:-false}"
INSTALL_LOG="${INSTALL_LOG:-/tmp/kodiak-install.log}"
TOOLBOX_IMAGE="ghcr.io/keethesh/kodiak-toolbox:latest"
INSTALL_STATE_FILE="$INSTALL_DIR/install-state.env"

# Colors and text effects
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

print_status() {
    echo -e "  ${DIM}·${NC}  $1"
}

print_success() {
    echo -e "  ${GREEN}✓${NC}  $1"
}

print_warning() {
    echo -e "  ${YELLOW}⚠${NC}  $1"
}

print_error() {
    echo -e "  ${RED}✗${NC}  $1"
}

print_step() {
    echo
    echo -e "  ${CYAN}${BOLD}▸${NC} ${BOLD}$1${NC}"
}

print_blank() {
    echo
}

print_rule() {
    echo -e "  ${DIM}$(printf '─%.0s' {1..50})${NC}"
}

print_banner() {
    echo
    echo -e "${CYAN}${BOLD}  ██╗  ██╗ ██████╗ ██████╗ ██╗ █████╗ ██╗  ██╗${NC}"
    echo -e "${CYAN}${BOLD}  ██║ ██╔╝██╔═══██╗██╔══██╗██║██╔══██╗██║ ██╔╝${NC}"
    echo -e "${CYAN}${BOLD}  █████╔╝ ██║   ██║██║  ██║██║███████║█████╔╝ ${NC}"
    echo -e "${CYAN}${BOLD}  ██╔═██╗ ██║   ██║██║  ██║██║██╔══██║██╔═██╗ ${NC}"
    echo -e "${CYAN}${BOLD}  ██║  ██╗╚██████╔╝██████╔╝██║██║  ██║██║  ██╗${NC}"
    echo -e "${CYAN}${BOLD}  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝${NC}"
    echo
    echo -e "  ${DIM}AI-Powered Penetration Testing Suite${NC}"
    echo -e "  ${DIM}$(printf '─%.0s' {1..50})${NC}"
    echo
}

print_section() {
    echo
    echo -e "  ${BOLD}$1${NC}"
}

print_item() {
    echo -e "    ${DIM}▪${NC}  $1"
}

print_command() {
    echo -e "    ${CYAN}\$${NC}  $1"
}

run_cmd() {
    local description="$1"
    shift

    print_status "$description"

    if [[ "$DRY_RUN" == "true" ]]; then
        print_command "$*"
        return 0
    fi

    if [[ "$VERBOSE" == "true" ]]; then
        print_command "$*"
        "$@"
        return $?
    fi

    "$@" >>"$INSTALL_LOG" 2>&1
}

run_cmd_shell() {
    local description="$1"
    local command_string="$2"

    print_status "$description"

    if [[ "$DRY_RUN" == "true" ]]; then
        print_command "$command_string"
        return 0
    fi

    if [[ "$VERBOSE" == "true" ]]; then
        print_command "$command_string"
        bash -o pipefail -c "$command_string"
        return $?
    fi

    bash -o pipefail -c "$command_string" >>"$INSTALL_LOG" 2>&1
}

run_cmd_allow_fail() {
    local description="$1"
    shift

    if [[ "$DRY_RUN" == "true" ]]; then
        print_status "$description"
        print_command "$*"
        return 0
    fi

    if [[ "$VERBOSE" == "true" ]]; then
        print_status "$description"
        print_command "$*"
        "$@" || true
        return 0
    fi

    "$@" >>"$INSTALL_LOG" 2>&1 || true
}

on_error() {
    local exit_code=$?
    local line_no="${BASH_LINENO[0]:-unknown}"
    local cmd="${BASH_COMMAND:-unknown}"
    local func_name="${FUNCNAME[1]:-main}"
    print_error "Error at line ${line_no} in ${func_name}: ${cmd}"
    if [[ "${DRY_RUN:-false}" != "true" ]]; then
        print_status "Install log: ${INSTALL_LOG:-/tmp/kodiak-install.log}"
    fi
    exit "$exit_code"
}

show_help() {
    print_banner
    echo "Usage: $0 [options]"

    print_section "Options"
    print_item "--help, -h         Show this help message"
    print_item "--version VERSION  Install specific version/branch (git tag or branch)"
    print_item "--branch BRANCH    Install from a specific git branch"
    print_item "--force, -f        Force reinstall even if already installed"
    print_item "--update, -u       Update Kodiak via git pull or PyPI upgrade"
    print_item "--skip-docker      Skip building the Kodiak toolbox Docker image"
    print_item "--reset-db         Reset database after installation"
    print_item "--dry-run          Print planned actions without executing them"
    print_item "--verbose, -v      Show full command output (default is concise)"

    print_section "Environment Variables"
    print_item "KODIAK_VERSION     Set specific version to install (default: latest)"
    print_item "DRY_RUN            Set to true to print commands only"
    print_item "VERBOSE            Set to true to show full command output"
    print_item "INSTALL_LOG        Path for installer command logs"

    print_section "Examples"
    print_item "$0"
    print_item "$0 --branch codex/runtime-convergence"
    print_item "$0 --force"
    print_item "$0 --update --reset-db"
    print_item "$0 --dry-run"
    print_blank
}

save_install_state() {
    local install_method="$1"
    local source_dir="${2:-}"

    if [[ "$DRY_RUN" == "true" ]]; then
        print_command "cat > \"$INSTALL_STATE_FILE\" <<'EOF' ... EOF"
        return 0
    fi

    mkdir -p "$INSTALL_DIR"
    cat > "$INSTALL_STATE_FILE" <<EOF
INSTALL_METHOD="$install_method"
SOURCE_DIR="$source_dir"
KODIAK_VERSION="$KODIAK_VERSION"
UPDATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
EOF
}

load_install_state() {
    if [[ -f "$INSTALL_STATE_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$INSTALL_STATE_FILE"
    fi
}

prefer_source_install() {
    if [[ -f "pyproject.toml" ]] && grep -q 'name = "kodiak-pentest"' pyproject.toml 2>/dev/null; then
        return 0
    fi

    load_install_state
    if [[ "${INSTALL_METHOD:-}" == "source" ]]; then
        return 0
    fi

    if [[ -d "$INSTALL_DIR/source/.git" ]]; then
        return 0
    fi

    return 1
}

cleanup_existing_kodiak_installations() {
    # Remove UV tool installations
    if command_exists uv; then
        run_cmd_allow_fail "Removing uv tool: kodiak-pentest" uv tool uninstall kodiak-pentest
        run_cmd_allow_fail "Removing uv tool: kodiak" uv tool uninstall kodiak
    fi

    # Remove pipx installations
    if command_exists pipx; then
        run_cmd_allow_fail "Removing pipx package: kodiak-pentest" pipx uninstall kodiak-pentest
        run_cmd_allow_fail "Removing pipx package: kodiak" pipx uninstall kodiak
    fi

    # Remove binaries and UV tool directories
    run_cmd_allow_fail "Removing existing kodiak binary from user bin" rm -f "$HOME/.local/bin/kodiak"
    run_cmd_allow_fail "Removing existing kodiak binary from /usr/local/bin" rm -f "/usr/local/bin/kodiak"
    run_cmd_allow_fail "Removing uv tool directory: kodiak-pentest" rm -rf "$HOME/.local/share/uv/tools/kodiak-pentest"
    run_cmd_allow_fail "Removing uv tool directory: kodiak" rm -rf "$HOME/.local/share/uv/tools/kodiak"
}

# ---------------------------------------------------------------------------
# Platform and dependency checks
# ---------------------------------------------------------------------------

# Detect OS and architecture
detect_platform() {
    local os arch
    
    case "$(uname -s)" in
        Linux*)     os="linux" ;;
        Darwin*)    os="macos" ;;
        CYGWIN*|MINGW*|MSYS*) os="windows" ;;
        *)          os="unknown" ;;
    esac
    
    case "$(uname -m)" in
        x86_64|amd64)   arch="x86_64" ;;
        aarch64|arm64)  arch="aarch64" ;;
        armv7l)         arch="armv7" ;;
        *)              arch="unknown" ;;
    esac
    
    echo "${os}-${arch}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check system requirements
check_requirements() {
    print_step "Checking system requirements..."
    
    # Check for root execution
    if [[ $EUID -eq 0 ]]; then
        print_warning "Running as root! Kodiak tool packages will be installed to /root/.local/bin."
        print_status "Browser binaries and config will also be placed in /root."
        print_warning "If this is unintended, press Ctrl+C within 5 seconds to cancel."
        if [[ "$DRY_RUN" != "true" ]]; then
            sleep 5
        fi
    fi
    
    # Check Python version
    if ! command_exists python3; then
        print_error "Python 3 is required but not installed"
        print_status "Please install Python 3.11+ and try again"
        exit 1
    fi
    
    local python_version
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        print_error "Python 3.11+ is required (found Python $python_version)"
        print_status "Please upgrade Python and try again"
        exit 1
    fi
    
    print_success "Python $python_version found"
    
    # Check curl/wget for downloads
    if ! command_exists curl && ! command_exists wget; then
        print_error "curl or wget is required for downloads"
        exit 1
    fi
    
    # Check Docker (optional but recommended)
    if command_exists docker; then
        if docker info >/dev/null 2>&1; then
            print_success "Docker found and running (recommended for full functionality)"
        else
            print_warning "Docker found but not running - some features may be limited"
        fi
    else
        print_warning "Docker not found - some features may be limited"
    fi
    
    # Check Git (needed for source installation)
    if ! command_exists git; then
        print_warning "Git not found - will limit installation options"
    else
        print_success "Git found"
    fi
}

# Install UV package manager
install_uv() {
    if command_exists uv; then
        local uv_version
        uv_version=$(uv --version 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' || echo "unknown")
        print_success "UV already installed (version $uv_version)"
        return 0
    fi
    
    print_step "Installing UV package manager..."
    
    local platform
    platform=$(detect_platform)
    
    case "$platform" in
        linux-x86_64|linux-aarch64|macos-x86_64|macos-aarch64)
            # Use official installer
            if command_exists curl; then
                run_cmd_shell "Installing uv via official curl installer" "curl -LsSf https://astral.sh/uv/install.sh | sh"
            elif command_exists wget; then
                run_cmd_shell "Installing uv via official wget installer" "wget -qO- https://astral.sh/uv/install.sh | sh"
            fi
            ;;
        *)
            # Fallback to pip installation
            print_warning "Using pip fallback for UV installation on $platform"
            run_cmd "Installing uv with pip fallback" python3 -m pip install --user uv
            ;;
    esac
    
    # Add UV to PATH if not already there
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        export PATH="$HOME/.local/bin:$PATH"
        
        # Add to shell profile
        for profile in ~/.bashrc ~/.zshrc ~/.profile; do
            if [[ -f "$profile" ]]; then
                if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$profile"; then
                    run_cmd_shell "Adding ~/.local/bin to PATH in $profile" "echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> \"$profile\""
                fi
                break
            fi
        done
    fi
    
    # Verify UV installation
    if command_exists uv; then
        local uv_version
        uv_version=$(uv --version 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' || echo "unknown")
        print_success "UV installed successfully (version $uv_version)"
    else
        print_error "UV installation failed"
        exit 1
    fi
}

# Install Playwright browsers and dependencies
install_playwright() {
    print_status "Installing Playwright browsers..."
    local args=("$@")
    
    if command_exists uv; then
        if run_cmd "Installing Playwright Chromium browser" uv run "${args[@]}" playwright install chromium; then
            if [[ "$(uname -s)" == "Linux" ]]; then
                print_status "Installing Playwright system dependencies (may prompt for sudo)..."
                run_cmd_allow_fail "Installing Playwright Linux dependencies" uv run "${args[@]}" playwright install-deps chromium
            fi
        else
            print_warning "Failed to install Playwright browsers. Browser tools may not work."
        fi
    fi
}

# ---------------------------------------------------------------------------
# Kodiak installation paths
# ---------------------------------------------------------------------------

# Install Kodiak
install_kodiak() {
    print_step "Installing Kodiak..."
    
    # Create directories
    run_cmd "Creating install directory" mkdir -p "$INSTALL_DIR"
    run_cmd "Creating binary directory" mkdir -p "$BIN_DIR"
    
    # Check if already installed and WORKING
    local kodiak_works=false
    if command_exists kodiak; then
        if kodiak --version >/dev/null 2>&1; then
            kodiak_works=true
        fi
    fi
    
    if [[ "$kodiak_works" == "true" ]] && [[ "$FORCE_INSTALL" != "true" ]] && [[ "$UPDATE_INSTALL" != "true" ]]; then
        local current_version
        current_version=$(kodiak --version 2>/dev/null | grep -o 'v[0-9.]*' || echo "unknown")
        
        # Check against target version if we can determine it
        # For now, simplistic check: if versions match, skip. If not, upgrade.
        # But source version is in pyproject.toml which we might not have here yet if curling.
        
        print_warning "Kodiak $current_version is already installed."
        print_status "To force a reinstall/upgrade, run with --force or --update"
        
        # Determine if we should auto-upgrade (e.g. if we are installing specific version)
        if [[ "$KODIAK_VERSION" != "latest" ]] && [[ "v$KODIAK_VERSION" != "$current_version" ]]; then
             print_status "Version mismatch detected. Upgrading to $KODIAK_VERSION..."
             FORCE_INSTALL=true
        else
             print_status "Skipping installation. Use --force to reinstall."
             # Skip installation but still run verification
             return 0
        fi
    elif command_exists kodiak && [[ "$kodiak_works" != "true" ]]; then
        print_warning "Found broken Kodiak installation, will reinstall..."
        FORCE_INSTALL=true
    fi
    
    if [[ "$FORCE_INSTALL" == "true" ]]; then
        print_status "Force reinstalling Kodiak..."

        # Aggressively clean up all existing Kodiak installations.
        print_status "Cleaning up existing installations..."
        cleanup_existing_kodiak_installations
    fi

    if prefer_source_install; then
        if [[ "$UPDATE_INSTALL" == "true" ]]; then
            print_status "Detected existing source-based install. Preserving source update workflow."
        else
            print_status "Detected source checkout. Installing from source."
        fi
        install_from_source
        return 0
    fi
    
    # Try PyPI installation first
    print_status "Attempting PyPI installation..."
    
    local uv_install_args=(uv tool install "kodiak-pentest[full]")
    if [[ "$UPDATE_INSTALL" == "true" ]] || [[ "$FORCE_INSTALL" == "true" ]]; then
        uv_install_args+=(--force)
    fi
    
    if run_cmd "Installing Kodiak from PyPI via uv" "${uv_install_args[@]}"; then
        print_success "Kodiak installed/updated from PyPI"
        save_install_state "pypi"
        
        install_playwright --with kodiak-pentest
        
        return 0
    fi
    
    print_warning "PyPI package not available, installing from source..."
    install_from_source
}

resolve_python_project_dir() {
    local base_dir="$1"

    if [[ -f "$base_dir/pyproject.toml" ]] || [[ -f "$base_dir/setup.py" ]]; then
        echo "$base_dir"
        return 0
    fi

    # Defensive fallback for nested layouts.
    if [[ -f "$base_dir/Kodiak/pyproject.toml" ]] || [[ -f "$base_dir/Kodiak/setup.py" ]]; then
        echo "$base_dir/Kodiak"
        return 0
    fi

    return 1
}

# Install from source
install_from_source() {
    print_step "Installing Kodiak from source..."
    
    if ! command_exists git; then
        print_error "Git is required for source installation"
        exit 1
    fi
    
    local source_dir="$INSTALL_DIR/source"
    local is_update=false
    local using_current_dir=false
    
    if [[ "$UPDATE_INSTALL" == "true" ]] && [[ -d "$source_dir/.git" ]]; then
        is_update=true
    fi
    
    # If we are already in a Kodiak source directory, use it
    if [[ -f "pyproject.toml" ]] && grep -q "name = \"kodiak-pentest\"" pyproject.toml 2>/dev/null; then
        print_status "Found local Kodiak source code. Installing from current directory..."
        source_dir="$PWD"
        using_current_dir=true
        cd "$source_dir"
        
        if [[ "$is_update" == "true" ]]; then
            print_status "Pulling latest changes in local repository..."
            
            # Handle uncommitted changes
            local dirty=false
            if ! git diff-index --quiet HEAD --; then
                print_warning "Local repository has uncommitted changes."
                print_status "Stashing local changes..."
                run_cmd_allow_fail "Stashing local repository changes" git stash
                dirty=true
            fi
            
            run_cmd "Pulling latest changes with rebase" git pull --rebase || {
                print_error "Failed to pull updates from repository. You may need to fetch manually."
                exit 1
            }
            
            if [[ "$dirty" == "true" ]]; then
                print_status "Restoring local changes..."
                run_cmd_allow_fail "Restoring stashed local changes" git stash pop
            fi
        fi
    else
        # Not in a source dir, we will use ~/.kodiak/source
        if [[ "$is_update" == "true" ]]; then
            print_status "Updating existing Kodiak repository..."
            cd "$source_dir"
            run_cmd "Fetching remote updates and tags" git fetch --all --tags
        else
            # Clean up existing installation
            if [[ -d "$source_dir" ]]; then
                print_status "Removing existing source installation..."
                run_cmd "Removing existing source directory" rm -rf "$source_dir"
            fi

            # Aggressively clean up all existing Kodiak installations.
            print_status "Cleaning up any existing Kodiak installations..."
            cleanup_existing_kodiak_installations
            
            # Clone repository
            print_status "Cloning Kodiak repository..."
            if ! run_cmd "Cloning Kodiak repository" git clone https://github.com/keethesh/Kodiak.git "$source_dir"; then
                print_error "Failed to clone repository"
                exit 1
            fi
            
            cd "$source_dir"
        fi
    fi
    
    # Checkout specific branch/version if specified
    if [[ "$KODIAK_VERSION" != "latest" ]]; then
        print_status "Checking out version $KODIAK_VERSION..."
        run_cmd_allow_fail "Checking out version $KODIAK_VERSION" git checkout "$KODIAK_VERSION"
        if [[ "$DRY_RUN" != "true" ]] && ! git rev-parse --verify --quiet "$KODIAK_VERSION" >/dev/null 2>&1; then
            print_warning "Version $KODIAK_VERSION not found"
        fi
        
        if [[ "$is_update" == "true" ]]; then
            # Handle uncommitted changes for specific version pull
            local dirty=false
            if ! git diff-index --quiet HEAD --; then
                run_cmd_allow_fail "Stashing local changes before version pull" git stash
                dirty=true
            fi
            
            run_cmd_allow_fail "Pulling branch $KODIAK_VERSION with rebase" git pull origin "$KODIAK_VERSION" --rebase
            
            if [[ "$dirty" == "true" ]]; then
                run_cmd_allow_fail "Restoring stashed local changes" git stash pop
            fi
        fi
    else
        # Latest defaults to the currently checked out branch on updates, or main for fresh clones.
        local update_branch="main"
        if [[ "$is_update" == "true" ]]; then
            local current_branch
            current_branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
            if [[ -n "$current_branch" ]]; then
                update_branch="$current_branch"
            fi
        fi

        if git show-ref --verify --quiet "refs/remotes/origin/$update_branch"; then
            print_status "Using branch $update_branch..."
            run_cmd_allow_fail "Checking out branch $update_branch" git checkout "$update_branch"
            if [[ "$is_update" == "true" ]]; then
                run_cmd_allow_fail "Pulling latest $update_branch branch changes" git pull origin "$update_branch" --rebase
            fi
        elif git show-ref --verify --quiet refs/remotes/origin/main; then
            print_warning "origin/$update_branch not found. Falling back to main."
            run_cmd_allow_fail "Checking out main branch" git checkout main
            if [[ "$is_update" == "true" ]]; then
                run_cmd_allow_fail "Pulling latest main branch changes" git pull origin main --rebase
            fi
        else
            print_warning "No suitable remote branch found. Staying on current branch."
        fi
    fi

    # Validate source checkout layout before invoking uv.
    local project_dir
    project_dir="$(resolve_python_project_dir "$source_dir" || true)"

    if [[ -z "$project_dir" ]] && [[ "$using_current_dir" != "true" ]]; then
        print_warning "Source checkout missing pyproject.toml/setup.py. Re-cloning repository..."
        run_cmd "Removing invalid source checkout" rm -rf "$source_dir"
        if ! run_cmd "Re-cloning Kodiak repository" git clone https://github.com/keethesh/Kodiak.git "$source_dir"; then
            print_error "Failed to re-clone repository"
            exit 1
        fi
        cd "$source_dir"

        if [[ "$KODIAK_VERSION" != "latest" ]]; then
            run_cmd_allow_fail "Checking out version $KODIAK_VERSION after re-clone" git checkout "$KODIAK_VERSION"
        elif git show-ref --verify --quiet refs/remotes/origin/main; then
            run_cmd_allow_fail "Checking out main after re-clone" git checkout main
        fi

        project_dir="$(resolve_python_project_dir "$source_dir" || true)"
    fi

    if [[ -z "$project_dir" ]]; then
        print_error "Source installation directory is missing pyproject.toml/setup.py: $source_dir"
        print_status "Directory snapshot:"
        ls -la "$source_dir" || true
        exit 1
    fi

    cd "$project_dir"
    print_status "Using source project directory: $project_dir"
    
    # Install using UV with force flag to always overwrite
    print_status "Installing dependencies and Kodiak..."
    if ! run_cmd "Installing Kodiak in editable mode via uv" uv tool install --force --editable ".[full]"; then
        print_error "Failed to install Kodiak from source"
        print_status "Trying alternative installation method..."
        
        # Fallback: try without --editable
        if ! run_cmd "Installing Kodiak in non-editable mode via uv" uv tool install --force ".[full]"; then
            print_error "Alternative installation also failed"
            exit 1
        fi
    fi
    
    # Install playwright browsers
    install_playwright --with ".[full]"
    save_install_state "source" "$source_dir"
    
    print_success "Kodiak installed from source"
}

# ---------------------------------------------------------------------------
# Post-install setup and validation
# ---------------------------------------------------------------------------

# Setup configuration
setup_configuration() {
    print_step "Setting up configuration..."
    
    # Create config directory
    run_cmd "Ensuring config directory exists" mkdir -p "$INSTALL_DIR"
    
    # Create a minimal config file with SQLite defaults
    local config_file="$INSTALL_DIR/config.env"
    if [[ ! -f "$config_file" ]]; then
        print_status "Creating default configuration (SQLite mode)..."
        if [[ "$DRY_RUN" == "true" ]]; then
            print_command "cat > \"$config_file\" << 'EOF' ... EOF"
        else
        cat > "$config_file" << 'EOF'
# Kodiak Configuration
# Generated by install script - run 'kodiak config' to customize

# Database: SQLite by default (zero external dependencies)
# NOTE: After major updates, run 'kodiak migrate --reset' to recreate schema
KODIAK_DB_TYPE=sqlite

# LLM: Configure Gemini with 'kodiak config'
# GOOGLE_API_KEY=your_api_key_here

# Agent Model Settings
KODIAK_PLANNER_MODEL=gemini/gemini-3-flash-preview
KODIAK_ANALYST_MODEL=gemini/gemini-3.1-pro-preview

# Agent Cycle Settings
KODIAK_PLANNER_CYCLE_INTERVAL=8.0
KODIAK_ANALYST_POLL_INTERVAL=15.0

# Failure Handling
KODIAK_FAILURE_THRESHOLD=3

# Application Settings
KODIAK_DEBUG=false
KODIAK_LOG_LEVEL=INFO
KODIAK_ENABLE_SAFETY=true
KODIAK_TOOL_TIMEOUT=300
KODIAK_MULTI_AGENT=true
KODIAK_MULTI_AGENT_WORKERS=4
KODIAK_GLOBAL_CONCURRENCY=6

# Toolbox Container (for security tools)
KODIAK_TOOLBOX_IMAGE=ghcr.io/keethesh/kodiak-toolbox:latest
EOF
        fi
        # Set restrictive permissions
        run_cmd_allow_fail "Setting restrictive permissions on config file" chmod 600 "$config_file"
    fi
    
    print_success "Configuration created at $config_file"
    print_status "Run 'kodiak config' to set up your Gemini model and API key"
    
    if [[ "$RESET_DB" == "true" ]]; then
        print_status "Resetting database schema..."
        if kodiak migrate --reset --force 2>/dev/null; then
            print_success "Database schema reset complete"
        else
            print_warning "Database reset skipped (may not be initialized yet)"
        fi
    else
        print_status "NOTE: After major updates, run: kodiak migrate --reset"
        print_status "This ensures the database schema is up to date"
    fi
}

# Verify installation
verify_installation() {
    print_step "Verifying installation..."
    
    # Check if kodiak command is available
    if ! command_exists kodiak; then
        print_error "Kodiak command not found in PATH"
        print_status "You may need to restart your shell or run:"
        print_status "  source ~/.bashrc  # or ~/.zshrc"
        print_status "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        return 1
    fi
    
    # Get version
    local version
    version=$(kodiak --version 2>/dev/null | grep -o 'v[0-9.]*' || echo "unknown")
    print_success "Kodiak $version installed successfully!"
    
    # Run installation check
    print_status "Running installation diagnostics..."
    if kodiak doctor; then
        print_success "Installation verification passed!"
        return 0
    else
        print_warning "Some optional dependencies may be missing"
        print_status "Kodiak will work with reduced functionality"
        return 0
    fi
}

verify_toolbox_tools() {
    local image="${1:-$TOOLBOX_IMAGE}"
    local missing=0
    local tools=(
        nmap
        nuclei
        subfinder
        httpx
        katana
        ffuf
        whatweb
        sqlmap
        wpscan
        commix
        searchsploit
    )

    print_status "Verifying required tools inside $image..."
    for tool in "${tools[@]}"; do
        if run_cmd "Checking tool '$tool' in toolbox image" docker run --rm --entrypoint /bin/sh "$image" -lc "command -v $tool"; then
            print_success "Tool '$tool' found in toolbox image"
        else
            print_error "Tool '$tool' NOT found in toolbox image"
            missing=1
        fi
    done

    return $missing
}

# Setup Docker image
setup_docker() {
    if [[ "$SKIP_DOCKER" == "true" ]]; then
        print_status "Skipping Docker environment setup as requested."
        return 0
    fi

    print_step "Setting up Docker environment..."
    
    if command_exists docker; then
        if docker info >/dev/null 2>&1; then
            print_status "Docker is running. Checking for kodiak-toolbox image..."
            
            # Check if image exists locally
            local image_exists=false
            if docker image inspect "$TOOLBOX_IMAGE" >/dev/null 2>&1; then
                image_exists=true
            fi
            
            if [[ "$image_exists" == "false" ]] || [[ "$FORCE_INSTALL" == "true" ]]; then
                local pulled=false
                print_status "Attempting to pull pre-built Kodiak toolbox image from GHCR..."
                if run_cmd "Pulling pre-built toolbox image" docker pull "$TOOLBOX_IMAGE"; then
                    print_success "Kodiak toolbox Docker image pulled successfully from GHCR"
                    pulled=true
                else
                    print_warning "Could not pull pre-built image from GHCR. Falling back to local build..."
                fi

                if [[ "$pulled" == "false" ]]; then
                    print_status "Building Kodiak toolbox Docker image locally (this may take a while)..."
                    
                    # Check if we are in the source directory (either from git clone or manual download)
                    local dockerfile_path=""
                    local build_context=""
                    if [[ -f "containers/Dockerfile" ]]; then
                        dockerfile_path="containers/Dockerfile"
                        build_context="containers"
                    elif [[ -f "$INSTALL_DIR/source/containers/Dockerfile" ]]; then
                        dockerfile_path="$INSTALL_DIR/source/containers/Dockerfile"
                        build_context="$INSTALL_DIR/source/containers"
                    fi
                    
                    if [[ -n "$dockerfile_path" ]]; then
                        if run_cmd "Building toolbox image locally" docker build -t "$TOOLBOX_IMAGE" -f "$dockerfile_path" "$build_context"; then
                            print_success "Kodiak toolbox Docker image built successfully"
                        else
                            print_warning "Failed to build Docker image locally"
                            print_status "You can build it later by running: docker build -t $TOOLBOX_IMAGE -f containers/Dockerfile containers/"
                        fi
                    else
                        print_warning "Dockerfile not found. Could not build Kodiak toolbox image locally."
                        print_status "The agent will fallback to individual tool containers when scanning."
                    fi
                fi
            else
                print_success "Kodiak toolbox image already exists locally. Skipping build."
                print_status "Use --force to rebuild the image."
            fi

            # Validate critical tools expected by the agent loop.
            if ! verify_toolbox_tools "$TOOLBOX_IMAGE"; then
                print_error "Toolbox image is missing required tools (nmap/nuclei/subfinder/httpx/katana/ffuf/whatweb/sqlmap/wpscan/commix/searchsploit)."
                print_status "Rebuild with: docker build -t $TOOLBOX_IMAGE -f containers/Dockerfile containers/"
                return 1
            fi
        else
            print_warning "Docker is installed but the daemon is not running."
            print_status "Start Docker and run 'docker pull $TOOLBOX_IMAGE' or build it manually."
        fi
    else
        print_warning "Docker not found. Security tools will rely on local installations."
    fi
}

# ---------------------------------------------------------------------------
# UX and CLI entrypoints
# ---------------------------------------------------------------------------

# Show next steps
show_next_steps() {
    print_success "Kodiak installation complete."

    echo
    echo -e "  ${DIM}$(printf '─%.0s' {1..50})${NC}"
    echo
    echo -e "  ${BOLD}Quick Start${NC}"
    echo
    echo -e "    ${CYAN}\$${NC}  kodiak config       ${DIM}Configure LLM & API key${NC}"
    echo -e "    ${CYAN}\$${NC}  kodiak init         ${DIM}Initialize the database${NC}"
    echo -e "    ${CYAN}\$${NC}  kodiak --target .   ${DIM}Start scanning${NC}"
    echo -e "    ${CYAN}\$${NC}  ./install.sh --update ${DIM}Update an existing install${NC}"
    echo
    echo -e "  ${DIM}$(printf '─%.0s' {1..50})${NC}"
    echo
    echo -e "  ${BOLD}What's Included${NC}"
    echo
    echo -e "    ${DIM}▪${NC}  SQLite database (zero external dependencies)"
    echo -e "    ${DIM}▪${NC}  Security tools via Docker (nmap, nuclei, sqlmap, …)"
    echo -e "    ${DIM}▪${NC}  TUI interface for real-time monitoring"
    echo
    echo -e "  ${DIM}$(printf '─%.0s' {1..50})${NC}"
    echo
    echo -e "  ${BOLD}Commands${NC}"
    echo
    echo -e "    ${CYAN}kodiak${NC}               Launch TUI interface"
    echo -e "    ${CYAN}kodiak config${NC}        Configure LLM and settings"
    echo -e "    ${CYAN}kodiak doctor${NC}        Check installation status"
    echo -e "    ${CYAN}kodiak --help${NC}        Show all commands"
    echo
    echo -e "  ${DIM}$(printf '─%.0s' {1..50})${NC}"
    echo
    echo -e "  ${DIM}github.com/keethesh/Kodiak${NC}"
    echo

    if [[ ! -f "$HOME/.local/bin/kodiak" ]]; then
        print_warning "If 'kodiak' command is not found, restart your shell or run:"
        print_command "source ~/.bashrc  # or ~/.zshrc"
    fi
    print_blank
}

# Cleanup on error
cleanup_on_error() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        print_error "Installation failed with exit code $exit_code"
        if [[ "$DRY_RUN" != "true" ]]; then
            print_status "Install log: $INSTALL_LOG"
        fi
        print_status "Cleaning up..."
        
        # Remove partial installation
        if [[ -d "$INSTALL_DIR/source" ]]; then
            run_cmd_allow_fail "Removing partial source directory" rm -rf "$INSTALL_DIR/source"
        fi
        
        print_status "You can try running the installer again or install manually"
        print_status "For help, visit: https://github.com/keethesh/Kodiak/issues"
    fi
}

# Handle command line arguments
handle_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                exit 0
                ;;
            --version)
                if [[ -n "${2:-}" ]]; then
                    KODIAK_VERSION="$2"
                    shift 2
                else
                    print_error "--version requires a version number"
                    exit 1
                fi
                ;;
            --branch)
                if [[ -n "${2:-}" ]]; then
                    KODIAK_VERSION="$2"
                    shift 2
                else
                    print_error "--branch requires a branch name"
                    exit 1
                fi
                ;;
            --force|-f)
                FORCE_INSTALL=true
                shift
                ;;
            --update|-u)
                UPDATE_INSTALL=true
                shift
                ;;
            --skip-docker)
                SKIP_DOCKER=true
                shift
                ;;
            --reset-db)
                RESET_DB=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                print_status "Use --help for usage information"
                exit 1
                ;;
        esac
    done
}

# Main installation function
main() {
    # Set up error handling
    trap on_error ERR
    trap cleanup_on_error EXIT
    
    print_banner
    
    # Handle command line arguments
    handle_arguments "$@"

    if [[ "$DRY_RUN" != "true" ]]; then
        : > "$INSTALL_LOG"
    fi
    
    # Show installation info
    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "Dry-run mode enabled. Commands will be printed but not executed."
    elif [[ "$VERBOSE" != "true" ]]; then
        print_status "Concise output mode enabled. Detailed logs: $INSTALL_LOG"
    fi

    if [[ "$KODIAK_VERSION" != "latest" ]]; then
        print_status "Installing Kodiak version: $KODIAK_VERSION"
    else
        print_status "Installing latest Kodiak version"
    fi
    print_blank
    
    # Run installation steps
    check_requirements
    install_uv
    install_kodiak
    setup_configuration
    setup_docker
    
    if verify_installation; then
        show_next_steps
        
        # Disable error trap on successful completion
        trap - EXIT
    else
        print_error "Installation verification failed"
        print_status "Kodiak may still work with limited functionality"
        exit 1
    fi
}

# Run main installation
main "$@"

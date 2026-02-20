#!/bin/bash
set -e

# Kodiak Installation Script
# Robust installation using UV (modern Python package manager)

KODIAK_VERSION="${KODIAK_VERSION:-latest}"
INSTALL_DIR="$HOME/.kodiak"
BIN_DIR="$HOME/.local/bin"
UV_VERSION="0.5.11"
FORCE_INSTALL="${FORCE_INSTALL:-false}"
UPDATE_INSTALL="${UPDATE_INSTALL:-false}"
SKIP_DOCKER="${SKIP_DOCKER:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

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
        sleep 5
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
                curl -LsSf https://astral.sh/uv/install.sh | sh
            elif command_exists wget; then
                wget -qO- https://astral.sh/uv/install.sh | sh
            fi
            ;;
        *)
            # Fallback to pip installation
            print_warning "Using pip fallback for UV installation on $platform"
            python3 -m pip install --user uv
            ;;
    esac
    
    # Add UV to PATH if not already there
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        export PATH="$HOME/.local/bin:$PATH"
        
        # Add to shell profile
        for profile in ~/.bashrc ~/.zshrc ~/.profile; do
            if [[ -f "$profile" ]]; then
                if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$profile"; then
                    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$profile"
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
        if uv run "${args[@]}" playwright install chromium; then
            if [[ "$(uname -s)" == "Linux" ]]; then
                print_status "Installing Playwright system dependencies (may prompt for sudo)..."
                uv run "${args[@]}" playwright install-deps chromium || print_warning "Failed to install dependencies automatically. Run 'playwright install-deps chromium' if browser tools fail."
            fi
        else
            print_warning "Failed to install Playwright browsers. Browser tools may not work."
        fi
    fi
}

# Install Kodiak
install_kodiak() {
    print_step "Installing Kodiak..."
    
    # Create directories
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BIN_DIR"
    
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
        
        # Aggressively clean up ALL existing Kodiak installations
        print_status "Cleaning up existing installations..."
        
        # Remove UV tool installations
        if command_exists uv; then
            uv tool uninstall kodiak-pentest 2>/dev/null || true
            uv tool uninstall kodiak 2>/dev/null || true
        fi
        
        # Remove pipx installations
        if command_exists pipx; then
            pipx uninstall kodiak-pentest 2>/dev/null || true
            pipx uninstall kodiak 2>/dev/null || true
        fi
        
        # Remove any existing kodiak binary in common locations
        rm -f "$HOME/.local/bin/kodiak" 2>/dev/null || true
        rm -f "/usr/local/bin/kodiak" 2>/dev/null || true
        
        # Remove UV tool directory for kodiak
        rm -rf "$HOME/.local/share/uv/tools/kodiak-pentest" 2>/dev/null || true
        rm -rf "$HOME/.local/share/uv/tools/kodiak" 2>/dev/null || true
    fi
    
    # Try PyPI installation first
    print_status "Attempting PyPI installation..."
    
    local uv_install_cmd="uv tool install kodiak-pentest[full]"
    if [[ "$UPDATE_INSTALL" == "true" ]] || [[ "$FORCE_INSTALL" == "true" ]]; then
        uv_install_cmd="$uv_install_cmd --force"
    fi
    
    if $uv_install_cmd 2>/dev/null; then
        print_success "Kodiak installed/updated from PyPI"
        
        install_playwright --with kodiak-pentest
        
        return 0
    fi
    
    print_warning "PyPI package not available, installing from source..."
    install_from_source
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
    
    if [[ "$UPDATE_INSTALL" == "true" ]] && [[ -d "$source_dir/.git" ]]; then
        is_update=true
    fi
    
    # If we are already in a Kodiak source directory, use it
    if [[ -f "pyproject.toml" ]] && grep -q "name = \"kodiak-pentest\"" pyproject.toml 2>/dev/null; then
        print_status "Found local Kodiak source code. Installing from current directory..."
        source_dir="$PWD"
        cd "$source_dir"
        
        if [[ "$is_update" == "true" ]]; then
            print_status "Pulling latest changes in local repository..."
            
            # Handle uncommitted changes
            local dirty=false
            if ! git diff-index --quiet HEAD --; then
                print_warning "Local repository has uncommitted changes."
                print_status "Stashing local changes..."
                git stash || true
                dirty=true
            fi
            
            git pull origin HEAD --rebase || {
                print_error "Failed to pull updates from repository. You may need to fetch manually."
                exit 1
            }
            
            if [[ "$dirty" == "true" ]]; then
                print_status "Restoring local changes..."
                git stash pop || print_warning "Merge conflicts detected while restoring stash. Please resolve manually."
            fi
        fi
    else
        # Not in a source dir, we will use ~/.kodiak/source
        if [[ "$is_update" == "true" ]]; then
            print_status "Updating existing Kodiak repository..."
            cd "$source_dir"
            git fetch --all --tags
        else
            # Clean up existing installation
            if [[ -d "$source_dir" ]]; then
                print_status "Removing existing source installation..."
                rm -rf "$source_dir"
            fi
            
            # Aggressively clean up ALL existing Kodiak installations
            print_status "Cleaning up any existing Kodiak installations..."
            
            # Remove UV tool installations
            if command_exists uv; then
                uv tool uninstall kodiak-pentest 2>/dev/null || true
                uv tool uninstall kodiak 2>/dev/null || true
            fi
            
            # Remove pipx installations
            if command_exists pipx; then
                pipx uninstall kodiak-pentest 2>/dev/null || true
                pipx uninstall kodiak 2>/dev/null || true
            fi
            
            # Remove any existing kodiak binary in common locations
            rm -f "$HOME/.local/bin/kodiak" 2>/dev/null || true
            rm -f "/usr/local/bin/kodiak" 2>/dev/null || true
            
            # Remove UV tool directory for kodiak
            rm -rf "$HOME/.local/share/uv/tools/kodiak-pentest" 2>/dev/null || true
            rm -rf "$HOME/.local/share/uv/tools/kodiak" 2>/dev/null || true
            
            # Clone repository
            print_status "Cloning Kodiak repository..."
            if ! git clone https://github.com/keethesh/Kodiak.git "$source_dir"; then
                print_error "Failed to clone repository"
                exit 1
            fi
            
            cd "$source_dir"
        fi
    fi
    
    # Checkout specific branch/version if specified
    if [[ "$KODIAK_VERSION" != "latest" ]]; then
        print_status "Checking out version $KODIAK_VERSION..."
        git checkout "$KODIAK_VERSION" || {
            print_warning "Version $KODIAK_VERSION not found"
        }
        
        if [[ "$is_update" == "true" ]]; then
            # Handle uncommitted changes for specific version pull
            local dirty=false
            if ! git diff-index --quiet HEAD --; then
                git stash || true
                dirty=true
            fi
            
            git pull origin "$KODIAK_VERSION" --rebase || true
            
            if [[ "$dirty" == "true" ]]; then
                git stash pop || print_warning "Conflicts restoring stash."
            fi
        fi
    else
        # Use refactor branch for now (until merged to main)
        if git show-ref --verify --quiet refs/remotes/origin/refactor/backend-rewrite; then
            print_status "Using refactor/backend-rewrite branch..."
            git checkout refactor/backend-rewrite
            if [[ "$is_update" == "true" ]] && [[ "$source_dir" != "$PWD" || $(git symbolic-ref --short HEAD 2>/dev/null) == "refactor/backend-rewrite" ]]; then
                git pull origin refactor/backend-rewrite --rebase || true
            fi
        else
            if [[ "$is_update" == "true" ]] && [[ "$source_dir" != "$PWD" || $(git symbolic-ref --short HEAD 2>/dev/null) == "main" ]]; then
                git pull origin main --rebase || true
            fi
        fi
    fi
    
    # Install using UV with force flag to always overwrite
    print_status "Installing dependencies and Kodiak..."
    if ! uv tool install --force --editable ".[full]"; then
        print_error "Failed to install Kodiak from source"
        print_status "Trying alternative installation method..."
        
        # Fallback: try without --editable
        if ! uv tool install --force ".[full]"; then
            print_error "Alternative installation also failed"
            exit 1
        fi
    fi
    
    # Install playwright browsers
    install_playwright --with ".[full]"
    
    print_success "Kodiak installed from source"
}

# Setup configuration
setup_configuration() {
    print_step "Setting up configuration..."
    
    # Create config directory
    mkdir -p "$INSTALL_DIR"
    
    # Create a minimal config file with SQLite defaults
    local config_file="$INSTALL_DIR/config.env"
    if [[ ! -f "$config_file" ]]; then
        print_status "Creating default configuration (SQLite mode)..."
        cat > "$config_file" << 'EOF'
# Kodiak Configuration
# Generated by install script - run 'kodiak config' to customize

# Database: SQLite by default (zero external dependencies)
KODIAK_DB_TYPE=sqlite

# LLM Provider: Configure with 'kodiak config'
# KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
# GOOGLE_API_KEY=your_api_key_here

# Application Settings
KODIAK_DEBUG=false
KODIAK_LOG_LEVEL=INFO
KODIAK_ENABLE_SAFETY=true
KODIAK_MAX_AGENTS=5
KODIAK_TOOL_TIMEOUT=300
KODIAK_ENABLE_HIVE_MIND=true

# Toolbox Container (for security tools)
KODIAK_TOOLBOX_IMAGE=ghcr.io/keethesh/kodiak-toolbox:latest
EOF
        # Set restrictive permissions
        chmod 600 "$config_file" 2>/dev/null || true
    fi
    
    print_success "Configuration created at $config_file"
    print_status "Run 'kodiak config' to set up your LLM provider"
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
            if docker image inspect ghcr.io/keethesh/kodiak-toolbox:latest >/dev/null 2>&1; then
                image_exists=true
            fi
            
            if [[ "$image_exists" == "false" ]] || [[ "$FORCE_INSTALL" == "true" ]]; then
                if [[ "$image_exists" == "true" ]]; then
                    print_status "Force install requested. Rebuilding Kodiak toolbox Docker image (this may take a while)..."
                else
                    print_status "Building Kodiak toolbox Docker image from scratch (this may take a while)..."
                fi
                
                # Check if we are in the source directory (either from git clone or manual download)
                local dockerfile_path=""
                if [[ -f "containers/Dockerfile" ]]; then
                    dockerfile_path="containers/Dockerfile"
                    build_context="containers"
                elif [[ -f "$INSTALL_DIR/source/containers/Dockerfile" ]]; then
                    dockerfile_path="$INSTALL_DIR/source/containers/Dockerfile"
                    build_context="$INSTALL_DIR/source/containers"
                fi
                
                if [[ -n "$dockerfile_path" ]]; then
                    if docker build -t ghcr.io/keethesh/kodiak-toolbox:latest -f "$dockerfile_path" "$build_context"; then
                        print_success "Kodiak toolbox Docker image built successfully"
                    else
                        print_warning "Failed to build Docker image locally"
                        print_status "You can build it later by running: docker build -t ghcr.io/keethesh/kodiak-toolbox:latest -f containers/Dockerfile containers/"
                    fi
                else
                    print_warning "Dockerfile not found. Could not build Kodiak toolbox image locally."
                    print_status "The agent will fallback to individual tool containers when scanning."
                fi
            else
                print_success "Kodiak toolbox image already exists locally. Skipping build."
                print_status "Use --force to rebuild the image."
            fi
        else
            print_warning "Docker is installed but the daemon is not running."
            print_status "Start Docker and run 'docker pull ghcr.io/keethesh/kodiak-toolbox:latest' or build it manually."
        fi
    else
        print_warning "Docker not found. Security tools will rely on local installations."
    fi
}

# Show next steps
show_next_steps() {
    echo
    print_success "🎉 Kodiak installation complete!"
    echo
    echo "📋 Quick Start:"
    echo "  1. Set up your LLM provider (interactive wizard):"
    echo "     ${CYAN}kodiak config${NC}"
    echo
    echo "  2. Initialize the database:"
    echo "     ${CYAN}kodiak init${NC}"
    echo
    echo "  3. Start scanning:"
    echo "     ${CYAN}kodiak --target ./my-app${NC}"
    echo
    echo "📦 What's Included:"
    echo "  • SQLite database (zero external dependencies)"
    echo "  • Security tools via Docker (nmap, nuclei, sqlmap, etc.)"
    echo "  • TUI interface for real-time monitoring"
    echo
    echo "📚 Commands:"
    echo "  ${CYAN}kodiak${NC}              Launch TUI interface"
    echo "  ${CYAN}kodiak config${NC}       Configure LLM and settings"
    echo "  ${CYAN}kodiak doctor${NC}       Check installation status"
    echo "  ${CYAN}kodiak --help${NC}       Show all commands"
    echo
    echo "🔗 Resources:"
    echo "  GitHub: https://github.com/keethesh/Kodiak"
    echo
    if [[ ! -f "$HOME/.local/bin/kodiak" ]]; then
        echo "⚠️  If 'kodiak' command is not found, restart your shell or run:"
        echo "  ${CYAN}source ~/.bashrc${NC}  # or ~/.zshrc"
    fi
}

# Cleanup on error
cleanup_on_error() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        print_error "Installation failed with exit code $exit_code"
        print_status "Cleaning up..."
        
        # Remove partial installation
        if [[ -d "$INSTALL_DIR/source" ]]; then
            rm -rf "$INSTALL_DIR/source"
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
                echo "Kodiak Installation Script"
                echo
                echo "Usage: $0 [options]"
                echo
                echo "Options:"
                echo "  --help, -h         Show this help message"
                echo "  --version VERSION  Install specific version/branch"
                echo "  --force, -f        Force reinstall even if already installed"
                echo "  --update, -u       Update Kodiak to the latest version via git pull or PyPI upgrade"
                echo "  --skip-docker      Skip building the Kodiak toolbox Docker image"
                echo "  --verbose, -v      Enable verbose output"
                echo
                echo "Environment variables:"
                echo "  KODIAK_VERSION     Set specific version to install (default: latest)"
                echo
                echo "Examples:"
                echo "  $0                 Install latest version"
                echo "  $0 --version v1.0  Install version v1.0"
                echo "  $0 --force         Force reinstall"
                echo
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
            --verbose|-v)
                set -x
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
    trap cleanup_on_error EXIT
    
    echo "🐻 Kodiak Installation Script"
    echo "=============================="
    echo
    
    # Handle command line arguments
    handle_arguments "$@"
    
    # Show installation info
    if [[ "$KODIAK_VERSION" != "latest" ]]; then
        print_status "Installing Kodiak version: $KODIAK_VERSION"
    else
        print_status "Installing latest Kodiak version"
    fi
    echo
    
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
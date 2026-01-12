#!/bin/bash
set -e

# Kodiak Installation Script
# Robust installation using UV (modern Python package manager)

KODIAK_VERSION="${KODIAK_VERSION:-latest}"
INSTALL_DIR="$HOME/.kodiak"
BIN_DIR="$HOME/.local/bin"
UV_VERSION="0.5.11"
FORCE_INSTALL="${FORCE_INSTALL:-false}"

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

# Install Kodiak
install_kodiak() {
    print_step "Installing Kodiak..."
    
    # Create directories
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BIN_DIR"
    
    # Check if already installed and handle accordingly
    if command_exists kodiak && [[ "$FORCE_INSTALL" != "true" ]]; then
        local current_version
        current_version=$(kodiak --version 2>/dev/null | grep -o 'v[0-9.]*' || echo "unknown")
        print_warning "Kodiak $current_version is already installed"
        print_status "Use --force to reinstall or run 'kodiak --help' to use existing installation"
        
        # Skip installation but still run verification
        return 0
    elif command_exists kodiak && [[ "$FORCE_INSTALL" == "true" ]]; then
        local current_version
        current_version=$(kodiak --version 2>/dev/null | grep -o 'v[0-9.]*' || echo "unknown")
        print_status "Force reinstalling Kodiak $current_version..."
        
        # Remove existing installation
        if command_exists uv; then
            uv tool uninstall kodiak-pentest 2>/dev/null || true
            uv tool uninstall kodiak 2>/dev/null || true
        fi
    fi
    
    # Try PyPI installation first
    print_status "Attempting PyPI installation..."
    if uv tool install kodiak-pentest[full] 2>/dev/null; then
        print_success "Kodiak installed from PyPI"
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
    
    # Clean up existing installation
    if [[ -d "$source_dir" ]]; then
        print_status "Removing existing source installation..."
        rm -rf "$source_dir"
    fi
    
    # Remove existing UV tool installation if it exists (try multiple package names)
    if command_exists uv; then
        print_status "Cleaning up any existing Kodiak installations..."
        uv tool uninstall kodiak-pentest 2>/dev/null || true
        uv tool uninstall kodiak 2>/dev/null || true
    fi
    
    # Also remove pipx installation if it exists
    if command_exists pipx; then
        pipx uninstall kodiak-pentest 2>/dev/null || true
        pipx uninstall kodiak 2>/dev/null || true
    fi
    
    # Remove any existing kodiak binary in ~/.local/bin
    if [[ -f "$BIN_DIR/kodiak" ]]; then
        print_status "Removing existing kodiak binary..."
        rm -f "$BIN_DIR/kodiak"
    fi
    
    # Clone repository
    print_status "Cloning Kodiak repository..."
    if ! git clone https://github.com/keethesh/Kodiak.git "$source_dir"; then
        print_error "Failed to clone repository"
        exit 1
    fi
    
    cd "$source_dir"
    
    # Checkout specific branch/version if specified
    if [[ "$KODIAK_VERSION" != "latest" ]]; then
        print_status "Checking out version $KODIAK_VERSION..."
        git checkout "$KODIAK_VERSION" || {
            print_warning "Version $KODIAK_VERSION not found, using main branch"
        }
    else
        # Use feature branch for now (until merged to main)
        if git show-ref --verify --quiet refs/remotes/origin/feature/tui-architecture; then
            print_status "Using feature/tui-architecture branch..."
            git checkout feature/tui-architecture
        fi
    fi
    
    # Install using UV with force flag to always overwrite
    print_status "Installing dependencies and Kodiak..."
    if ! uv tool install --force --editable ".[full]"; then
        print_error "Failed to install Kodiak from source"
        exit 1
    fi
    
    print_success "Kodiak installed from source"
}

# Setup configuration
setup_configuration() {
    print_step "Setting up configuration..."
    
    # Create config directory
    mkdir -p "$INSTALL_DIR"
    
    # Create minimal docker-compose.yml for database
    local compose_file="$INSTALL_DIR/docker-compose.yml"
    if [[ ! -f "$compose_file" ]]; then
        print_status "Creating Docker Compose configuration..."
        cat > "$compose_file" << 'EOF'
services:
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

volumes:
  kodiak_postgres_data:
EOF
    fi
    
    # Create example environment file
    local env_example="$INSTALL_DIR/.env.example"
    if [[ ! -f "$env_example" ]]; then
        print_status "Creating environment configuration template..."
        cat > "$env_example" << 'EOF'
# Kodiak Configuration Template
# Copy to .env and customize for your environment

# LLM Configuration (choose one)
# Google Gemini (Recommended)
KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
GOOGLE_API_KEY=your_google_api_key_here

# OpenAI GPT
# KODIAK_LLM_MODEL=openai/gpt-4
# OPENAI_API_KEY=your_openai_api_key_here

# Anthropic Claude
# KODIAK_LLM_MODEL=anthropic/claude-3-5-sonnet-20241022
# ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Local Ollama (no API key required)
# KODIAK_LLM_MODEL=ollama/llama3.1:70b

# Database Configuration
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=kodiak_db
POSTGRES_USER=kodiak
POSTGRES_PASSWORD=kodiak_password

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
EOF
    fi
    
    print_success "Configuration files created in $INSTALL_DIR"
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

# Show next steps
show_next_steps() {
    echo
    print_success "🎉 Kodiak installation complete!"
    echo
    echo "📋 Next steps:"
    echo "  1. Configure your LLM provider:"
    echo "     ${CYAN}kodiak config${NC}"
    echo
    echo "  2. Initialize the database (optional):"
    echo "     ${CYAN}kodiak init${NC}"
    echo
    echo "  3. Launch Kodiak:"
    echo "     ${CYAN}kodiak${NC}"
    echo
    echo "  4. Or scan a target directly:"
    echo "     ${CYAN}kodiak --target ./my-app${NC}"
    echo
    echo "📚 Additional commands:"
    echo "  ${CYAN}kodiak --help${NC}        Show all available commands"
    echo "  ${CYAN}kodiak doctor${NC}        Check installation and dependencies"
    echo "  ${CYAN}kodiak api${NC}           Start API server mode"
    echo
    echo "📁 Configuration files:"
    echo "  ${INSTALL_DIR}/.env.example    Environment configuration template"
    echo "  ${INSTALL_DIR}/docker-compose.yml    Database setup"
    echo
    echo "🔗 Resources:"
    echo "  GitHub: https://github.com/keethesh/Kodiak"
    echo "  Documentation: https://github.com/keethesh/Kodiak/blob/main/README.md"
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
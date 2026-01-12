#!/bin/bash
set -e

# Kodiak Installation Script
# Similar to Strix's installation approach

KODIAK_VERSION="latest"
INSTALL_DIR="$HOME/.kodiak"
BIN_DIR="$HOME/.local/bin"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

check_requirements() {
    print_status "Checking system requirements..."
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    REQUIRED_VERSION="3.11"
    
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        print_error "Python 3.11+ is required (found Python $PYTHON_VERSION)"
        print_status "Please upgrade Python and try again"
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION found"
    
    # Check pip
    if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
        print_error "pip is required but not installed"
        exit 1
    fi
    
    # Check Docker (optional but recommended)
    if command -v docker &> /dev/null; then
        print_success "Docker found (recommended for full functionality)"
    else
        print_warning "Docker not found - some features may be limited"
    fi
}

install_pipx() {
    if command -v pipx &> /dev/null; then
        print_success "pipx already installed"
        return
    fi
    
    print_status "Installing pipx..."
    
    if command -v pip3 &> /dev/null; then
        pip3 install --user pipx
    else
        pip install --user pipx
    fi
    
    # Add pipx to PATH if not already there
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
        export PATH="$HOME/.local/bin:$PATH"
    fi
    
    print_success "pipx installed successfully"
}

install_kodiak() {
    print_status "Installing Kodiak..."
    
    # Create directories
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$BIN_DIR"
    
    # Install via pipx for isolated environment
    if command -v pipx &> /dev/null; then
        print_status "Installing Kodiak via pipx..."
        pipx install kodiak-pentest[full] || {
            print_warning "PyPI package not available, installing from source..."
            install_from_source
        }
    else
        print_status "Installing Kodiak via pip..."
        pip3 install --user kodiak-pentest[full] || {
            print_warning "PyPI package not available, installing from source..."
            install_from_source
        }
    fi
}

install_from_source() {
    print_status "Installing Kodiak from source..."
    
    # Check if we're already in the Kodiak directory
    if [[ -f "pyproject.toml" ]] && grep -q "kodiak-pentest" pyproject.toml; then
        print_status "Installing from current directory..."
        pip3 install --user -e .[full]
    else
        # Clone repository
        if command -v git &> /dev/null; then
            print_status "Cloning Kodiak repository..."
            cd "$INSTALL_DIR"
            git clone https://github.com/keethesh/Kodiak.git source
            cd source
            pip3 install --user -e .[full]
        else
            print_error "Git is required to install from source"
            exit 1
        fi
    fi
}

setup_configuration() {
    print_status "Setting up initial configuration..."
    
    # Create config directory
    mkdir -p "$INSTALL_DIR"
    
    # Create minimal docker-compose.yml for database
    cat > "$INSTALL_DIR/docker-compose.yml" << 'EOF'
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
    
    print_success "Configuration files created in $INSTALL_DIR"
}

verify_installation() {
    print_status "Verifying installation..."
    
    if command -v kodiak &> /dev/null; then
        INSTALLED_VERSION=$(kodiak --version 2>/dev/null | grep -o 'v[0-9.]*' || echo "unknown")
        print_success "Kodiak $INSTALLED_VERSION installed successfully!"
        
        print_status "Running installation check..."
        kodiak doctor
        
        return 0
    else
        print_error "Kodiak command not found in PATH"
        print_status "You may need to restart your shell or run:"
        print_status "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        return 1
    fi
}

show_next_steps() {
    echo
    print_success "🎉 Kodiak installation complete!"
    echo
    echo "Next steps:"
    echo "  1. Configure your LLM provider:"
    echo "     kodiak config"
    echo
    echo "  2. Initialize the database:"
    echo "     kodiak init"
    echo
    echo "  3. Launch Kodiak:"
    echo "     kodiak"
    echo
    echo "  4. Or scan a target directly:"
    echo "     kodiak --target ./my-app"
    echo
    echo "For help and documentation:"
    echo "  kodiak --help"
    echo "  kodiak doctor"
    echo
    echo "Join our community:"
    echo "  GitHub: https://github.com/keethesh/Kodiak"
    echo
}

main() {
    echo "🐻 Kodiak Installation Script"
    echo "=============================="
    echo
    
    check_requirements
    install_pipx
    install_kodiak
    setup_configuration
    
    if verify_installation; then
        show_next_steps
    else
        print_error "Installation verification failed"
        print_status "Please check the error messages above and try again"
        exit 1
    fi
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "Kodiak Installation Script"
        echo
        echo "Usage: $0 [options]"
        echo
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --version      Install specific version"
        echo
        echo "Environment variables:"
        echo "  KODIAK_VERSION Set specific version to install (default: latest)"
        echo
        exit 0
        ;;
    --version)
        if [[ -n "${2:-}" ]]; then
            KODIAK_VERSION="$2"
            print_status "Installing Kodiak version $KODIAK_VERSION"
        else
            print_error "--version requires a version number"
            exit 1
        fi
        ;;
esac

# Run main installation
main "$@"
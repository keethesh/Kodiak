.PHONY: help install dev-install format lint type-check test test-cov clean pre-commit setup-dev build publish

help:
	@echo "Available commands:"
	@echo "  setup-dev     - Install all development dependencies"
	@echo "  install       - Install production dependencies"
	@echo "  dev-install   - Install development dependencies"
	@echo ""
	@echo "Code Quality:"
	@echo "  format        - Format code with black and isort"
	@echo "  lint          - Lint code with ruff"
	@echo "  type-check    - Run type checking with mypy"
	@echo "  check-all     - Run all code quality checks"
	@echo ""
	@echo "Testing:"
	@echo "  test          - Run tests with pytest"
	@echo "  test-cov      - Run tests with coverage reporting"
	@echo ""
	@echo "Development:"
	@echo "  clean         - Clean up cache files and artifacts"
	@echo "  build         - Build package for distribution"
	@echo "  publish       - Publish to PyPI (requires credentials)"

install:
	poetry install --only=main

dev-install:
	poetry install --with=dev

setup-dev: dev-install
	@echo "✅ Development environment setup complete!"
	@echo "Run 'make check-all' to verify everything works correctly."

format:
	@echo "🎨 Formatting code with black and isort..."
	poetry run black kodiak/ tests/
	poetry run isort kodiak/ tests/
	@echo "✅ Code formatting complete!"

lint:
	@echo "🔍 Linting code with ruff..."
	poetry run ruff check kodiak/ tests/ --fix
	@echo "✅ Linting complete!"

type-check:
	@echo "🔍 Type checking with mypy..."
	poetry run mypy kodiak/
	@echo "✅ Type checking complete!"

check-all: format lint type-check
	@echo "✅ All code quality checks passed!"

test:
	@echo "🧪 Running tests..."
	poetry run pytest -v
	@echo "✅ Tests complete!"

test-cov:
	@echo "🧪 Running tests with coverage..."
	poetry run pytest -v --cov=kodiak --cov-report=term-missing --cov-report=html
	@echo "✅ Tests with coverage complete!"
	@echo "📊 Coverage report generated in htmlcov/"

clean:
	@echo "🧹 Cleaning up cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info/
	@echo "✅ Cleanup complete!"

build: clean
	@echo "📦 Building package..."
	poetry build
	@echo "✅ Package built successfully!"
	@echo "📁 Distribution files in dist/"

publish: build
	@echo "🚀 Publishing to PyPI..."
	poetry publish
	@echo "✅ Package published successfully!"

# Docker commands
docker-build:
	@echo "🐳 Building Docker image..."
	docker-compose build kodiak
	@echo "✅ Docker image built!"

docker-up:
	@echo "🐳 Starting services..."
	docker-compose up -d
	@echo "✅ Services started!"

docker-down:
	@echo "🐳 Stopping services..."
	docker-compose down
	@echo "✅ Services stopped!"

docker-logs:
	docker-compose logs -f kodiak

# Installation commands
install-local:
	@echo "📦 Installing Kodiak locally..."
	pip install -e .[full]
	@echo "✅ Kodiak installed locally!"

install-user:
	@echo "📦 Installing Kodiak for current user..."
	pip install --user .[full]
	@echo "✅ Kodiak installed for user!"

# Development workflow
dev: format lint type-check test
	@echo "✅ Development cycle complete!"
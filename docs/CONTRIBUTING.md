# Contributing to Kodiak

We welcome contributions to Kodiak! Since this is a security tool, please follow our guidelines strictly.

## Development Setup

### Backend
1. **Prerequisites**: Python 3.11+, Poetry, Docker, PostgreSQL.
2. **Setup**:
   ```bash
   cd backend
   poetry install
   cp .env.example .env
   # Start DB
   docker run --name kodiak-db -e POSTGRES_PASSWORD=kodiak -p 5432:5432 -d postgres
   poetry run uvicorn main:app --reload
   ```

### Frontend
1. **Prerequisites**: Node.js 20+.
2. **Setup**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Code Standards
- **Python**: We use `ruff` for linting and formatting. Run `ruff check .` before committing.
- **Type Hints**: Strict type checking is enforced. Pydantic models must be used for all data structures.
- **Safety**: NEVER commit API keys. Use `.env` files.

## Adding New Tools
1. Create a `Tool` class in `backend/kodiak/core/tools/`.
2. Register it in `backend/kodiak/core/tools/inventory.py`.
3. Ensure it returns a Pydantic model, not raw text.

## Pull Requests
- PRs must pass all tests (`pytest`).
- Semantic Commit Messages (e.g., `feat: add wapiti support`, `fix: synchronization bug`).

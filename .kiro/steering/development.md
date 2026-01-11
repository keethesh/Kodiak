---
inclusion: manual
---

# Kodiak Development Guide

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)
- OpenAI API key or other LLM provider

### Environment Setup
```bash
# Clone and enter directory
git clone <repository-url>
cd kodiak

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# Start full stack with Docker
docker-compose up --build
```

### Local Development Setup
```bash
# Backend setup
cd backend
poetry install
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend setup (in new terminal)
cd frontend
npm install
npm run dev

# Database (in new terminal)
docker-compose up db
```

## Development Workflow

### Adding New Security Tools
1. Create tool class in `backend/kodiak/core/tools/definitions/`
2. Inherit from `KodiakTool` base class
3. Implement required methods: `name`, `description`, `parameters_schema`, `_execute`
4. Register in `backend/kodiak/core/tools/inventory.py`
5. Test with implementation test suite

### Adding New Skills
1. Create YAML file in appropriate category under `backend/kodiak/skills/definitions/`
2. Follow the skill specification format
3. Include techniques, examples, validation methods
4. Test skill loading with skills API endpoints

### Database Changes
```bash
# Generate migration (when Alembic is set up)
cd backend
poetry run alembic revision --autogenerate -m "Description"

# Apply migrations
poetry run alembic upgrade head
```

### Testing
```bash
# Run implementation tests
cd backend
python test_implementation.py

# Run unit tests (when implemented)
poetry run pytest

# Frontend tests
cd frontend
npm test
```

## Architecture Guidelines

### Tool Development
- All tools must inherit from `KodiakTool`
- Use Pydantic models for argument validation
- Return structured `ToolResult` objects
- Include comprehensive error handling
- Support Hive Mind caching through base class

### Skills Development
- Use YAML format for skill definitions
- Include practical examples with payloads
- Provide validation methods for findings
- Reference authoritative sources
- Keep knowledge content focused and actionable

### API Development
- Follow FastAPI patterns with async/await
- Use dependency injection for database sessions
- Implement proper error handling and status codes
- Include comprehensive OpenAPI documentation
- Support WebSocket for real-time features

### Frontend Development
- Use Next.js App Router with Server/Client components
- Implement real-time updates via WebSocket hooks
- Follow component composition patterns
- Use TypeScript for type safety
- Implement responsive design with TailwindCSS

## Common Issues and Solutions

### Docker Build Issues
```bash
# If poetry.lock is corrupted
cd backend
rm poetry.lock
poetry lock

# If Docker build fails
docker-compose down
docker system prune -f
docker-compose up --build
```

### Database Connection Issues
```bash
# Reset database
docker-compose down -v
docker-compose up db
# Wait for database to be ready, then start backend
```

### Skills Loading Issues
```bash
# Verify skills directory structure
ls -la backend/kodiak/skills/definitions/

# Test skills loading
curl http://localhost:8000/api/v1/skills/
```

### Tool Execution Issues
```bash
# Verify tools are installed in container
docker-compose exec backend which nmap
docker-compose exec backend which nuclei

# Test tool execution
curl -X POST http://localhost:8000/api/v1/tools/test
```

## Code Quality

### Python Code Standards
```bash
cd backend
poetry run black kodiak/
poetry run isort kodiak/
poetry run ruff check kodiak/
poetry run mypy kodiak/
```

### TypeScript Code Standards
```bash
cd frontend
npm run lint
npm run type-check
```

## Debugging

### Backend Debugging
- Use `loguru` for structured logging
- Enable debug mode in FastAPI for detailed errors
- Use `pdb` or IDE debugger for step-through debugging
- Monitor WebSocket connections in browser dev tools

### Frontend Debugging
- Use React Developer Tools
- Monitor WebSocket messages in Network tab
- Use browser console for JavaScript errors
- Enable Next.js debug mode for detailed routing info

### Database Debugging
```bash
# Connect to database
docker-compose exec db psql -U kodiak -d kodiak_db

# View tables
\dt

# Query data
SELECT * FROM project LIMIT 5;
```

## Performance Optimization

### Backend Performance
- Use async/await for all I/O operations
- Implement database connection pooling
- Cache frequently accessed data
- Use background tasks for long-running operations

### Frontend Performance
- Implement lazy loading for heavy components
- Use React.memo for expensive computations
- Optimize WebSocket event handling
- Implement proper loading states

### Database Performance
- Add indexes for frequently queried fields
- Use efficient queries with proper joins
- Implement pagination for large datasets
- Monitor query performance with EXPLAIN

## Security Considerations

### Development Security
- Never commit API keys or secrets
- Use environment variables for configuration
- Validate all user inputs
- Implement proper authentication and authorization

### Tool Security
- Validate tool parameters before execution
- Implement safety checks for dangerous operations
- Use approval workflows for high-risk actions
- Log all tool executions for audit trail

## Deployment

### Development Deployment
```bash
# Full stack with Docker Compose
docker-compose up --build

# Individual services
docker-compose up db
docker-compose up backend
docker-compose up frontend
```

### Production Considerations
- Use production-ready database configuration
- Implement proper logging and monitoring
- Set up health checks and readiness probes
- Configure proper resource limits
- Use secrets management for sensitive data

This guide provides the essential information for developing and maintaining Kodiak effectively.
# AI Drug Discovery Platform

AI-powered drug discovery platform for molecular analysis and predictions.

## Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL 16 (via Docker)
- Redis 7 (via Docker)

### Quick Start

1. **Start infrastructure:**
   ```bash
   docker-compose up -d postgres redis
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # or
   .venv\Scripts\activate     # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Set up environment:**
   ```bash
   cp .env.example .env
   ```

5. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Start the API:**
   ```bash
   uvicorn apps.api.main:app --reload
   ```

7. **Access the API:**
   - API: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## Development

### Running Tests

```bash
pytest tests/ -v
```

With coverage:
```bash
pytest tests/ --cov=apps --cov=packages --cov=db --cov-report=html
```

### Pre-commit Hooks

Install hooks:
```bash
pre-commit install
```

Run on all files:
```bash
pre-commit run --all-files
```

### Code Quality

Format code:
```bash
black .
```

Lint:
```bash
ruff check .
```

Type check:
```bash
mypy apps packages db
```

## Project Structure

```
ai-drug-discovery/
├── apps/api/           # FastAPI application
├── packages/           # Shared packages (ml, chemistry)
├── db/                 # Database models and sessions
├── alembic/            # Database migrations
├── tests/              # Test files
├── docker-compose.yml  # Docker services
└── pyproject.toml      # Project configuration
```

## API Endpoints

- `GET /health` - Basic health check
- `GET /health/ready` - Readiness check (DB + Redis)
- `GET /api/v1/molecules` - Molecules API (placeholder)
- `GET /api/v1/targets` - Targets API (placeholder)
- `GET /api/v1/predictions` - Predictions API (placeholder)

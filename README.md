### Scripulya AI

Scripulya AI is a FastAPI-based backend service that generates and manages scripts, scenes, and characters with the help of Google's Gemini generative AI. The service is structured following Clean / Hexagonal architecture principles (domain → application → infrastructure → controllers), uses PostgreSQL for persistence, and is fully containerised with Docker Compose for local development.

---

### Project Structure

```
scripulya_ai/
├── src/                       # Application source code
│   ├── app.py                 # FastAPI application factory
│   ├── main.py                # Entry point (CLI via click, runs uvicorn)
│   ├── conf.py                # Settings (pydantic-settings)
│   ├── domain/                # Domain layer
│   │   └── models.py          # Core business entities (scripts, scenes, characters, users)
│   ├── application/           # Application/use-case layer
│   │   └── auth/              # JWT auth service and related use cases
│   ├── infrastructure/        # External integrations & frameworks
│   │   └── web/               # Web middlewares (correlation id, error handling, etc.)
│   └── controllers/           # HTTP controllers (FastAPI routers)
│       └── api/v1/            # Versioned REST API (scenes, characters, scripts, auth…)
├── tests/
│   ├── unit/                  # Unit tests (pure, fast)
│   └── e2e/                   # End-to-end API tests
├── scripts/
│   └── init.sql               # DB bootstrap script (mounted into postgres container)
├── google_api_mock/           # Local mock for Google Generative Language API
├── docs/                      # Project documentation
├── Dockerfile                 # Multi-stage image for the app
├── docker-compose.yml         # Local stack: app + postgres + mock-google-api
├── requirements.txt           # Runtime dependencies
├── requirements-mock.txt      # Dependencies for the Google API mock
├── pyproject.toml             # Project metadata + Ruff config + dev dependencies
├── pytest.ini                 # Pytest configuration (markers, asyncio, testpaths)
├── .pre-commit-config.yaml    # Pre-commit hooks (Ruff lint + format)
├── openapi.json               # Generated OpenAPI schema
├── provision.sh               # Provisioning script (Docker + Python 3.13 on Ubuntu)
└── Vagrantfile                # Optional VM setup
```

#### Module overview

- `src/domain` — Pure business models and rules. No framework or I/O dependencies.
- `src/application` — Use cases / services that orchestrate domain logic. Includes `auth/jwt_service.py` for token issuing and verification.
- `src/infrastructure` — Adapters: database (SQLAlchemy + asyncpg), web middlewares, external HTTP clients (Gemini), etc.
- `src/controllers/api/v1` — FastAPI routers exposing the public REST API (`/scenes`, `/characters`, `/scripts`, `/auth`, …).
- `src/app.py` / `src/main.py` — Wire everything together via the `dishka` DI container and launch uvicorn.
- `google_api_mock/` — A standalone container that impersonates `generativelanguage.googleapis.com` so the app can be developed and tested offline.
- `tests/unit` and `tests/e2e` — Test suites; markers `unit` and `e2e` are registered in `pytest.ini`.

---

### Local Deployment

#### Prerequisites

- Docker and Docker Compose plugin
- Python 3.13 (only needed for running tests/linters outside Docker)
- `git`

A one-shot provisioner for a fresh Ubuntu host is available in `provision.sh` (installs Docker, Python 3.13, creates a virtualenv).

#### 1. Clone and configure

```bash
git clone <repo-url> scripulya_ai
cd scripulya_ai
```

Create / edit `.env` in the project root:

You can enter a fake API key here, 

```dotenv
GEMINI_API_KEY=your_real_or_fake_key
```

For fully offline development, any value is fine — the `mock-google-api` service intercepts the Gemini host via a Docker network alias (`generativelanguage.googleapis.com`).

#### 2. Run with Docker Compose (recommended)

```bash
docker compose up --build
```

This starts three services:

- `app` — FastAPI app on `http://localhost:8000`
- `postgres` — PostgreSQL 15 on `localhost:5432` (`user` / `password` / `dbname`), initialised from `scripts/init.sql`
- `mock-google-api` — Gemini API stub

Healthcheck (defined in the `Dockerfile`) probes `http://localhost:8000` every 30s.

Stop the stack:

```bash
docker compose down          # keep volumes
docker compose down -v       # also drop postgres data
```

#### 3. Run without Docker (optional)

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Make sure a Postgres instance matching docker-compose.yml is reachable
python -m src.main --http
```

The app listens on port `8000` and serves OpenAPI docs at `http://localhost:8000/docs`.

---

### Linters & Formatting

The project uses [Ruff](https://docs.astral.sh/ruff/) (lint + format) and [pre-commit](https://pre-commit.com/). Versions are pinned in `pyproject.toml` (`[dependency-groups].dev`) and `.pre-commit-config.yaml`.

#### Install

```bash
source .venv/bin/activate
pip install pre-commit ruff
# or, using uv / dependency groups:
#   uv sync --group dev

pre-commit install          # installs the git hook
```

#### Usage

```bash
# Lint
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Format (line length 120, double quotes, tab indent — see pyproject.toml)
ruff format .

# Run all hooks on the whole repo
pre-commit run --all-files
```

The hook also runs automatically on `git commit`.

---

### Running Tests

Pytest configuration lives in `pytest.ini`:

- `testpaths = tests`
- `asyncio_mode = auto`
- Registered markers: `unit`, `e2e`

#### Install test dependencies

```bash
source .venv/bin/activate
pip install -r requirements.txt   # pytest + pytest-asyncio are part of deps
```

#### Commands

```bash
# All tests
pytest

# Only unit tests
pytest -m unit

# Only end-to-end tests (require the full Docker stack to be up)
docker compose up -d
pytest -m e2e

# A single file / test
pytest tests/e2e/test_characters_api.py
pytest tests/e2e/test_characters_api.py::test_create_character
```

#### Running tests inside the container

```bash
docker compose run --rm app pytest -m unit
```

---

### Useful Endpoints

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI schema (also committed as `openapi.json`): `http://localhost:8000/openapi.json`

---

### CI

GitHub Actions workflows live in `.github/workflows/` and typically run Ruff and the pytest suite on push / pull request — keep the same commands listed above green locally before pushing.

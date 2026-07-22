# DreamEscape AI Backend

Backend service for an AI-powered roleplay platform.

DreamEscape allows users to enter interactive fictional scenes, choose the character they want to play, and communicate with AI-controlled characters. The backend stores the roleplay world, builds the prompt for each conversation, sends generation requests to an external LLM agent, and delivers generated responses to clients in real time.

This repository contains the **backend API and roleplay orchestration logic**. It is not a standalone chatbot UI and it does not contain the mobile application or the external LLM worker.

## What the service does

A typical user flow looks like this:

1. A user authenticates and receives a JWT access token.
2. The user browses public roleplay scenes and characters or creates private ones.
3. The user starts a chat inside a selected scene.
4. The user chooses a character representing their persona in that chat.
5. The client sends a message to the backend.
6. The backend builds an LLM system prompt from:
   - the global roleplay instructions;
   - the selected scene and its environment;
   - the AI-controlled characters attached to the scene;
   - the character selected as the user's persona;
   - the previous chat messages;
   - the model and generation settings selected for the chat.
7. The generation request is delegated to `scripulya_agent` through RabbitMQ.
8. The generated response is stored in PostgreSQL and streamed to the client through Server-Sent Events.

In short, this service is the application layer between a roleplay client, persistent world data, and one or more LLM providers.

## Core concepts

### Scene

A scene defines the world in which a roleplay conversation takes place.

It contains:

- a title and public description;
- a background prompt describing the environment;
- an initial message shown when a chat starts;
- a list of characters participating in the scene;
- visibility settings;
- associated media assets.

Examples include a fantasy tavern, a space station, a magical forest, or any other interactive setting.

### Character

A character defines a personality that can participate in a scene.

Each character has:

- a name;
- a system prompt describing personality and behavior;
- an owner;
- public or private visibility;
- optional images.

Characters attached to a scene are included in the LLM context and act as inhabitants of that world.

### User persona

A user can select a character as their own persona for a particular chat.

The prompt explicitly distinguishes the user's persona from AI-controlled characters. This lets the model narrate events from the user's perspective and describe how the environment and other characters react to them.

### Chat

A chat is a persistent roleplay session connected to:

- one authenticated user;
- one scene;
- one user persona;
- generation settings;
- a message history.

### Message generation

Message generation is asynchronous.

The API accepts a user message and returns `202 Accepted`. For real LLM models, the backend publishes a generation request to RabbitMQ. A separate `scripulya_agent` service communicates with the selected provider and sends the result back.

The backend then:

1. persists the model response;
2. updates the message status;
3. publishes the response to the chat's Server-Sent Events stream.

A built-in `testing_mock` model can be used for local development without an external LLM provider.

## Main features

- JWT-based authentication and authorization
- Public and private scenes
- Public and private characters
- User-defined roleplay personas
- Persistent chats and message history
- Per-chat model and generation settings
- Dynamic prompt assembly from scenes, characters, personas, and history
- Asynchronous LLM generation through RabbitMQ
- Real-time chat updates through Server-Sent Events
- PostgreSQL persistence through async SQLAlchemy
- Character and scene search
- Likes and bookmarks
- Character-to-scene assignment
- Image upload and media metadata management
- MinIO/S3-compatible object storage
- Redis-based generation heartbeat monitoring
- Failed and stalled generation detection
- Correlation IDs and structured request logging
- Unit and end-to-end test suites
- Offline mock implementations for local development

## Architecture

The project follows a ports-and-adapters style architecture:

```text
Mobile or web client
        |
        | HTTP + Server-Sent Events
        v
FastAPI controllers
        |
        v
Application services
        |
        +------------------+------------------+------------------+
        |                  |                  |                  |
        v                  v                  v                  v
   PostgreSQL          RabbitMQ            MinIO              Redis
   application         LLM request         media              generation
   state               and result queues   storage            heartbeat
                           |
                           v
                    scripulya_agent
                           |
                           v
                     LLM providers
```

### Generation flow

```text
POST /api/v1/messages
        |
        v
Validate chat ownership and selected persona
        |
        v
Load scene, characters, chat settings, and message history
        |
        v
Build the complete roleplay system prompt
        |
        v
Persist the user's message
        |
        v
Publish an LLM request to RabbitMQ
        |
        v
scripulya_agent calls the selected LLM provider
        |
        v
Backend consumes the generation result
        |
        +--> Persist the model message
        |
        +--> Push the message to the client's SSE connection
```

The backend does not need to know the implementation details of every LLM provider. Provider communication is delegated to the separate agent service, while this repository remains responsible for roleplay rules, persistence, authorization, prompt construction, and client-facing APIs.

## Technology stack

- **Python 3.13**
- **FastAPI** and Uvicorn
- **Pydantic** and `pydantic-settings`
- **SQLAlchemy 2** with `asyncpg`
- **PostgreSQL 15**
- **FastStream** and RabbitMQ
- **Redis**
- **MinIO / S3-compatible storage**
- **Dishka** dependency injection
- **PyJWT**
- **pytest** and `pytest-asyncio`
- **Ruff**
- **Docker Compose**

## Repository structure

```text
src/
├── app.py                       FastAPI application and lifecycle
├── main.py                      HTTP server entry point
├── conf.py                      Environment-based configuration
│
├── domain/
│   └── models.py                Core domain entities
│
├── application/
│   ├── auth/                    Authentication and JWT services
│   ├── character/               Character use cases
│   ├── chats/                   Chats, prompts, and LLM orchestration
│   ├── events/                  Server-Sent Events handling
│   ├── media/                   Media use cases
│   ├── message/                 Message persistence and lifecycle
│   ├── scene/                   Scene use cases
│   ├── user/                    User use cases
│   ├── llm_watchdog.py          Stalled-generation detection
│   └── ports.py                 Application interfaces and shared DTOs
│
├── controllers/
│   ├── api/v1/                  Public REST API
│   └── rabbit/v1/               RabbitMQ result consumers
│
└── infrastructure/
    ├── database/                SQLAlchemy models and unit of work
    ├── gateways/                PostgreSQL, RabbitMQ, Redis, and MinIO adapters
    ├── logging/                 Logging configuration
    ├── web/                     Middleware and exception handlers
    └── di.py                    Dependency injection configuration

tests/
├── unit/                        Isolated service and gateway tests
└── e2e/                         HTTP and RabbitMQ integration tests

scripts/
├── init.sql                     PostgreSQL schema and development data
└── seed_minio_media.py          Development media seeding

build/
└── Dockerfile                   Application container

deploy/
└── docker-compose.yml           Local development stack

google_api_mock/                 Legacy/local provider API mock
docs/                            Flow diagrams and debugging notes
```

## API overview

The REST API is versioned under `/api/v1`.

| Area | Purpose |
|---|---|
| `/api/v1/auth` | Authentication and token issuing |
| `/api/v1/users` | User lookup and user operations |
| `/api/v1/scenes` | Scene creation, discovery, likes, bookmarks, and character assignment |
| `/api/v1/characters` | Character creation, discovery, likes, and bookmarks |
| `/api/v1/chats` | Persistent roleplay sessions and persona selection |
| `/api/v1/messages` | Message history and LLM generation requests |
| `/api/v1/chats/{chat_id}/events` | Real-time model responses through SSE |
| `/api/v1/chat-settings` | Model and generation settings |
| `/api/v1/media` | Image upload and media access |
| `/health` | Service health information |

After starting the application, interactive API documentation is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI schema: `http://localhost:8000/openapi.json`

## Local development

### Requirements

For the Docker-based setup:

- Git
- Docker
- Docker Compose

For running the application directly:

- Python 3.13
- PostgreSQL
- RabbitMQ when the external LLM agent is enabled
- Redis for generation heartbeat monitoring
- MinIO or another S3-compatible object store for media operations

### Clone the repository

```bash
git clone https://github.com/scripulya-ai-roleplay/dreamescape_ai.git
cd dreamescape_ai
```

### Configure the environment

Create a local environment file:

```bash
cp .env.example .env
```

Important settings include:

```dotenv
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/dbname

JWT_SECRET_KEY=change-this-in-production
JWT_ALGORITHM=HS256

LLM_AGENT_ENABLED=false
RABBIT_URL=amqp://guest:guest@rabbitmq:5672/
LLM_AGENT_REQUEST_QUEUE=llm.agent.request
LLM_AGENT_RESULT_QUEUE=llm.agent.result

REDIS_URL=redis://redis:6379/0

MINIO_INTERNAL_ENDPOINT=minio:9000
MINIO_PUBLIC_ENDPOINT=localhost:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
```

Never use the example credentials or JWT secret in production.

### Start with Docker Compose

```bash
docker compose -f deploy/docker-compose.yml up --build
```

The bundled Compose configuration starts:

- the FastAPI backend on port `8000`;
- PostgreSQL on port `5432`;
- RabbitMQ on port `5672`;
- the RabbitMQ management UI on port `15672`;
- a local provider API mock.

The default Compose configuration sets:

```dotenv
LLM_AGENT_ENABLED=false
```

This means the backend can be exercised without running `scripulya_agent`. Use the `testing_mock` model for fully offline message generation.

Media upload endpoints require a reachable MinIO/S3-compatible service. Production-like asynchronous generation additionally requires Redis and a running `scripulya_agent` connected to the same RabbitMQ broker.

Stop the stack with:

```bash
docker compose -f deploy/docker-compose.yml down
```

Remove the PostgreSQL development volume as well:

```bash
docker compose -f deploy/docker-compose.yml down -v
```

## Running without Docker

Create a virtual environment and install the locked dependencies:

```bash
python3.13 -m venv .venv
source .venv/bin/activate

pip install uv==0.10.4
uv sync --frozen
```

Make sure the services referenced by `.env` are reachable, then start the API:

```bash
python -m src.main --http
```

The server listens on `http://localhost:8000` by default.

## Using the external LLM agent

This backend does not call production LLM providers directly.

To enable real asynchronous generation:

1. Start RabbitMQ.
2. Start Redis.
3. Start `scripulya_agent`.
4. Configure the agent and this backend to use the same RabbitMQ queues.
5. Set:

```dotenv
LLM_AGENT_ENABLED=true
```

The backend publishes requests to:

```text
llm.agent.request
```

It consumes results from:

```text
llm.agent.result
```

The agent is responsible for selecting and calling the configured LLM provider. The backend is responsible for building the roleplay context, storing the conversation, enforcing access rules, and delivering results to the client.

## Tests

Run the complete test suite:

```bash
pytest
```

Run only unit tests:

```bash
pytest -m unit
```

Run only end-to-end tests:

```bash
pytest -m e2e
```

Run an individual test module:

```bash
pytest tests/e2e/test_messages_api.py
```

The test suite covers authentication, users, scenes, characters, chats, messages, media, prompt construction, authorization, RabbitMQ integration, Server-Sent Events, Redis heartbeats, and stalled-generation handling.

## Code quality

Run Ruff checks:

```bash
ruff check .
```

Apply safe automatic fixes:

```bash
ruff check --fix .
```

Format the project:

```bash
ruff format .
```

Run all configured pre-commit hooks:

```bash
pre-commit run --all-files
```

## What this repository demonstrates

This is an application backend rather than a collection of isolated AI experiments.

Its main engineering concerns are:

- modelling an interactive roleplay domain;
- separating business logic from framework and infrastructure code;
- secure ownership and visibility rules for user-generated content;
- dynamic prompt construction from persistent domain entities;
- asynchronous communication between the API and LLM workers;
- real-time response delivery;
- reliable handling of failed or stalled generations;
- testable adapters for databases, queues, object storage, and LLM services.

## Project status

The service is under active development.

The repository currently focuses on the backend API and infrastructure required by a roleplay client. The client application and the external `scripulya_agent` worker are separate components.

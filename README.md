# VoxGuard — Verifiable Digital Election System

> **Every Vote. Protected. Verifiable.**

A microservices-based digital election platform with cryptographic audit trails, identity-vote separation, and three-way result reconciliation.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────────────┐
│  React/Vite │────▶│ API Gateway  │────▶│  6 Backend Services      │
│  Frontend   │     │   :8000      │     │  (FastAPI/Python)        │
│   :5173     │     └──────────────┘     └──────────────────────────┘
└─────────────┘            │                        │
                           │              ┌─────────┴─────────┐
                      ┌────┴────┐    ┌────┴────┐    ┌────────┴───────┐
                      │  Redis  │    │Postgres │    │   RabbitMQ     │
                      │  :6379  │    │  :5432  │    │  :5672/:15672  │
                      └─────────┘    └─────────┘    └────────────────┘
```

| Service | Port | Database | Responsibility |
|---------|------|----------|----------------|
| `api-gateway` | 8000 | — | Request routing, correlation IDs, timeout |
| `auth-service` | 8001 | `auth_db` | Authentication, JWT, sessions |
| `voter-service` | 8002 | `voter_db` | Elections, candidates, eligibility |
| `ballot-service` | 8003 | `ballot_db` | Vote casting, receipts, anti-double-vote |
| `audit-service` | 8004 | `audit_db` | Hash chain, verification, checkpoints |
| `result-service` | 8005 | `result_db` | Tally, reconciliation, finalization |
| `security-service` | 8006 | `security_db` | Anomaly detection, alerts, Attack Lab |

## Prerequisites

- **Docker Desktop** ≥ 29.x with Docker Compose v5+
- **Node.js** ≥ 18 (for local frontend development)
- **Python** ≥ 3.10 (for local backend development/testing)

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env — replace all CHANGE_ME values with development secrets
```

### 2. Start with Docker Compose

```bash
# Build and start all services
docker compose up -d --build

# Check status
docker compose ps

# View logs
docker compose logs -f
```

### 3. Verify Health

```bash
# Gateway
curl http://localhost:8000/health/live

# Individual services
curl http://localhost:8001/health/live  # auth
curl http://localhost:8002/health/live  # voter
curl http://localhost:8003/health/live  # ballot
curl http://localhost:8004/health/live  # audit
curl http://localhost:8005/health/live  # result
curl http://localhost:8006/health/live  # security

# Readiness (includes dependency checks)
curl http://localhost:8001/health/ready
```

### 4. Access

| Component | URL |
|-----------|-----|
| Frontend | http://localhost:5173 |
| API Gateway | http://localhost:8000 |
| API Docs (per service) | http://localhost:800{1-6}/docs |
| RabbitMQ Management | http://localhost:15672 |

## Project Structure

```
voxguard/
├── apps/web/                  # React + Vite + TypeScript + Tailwind CSS
├── services/
│   ├── api-gateway/           # HTTP proxy to backend services
│   ├── auth-service/          # Authentication & authorization
│   ├── voter-service/         # Elections & voter management
│   ├── ballot-service/        # Vote casting & receipts
│   ├── audit-service/         # Cryptographic audit chain
│   ├── result-service/        # Tally & finalization
│   └── security-service/      # Anomaly detection & alerts
├── packages/contracts/        # Shared event envelope & error schemas
├── infra/docker/              # PostgreSQL init scripts
├── tests/
│   ├── smoke/                 # End-to-end health checks
│   └── integration/           # Cross-service tests
├── docs/                      # Project documentation
├── compose.yaml               # Docker Compose configuration
└── .env.example               # Environment template
```

Each backend service follows this structure:

```
service/
├── app/
│   ├── main.py                # FastAPI application
│   ├── api/                   # Route handlers
│   ├── core/config.py         # Pydantic settings
│   ├── schemas/               # Request/response models
│   ├── services/              # Business logic
│   └── infrastructure/        # Database, messaging
├── tests/
├── alembic/                   # Database migrations (if applicable)
├── pyproject.toml
└── Dockerfile
```

## Development

### Running Tests

```bash
# Backend unit tests (per service)
cd services/api-gateway
pip install -e ".[dev]"
python -m pytest tests/ -v

# Smoke tests (requires Docker Compose running)
pip install httpx pytest
python -m pytest tests/smoke/ -v

# Frontend type check
cd apps/web
npm install
npx tsc --noEmit

# Frontend build
npx vite build
```

### Running Migrations

Each database-backed service has its own Alembic configuration:

```bash
cd services/auth-service

# Create a migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Check current revision
alembic current
```

> **Note:** Migration files are not yet created — the database schema from `docs/04_DATABASE_DESIGN_ERD.md` needs team confirmation before generating migrations.

### Local Development (without Docker)

```bash
# Start infrastructure only
docker compose up -d postgres rabbitmq redis

# Run a service locally
cd services/api-gateway
export APP_ENV=local
uvicorn app.main:app --reload --port 8000

# Run frontend locally
cd apps/web
npm run dev
```

## Infrastructure

### PostgreSQL

- Single instance with **6 isolated databases** (`auth_db`, `voter_db`, `ballot_db`, `audit_db`, `result_db`, `security_db`)
- Per-service database roles with restricted access
- Init script at `infra/docker/postgres/init-databases.sh`
- Persistent volume: `pg_data`

### RabbitMQ

- Exchange: `voxguard.events` (topic, durable)
- Vhost: `voxguard`
- Management UI: http://localhost:15672
- Persistent volume: `rabbitmq_data`

### Redis

- Used for rate limiting and caching
- **Not** used as source of truth for vote deduplication
- Max memory: 128MB with LRU eviction

## Health Endpoints

All services expose:

| Endpoint | Purpose |
|----------|---------|
| `GET /health/live` | Liveness — service is running |
| `GET /health/ready` | Readiness — dependencies available |

Health responses include `service` name and `status`. Readiness checks include dependency status (database, etc.) with timeout protection. No secrets or connection strings are exposed.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Service fails to start | Check `docker compose logs <service>` for errors |
| Database connection errors | Verify `.env` database URLs match init script passwords |
| Empty env vars in compose | Ensure `.env` file exists (copy from `.env.example`) |
| Port conflicts | Check for other processes on 5173, 8000-8006, 5432, 5672, 6379 |
| RabbitMQ not ready | Wait ~30s on first start; check `docker compose logs rabbitmq` |
| Frontend blank page | Check browser console; verify `VITE_API_BASE_URL` |

## Documentation

Detailed project documentation is in the `docs/` directory:

| Document | Contents |
|----------|----------|
| `01_PROJECT_CHARTER.md` | Project scope, objectives, constraints |
| `02_SOFTWARE_REQUIREMENTS_SPECIFICATION.md` | Functional & non-functional requirements |
| `03_SYSTEM_ARCHITECTURE_DOCUMENT.md` | Architecture decisions & service design |
| `04_DATABASE_DESIGN_ERD.md` | Database schemas & constraints |
| `05_API_CONTRACT_SPECIFICATION.md` | REST API & event contracts |
| `06_THREAT_MODEL_SECURITY_DESIGN.md` | Security analysis & controls |
| `07_TEST_PLAN_ACCEPTANCE_CRITERIA.md` | Test strategy & acceptance criteria |
| `08_PROJECT_PLAN_SPRINT_BACKLOG.md` | Sprint plan & task breakdown |

## License

This is an academic project. See project documentation for usage terms.

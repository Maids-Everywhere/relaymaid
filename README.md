# RelayMaid

RelayMaid is a multi-tenant service for secure and reliable webhook delivery.
It is an independent production-style portfolio project.

## Current milestone

The repository currently contains the architecture pack and a minimal FastAPI
application. Business logic, persistence, RLS, and delivery workers will be
added as reviewed vertical slices.

## Backend development

Requirements: Python 3.12+ and `uv`.

```bash
make install
make check
make run
```

The API is then available at `http://localhost:8000`, with process health at
`GET /health` and OpenAPI documentation at `/docs`.

## Containers

```bash
docker compose up --build
```

This starts the API, PostgreSQL, and Redis. PostgreSQL and Redis are present for
the next persistence milestone; the initial health endpoint deliberately checks
only whether the API process is alive.

## Dev Container

Open the repository in a Dev Containers-compatible editor and select **Reopen in
Container**. The environment installs the backend dependencies and uses the root
`compose.yaml` with `.devcontainer/compose.yaml` as an overlay. Both workflows use
the `relaymaid` Compose project, sharing one PostgreSQL container and data volume
and one Redis container. Use the same Compose project name in both workflows;
overriding it with `-p` or `COMPOSE_PROJECT_NAME` creates a separate stack.

PostgreSQL and Redis are published on host ports `5432` and `6379`. Inside the
devcontainer, they are reached as `postgres:5432` and `redis:6379`, using the
credentials from the root `.env` (or the defaults in `.env.example`). Closing the
editor leaves the shared services running.

Start the reloading API when needed:

```bash
make run
```

The API is available at `http://localhost:8000`.

If the Compose API is already running, run `docker compose stop api` on the host
first to free port `8000` for the devcontainer's reloading API.

Run migrations from the devcontainer's `backend` directory:

```bash
uv run alembic upgrade head
```

These migrations target the same PostgreSQL database available on the host at
`localhost:5432`.

### Switching from the separate devcontainer database

If you used the previous configuration, close the devcontainer and run these
commands from the repository root in a **host terminal**:

```bash
docker compose -p relaymaid_devcontainer -f compose.yaml -f .devcontainer/compose.yaml down
docker compose up -d postgres redis
```

Then select **Dev Containers: Rebuild and Reopen in Container** and run the
migration command above. The old devcontainer database volume is retained, but
its data is not copied into the shared database. The shared database continues
to use the existing `relaymaid_postgres_data` volume.

## Architecture

See `docs/` for MVP boundaries, system architecture, event lifecycle, threat
model, and architecture decision records.

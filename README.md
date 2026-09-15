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

## Architecture

See `docs/` for MVP boundaries, system architecture, event lifecycle, threat
model, and architecture decision records.


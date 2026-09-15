# ADR-001: System architecture

Status: Proposed  
Date: 2026-09-15

## Context

RelayMaid must demonstrate reliable webhook processing and tenant isolation
without becoming a distributed system that cannot be completed in the intended
portfolio scope.

## Decision

Build a modular monolith in one repository and one Python codebase, deployed as
separate process types:

- FastAPI serves dashboard and ingestion APIs.
- Celery workers perform outbound delivery and recovery jobs.
- PostgreSQL is the system of record.
- Redis is the Celery broker, not the authoritative record of delivery state.
- A transactional outbox bridges database commits and task publication.
- Next.js provides a deliberately small dashboard.

The API uses async SQLAlchemy. Celery tasks may use a synchronous database and
HTTP stack to avoid managing event loops inside Celery worker processes. Domain
rules and state transitions remain shared and independently testable.

## Trust paths

### Authenticated dashboard API

The application verifies the JWT and derives user ID, organization ID, and role
from its signed claims and current database state. Request bodies and query
parameters cannot select the tenant.

### Public webhook ingestion

An external sender has no user JWT. It calls an unguessable public endpoint key.
A narrowly scoped lookup resolves that key to a webhook endpoint, after which
the request must pass HMAC verification using that endpoint's secret. The
endpoint's stored organization ID establishes tenant context for the ingestion
transaction.

This pre-tenant lookup is a separate security boundary. It must not become a
general-purpose path that bypasses RLS or exposes endpoint metadata.

## Data isolation

- Shared-schema multi-tenancy is used.
- Tenant-owned tables include `organization_id`.
- PostgreSQL RLS policies use both `USING` and `WITH CHECK`.
- Tenant context is set with transaction-local configuration.
- The runtime application role is neither table owner nor `BYPASSRLS`.
- Tenant-owned tables use `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
- Migration ownership is separated from runtime roles.
- Composite foreign keys include `organization_id` where they cross tenant tables.

RLS is defense in depth, not a replacement for authorization. Role checks such
as owner versus viewer remain application responsibilities.

## Reliable ingestion

The ingestion transaction inserts the event using a database uniqueness
constraint on `(organization_id, endpoint_id, external_event_id)`. It inserts an
outbox message in the same transaction. A uniqueness conflict is treated as a
duplicate, not as a server error.

A dispatcher publishes pending outbox messages. Publication and marking a row
published cannot be one atomic transaction across PostgreSQL and Redis, so the
dispatcher may publish a task more than once. Delivery processing must therefore
be idempotent with respect to task execution.

## Delivery semantics

RelayMaid offers at-least-once delivery. Database state and a lease/row-locking
protocol prevent normal concurrent attempts, but crashes and uncertain network
outcomes can still lead to another outbound request.

Each request sends a stable `Idempotency-Key` and RelayMaid event identifier.
Exactly-once business execution is possible only when the destination honors
that key or provides an equivalent deduplication contract.

## Outbound security

All destination calls pass through one HTTP client boundary. It permits only
HTTP(S), rejects credentials and prohibited IP ranges, resolves DNS at delivery
time, disables redirects, limits time and response bytes, and never logs secrets
or complete payloads. Production deployments should additionally restrict
network egress because application-only SSRF checks are not a complete sandbox.

## Consequences

### Positive

- Important reliability behavior is explicit and testable.
- PostgreSQL remains the recovery source even if Redis loses broker messages.
- The project demonstrates meaningful security and concurrency decisions.
- A modular monolith stays feasible within the portfolio time budget.

### Costs and limitations

- Database roles, RLS tests, and transaction handling add setup complexity.
- The outbox provides at-least-once publication, not atomic PostgreSQL/Redis commit.
- Shared-schema RLS requires disciplined transaction boundaries everywhere.
- Application-level SSRF checks should be backed by infrastructure egress controls.
- JWT revocation and full user lifecycle management are deferred.

## Rejected alternatives

- Microservices: greater operational cost without strengthening the portfolio proof.
- Direct `transaction.commit(); task.delay()`: can lose work between commit and publish.
- Redis as delivery state: weaker recovery and transactional guarantees than PostgreSQL.
- Application filtering without RLS: one forgotten filter can disclose another tenant.
- Schema-per-tenant: unnecessary migration and connection complexity for this MVP.


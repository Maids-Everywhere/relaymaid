# RelayMaid MVP

Status: Draft 1 — ready for review  
Product: RelayMaid  
Tagline: Reliable webhook delivery for multi-tenant applications.

## Problem

Applications that send webhooks must otherwise build durable storage, retries,
failure classification, delivery history, recovery jobs, and operational tools
themselves. RelayMaid accepts a webhook, persists it durably, and takes
responsibility for attempting delivery to a configured destination.

RelayMaid provides at-least-once delivery. It does not claim exactly-once
delivery: if the destination processes a request but its response is lost, only
destination-side idempotency can prevent a repeated business operation.

## MVP goals

- Prove production-style FastAPI and PostgreSQL engineering.
- Isolate organizations in both the API authorization layer and PostgreSQL RLS.
- Verify inbound webhooks using HMAC over timestamp plus raw request body.
- Guarantee ingestion idempotency with a database uniqueness constraint.
- Persist an event and its outbox message in one transaction.
- Deliver asynchronously and record every attempt.
- Retry only transient failures with exponential backoff and jitter.
- Recover from publisher and worker failures.
- Provide a small Next.js interface for configuration and inspection.

## In scope

- Organizations and users with `owner` and `viewer` roles.
- Email/password login and short-lived JWT access tokens.
- The current login flow infers a user's sole organization. Explicit organization
  selection for multi-organization users will be provided in a later slice.
- Webhook endpoint creation, listing, update, enable/disable, and secret creation.
- Public ingestion endpoint identified by an unguessable endpoint key.
- JSON payloads with explicit size and content-type limits.
- HMAC-SHA256 signature verification and timestamp replay tolerance.
- Events, delivery attempts, transactional outbox, Celery, and Redis.
- Automatic and manual retries.
- SSRF-aware outbound HTTP client.
- Structured logs, correlation identifiers, Docker Compose, tests, and CI.
- Seed data for two organizations.

## Out of scope for v1

- Billing, subscriptions, invitations, SSO, social login, and refresh tokens.
- Password reset and email verification.
- Secret rotation without downtime.
- Multiple destination types or workflow builders.
- Payload encryption at rest beyond infrastructure/database encryption.
- Analytics beyond counts and status filters.
- Kubernetes, microservices, mobile clients, and live push updates.

## Roles

### Owner

Can view events and attempts, manage endpoints, reveal a newly generated secret
once, and trigger a manual retry.

### Viewer

Can view events, attempts, and endpoint metadata. Cannot see secrets, change
configuration, or trigger delivery.

## Acceptance criteria

### Tenant isolation

- Client-provided organization identifiers are never trusted.
- Dashboard tenant context comes only from a verified access token.
- Organization A cannot read, insert, update, or delete organization B rows.
- RLS still blocks cross-tenant access when application code queries only by ID.
- Tenant-aware foreign keys prevent cross-organization relationships.
- A request without tenant context cannot access tenant-owned rows.
- Tenant context cannot leak through a pooled database connection.
- Security tests run as the non-owner application database role.

### Ingestion

- Unknown and disabled endpoint keys are rejected.
- The signature covers `<timestamp>.<raw_body>` and uses constant-time comparison.
- Old or unreasonably future timestamps are rejected.
- Unsupported content type and oversized bodies are rejected before processing.
- A valid request atomically creates one event and one outbox message.
- Concurrent duplicate requests create exactly one event.
- A duplicate receives a stable successful response referring to that event.
- The response does not wait for destination delivery.

### Delivery

- Every real HTTP attempt has an immutable delivery-attempt record.
- Timeouts, connection failures, HTTP 429, and selected 5xx responses are retried.
- Validation errors, HTTP 400, 401, and 403 are not automatically retried.
- Backoff is exponential, bounded, and includes jitter.
- Delivery stops after the configured retry limit.
- Manual retry appends history rather than rewriting it.
- Two workers cannot intentionally deliver the same event concurrently.
- Stale work and unpublished outbox messages can be recovered.
- Each outbound request has a stable idempotency key based on the event ID.

### Security and operations

- Destination URLs cannot resolve to prohibited private or special-use addresses.
- Redirects are disabled; DNS and resolved addresses are checked at delivery time.
- HTTP timeouts and response sizes are bounded.
- Logs exclude secrets, authorization headers, and full payload bodies.
- Requests and tasks can be correlated by stable identifiers.

## Definition of done

The MVP runs locally with one documented command, passes linting, typing and
tests in CI, demonstrates two isolated organizations, and includes a scripted
success, retry, permanent failure, duplicate ingestion, and cross-tenant denial.

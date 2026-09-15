# RelayMaid threat model

Status: Draft 1 — ready for review

## Assets

- Organization membership and user identities.
- Endpoint signing secrets.
- Webhook payloads and event metadata.
- Destination URLs and delivery history.
- Authorization boundaries between organizations.
- Availability of ingestion and delivery processing.

## Trust boundaries

1. Browser to dashboard API: untrusted input authenticated with a JWT.
2. External sender to public ingestion API: untrusted input authenticated by HMAC.
3. API/worker to PostgreSQL: separate runtime roles with RLS restrictions.
4. API/dispatcher to Redis: tasks are hints; PostgreSQL is authoritative.
5. Worker to destination: hostile network and potentially malicious tenant URL.
6. Operators/migrations: privileged path outside normal tenant access.

## Primary threats and controls

| Threat | Primary controls | Residual risk |
|---|---|---|
| Cross-tenant read/write | JWT-derived context, authorization, RLS, composite FKs, security tests | Privileged migration/operator role can bypass controls |
| Tenant-context leakage | `SET LOCAL` inside explicit transactions, pool tests, fail-closed policies | Incorrect driver/session integration must be caught by tests |
| Forged webhook | HMAC-SHA256 over timestamp and raw body, constant-time comparison | Stolen secret permits forgery |
| Replay | Timestamp tolerance plus DB idempotency key | A sender reusing IDs incorrectly may cause valid events to deduplicate |
| Concurrent duplicate ingestion | Database unique constraint and conflict handling | None for event-row creation under the defined key |
| Lost enqueue after commit | Transactional outbox and recovery dispatcher | Duplicate task publication remains possible |
| Duplicate destination operation | Stable outbound idempotency key | Cannot be guaranteed if destination ignores idempotency |
| Worker crash mid-delivery | Lease/state timeout and recovery job | Network result may remain unknowable |
| SSRF | URL parsing, prohibited ranges, DNS checks, no redirects, strict time/size limits | Strongest production control requires network egress policy |
| Secret disclosure | Encrypted storage, one-time display, redacted logs/errors | Application with master key can decrypt secrets |
| Payload/log leakage | No body logging, bounded excerpts, structured allowlist fields | Operators with DB access can read stored payloads |
| Resource exhaustion | Body limit, timeouts, DB constraints, documented rate limiting | Distributed abuse needs gateway/WAF controls |
| Unauthorized manual retry | Owner-only authorization and audit metadata | Compromised owner account retains its privileges |

## Abuse cases to test

- Viewer attempts endpoint mutation and manual retry.
- Tenant A requests tenant B object by known UUID.
- Tenant A attempts to relate its event to tenant B endpoint.
- A request reaches tenant tables without tenant context.
- A pooled connection is reused by another organization.
- Two identical signed webhooks arrive concurrently.
- Signature uses parsed/reformatted JSON rather than original bytes.
- Destination resolves to loopback, private IPv4, link-local, IPv6 local, or metadata IP.
- Public URL redirects to a private address.
- Two workers receive duplicate tasks for the same event.
- Worker dies before HTTP call, during call, and after response but before commit.
- Dispatcher publishes a task and dies before marking the outbox row.
- Destination returns a huge or sensitive response body.

## Explicit non-guarantees

- RelayMaid does not guarantee exactly-once execution by a destination.
- RLS does not constrain a superuser, `BYPASSRLS` role, or improperly configured owner.
- Application-only SSRF validation is not equivalent to network isolation.
- Stored payload confidentiality against database administrators is not provided in v1.
- Compromised endpoint secrets cannot be distinguished from the legitimate sender.


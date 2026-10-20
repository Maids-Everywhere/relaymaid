# RelayMaid threat model

Status: Implemented

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
| SSRF | Configuration-time URL parsing, rejection of credentials, local hosts, single-label hosts, and non-public literal IP addresses; delivery-time DNS/IP validation and redirect controls are tracked by #13 | DNS rebinding and network-level bypasses remain possible until request-time and infrastructure controls are implemented |
| Secret disclosure | Encrypted storage, one-time display, redacted logs/errors | Application with master key can decrypt secrets |
| Payload/log leakage | No body logging, bounded excerpts, structured allowlist fields | Operators with DB access can read stored payloads |
| Resource exhaustion | Body limit, timeouts, DB constraints, documented rate limiting | Distributed abuse needs gateway/WAF controls |
| Unauthorized manual retry | Owner-only authorization and audit metadata | Compromised owner account retains its privileges |

## SSRF enforcement boundary

Tenants control WebhookEndpoint.destination_url, while RelayMaid workers will make server-side HTTP requests to that address. The destination must therefore be treated as hostile input.

## Configuration-time validation

When an endpoint is created or updated, RelayMaid currently:
* accepts only syntactically valid HTTP or HTTPS URLs;
* rejects URLs containing user information or passwords;
* rejects localhost and its subdomains;
* rejects single-label hostnames such as redis, postgres, or metadata;
* rejects literal loopback, private, link-local, shared, reserved, unspecified, documentation, multicast, and other non-global IPv4 and IPv6 addresses;
* handles IPv4-mapped IPv6 addresses according to their embedded IPv4 address;
* does not perform DNS resolution.

This validation prevents obvious attempts to target local services or cloud metadata endpoints. It is not a complete SSRF boundary because a public-looking hostname can later resolve to a prohibited address.

## Delivery-time validation

Before every outbound delivery attempt, including retries, the worker must:
* resolve the destination hostname;
* inspect every resolved IPv4 and IPv6 address;
* reject the delivery if any resolved address is non-global or otherwise prohibited;
* prevent a second uncontrolled DNS resolution between validation and connection, or route the request through an outbound proxy that enforces the same policy;
* disable HTTP redirects rather than automatically following an unvalidated destination;
* apply bounded connection, read, and total request timeouts;
* limit the amount of response data that RelayMaid reads and stores.

These controls are part of the delivery implementation tracked by #13. Repeating the validation for every attempt is necessary because DNS results can change between retries.

## Infrastructure boundary

Application validation is not equivalent to network isolation. A production deployment should additionally restrict worker egress through firewall rules, security groups, or an outbound proxy. Access to loopback, private networks, link-local ranges, cloud metadata services, and other internal infrastructure should be denied independently of application code.

RelayMaid does not currently provide a production guarantee against DNS rebinding until delivery-time validation and network egress controls are in place.

## Local development

Private and local destination URLs remain rejected through the public endpoint-management API. Integration tests should inject a controlled HTTP transport or create test records directly instead of weakening the production validation policy. Any future development-only bypass must be explicit and must be rejected when the application runs in production mode.

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
- A hostname returns both public and private DNS addresses.
- A hostname resolves to a public address during configuration and a private address during delivery.
- A public destination responds with a redirect to an internal address.

## Explicit non-guarantees

- RelayMaid does not guarantee exactly-once execution by a destination.
- RLS does not constrain a superuser, `BYPASSRLS` role, or improperly configured owner.
- Application-only SSRF validation is not equivalent to network isolation.
- Stored payload confidentiality against database administrators is not provided in v1.
- Compromised endpoint secrets cannot be distinguished from the legitimate sender.


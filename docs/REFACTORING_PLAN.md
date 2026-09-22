# RelayMaid refactoring plan

Status: In progress  
Last updated: 2026-09-22

## Objective

Prepare the existing modular monolith for the MVP without introducing a full
clean-architecture rewrite. Refactoring should make transaction ownership,
tenant identity, API boundaries, and deployment behavior explicit before the
webhook delivery features are added.

## Architectural direction

Keep the current layers, with these dependency rules:

```text
API and workers -> services -> domain
API and workers -> database adapters
services -> database models/session + security + domain
database models -> domain
domain -> standard library only
```

Target package structure:

```text
src/relaymaid/
├── main.py
├── lifespan.py
├── config.py
├── api/
│   ├── dependencies/
│   │   ├── auth.py
│   │   └── database.py
│   ├── routes/
│   └── schemas/
├── services/
├── domain/
├── security/
├── db/
│   ├── base.py
│   ├── engine.py
│   ├── session.py
│   └── models/
└── workers/
```

The structure should grow through focused feature slices rather than generic
repositories or duplicate domain and persistence models.

## Phase 0: Record foundational decisions

- Decide how a user selects an organization during authentication.
- Decide whether login email addresses are globally unique or scoped to an
  organization.
- Define the worker database authorization model.
- Define the restricted public endpoint lookup used before tenant context is
  available.
- Record accepted decisions in ADRs before migrations and API contracts depend
  on them.

Recommended MVP direction: retain global user identities, put the selected
organization in the access token, and revalidate the user's active membership
and role against the database on every authenticated request.

## Phase 1: Establish correctness guardrails

- Make API integration tests use fresh sessions and the same transaction
  dependency as production.
- Verify successful API writes from a separate session.
- Verify failed requests roll back all writes.
- Pin Testcontainers to the supported PostgreSQL version.
- Consolidate organization-name and email validation.
- Add explicit response models for every auth endpoint.
- Standardize response identifier names.

Completion criteria:

- Separate requests do not share an `AsyncSession`.
- A successful write is committed before it is observed by another session.
- A failed request leaves no partial records.
- Request validation cannot produce values that violate known column lengths.

## Phase 2: Clarify application boundaries

- Move FastAPI database and authentication dependencies under
  `relaymaid.api.dependencies`.
- Move HTTP request and response schemas under `relaymaid.api.schemas`.
- Remove FastAPI imports from `relaymaid.db`.
- Pass primitive keyword arguments from routes into services instead of HTTP
  schema objects.
- Rename authentication concepts accurately, including `authorize_user` to
  `authenticate_user` and `UserRole` to `MembershipRole`.
- Move JWT encoding and decoding into `relaymaid.security.tokens`.
- Make token helpers synchronous, typed, and explicit about settings.
- Return focused service result values instead of exposing complete ORM objects
  to API routes.
- Remove the unused organization repository unless independent organization
  creation becomes a supported use case.

Completion criteria:

- `db` has no dependency on FastAPI or API schemas.
- Services have no dependency on HTTP schemas.
- Token mechanics and credential authentication have distinct ownership.
- Internal imports use explicit modules consistently.

## Phase 3: Implement tenant isolation

- Introduce an authenticated principal containing user ID, organization ID, and
  membership role.
- Revalidate active users and current memberships for authenticated requests.
- Add separate migration-owner and runtime application database roles.
- Add tenant-aware foreign keys and PostgreSQL RLS policies using both `USING`
  and `WITH CHECK`.
- Enable and force RLS on tenant-owned tables.
- Set tenant context transaction-locally before tenant queries.
- Run isolation tests as the non-owner application role.
- Test missing context, cross-tenant access, and pooled-connection context leaks.

Completion criteria are the tenant-isolation acceptance criteria in `MVP.md`.

## Phase 4: Make development and deployment reproducible

- Include migration assets in a deployable image or dedicated migration image.
- Add an explicit Compose migration step.
- Add a backend `.dockerignore`.
- Decouple Alembic database configuration from unrelated JWT settings.
- Document environment bootstrap from `.env.example`.
- Use a deterministic test-only JWT secret in CI.
- Align Python, uv, PostgreSQL, Ruff, and type-checker versions across local
  development, containers, and CI.
- Make `make check` and CI run the same formatting, linting, typing, migration,
  and test checks.
- Expose separate unit and integration test commands.

## Phase 5: Add MVP feature slices

Implement each slice with its migration, service, API or worker adapter, and
tenant-isolation tests:

1. Webhook endpoint configuration and secret handling.
2. Signed ingestion with event and outbox persistence.
3. Delivery state transitions, attempts, leases, and retry policy.
4. Dispatcher, delivery, and recovery workers.
5. Operational logging, seed/demo flows, and the dashboard.

## Test organization

Mirror source responsibilities consistently beneath `tests/unit` and
`tests/integration`. Integration tests must be identifiable by directory without
requiring every test author to remember a marker. Database tests should use the
supported PostgreSQL version and production-equivalent transaction boundaries.

## Deliberate non-goals

- Do not introduce repository interfaces for every model.
- Do not create parallel domain and persistence entity classes.
- Do not introduce shared model mixins until enough models share a stable policy.
- Do not build generic worker abstractions before event, lease, and retry
  semantics are fixed.
- Do not reorganize the project into microservices.

## Progress

- [x] Review the current file structure and dependency boundaries.
- [x] Agree to optimize the refactor for the MVP architecture.
- [ ] Complete Phase 0 decisions and ADRs.
- [x] Complete Phase 1 correctness guardrails.
- [x] Complete Phase 2 application-boundary cleanup.
- [ ] Complete Phase 3 tenant isolation.
- [ ] Complete Phase 4 reproducible development and deployment.
- [ ] Build Phase 5 feature slices.

Phase 1 completed on 2026-09-22:

- API integration tests now exercise the production request-session dependency.
- Successful writes are checked through an independent session.
- Mid-request integrity failures are verified to roll back all related records.
- Testcontainers is pinned to PostgreSQL 17.
- Registration reuses the organization-name constraints and enforces the email
  column length.
- `/auth/me` has an explicit response model and consistently returns `user_id`.

Phase 2 completed on 2026-09-22:

- ADR-002 records global email identity and the staged organization-selection
  design.
- FastAPI dependencies and transport schemas now live beneath `api`.
- Services accept application values rather than HTTP schema objects.
- JWT mechanics now live in a synchronous, explicitly configured security module.
- Authentication and registration return focused scalar results instead of ORM
  objects.
- `UserRole` was renamed to `MembershipRole` without changing persisted values.
- The unused organization repository and its parallel CRUD schemas were removed.

Next slice: add runtime database roles, transaction-local tenant context, and RLS.

Phase 3 authentication foundation completed on 2026-09-22:

- Login currently accepts email and password without an organization and infers a
  tenant only when exactly one membership exists.
- Access tokens carry signed user, organization, and membership-role claims.
- Authenticated requests revalidate the active user and current membership.
- The request principal contains user ID, organization ID, email, and the current
  database role rather than exposing an ORM user.
- Tests cover ambiguous membership selection, unrelated organizations, and role
  changes after token issuance.

Phase 3 remains in progress until runtime database roles, transaction-local
tenant context, RLS policies, and isolation tests are implemented.

Explicit organization selection during login is also deferred to a future
authentication slice. Until then, multi-membership accounts cannot log in.

# ADR-002: Authentication tenant context

Status: Accepted  
Date: 2026-09-22

## Context

RelayMaid users authenticate with email and password, while authorization and
row-level security operate in the context of an organization membership. A user
may eventually belong to more than one organization, so a user ID alone cannot
establish tenant context.

The initial schema already models users globally and relates them to
organizations through memberships. The authentication design must preserve that
model without trusting a client-provided organization ID as authorization.

## Decision

- User email addresses are globally unique login identifiers.
- Users remain global records and may have multiple organization memberships.
- Login will accept an organization ID as a requested membership selection once
  the multi-organization selection flow is introduced.
- If a user has exactly one current membership, the organization can be inferred.
- If a user has multiple current memberships, an explicit organization selection
  will be required.
- The server verifies the selected membership before issuing an access token.
- Access tokens identify the user and selected organization. A role claim may be
  included for convenience, but current user, membership, and role state are
  revalidated against the database for authenticated requests.
- The validated principal contains `user_id`, `organization_id`, and membership
  role. That principal, not request data, establishes transaction-local tenant
  context.
- Inactive users, missing memberships, or invalid organization selections fail
  authentication without revealing which condition failed.

An organization ID supplied during login selects among memberships already
authorized by the database. It is not accepted as proof of membership and is
never used directly as tenant context before verification.

## Current rollout

The current `/auth/login` contract accepts only email and password. It infers the
organization when exactly one membership exists and rejects authentication when
multiple memberships make the tenant ambiguous. Supplying `organization_id` is
currently a validation error. Explicit organization selection will be added in a
future authentication slice.

## Consequences

### Positive

- Login remains unambiguous when users have multiple memberships.
- Tenant context can be established before tenant-owned queries execute.
- Membership and role changes take effect without waiting for token expiration.
- Global email uniqueness matches the existing schema and avoids requiring an
  organization identifier before credentials can be located.

### Costs

- Authentication requires a membership lookup in addition to a user lookup.
- Multi-organization clients need an organization-selection flow.
- Signed role claims cannot be treated as the current source of truth.
- Deleting or disabling a membership invalidates access even while a token is
  otherwise valid.

## Deferred decisions

- The worker database authorization model remains a separate decision.
- Restricted public endpoint lookup before tenant context remains a separate
  security decision.
- Refresh tokens and token revocation remain outside the MVP.

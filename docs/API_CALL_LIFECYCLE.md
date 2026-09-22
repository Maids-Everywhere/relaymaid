# Current API call lifecycle

Status: Current implementation  
Last updated: 2026-09-22

## Overall lifecycle

```mermaid
flowchart TD
    Client[Client] --> App[FastAPI application]
    App --> Router[Route matching]
    Router --> Validation[Pydantic request validation]

    Validation -->|Invalid| E422[422 validation response]
    Validation --> Dependencies[Resolve route dependencies]

    Dependencies --> DBSession[Open AsyncSession]
    DBSession --> Transaction[Begin database transaction]
    Transaction --> Route[Execute route handler]
    Route --> Service[Application service]
    Service --> Database[(PostgreSQL)]
    Service --> Route

    Route --> Response[Pydantic response serialization]
    Response --> Finalize{Request successful?}

    Finalize -->|Yes| Commit[Commit transaction]
    Finalize -->|Exception| Rollback[Rollback transaction]

    Commit --> Close[Close session]
    Rollback --> Close
    Close --> ClientResponse[HTTP response]
```

## Registration

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant D as Database dependency
    participant R as Auth route
    participant S as Registration service
    participant P as PostgreSQL

    C->>A: POST /auth/register
    Note over C,A: email, password, organization_name

    A->>A: Validate RegisterRequest
    A->>D: Resolve DatabaseSession
    D->>P: Open session and begin transaction
    D-->>R: AsyncSession

    R->>S: register_owner(...)
    S->>S: Hash password in worker thread
    S->>P: INSERT user and organization
    S->>P: Flush generated IDs
    S->>P: INSERT owner membership
    S->>P: Flush membership

    alt Email already exists
        P-->>S: Unique constraint violation
        S-->>R: EmailAlreadyExistsError
        R-->>A: HTTP 409
        D->>P: Roll back transaction
        A-->>C: 409 Conflict
    else Registration succeeds
        S-->>R: IDs, email, owner role
        R-->>A: RegisterResponse
        D->>P: Commit transaction
        A-->>C: 201 Created
    end
```

## Login

Organization selection is not currently accepted. The sole membership is
inferred.

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant D as Database dependency
    participant R as Auth route
    participant S as Authentication service
    participant P as PostgreSQL
    participant T as Token security

    C->>A: POST /auth/login
    Note over C,A: email and password only

    A->>A: Validate LoginRequest
    A->>D: Open session and transaction
    D-->>R: AsyncSession

    R->>S: authenticate_user(email, password)
    S->>P: Find global user by email
    S->>S: Verify password in worker thread
    S->>P: Load user memberships

    alt No user, invalid password, or inactive user
        S-->>R: InvalidCredentialsError
        R-->>C: 401 Invalid credentials
    else No membership or multiple memberships
        Note over S: Tenant cannot be inferred
        S-->>R: InvalidCredentialsError
        R-->>C: 401 Invalid credentials
    else Exactly one membership
        S->>T: Create signed JWT
        Note over T: User ID, organization ID, role, issued and expiry times
        T-->>S: Access token
        S-->>R: AuthenticationResult
        D->>P: Commit transaction
        R-->>C: 200 LoginResponse
    end
```

Current login response:

```json
{
  "user_id": "uuid",
  "organization_id": "uuid",
  "email": "user@example.com",
  "role": "owner",
  "access_token": "jwt"
}
```

## Authenticated request

The current authenticated endpoint is `GET /auth/me`.

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant D as Database dependency
    participant B as Bearer dependency
    participant T as Token security
    participant P as PostgreSQL
    participant R as Route

    C->>A: GET /auth/me
    Note over C,A: Authorization: Bearer JWT

    A->>D: Open session and transaction
    A->>B: Resolve CurrentPrincipal
    B->>B: Extract bearer credentials
    B->>T: Decode and validate JWT

    alt Missing, expired, or invalid token
        T-->>B: InvalidAccessTokenError
        B-->>C: 401 Unauthorized
    else Valid token
        T-->>B: User ID, organization ID, token role
        B->>P: Query active user and current membership

        alt User or membership no longer valid
            B-->>C: 401 Unauthorized
        else Current membership exists
            P-->>B: Email and current database role
            Note over B: Database role replaces a potentially stale token role
            B-->>R: AuthenticatedPrincipal
            R-->>C: 200 CurrentUserResponse
        end
    end
```

## Health endpoints

```mermaid
flowchart LR
    Live[GET /health/live] --> Process[Return process status]
    Process --> OK1[200 OK]

    Ready[GET /health/ready] --> Engine[Resolve database engine]
    Engine --> Probe[SELECT 1]

    Probe -->|Success| OK2[200 Ready]
    Probe -->|Database error| Unavailable[503 Service Unavailable]
```

## Planned lifecycle change

The next tenant-isolation slice will establish transaction-local tenant context
after principal validation and before tenant-owned queries. PostgreSQL RLS will
then enforce that context for tenant-owned tables.

from fastapi import APIRouter, HTTPException, status

from relaymaid.db.dependencies import DatabaseSession
from relaymaid.dependencies.auth import CurrentUser
from relaymaid.schemas import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from relaymaid.services.auth import authorize_user
from relaymaid.services.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
)
from relaymaid.services.registration import register_owner

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register(data: RegisterRequest, session: DatabaseSession) -> RegisterResponse:
    try:
        result = await register_owner(session, data)
    except EmailAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from error

    return RegisterResponse(
        user_id=result.user.id,
        organization_id=result.organization.id,
        membership_id=result.membership.id,
        email=result.user.email,
        role=result.membership.role,
    )


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(data: LoginRequest, session: DatabaseSession) -> LoginResponse:
    try:
        result = await authorize_user(session, data)
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from error

    return LoginResponse(
        user_id=result.user.id,
        email=result.user.email,
        access_token=result.access_token,
    )


@router.get("/me")
async def get_me(current_user: CurrentUser) -> dict[str, str]:
    return {
        "id": str(current_user.id),
        "email": current_user.email,
    }

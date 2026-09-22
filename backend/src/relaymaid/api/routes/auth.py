from fastapi import APIRouter, HTTPException, status

from relaymaid.api.dependencies.auth import CurrentPrincipal
from relaymaid.api.dependencies.database import DatabaseSession
from relaymaid.api.schemas import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from relaymaid.config import get_settings
from relaymaid.services.authentication import authenticate_user
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
        result = await register_owner(
            session,
            email=str(data.email),
            password=data.password.get_secret_value(),
            organization_name=data.organization_name,
        )
    except EmailAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from error

    return RegisterResponse(
        user_id=result.user_id,
        organization_id=result.organization_id,
        membership_id=result.membership_id,
        email=result.email,
        role=result.role,
    )


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(data: LoginRequest, session: DatabaseSession) -> LoginResponse:
    settings = get_settings()
    try:
        result = await authenticate_user(
            session,
            email=str(data.email),
            password=data.password.get_secret_value(),
            token_secret=settings.jwt_secret_token,
            token_lifetime=settings.jwt_lifetime,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from error

    return LoginResponse(
        user_id=result.user_id,
        organization_id=result.organization_id,
        email=result.email,
        role=result.role,
        access_token=result.access_token,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(current_user: CurrentPrincipal) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=current_user.user_id,
        organization_id=current_user.organization_id,
        email=current_user.email,
        role=current_user.role,
    )

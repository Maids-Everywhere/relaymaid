from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from relaymaid.db.dependencies import DatabaseSession
from relaymaid.schemas import RegisterRequest, RegisterResponse
from relaymaid.services.registration import register_owner

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register(data: RegisterRequest, session: DatabaseSession) -> RegisterResponse:
    try:
        result = await register_owner(session, data)
    except IntegrityError as error:
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

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from relaymaid.api.schemas.organization import OrganizationName
from relaymaid.domain import MembershipRole


class _EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return str(value).lower().strip()


class RegisterRequest(_EmailRequest):
    password: SecretStr = Field(
        min_length=12,
        max_length=128,
        description="Password must be between 12 and 128 characters.",
    )
    organization_name: OrganizationName


class RegisterResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    membership_id: UUID
    email: EmailStr
    role: MembershipRole


class LoginRequest(_EmailRequest):
    password: SecretStr


class LoginResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    email: EmailStr
    role: MembershipRole
    access_token: str


class CurrentUserResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    email: EmailStr
    role: MembershipRole

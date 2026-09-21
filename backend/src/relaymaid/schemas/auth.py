from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator

from relaymaid.domain import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(
        min_length=12,
        max_length=128,
        description="Password must be between 12 and 128 characters.",
    )
    organization_name: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize the email address."""
        return str(value).lower().strip()


class RegisterResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    membership_id: UUID
    email: EmailStr
    role: UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize the email address."""
        return str(value).lower().strip()


class LoginResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    access_token: str

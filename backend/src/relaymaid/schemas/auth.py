from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator


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

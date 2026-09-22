import pytest
from pydantic import ValidationError

from relaymaid.api.schemas.auth import LoginRequest, RegisterRequest


def test_register_request_accepts_valid_email_and_password() -> None:
    password = "securepassword123"
    request = RegisterRequest.model_validate(
        {
            "email": "   TEST@EXAMPLE.COM   ",
            "password": password,
            "organization_name": "  Test Org  ",
        }
    )
    assert request.email == "test@example.com"
    assert request.password.get_secret_value() == password
    assert request.organization_name == "Test Org"


def test_register_request_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "email": "invalid-email",
                "password": "securepassword123",
                "organization_name": "Test Org",
            }
        )


@pytest.mark.parametrize("password", ["short", "a" * 129])
def test_register_request_rejects_invalid_password(password: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "email": "test@example.com",
                "password": password,
                "organization_name": "Test Org",
            }
        )


@pytest.mark.parametrize("organization_name", ["", "   ", "a" * 201])
def test_register_request_rejects_invalid_organization_name(
    organization_name: str,
) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "email": "test@example.com",
                "password": "securepassword123",
                "organization_name": organization_name,
            }
        )


def test_login_request_accepts_email_and_password() -> None:
    request = LoginRequest.model_validate(
        {"email": "TEST@EXAMPLE.COM", "password": "password"}
    )

    assert request.email == "test@example.com"
    assert request.password.get_secret_value() == "password"


def test_login_request_rejects_organization_until_selection_is_supported() -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(
            {
                "email": "test@example.com",
                "password": "password",
                "organization_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        )

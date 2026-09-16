from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from relaymaid.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
)


def test_organization_create_accepts_valid_name() -> None:
    schema = OrganizationCreate(name="Acme")

    assert schema.name == "Acme"


def test_organization_create_strips_name_whitespace() -> None:
    schema = OrganizationCreate(name="  Acme  ")

    assert schema.name == "Acme"


@pytest.mark.parametrize("name", ["", "    ", "a" * 201])
def test_organization_create_rejects_invalid_name(name: str) -> None:
    with pytest.raises(ValidationError):
        OrganizationCreate(name=name)


def test_organization_response_reads_attributes() -> None:
    organization_id = uuid4()
    created_at = datetime.now(UTC)

    organization = SimpleNamespace(
        id=organization_id, name="Acme", created_at=created_at
    )

    response = OrganizationResponse.model_validate(organization)

    assert response.id == organization_id
    assert response.name == "Acme"
    assert response.created_at == created_at

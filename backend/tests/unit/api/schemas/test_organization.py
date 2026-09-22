import pytest
from pydantic import TypeAdapter, ValidationError

from relaymaid.api.schemas.organization import OrganizationName

organization_name_adapter = TypeAdapter(OrganizationName)


def test_organization_name_strips_whitespace() -> None:
    assert organization_name_adapter.validate_python("  Acme  ") == "Acme"


@pytest.mark.parametrize("name", ["", "    ", "a" * 201])
def test_organization_name_rejects_invalid_value(name: str) -> None:
    with pytest.raises(ValidationError):
        organization_name_adapter.validate_python(name)

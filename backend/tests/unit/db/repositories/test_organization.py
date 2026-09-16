from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models.organization import Organization
from relaymaid.db.repositories import create_organization
from relaymaid.schemas import OrganizationCreate


@pytest.mark.anyio
async def test_create_organization_adds_and_flushes_to_database() -> None:
    session = Mock(spec=AsyncSession)
    session.flush = AsyncMock()

    data = OrganizationCreate(name="   Acme   ")
    organization = await create_organization(session, data)

    assert isinstance(organization, Organization)
    assert organization.name == "Acme"

    session.add.assert_called_once_with(organization)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()

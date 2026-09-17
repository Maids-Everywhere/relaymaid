import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models.organization import Organization
from relaymaid.db.repositories.organization import create_organization
from relaymaid.schemas import OrganizationCreate


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_organization_persist_model(db_session: AsyncSession):

    # Create a new organization
    org_data = OrganizationCreate(name="Test Organization")
    new_org = await create_organization(db_session, org_data)
    # Verify that the organization was created correctly
    assert isinstance(new_org, Organization)
    assert new_org.name == "Test Organization"
    assert new_org.id is not None
    assert new_org.created_at is not None

    result = await db_session.scalar(
        select(Organization).where(Organization.id == new_org.id)
    )

    assert result is new_org

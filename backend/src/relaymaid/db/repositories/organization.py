from sqlalchemy.ext.asyncio import AsyncSession

from relaymaid.db.models import Organization
from relaymaid.schemas import OrganizationCreate


async def create_organization(
    session: AsyncSession, data: OrganizationCreate
) -> Organization:
    """
    Create a new organization in the database.

    Args:
        session (AsyncSession): The asynchronous SQLAlchemy session.
        data (OrganizationCreate): The data for the new organization.
    Returns:
        Organization: The newly created organization.
    """
    new_organization = Organization(name=data.name)
    session.add(new_organization)
    await session.flush()
    return new_organization

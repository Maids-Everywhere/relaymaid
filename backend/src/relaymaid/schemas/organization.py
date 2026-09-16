from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

OrganizationName = Annotated[
    str, StringConstraints(max_length=200, min_length=1, strip_whitespace=True)
]


class OrganizationCreate(BaseModel):
    name: OrganizationName


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime

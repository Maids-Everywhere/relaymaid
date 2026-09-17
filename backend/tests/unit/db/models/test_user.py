from sqlalchemy import UniqueConstraint

import relaymaid.db.models.user  # noqa: F401
from relaymaid.db.base import Base


def test_user_is_registered_in_metadata() -> None:
    table = Base.metadata.tables["users"]

    assert set(table.columns.keys()) == {
        "id",
        "email",
        "hashed_password",
        "created_at",
        "is_active",
    }
    unique_constraints = {
        tuple(c.columns.keys())
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
    }
    assert ("email",) in unique_constraints

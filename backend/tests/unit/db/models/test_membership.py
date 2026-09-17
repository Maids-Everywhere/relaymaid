from sqlalchemy import UniqueConstraint

import relaymaid.db.models  # noqa: F401
from relaymaid.db.base import Base


def test_membership_is_registered_in_metadata() -> None:
    table = Base.metadata.tables["memberships"]

    assert set(table.columns.keys()) == {
        "id",
        "user_id",
        "organization_id",
        "role",
        "created_at",
    }
    assert table.primary_key.columns.keys() == ["id"]
    unique_constraints = {
        tuple(c.columns.keys())
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
    }
    assert ("user_id", "organization_id") in unique_constraints

    index_columns = {tuple(c.columns.keys()) for c in table.indexes}
    assert ("organization_id",) in index_columns


def test_membership_references_users_and_organizations() -> None:
    table = Base.metadata.tables["memberships"]

    foreign_keys = {(fk.target_fullname) for fk in table.foreign_keys}
    assert {"users.id", "organizations.id"} == foreign_keys

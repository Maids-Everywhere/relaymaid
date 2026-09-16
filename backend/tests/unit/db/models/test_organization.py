import relaymaid.db.models  # noqa: F401
from relaymaid.db.base import Base


def test_organization_is_registered_in_metadata() -> None:
    table = Base.metadata.tables["organizations"]

    assert set(table.columns.keys()) == {
        "id",
        "name",
        "created_at",
    }
    assert table.primary_key.columns.keys() == ["id"]

import pytest

from relaymaid.db.base import NAMING_CONVENTION, Base


@pytest.mark.anyio
def test_base_metadata_contains_expected_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION

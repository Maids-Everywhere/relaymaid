from relaymaid.domain.roles import UserRole


def test_user_role_enum():
    assert UserRole.OWNER == "owner"
    assert UserRole.VIEWER == "viewer"

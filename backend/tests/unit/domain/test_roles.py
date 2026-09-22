from relaymaid.domain.roles import MembershipRole


def test_membership_role_enum() -> None:
    assert MembershipRole.OWNER == "owner"
    assert MembershipRole.VIEWER == "viewer"

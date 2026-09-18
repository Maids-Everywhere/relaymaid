from relaymaid.security.passwords import hash_password, verify_password


def test_hash_password_doesnt_return_plaintext():
    password = "mysecretpassword"
    hashed_password = hash_password(password)

    assert hashed_password != password
    assert hashed_password.startswith("$argon2")
    assert 200 >= len(hashed_password) > 0


def test_hash_password_returns_different_hashes_for_same_password():
    password = "mysecretpassword"
    hashed_password1 = hash_password(password)
    hashed_password2 = hash_password(password)

    assert hashed_password1 != hashed_password2


def test_verify_password_correctly_verifies():
    password = "mysecretpassword"
    hashed_password = hash_password(password)

    assert verify_password(password, hashed_password) is True


def test_verify_password_fails_for_incorrect_password():
    password = "mysecretpassword"
    hashed_password = hash_password(password)

    assert verify_password("wrongpassword", hashed_password) is False

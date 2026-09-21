class EmailAlreadyExistsError(Exception):
    """Raises if user already registered"""

    pass


class InvalidCredentialsError(Exception):
    """Raises if credentials are invalid"""

    pass

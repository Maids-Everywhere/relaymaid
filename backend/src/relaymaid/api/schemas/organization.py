from typing import Annotated

from pydantic import StringConstraints

OrganizationName = Annotated[
    str, StringConstraints(max_length=200, min_length=1, strip_whitespace=True)
]

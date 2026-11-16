"""Field validators shared by company forms and bulk upload."""

import unicodedata

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

HTTPS_URL_MESSAGE = "Enter a full https:// URL, for example https://example.com/products."

_https_url_validator = URLValidator(schemes=["https"], message=HTTPS_URL_MESSAGE)


def _has_space_or_control(value: str) -> bool:
    """Return whether the value has whitespace, control or format characters."""
    return any(
        char.isspace() or unicodedata.category(char) in ("Cc", "Cf")
        for char in value
    )


def validate_https_url(value) -> None:
    """Reject anything but an absolute https:// URL with a valid host."""
    if isinstance(value, str) and _has_space_or_control(value):
        raise ValidationError(HTTPS_URL_MESSAGE, code="invalid")
    # URLValidator rejects non-strings, other schemes, bad hosts and long URLs.
    _https_url_validator(value)

from urllib.parse import urlsplit

from csp.constants import NONE, SELF, UNSAFE_INLINE


REPORTING_GROUP = "csp-endpoint"

BASE_CSP_DIRECTIVES = {
    "default-src": [SELF],
    "script-src": [
        SELF,
        "https://cdn.jsdelivr.net",
        "https://unpkg.com",
    ],
    "script-src-attr": [NONE],
    "style-src": [
        SELF,
        "https://cdn.jsdelivr.net",
        "https://fonts.googleapis.com",
        "https://unpkg.com",
        UNSAFE_INLINE,
    ],
    "style-src-elem": [
        SELF,
        "https://cdn.jsdelivr.net",
        "https://fonts.googleapis.com",
        "https://unpkg.com",
    ],
    "style-src-attr": [UNSAFE_INLINE],
    "font-src": [SELF, "https://fonts.gstatic.com"],
    "img-src": [
        SELF,
        "data:",
        "https://unpkg.com",
        "https://tile.openstreetmap.org",
        "https://basemap.nationalmap.gov",
    ],
    "connect-src": [SELF],
    "form-action": [SELF],
    "manifest-src": [SELF],
    "media-src": [SELF],
    "base-uri": [NONE],
    "object-src": [NONE],
    "frame-src": [NONE],
    "worker-src": [NONE],
    "frame-ancestors": [NONE],
}


def validate_report_uri(value):
    """Return a valid HTTPS reporting endpoint or None."""
    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate or any(character in candidate for character in '\r\n"\\'):
        return None

    try:
        parsed = urlsplit(candidate)
        parsed.port
    except ValueError:
        return None

    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        return None
    return candidate


def build_csp_directives(report_uri=None):
    """Build the shared CSP directives with optional reporting."""
    directives = {
        directive: list(sources) if isinstance(sources, list) else sources
        for directive, sources in BASE_CSP_DIRECTIVES.items()
    }
    valid_report_uri = validate_report_uri(report_uri)
    if valid_report_uri:
        directives["report-uri"] = [valid_report_uri]
        directives["report-to"] = REPORTING_GROUP
    return directives

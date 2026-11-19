"""US State and ZIP rules shared by company forms, bulk upload and migrations."""

import re

US_COUNTRY = "USA"
US_COUNTRY_ALIASES = frozenset({"usa", "us", "united states"})

# USPS codes for the 50 states, DC and the inhabited territories.
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
    "AS": "American Samoa", "GU": "Guam", "MP": "Northern Mariana Islands",
    "PR": "Puerto Rico", "VI": "U.S. Virgin Islands",
}
_STATE_ALIASES = {"Washington DC": "DC", "Virgin Islands": "VI"}

US_STATE_CHOICES = sorted(
    ((code, f"{name} ({code})") for code, name in US_STATES.items()),
    key=lambda choice: choice[1],
)

STATE_MESSAGE = "For a USA company, choose a USPS state code such as OR."
ZIP_MESSAGE = "For a USA company, enter 5 digits or ZIP+4, such as 97331-1234."

_US_ZIP = re.compile(r"[0-9]{5}(-[0-9]{4})?")


def location_key(value) -> str:
    """Lowercase a name and drop periods, commas and extra spaces."""
    return " ".join(re.sub(r"[.,]", "", str(value or "")).split()).lower()


_STATE_CODES = {
    location_key(name): code
    for names in (
        {code: code for code in US_STATES},
        {name: code for code, name in US_STATES.items()},
        _STATE_ALIASES,
    )
    for name, code in names.items()
}


def is_us_country(country) -> bool:
    """Return whether the country names the United States."""
    return location_key(country) in US_COUNTRY_ALIASES


def usps_state_code(state) -> str | None:
    """Return the USPS code for a state code or full name, else None."""
    return _STATE_CODES.get(location_key(state))


def clean_location(
    country, state, zip_code, *, allow_state_names: bool = True
) -> tuple[str, str, dict[str, str]]:
    """Normalize State and ZIP for the country.

    Args:
        allow_state_names: Accept a full state name for a USA company, not only a code.

    Returns:
        The cleaned State and ZIP, and error messages keyed by field name.
    """
    state = str(state or "").strip()
    zip_code = str(zip_code or "").strip()
    if not is_us_country(country):
        return state, zip_code, {}

    errors = {}
    if state:
        if allow_state_names:
            code = usps_state_code(state)
        else:
            code = state.upper() if state.upper() in US_STATES else None
        if code is None:
            errors["State"] = STATE_MESSAGE
        else:
            state = code
    if zip_code and not _US_ZIP.fullmatch(zip_code):
        errors["ZIP"] = ZIP_MESSAGE
    return state, zip_code, errors

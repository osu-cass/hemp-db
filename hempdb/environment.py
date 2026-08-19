import os


def env_bool(name, default=False):
    """Read a boolean environment variable using common true values."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_rate(name, default):
    """Read an environment variable as a sampling rate from zero to one."""
    value = os.getenv(name)
    if value is None:
        return default

    try:
        rate = float(value)
    except ValueError:
        raise RuntimeError(f'{name} must be a number between 0 and 1.') from None

    if not 0 <= rate <= 1:
        raise RuntimeError(f'{name} must be a number between 0 and 1.')
    return rate

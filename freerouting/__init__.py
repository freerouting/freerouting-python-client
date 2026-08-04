"""Official Python client for the Freerouting REST API."""

__version__ = "2.2.0"

from .client import (
    FreeroutingClient,
    FreeroutingError,
    FreeroutingAPIError,
    FreeroutingAuthError,
)

__all__ = [
    "FreeroutingClient",
    "FreeroutingError",
    "FreeroutingAPIError",
    "FreeroutingAuthError",
    "__version__",
]

"""HTTP client with retry and timeout for external API calls."""

import logging

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10  # seconds


class ExternalServiceError(Exception):
    """Raised when an external service call fails after retries."""

    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    reraise=True,
)
def resilient_request(method: str, url: str, **kwargs) -> requests.Response:
    """Make an HTTP request with retry and timeout.

    Retries up to 3 times with exponential backoff on connection errors
    and timeouts. Default timeout is 10 seconds.
    """
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    logger.debug("HTTP %s %s (timeout=%s)", method, url, kwargs.get("timeout"))
    response = requests.request(method, url, **kwargs)
    return response


def resilient_get(url: str, **kwargs) -> requests.Response:
    """GET request with retry and timeout."""
    return resilient_request("GET", url, **kwargs)


def resilient_post(url: str, **kwargs) -> requests.Response:
    """POST request with retry and timeout."""
    return resilient_request("POST", url, **kwargs)

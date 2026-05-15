"""
Resilience patterns for Venture OS — automatic retries + rate limiting.

Provides decorators for:
- Exponential backoff retry on transient failures (429, 5xx, timeouts)
- Per-API rate limiting to avoid triggering rate limits
- Structured error logging for debugging
"""

import time
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Optional

import httpx

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────────
# RETRY LOGIC — Exponential Backoff with Jitter
# ────────────────────────────────────────────────────────────────────────────────


def with_retry(
    max_attempts: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.ReadTimeout,
    ),
    retryable_status_codes: Tuple[int, ...] = (429, 500, 502, 503, 504),
):
    """
    Decorator for automatic retry with exponential backoff + jitter.

    Retries on:
    - Transient HTTP errors (429 rate limit, 5xx server errors)
    - Network errors (timeouts, connection errors)

    Backs off: 1s → 2s → 4s → ... up to max_wait, with ±20% random jitter

    Args:
        max_attempts: Total number of attempts (default 3 = try once, retry twice)
        initial_wait: Starting backoff in seconds (default 1.0)
        max_wait: Maximum backoff in seconds (default 60.0)
        backoff_factor: Multiply wait by this each retry (default 2.0 = exponential)
        jitter: Add ±20% random jitter to avoid thundering herd (default True)
        retryable_exceptions: Which exceptions trigger a retry
        retryable_status_codes: Which HTTP status codes trigger a retry

    Example:
        @with_retry(max_attempts=3, initial_wait=2.0)
        def call_hunter_api(email: str):
            return httpx.get("https://api.hunter.io/...", params={"email": email})
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            wait = initial_wait
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)

                    # Check if response has a retryable status code
                    if (
                        isinstance(result, httpx.Response)
                        and result.status_code in retryable_status_codes
                    ):
                        if attempt < max_attempts:
                            logger.warning(
                                f"{func.__name__} got {result.status_code}, retrying "
                                f"(attempt {attempt}/{max_attempts}), waiting {wait:.1f}s"
                            )
                            _wait_with_jitter(wait, jitter)
                            wait = min(wait * backoff_factor, max_wait)
                            continue
                        else:
                            raise httpx.HTTPStatusError(
                                f"HTTP {result.status_code} after {max_attempts} attempts",
                                request=result.request,
                                response=result,
                            )

                    return result

                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"{func.__name__} failed: {type(e).__name__}: {e}, "
                            f"retrying (attempt {attempt}/{max_attempts}), waiting {wait:.1f}s"
                        )
                        _wait_with_jitter(wait, jitter)
                        wait = min(wait * backoff_factor, max_wait)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def _wait_with_jitter(wait: float, jitter: bool) -> None:
    """Sleep for wait seconds, optionally adding ±20% jitter."""
    if jitter:
        import random

        jitter_factor = random.uniform(0.8, 1.2)
        wait = wait * jitter_factor
    time.sleep(wait)


# ────────────────────────────────────────────────────────────────────────────────
# RATE LIMITING — Per-API Token Bucket
# ────────────────────────────────────────────────────────────────────────────────


class RateLimiter:
    """Token bucket rate limiter — enforces max N requests per second."""

    def __init__(self, max_per_second: float = 1.0, burst: int = 1):
        """
        Args:
            max_per_second: Rate limit (e.g., 2.0 = 2 requests/second)
            burst: Allow burst of N requests before enforcing rate limit
        """
        self.max_per_second = max_per_second
        self.burst = burst
        self.min_interval = 1.0 / max_per_second
        self.tokens = burst  # Start with burst tokens
        self.last_update = time.time()

    def acquire(self) -> None:
        """Block until a token is available."""
        while self.tokens < 1:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.max_per_second)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.max_per_second
                time.sleep(min(wait_time, 0.01))  # Sleep in short bursts

        self.tokens -= 1
        self.last_update = time.time()


_rate_limiters = {}


def with_rate_limit(
    max_per_second: float = 1.0,
    burst: int = 1,
    limiter_key: Optional[str] = None,
):
    """
    Decorator for per-API rate limiting.

    Uses a token bucket to enforce max N requests per second.
    Multiple calls to the same API share the same limiter.

    Args:
        max_per_second: Rate limit (e.g., 2.0 = 2 requests/second)
        burst: Allow burst of N requests before enforcing limit
        limiter_key: Shared limiter key (default: function name)

    Example:
        @with_rate_limit(max_per_second=1.0)  # Max 1 req/sec
        def lookup_email(first: str, last: str, domain: str):
            return hunter_api.search(first, last, domain)

        # Calls to lookup_email will never exceed 1 req/sec across the app
    """

    def decorator(func: Callable) -> Callable:
        key = limiter_key or func.__name__

        if key not in _rate_limiters:
            _rate_limiters[key] = RateLimiter(max_per_second, burst)

        @wraps(func)
        def wrapper(*args, **kwargs):
            _rate_limiters[key].acquire()
            return func(*args, **kwargs)

        return wrapper

    return decorator


# ────────────────────────────────────────────────────────────────────────────────
# COMBINED: Retry + Rate Limit
# ────────────────────────────────────────────────────────────────────────────────


def api_call(
    max_per_second: float = 1.0,
    max_attempts: int = 3,
    initial_wait: float = 1.0,
):
    """
    Combined decorator: rate limit + retry with backoff.
    Apply INSIDE to OUTSIDE: @api_call(...) @some_function

    Example:
        @api_call(max_per_second=2.0, max_attempts=3)
        def call_notion(page_id: str):
            return httpx.get(f"https://api.notion.com/v1/pages/{page_id}", ...)
    """

    def decorator(func: Callable) -> Callable:
        # First apply rate limiting (outer)
        rate_limited = with_rate_limit(max_per_second=max_per_second)(func)
        # Then apply retry (inner)
        retried = with_retry(max_attempts=max_attempts, initial_wait=initial_wait)(
            rate_limited
        )
        return retried

    return decorator


# ────────────────────────────────────────────────────────────────────────────────
# PRESET CONFIGURATIONS FOR COMMON APIS
# ────────────────────────────────────────────────────────────────────────────────

# OpenAI: 100 req/min (1.67 req/sec) — conservative to stay safe
openai_api_call = lambda func: api_call(max_per_second=1.0, max_attempts=3)(func)

# Hunter.io free tier: 50 queries/month = ~1 per 8 hours — be very conservative
hunter_api_call = lambda func: api_call(
    max_per_second=0.5, max_attempts=3, initial_wait=2.0
)(func)

# Notion: 3 req/sec, but backoff aggressively on 429
notion_api_call = lambda func: api_call(
    max_per_second=2.0, max_attempts=5, initial_wait=1.0
)(func)


# Apollo: (add rate limit if needed)

# Airtable: 5 req/sec — moderate
airtable_api_call = lambda func: api_call(max_per_second=3.0, max_attempts=3)(func)

# Resend: 10 req/sec — generous
resend_api_call = lambda func: api_call(max_per_second=8.0, max_attempts=3)(func)

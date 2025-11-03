"""Utilities for stabilizing E2E tests (retries, backoff, waits).

These helpers are intended to mitigate flakiness due to external services
such as blockchain confirmations, backend eventual consistency, or server
startup timing by applying bounded retries with exponential backoff and
polling for conditions to become true.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Optional, Tuple, Type, TypeVar

T = TypeVar("T")


def _compute_backoff_delay(
    attempt_index: int,
    *,
    base_delay_secs: float,
    max_delay_secs: float,
) -> float:
    """Compute exponential backoff delay with jitter.

    The delay grows exponentially with attempts and includes a small random
    jitter to avoid thundering herds, capped at ``max_delay_secs``.
    """

    exponential = base_delay_secs * (2 ** max(0, attempt_index - 1))
    jitter = random.uniform(0.85, 1.15)
    return min(max_delay_secs, exponential * jitter)


def retry_with_backoff(
    func: Callable[[], T],
    *,
    label: str = "operation",
    attempts: int = 6,
    base_delay_secs: float = 0.5,
    max_delay_secs: float = 8.0,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
) -> T:
    """Run ``func`` with bounded retries and exponential backoff.

    Args:
        func: Zero-arg callable to execute.
        label: Human-readable label for logging purposes.
        attempts: Maximum attempts (including the first try).
        base_delay_secs: Initial delay before the second attempt.
        max_delay_secs: Upper bound for the backoff delay.
        retry_on: Exception types that trigger a retry.
        on_retry: Optional callback invoked before sleeping between retries.

    Returns:
        The return value from ``func``.

    Raises:
        The last caught exception if all attempts fail.
    """

    last_exc: Optional[BaseException] = None
    for i in range(1, max(1, attempts) + 1):
        try:
            return func()
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if i >= attempts:
                break
            delay = _compute_backoff_delay(
                i, base_delay_secs=base_delay_secs, max_delay_secs=max_delay_secs
            )
            if on_retry is not None:
                try:
                    on_retry(i, exc, delay)
                except Exception:
                    # Never allow logging hooks to break the retry flow
                    pass
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc


def wait_for_condition(
    predicate: Callable[[], Optional[T] | bool],
    *,
    label: str = "condition",
    timeout_secs: float = 45.0,
    poll_interval_secs: float = 1.5,
    on_wait: Optional[Callable[[float], None]] = None,
) -> Optional[T]:
    """Poll ``predicate`` until it returns truthy or timeout expires.

    ``predicate`` may return either a boolean or a value. If a value is
    returned, any truthy value will be returned to the caller.

    Args:
        predicate: Zero-arg callable that evaluates the condition.
        label: Human-readable label for logging purposes.
        timeout_secs: Maximum time to wait.
        poll_interval_secs: Time between polls.
        on_wait: Optional callback invoked after each unsuccessful poll.

    Returns:
        The truthy value returned by ``predicate`` or ``True`` if predicate
        returns a boolean ``True``. ``None`` if the timeout expires.
    """

    deadline = time.monotonic() + max(0.0, timeout_secs)
    last_value: Optional[T] = None

    while time.monotonic() < deadline:
        value = predicate()
        if isinstance(value, bool):
            if value:
                return True  # type: ignore[return-value]
        else:
            last_value = value
            if value:
                return value

        if on_wait is not None:
            try:
                on_wait(poll_interval_secs)
            except Exception:
                pass
        time.sleep(poll_interval_secs)

    return last_value

"""Unit tests for the retry_api_call decorator in llm_engine."""

from unittest.mock import patch

import pytest

from src.core.llm_engine import retry_api_call


def test_retry_succeeds_on_first_attempt() -> None:
    """Function returns immediately when no error is raised."""
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def succeed() -> str:
        nonlocal call_count
        call_count += 1
        return "ok"

    assert succeed() == "ok"
    assert call_count == 1


def test_retry_recovers_after_transient_error() -> None:
    """Function retries and succeeds after a transient error."""
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def fail_then_succeed() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:  # noqa: PLR2004
            raise ValueError("CONNECTION_ERROR")
        return "recovered"

    assert fail_then_succeed() == "recovered"
    assert call_count == 3  # noqa: PLR2004


@pytest.mark.parametrize(
    "error_tag",
    [
        "SERVICE_UNAVAILABLE_ERROR",
        "CONNECTION_ERROR",
    ],
)
def test_retry_exhausts_max_retries(error_tag: str) -> None:
    """Raises after max retries for each transient error type."""
    call_count = 0

    @retry_api_call(max_retries=2, base_delay=0.01)
    def always_fail() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError(error_tag)

    with pytest.raises(ValueError, match=error_tag):
        always_fail()
    assert call_count == 3  # noqa: PLR2004 — 1 initial + 2 retries


def test_timeout_error_is_not_retried() -> None:
    """TIMEOUT_ERROR is intentionally NOT in TRANSIENT_ERROR_TAGS.

    A request that exceeded the (already generous) per-call timeout
    indicates the model is genuinely slow on this prompt; retrying
    with the same content typically times out again and silently
    burns ``max_retries × timeout`` seconds.  Regression guard.
    """
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def always_timeout() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("TIMEOUT_ERROR")

    with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
        always_timeout()
    assert call_count == 1


def test_no_retry_for_non_transient_error() -> None:
    """Non-transient errors are raised immediately without retry."""
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def auth_fail() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("AUTH_ERROR")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        auth_fail()
    assert call_count == 1


def test_no_retry_for_quota_error() -> None:
    """QUOTA_ERROR is not retried."""
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def quota_fail() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("QUOTA_ERROR")

    with pytest.raises(ValueError, match="QUOTA_ERROR"):
        quota_fail()
    assert call_count == 1


def test_retry_uses_exponential_backoff() -> None:
    """Verifies delays follow exponential backoff pattern."""
    delays: list[float] = []

    @retry_api_call(max_retries=3, base_delay=1.0)
    def always_fail() -> None:
        raise ValueError("CONNECTION_ERROR")

    with (
        patch("src.core.llm_engine.time.sleep", side_effect=delays.append),
        pytest.raises(ValueError, match="CONNECTION_ERROR"),
    ):
        always_fail()

    assert len(delays) == 3  # noqa: PLR2004
    assert delays[0] == pytest.approx(1.0)  # 1.0 * 2^0
    assert delays[1] == pytest.approx(2.0)  # 1.0 * 2^1
    assert delays[2] == pytest.approx(4.0)  # 1.0 * 2^2


def test_non_valueerror_exception_not_retried() -> None:
    """Non-ValueError exceptions (RuntimeError, OSError) are re-raised immediately."""
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def runtime_fail() -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("unexpected crash")

    with pytest.raises(RuntimeError, match="unexpected crash"):
        runtime_fail()
    assert call_count == 1  # No retries


def test_unknown_valueerror_message_not_retried() -> None:
    """ValueError with an unknown tag is re-raised immediately."""
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def unknown_fail() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("SOME_RANDOM_ERROR")

    with pytest.raises(ValueError, match="SOME_RANDOM_ERROR"):
        unknown_fail()
    assert call_count == 1  # No retries


def test_transient_then_non_transient_stops_at_non_transient() -> None:
    """Transient error retried, then non-transient error stops retries."""
    call_count = 0

    @retry_api_call(max_retries=5, base_delay=0.01)
    def mixed_fail() -> None:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:  # noqa: PLR2004
            raise ValueError("CONNECTION_ERROR")
        raise ValueError("AUTH_ERROR")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        mixed_fail()
    assert call_count == 3  # noqa: PLR2004  — 2 retries + 1 final


def test_retry_preserves_function_metadata() -> None:
    """Decorated function retains original name and docstring."""

    @retry_api_call()
    def my_function() -> None:
        """My docstring."""

    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "My docstring."

"""
Reconnection manager with exponential backoff.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class ReconnectionManager:
    """
    Manages reconnection attempts with exponential backoff.

    Implements the strategy:
    - 1s → 2s → 4s → 8s → 16s → 32s → 60s (max)
    - Reset counter on successful connection
    """

    def __init__(
        self,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        max_attempts: int = 10,
    ):
        """
        Initialize reconnection manager.

        Args:
            initial_backoff: Initial backoff time in seconds
            max_backoff: Maximum backoff time in seconds
            max_attempts: Maximum number of reconnection attempts (0 = unlimited)
        """
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._max_attempts = max_attempts

        self._attempts = 0
        self._current_backoff = initial_backoff

    async def wait_before_reconnect(self) -> bool:
        """
        Wait before attempting reconnection with exponential backoff.

        Returns:
            True if should retry, False if max attempts exceeded

        Raises:
            Never - returns False instead
        """
        self._attempts += 1

        # Check if max attempts exceeded
        if self._max_attempts > 0 and self._attempts > self._max_attempts:
            logger.error(
                f"Max reconnection attempts ({self._max_attempts}) exceeded"
            )
            return False

        logger.info(
            f"Reconnection attempt {self._attempts}"
            + (f"/{self._max_attempts}" if self._max_attempts > 0 else "")
            + f" in {self._current_backoff:.1f}s"
        )

        # Wait with current backoff
        await asyncio.sleep(self._current_backoff)

        # Increase backoff for next attempt (exponential)
        self._current_backoff = min(
            self._current_backoff * 2.0,
            self._max_backoff,
        )

        return True

    def reset(self) -> None:
        """Reset reconnection state after successful connection."""
        if self._attempts > 0:
            logger.info(
                f"Connection established after {self._attempts} attempts, "
                "resetting reconnection state"
            )

        self._attempts = 0
        self._current_backoff = self._initial_backoff

    @property
    def attempts(self) -> int:
        """Get the number of reconnection attempts."""
        return self._attempts

    @property
    def current_backoff(self) -> float:
        """Get the current backoff time."""
        return self._current_backoff

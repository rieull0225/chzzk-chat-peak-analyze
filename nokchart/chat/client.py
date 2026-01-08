"""
Main Chzzk chat client with reconnection logic.
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable, Dict, Any

from nokchart.chat.websocket import ChzzkWebSocket
from nokchart.chat.reconnect import ReconnectionManager
from nokchart.chat.models import ChatMessage, DonationMessage
from nokchart.chat.http import get_chat_channel_id, get_access_token
from nokchart.chat.exceptions import (
    ChzzkChatError,
    ConnectionLostError,
    HeartbeatTimeoutError,
    MaxReconnectAttemptsError,
    ChannelNotFoundError,
)

logger = logging.getLogger(__name__)


class ChzzkChatClient:
    """
    Chzzk chat client with robust reconnection logic.

    Compatible with the chzzkpy ChatClient API for drop-in replacement.
    """

    def __init__(
        self,
        channel_id: str,
        max_reconnect_attempts: int = 10,
        max_backoff: float = 60.0,
    ):
        """
        Initialize chat client.

        Args:
            channel_id: The Chzzk channel ID
            max_reconnect_attempts: Maximum reconnection attempts (0 = unlimited)
            max_backoff: Maximum backoff time in seconds
        """
        self._channel_id = channel_id
        self._max_reconnect_attempts = max_reconnect_attempts
        self._max_backoff = max_backoff

        self._websocket: Optional[ChzzkWebSocket] = None
        self._reconnection_manager = ReconnectionManager(
            max_attempts=max_reconnect_attempts,
            max_backoff=max_backoff,
        )

        self._running = False
        self._event_handlers: Dict[str, Callable] = {}

        # Statistics
        self._total_reconnects = 0
        self._total_errors = 0

        logger.info(f"Initialized ChzzkChatClient for channel {channel_id}")

    def event(self, func: Callable) -> Callable:
        """
        Decorator for registering event handlers.

        Compatible with chzzkpy's @client.event decorator.

        Usage:
            @client.event
            async def on_chat(message: ChatMessage):
                print(f"{message.profile.nickname}: {message.content}")

        Supported events:
            - on_connect(): Called when connected
            - on_disconnect(): Called when disconnected
            - on_chat(message: ChatMessage): Called for chat messages
            - on_donation(message: DonationMessage): Called for donations
        """
        event_name = func.__name__
        self._event_handlers[event_name] = func
        logger.debug(f"Registered event handler: {event_name}")
        return func

    async def _dispatch_event(self, event_name: str, *args, **kwargs) -> None:
        """Dispatch an event to registered handlers."""
        handler = self._event_handlers.get(event_name)
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in event handler {event_name}: {e}", exc_info=True)

    async def _connect(self) -> ChzzkWebSocket:
        """
        Establish connection to chat server.

        Returns:
            Connected ChzzkWebSocket instance

        Raises:
            ChannelNotFoundError: If channel not found or not live
            ConnectionError: If connection fails
        """
        logger.info(f"Connecting to channel {self._channel_id}...")

        # Get chat channel ID
        chat_channel_id = await get_chat_channel_id(self._channel_id)
        if not chat_channel_id:
            raise ChannelNotFoundError(
                f"Channel {self._channel_id} is not live or doesn't exist"
            )

        # Get access token
        access_token = await get_access_token(chat_channel_id)

        # Connect WebSocket
        websocket = await ChzzkWebSocket.connect(
            channel_id=self._channel_id,
            chat_channel_id=chat_channel_id,
            access_token=access_token,
        )

        logger.info("Successfully connected to chat server")
        return websocket

    async def _handle_message(self, msg: Dict[str, Any]) -> None:
        """
        Handle incoming message and dispatch appropriate events.

        Args:
            msg: Raw message dictionary from WebSocket
        """
        cmd = msg.get("cmd")
        body = msg.get("bdy")

        # Chat/Special chat messages (cmd=93101 or 93102)
        # Body contains a list of messages
        if cmd in (93101, 93102):
            if not body or not isinstance(body, list):
                return

            for message_data in body:
                try:
                    # Determine message type from msgTypeCode or messageTypeCode
                    msg_type = (
                        message_data.get("msgTypeCode") or
                        message_data.get("messageTypeCode") or
                        1  # Default to TEXT
                    )

                    # Handle chat message (type=1: TEXT)
                    if msg_type == 1:
                        chat_message = ChatMessage.from_raw(message_data)
                        await self._dispatch_event("on_chat", chat_message)

                    # Handle donation message (type=10: DONATION)
                    elif msg_type == 10:
                        donation_message = DonationMessage.from_raw(message_data)
                        await self._dispatch_event("on_donation", donation_message)

                    else:
                        logger.debug(f"Unhandled message type: {msg_type}")

                except Exception as e:
                    logger.error(
                        f"Error parsing message (cmd={cmd}, type={msg_type}): {e}",
                        exc_info=True
                    )

        else:
            logger.debug(f"Received message with cmd={cmd}")

    async def start(self) -> None:
        """
        Start the chat client with automatic reconnection.

        This method runs indefinitely until stop() is called or
        max reconnection attempts are exceeded.

        Raises:
            MaxReconnectAttemptsError: If max reconnection attempts exceeded
        """
        self._running = True
        logger.info("Starting chat client...")

        while self._running:
            try:
                # Connect
                self._websocket = await self._connect()
                self._reconnection_manager.reset()

                # Dispatch connect event
                await self._dispatch_event("on_connect")

                # Poll for events
                async for msg in self._websocket.poll_events():
                    if not self._running:
                        break
                    await self._handle_message(msg)

                # If we exit the loop normally (not via exception), connection closed
                if self._running:
                    logger.warning("Connection closed normally")
                    raise ConnectionLostError("Connection closed")

            except (ConnectionLostError, HeartbeatTimeoutError) as e:
                logger.warning(f"Connection lost: {e}")
                self._total_reconnects += 1

                # Dispatch disconnect event
                await self._dispatch_event("on_disconnect")

                # Close existing connection
                if self._websocket:
                    await self._websocket.close()
                    self._websocket = None

                # Stop if not running
                if not self._running:
                    break

                # Attempt reconnection
                if not await self._reconnection_manager.wait_before_reconnect():
                    raise MaxReconnectAttemptsError(
                        f"Failed to reconnect after {self._reconnection_manager.attempts} attempts"
                    )

            except ChannelNotFoundError as e:
                logger.error(f"Channel error: {e}")
                # Don't reconnect if channel doesn't exist
                raise

            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                self._total_errors += 1
                # For unexpected errors, try to reconnect
                if not await self._reconnection_manager.wait_before_reconnect():
                    raise MaxReconnectAttemptsError(
                        f"Failed to reconnect after {self._reconnection_manager.attempts} attempts"
                    )

        logger.info("Chat client stopped")

    async def stop(self) -> None:
        """Stop the chat client."""
        logger.info("Stopping chat client...")
        self._running = False

        if self._websocket:
            await self._websocket.close()
            self._websocket = None

    async def close(self) -> None:
        """Alias for stop() for compatibility."""
        await self.stop()

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._websocket is not None and not self._websocket.closed

    @property
    def total_reconnects(self) -> int:
        """Get total number of reconnections."""
        return self._total_reconnects

    @property
    def total_errors(self) -> int:
        """Get total number of errors."""
        return self._total_errors

"""
WebSocket connection management for Chzzk chat.
"""

import aiohttp
import asyncio
import json
import logging
from typing import Optional, AsyncIterator, Dict, Any

from nokchart.chat.exceptions import (
    ConnectionError as ChzzkConnectionError,
    ConnectionLostError,
    HeartbeatTimeoutError,
    AuthenticationError,
)

logger = logging.getLogger(__name__)


class ChzzkWebSocket:
    """
    WebSocket connection to Chzzk chat server with heartbeat monitoring.
    """

    def __init__(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        channel_id: str,
        chat_channel_id: str,
        session_id: Optional[str] = None,
    ):
        self._ws = ws
        self._channel_id = channel_id
        self._chat_channel_id = chat_channel_id
        self._session_id = session_id
        self._tid = 1
        self._closed = False

    @classmethod
    async def connect(
        cls,
        channel_id: str,
        chat_channel_id: str,
        access_token: str,
        timeout: float = 10.0,
    ) -> "ChzzkWebSocket":
        """
        Establish WebSocket connection and perform handshake.

        Args:
            channel_id: The Chzzk channel ID
            chat_channel_id: The chat channel ID
            access_token: The access token
            timeout: Connection timeout in seconds

        Returns:
            Connected ChzzkWebSocket instance

        Raises:
            ConnectionError: If connection or handshake fails
            AuthenticationError: If authentication fails
        """
        # Select server using the same algorithm as chzzkpy
        server_id = (sum(ord(c) for c in channel_id) % 9) + 1
        url = f"wss://kr-ss{server_id}.chat.naver.com/chat"

        logger.info(f"Connecting to {url} (server_id={server_id})")

        try:
            # Add headers to appear more like a real browser
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Origin": "https://chzzk.naver.com",
                "Referer": "https://chzzk.naver.com/",
            }

            session = aiohttp.ClientSession()
            ws = await asyncio.wait_for(
                session.ws_connect(url, headers=headers, heartbeat=30.0),
                timeout=timeout,
            )

            # Create instance
            instance = cls(
                ws=ws,
                channel_id=channel_id,
                chat_channel_id=chat_channel_id,
            )
            instance._session = session  # Store session for cleanup

            # Send CONNECT message
            connect_msg = {
                "bdy": {
                    "accTkn": access_token,
                    "auth": "READ",
                    "devType": 2001,
                    "uid": None,
                },
                "cid": chat_channel_id,
                "cmd": 100,
                "tid": 1,
                "svcid": "game",
                "ver": "2",
            }

            await instance._send(connect_msg)
            logger.debug(f"Sent CONNECT message: {connect_msg}")

            # Wait for CONNECTED response (cmd=10100)
            try:
                response = await asyncio.wait_for(
                    ws.receive_json(),
                    timeout=timeout,
                )

                if response.get("cmd") == 10100:
                    body = response.get("bdy", {})
                    instance._session_id = body.get("sid")
                    logger.info(f"Connected successfully (session_id={instance._session_id})")
                    return instance
                else:
                    raise AuthenticationError(
                        f"Unexpected response: {response.get('cmd')}"
                    )

            except asyncio.TimeoutError:
                await instance.close()
                raise ChzzkConnectionError("Timeout waiting for CONNECTED response")

        except aiohttp.ClientError as e:
            raise ChzzkConnectionError(f"WebSocket connection failed: {e}")
        except asyncio.TimeoutError:
            raise ChzzkConnectionError("Connection timeout")

    async def _send(self, data: Dict[str, Any]) -> None:
        """Send JSON message to WebSocket."""
        try:
            await self._ws.send_json(data)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise ConnectionLostError(f"Failed to send message: {e}")

    async def _send_ping(self) -> None:
        """Send PING message (cmd=0)."""
        ping_msg = {"cmd": 0, "tid": self._tid}
        self._tid += 1
        await self._send(ping_msg)
        logger.debug("Sent PING")

    async def receive_message(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Receive a single message from WebSocket.

        Args:
            timeout: Timeout in seconds, None for no timeout

        Returns:
            Parsed JSON message, or None if connection closed

        Raises:
            ConnectionLostError: If connection is lost
            asyncio.TimeoutError: If timeout occurs
        """
        if self._closed:
            return None

        try:
            if timeout:
                msg = await asyncio.wait_for(self._ws.receive(), timeout=timeout)
            else:
                msg = await self._ws.receive()

            if msg.type == aiohttp.WSMsgType.TEXT:
                return json.loads(msg.data)
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.warning("WebSocket closed by server")
                raise ConnectionLostError("WebSocket closed by server")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {self._ws.exception()}")
                raise ConnectionLostError(f"WebSocket error: {self._ws.exception()}")
            else:
                logger.warning(f"Unexpected message type: {msg.type}")
                return None

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            raise ConnectionLostError(f"Error receiving message: {e}")

    async def poll_events(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Poll for events with heartbeat monitoring.

        This will be implemented in Phase 3 with proper heartbeat logic.
        For now, this is a placeholder that yields messages.

        Yields:
            Parsed message dictionaries

        Raises:
            ConnectionLostError: If connection is lost
            HeartbeatTimeoutError: If heartbeat timeout occurs
        """
        while not self._closed:
            try:
                # Phase 3 will add proper heartbeat with 58-second timeout
                msg = await self.receive_message(timeout=58.0)

                if msg is None:
                    continue

                cmd = msg.get("cmd")

                # Handle PONG (cmd=10000)
                if cmd == 10000:
                    logger.debug("Received PONG")
                    continue

                # Handle PING (cmd=0) - respond with PONG
                elif cmd == 0:
                    logger.debug("Received PING, sending PONG")
                    await self._send({"cmd": 10000})
                    continue

                # Yield other messages
                else:
                    yield msg

            except asyncio.TimeoutError:
                # Phase 3: This will trigger PING/PONG exchange
                logger.debug("Timeout waiting for message (heartbeat)")
                await self._send_ping()

                # Wait for PONG with 3-second timeout
                try:
                    pong_msg = await self.receive_message(timeout=3.0)
                    if pong_msg and pong_msg.get("cmd") == 10000:
                        logger.debug("Received PONG after timeout")
                        continue
                    else:
                        raise HeartbeatTimeoutError("No PONG response")
                except asyncio.TimeoutError:
                    raise HeartbeatTimeoutError("No PONG response within 3 seconds")

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._closed:
            return

        self._closed = True

        try:
            if not self._ws.closed:
                await self._ws.close()
        except Exception as e:
            logger.warning(f"Error closing WebSocket: {e}")

        try:
            if hasattr(self, "_session"):
                await self._session.close()
        except Exception as e:
            logger.warning(f"Error closing session: {e}")

        logger.info("WebSocket connection closed")

    @property
    def session_id(self) -> Optional[str]:
        """Get the session ID."""
        return self._session_id

    @property
    def closed(self) -> bool:
        """Check if connection is closed."""
        return self._closed

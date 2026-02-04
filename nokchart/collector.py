"""Chat event collector for Chzzk streams."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Use custom chat client for better reliability
from nokchart.chat import ChzzkChatClient, ChatMessage, DonationMessage, get_live_status

from nokchart.models import ChatEvent, EventType, StreamInfo, StreamStatus

logger = logging.getLogger(__name__)


class ChzzkChannelClient:
    """
    Chzzk channel chat client using unofficial chzzkpy library.

    This client connects to a specific channel's chat stream without authentication
    (read-only mode). Each channel requires its own client instance.
    """

    def __init__(self, channel_id: str):
        """
        Initialize Chzzk channel client.

        Args:
            channel_id: Chzzk channel ID to monitor
        """
        self.channel_id = channel_id
        self.client: Optional[ChzzkChatClient] = None
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._connected = False
        self._connect_task: Optional[asyncio.Task] = None
        self._status_client = None  # Reusable client for status checks

    async def initialize(self):
        """Initialize the chat client for this channel."""
        if self.client is not None:
            return

        logger.info(f"Initializing ChzzkChatClient for channel {self.channel_id}")

        # Create ChzzkChatClient with robust reconnection
        self.client = ChzzkChatClient(
            channel_id=self.channel_id,
            max_reconnect_attempts=100,  # Many attempts for unstable servers
            max_backoff=30.0,  # Max 30 seconds backoff for faster recovery
        )

        # Track connection state
        self._disconnect_notified = False

        # Register event handlers
        @self.client.event
        async def on_chat(message: ChatMessage):
            """Handle incoming chat message."""
            # Handle case where profile is None (system messages)
            if message.profile:
                nickname = message.profile.nickname
                user_id_hash = message.profile.user_id_hash
            else:
                nickname = "Unknown"
                user_id_hash = ""

            logger.debug(f"📨 Received chat from {self.channel_id}: {nickname}: {message.content}")
            event = {
                'type': 'chat',
                'user': nickname,
                'user_id': user_id_hash,
                'text': message.content,
                'message_id': message.msg_id,
                'timestamp': datetime.now(timezone.utc),
            }
            await self._event_queue.put(event)
            logger.debug(f"✅ Queued chat event from {self.channel_id}")

        @self.client.event
        async def on_donation(message: DonationMessage):
            """Handle incoming donation."""
            # Handle case where profile is None
            if message.profile:
                nickname = message.profile.nickname
                user_id_hash = message.profile.user_id_hash
            else:
                nickname = "Unknown"
                user_id_hash = ""

            logger.info(f"💰 Received donation from {self.channel_id}: {nickname}")
            event = {
                'type': 'donation',
                'user': nickname,
                'user_id': user_id_hash,
                'text': message.content,
                'amount': message.amount or 0,
                'timestamp': datetime.now(timezone.utc),
            }
            await self._event_queue.put(event)
            logger.debug(f"✅ Queued donation event from {self.channel_id}")

        @self.client.event
        async def on_connect():
            """Handle connection established."""
            logger.info(f"🔗 WebSocket connected for channel {self.channel_id}")
            self._disconnect_notified = False

        @self.client.event
        async def on_disconnect():
            """Handle connection lost."""
            if not self._disconnect_notified:
                logger.warning(
                    f"⚠️  WebSocket disconnected for channel {self.channel_id}. "
                    "Client will attempt to reconnect automatically."
                )
                self._disconnect_notified = True

                # Put a special event to signal potential stream end check
                await self._event_queue.put({
                    'type': 'system',
                    'event': 'disconnect',
                    'timestamp': datetime.now(timezone.utc),
                })

        logger.info(f"Registered event handlers for channel {self.channel_id}")

    async def get_stream_status(self) -> Optional[StreamInfo]:
        """
        Get current stream status for this channel.

        Returns:
            StreamInfo if channel is live, None otherwise
        """
        await self.initialize()

        try:
            # Get live status using HTTP API
            status = await get_live_status(self.channel_id)

            if status is None:
                logger.info(f"Channel {self.channel_id} is not live (no status)")
                return None

            # Check livePollingStatusJson for actual streaming status
            # The outer "status" field can be "CLOSE" even when streaming
            is_live = False
            polling_json = status.get("livePollingStatusJson")
            if polling_json:
                import json
                try:
                    polling = json.loads(polling_json)
                    is_live = polling.get("isPublishing", False)
                except json.JSONDecodeError:
                    pass

            # Fallback to status field if no polling JSON
            if not is_live:
                is_live = status.get("status") == "OPEN"

            if not is_live:
                logger.info(f"Channel {self.channel_id} is not live")
                return None

            # Extract stream information
            live_id = status.get("liveId")
            stream_id = f"{live_id}_{self.channel_id}" if live_id else f"unknown_{self.channel_id}"

            return StreamInfo(
                stream_id=stream_id,
                channel_id=self.channel_id,
                live_id=live_id,  # Store live_id to detect new broadcasts
                title=status.get("liveTitle", "Unknown"),
                status=StreamStatus.LIVE,
                start_time=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(f"Error getting stream status for {self.channel_id}: {e}", exc_info=True)
            return None

    async def connect_chat(self):
        """
        Connect to chat stream and yield chat events.

        Yields:
            Raw chat event dictionaries (filters out system events)
        """
        await self.initialize()

        # Start the chat client in the background
        logger.info(f"Starting ChatClient connection for {self.channel_id}")
        self._connect_task = asyncio.create_task(self.client.start())

        # Wait a bit for connection to establish
        await asyncio.sleep(2)

        try:
            # Yield events from queue
            while True:
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)

                    # Filter out system events (used internally for disconnect notifications)
                    if event.get('type') == 'system':
                        logger.debug(f"System event received: {event.get('event')}")
                        continue

                    yield event
                except asyncio.TimeoutError:
                    # Check if client task is still running
                    if self._connect_task and self._connect_task.done():
                        # Log exception if task failed
                        try:
                            exception = self._connect_task.exception()
                            if exception:
                                logger.error(f"Chat client task failed: {exception}", exc_info=exception)
                            else:
                                logger.warning(f"Chat client task finished unexpectedly (no exception)")
                        except Exception as e:
                            logger.warning(f"Chat client task finished (could not get exception: {e})")
                        break
                    continue

        except Exception as e:
            logger.error(f"Error in chat event handler for {self.channel_id}: {e}", exc_info=True)
            raise
        finally:
            # Clean up and reset for potential reuse
            if self._connect_task:
                self._connect_task.cancel()
                try:
                    await self._connect_task
                except asyncio.CancelledError:
                    pass

            # Reset client state so it can be reinitialized for status checks
            if self.client:
                await self.client.close()
                self.client = None
            logger.info(f"Chat connection ended for {self.channel_id}, client reset for reuse")

    async def close(self):
        """Close client connection and reset state for reuse."""
        if self._connect_task:
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass

        if self.client:
            await self.client.close()
            # Reset client so it can be reinitialized for next collection
            self.client = None

        if self._status_client:
            await self._status_client.close()

        # Clear event queue
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        self._connected = False
        logger.info(f"Closed and reset ChatClient for channel {self.channel_id}")


class Collector:
    """Collects chat events from a live stream."""

    def __init__(
        self,
        stream_info: StreamInfo,
        output_dir: Path,
        client: Optional[ChzzkChannelClient] = None,
        idle_timeout_minutes: int = 2,  # Changed to 2 minutes for smart detection
    ):
        self.stream_info = stream_info
        self.output_dir = output_dir
        self.client = client
        self.events_file = output_dir / "events.jsonl"
        self.running = False
        self.event_count = 0
        self.start_time: Optional[datetime] = None
        self.last_event_time: Optional[datetime] = None
        self.idle_timeout_minutes = idle_timeout_minutes
        self.last_idle_check_time: Optional[datetime] = None

    async def start(self):
        """Start collecting chat events."""
        if not self.client:
            logger.error("No ChzzkChannelClient provided to Collector")
            return

        self.running = True
        self.start_time = datetime.now(timezone.utc)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting collection for stream {self.stream_info.stream_id}")

        try:
            async for event in self._collect_events():
                if not self.running:
                    break
                await self._save_event(event)
                self.event_count += 1

                if self.event_count % 100 == 0:
                    logger.info(f"Collected {self.event_count} events")

        except Exception as e:
            logger.error(f"Error during collection: {e}", exc_info=True)
            raise
        finally:
            logger.info(
                f"Collection stopped. Total events: {self.event_count}, "
                f"Duration: {datetime.now(timezone.utc) - self.start_time}"
            )

    async def stop(self):
        """Stop collecting events."""
        self.running = False

    def is_idle(self) -> bool:
        """Check if collector has been idle (no events) for too long.

        Returns:
            True if idle timeout exceeded, False otherwise
        """
        if self.last_event_time is None:
            # No events yet, check against start time
            if self.start_time is None:
                return False
            idle_duration = datetime.now(timezone.utc) - self.start_time
        else:
            idle_duration = datetime.now(timezone.utc) - self.last_event_time

        idle_minutes = idle_duration.total_seconds() / 60
        return idle_minutes >= self.idle_timeout_minutes

    async def check_stream_and_connection(self) -> tuple[bool, str]:
        """
        Check stream status and connection health when idle detected.

        Returns:
            Tuple of (should_stop: bool, reason: str)
        """
        logger.info(f"Idle detected ({self.idle_timeout_minutes}min). Checking stream and connection status...")

        try:
            # Check if stream is still live
            status = await get_live_status(self.stream_info.channel_id)

            if status is None or status.get("status") != "OPEN":
                logger.info("Stream is no longer live. Stopping collection.")
                return (True, "stream_ended")

            # Stream is still live, check connection status
            logger.info("Stream is still live. Checking connection status...")

            if not self.client or not self.client.client:
                logger.warning("Client not initialized")
                return (True, "client_not_initialized")

            if not self.client.client.is_connected:
                logger.warning(
                    "WebSocket disconnected but stream is live. "
                    "Client should be reconnecting automatically. Continuing..."
                )
                return (False, "reconnecting")

            # Stream is live and connected, but no chats
            # This could be a quiet stream or connection issue
            logger.warning(
                f"Stream is live and connected, but no chats for {self.idle_timeout_minutes} minutes. "
                "This might indicate a connection issue or very quiet stream."
            )
            return (False, "quiet_stream")

        except Exception as e:
            logger.error(f"Error checking stream/connection status: {e}", exc_info=True)
            # On error, don't stop - let the normal idle timeout handle it
            return (False, "check_error")

    async def _collect_events(self):
        """
        Collect events from chat stream.

        This generator yields ChatEvent objects from the stream.
        """
        # Use the client to connect to chat
        async for raw_event in self.client.connect_chat():
            # Parse raw event into ChatEvent

            # Calculate relative time from stream start
            t_ms = 0
            if self.stream_info.start_time and self.start_time:
                delta = datetime.now(timezone.utc) - self.stream_info.start_time
                t_ms = int(delta.total_seconds() * 1000)

            # Determine event type
            event_type = EventType.CHAT
            if raw_event.get('type') == 'donation':
                event_type = EventType.DONATION

            event = ChatEvent(
                stream_id=self.stream_info.stream_id,
                type=event_type,
                t_ms=t_ms,
                user=raw_event.get('user'),
                user_id=raw_event.get('user_id'),
                text=raw_event.get('text'),
                amount=raw_event.get('amount'),
                message_id=raw_event.get('message_id'),
                received_at=raw_event.get('timestamp', datetime.now(timezone.utc)),
                raw=raw_event,
            )

            yield event

    async def _save_event(self, event: ChatEvent):
        """Save event to events.jsonl file."""
        # Update last event time
        self.last_event_time = datetime.now(timezone.utc)

        with open(self.events_file, "a") as f:
            # Convert to JSON and write as single line
            event_dict = event.model_dump(mode="json", exclude_none=False)
            f.write(json.dumps(event_dict, ensure_ascii=False) + "\n")

    def generate_report(self) -> dict:
        """Generate collection report."""
        report = {
            "stream_id": self.stream_info.stream_id,
            "channel_id": self.stream_info.channel_id,
            "event_count": self.event_count,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": datetime.now(timezone.utc).isoformat(),
            "events_file": str(self.events_file),
        }

        # Add client statistics if available
        if self.client and self.client.client:
            report["reconnect_count"] = self.client.client.total_reconnects
            report["error_count"] = self.client.client.total_errors

        return report

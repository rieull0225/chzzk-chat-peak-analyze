"""Chat event collector for Chzzk streams."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chzzkpy.unofficial.chat import ChatClient, ChatMessage, DonationMessage

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
        self.client: Optional[ChatClient] = None
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._connected = False
        self._connect_task: Optional[asyncio.Task] = None
        self._status_client = None  # Reusable client for status checks

    async def initialize(self):
        """Initialize the chat client for this channel."""
        if self.client is not None:
            return

        logger.info(f"Initializing ChatClient for channel {self.channel_id}")

        # Create ChatClient for this specific channel
        self.client = ChatClient(self.channel_id)

        # Register event handlers
        @self.client.event
        async def on_chat(message: ChatMessage):
            """Handle incoming chat message."""
            logger.info(f"📨 Received chat from {self.channel_id}: {message.profile.nickname}: {message.content}")
            event = {
                'type': 'chat',
                'user': message.profile.nickname,
                'user_id': message.profile.user_id_hash,
                'text': message.content,
                'message_id': message.msg_id if hasattr(message, 'msg_id') else None,
                'timestamp': datetime.now(timezone.utc),
            }
            await self._event_queue.put(event)
            logger.info(f"✅ Queued chat event from {self.channel_id}")

        @self.client.event
        async def on_donation(message: DonationMessage):
            """Handle incoming donation."""
            logger.info(f"💰 Received donation from {self.channel_id}: {message.profile.nickname if hasattr(message, 'profile') else 'Unknown'}")
            event = {
                'type': 'donation',
                'user': message.profile.nickname if hasattr(message, 'profile') else None,
                'user_id': message.profile.user_id_hash if hasattr(message, 'profile') else None,
                'text': message.extras.message if hasattr(message, 'extras') and hasattr(message.extras, 'message') else '',
                'amount': message.extras.pay_amount if hasattr(message, 'extras') and hasattr(message.extras, 'pay_amount') else 0,
                'timestamp': datetime.now(timezone.utc),
            }
            await self._event_queue.put(event)
            logger.info(f"✅ Queued donation event from {self.channel_id}")

        logger.info(f"Registered event handlers for channel {self.channel_id}")

    async def get_stream_status(self) -> Optional[StreamInfo]:
        """
        Get current stream status for this channel.

        Returns:
            StreamInfo if channel is live, None otherwise
        """
        await self.initialize()

        try:
            # Get live status using unofficial API
            from chzzkpy.unofficial import Client

            # Reuse status client to avoid closing shared sessions
            if self._status_client is None:
                self._status_client = Client()
                await self._status_client._async_setup_hook()

            status = await self._status_client.live_status(channel_id=self.channel_id)

            if status is None or status.status != "OPEN":
                logger.info(f"Channel {self.channel_id} is not live")
                return None

            return StreamInfo(
                stream_id=f"{status.live_id}_{self.channel_id}" if hasattr(status, 'live_id') else f"unknown_{self.channel_id}",
                channel_id=self.channel_id,
                title=status.live_title if hasattr(status, 'live_title') else "Unknown",
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
            Raw chat event dictionaries
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
            # Clean up
            if self._connect_task:
                self._connect_task.cancel()
                try:
                    await self._connect_task
                except asyncio.CancelledError:
                    pass

    async def close(self):
        """Close client connection."""
        if self._connect_task:
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass

        if self.client:
            await self.client.close()

        if self._status_client:
            await self._status_client.close()

        logger.info(f"Closed ChatClient for channel {self.channel_id}")


class Collector:
    """Collects chat events from a live stream."""

    def __init__(
        self,
        stream_info: StreamInfo,
        output_dir: Path,
        client: Optional[ChzzkChannelClient] = None,
        idle_timeout_minutes: int = 30,
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
        return {
            "stream_id": self.stream_info.stream_id,
            "channel_id": self.stream_info.channel_id,
            "event_count": self.event_count,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": datetime.now(timezone.utc).isoformat(),
            "events_file": str(self.events_file),
        }

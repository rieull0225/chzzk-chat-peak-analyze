"""Data models and schemas for NokChart."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field


class EventType(str, Enum):
    """Event types."""

    CHAT = "chat"
    DONATION = "donation"


class StreamStatus(str, Enum):
    """Stream status."""

    OFFLINE = "OFFLINE"
    LIVE = "LIVE"


class ChatEvent(BaseModel):
    """Chat event model matching events.jsonl schema."""

    stream_id: str
    type: EventType
    t_ms: int  # Relative time from stream start in milliseconds
    user: Optional[str] = None
    user_id: Optional[str] = None
    text: Optional[str] = None
    amount: Optional[int] = None  # For donation events
    message_id: Optional[str] = None
    received_at: Optional[datetime] = None
    raw: Optional[dict[str, Any]] = None


class Peak(BaseModel):
    """Peak interval model."""

    start_sec: int
    end_sec: int
    value: int  # Chat count or spike score
    rank: int
    surge_ratio: Optional[float] = None  # Surge ratio (current / previous average)

    @computed_field
    @property
    def clip_start_sec(self) -> int:
        """Get clip start time (10 seconds before peak start)."""
        return max(0, self.start_sec - 10)

    @computed_field
    @property
    def start_time(self) -> str:
        """Convert start_sec to HH:MM:SS format."""
        hours = self.start_sec // 3600
        minutes = (self.start_sec % 3600) // 60
        seconds = self.start_sec % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @computed_field
    @property
    def end_time(self) -> str:
        """Convert end_sec to HH:MM:SS format."""
        hours = self.end_sec // 3600
        minutes = (self.end_sec % 3600) // 60
        seconds = self.end_sec % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @computed_field
    @property
    def clip_start_time(self) -> str:
        """Convert clip_start_sec to HH:MM:SS format (10 seconds before peak)."""
        clip_sec = self.clip_start_sec
        hours = clip_sec // 3600
        minutes = (clip_sec % 3600) // 60
        seconds = clip_sec % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class PeaksOutput(BaseModel):
    """Peaks output model matching peaks.json schema."""

    stream_id: str
    window_sec: int
    peaks: list[Peak]


class StreamInfo(BaseModel):
    """Stream information."""

    stream_id: str
    channel_id: str
    title: Optional[str] = None
    status: StreamStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class Config(BaseModel):
    """Configuration model."""

    # Chzzk API credentials
    chzzk_client_id: Optional[str] = None
    chzzk_client_secret: Optional[str] = None

    # Watcher settings
    poll_interval_sec: int = 60
    restart_resume: bool = True
    idle_timeout_minutes: int = 10  # Stop collecting if no chat for N minutes

    # Peak detection settings
    peak_window_sec: int = 60
    topk: int = 50
    min_peak_gap_sec: int = 120

    # Aggregation settings
    rolling_sec: int = 10

    # Output settings
    outdir: str = "output"

    # Retry settings
    max_retries: int = 5
    backoff_factor: int = 2

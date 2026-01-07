"""
Chzzk WebSocket chat client with robust reconnection logic.
"""

from nokchart.chat.client import ChzzkChatClient
from nokchart.chat.models import ChatMessage, DonationMessage
from nokchart.chat.http import get_live_status, get_chat_channel_id, get_access_token
from nokchart.chat.exceptions import (
    ChzzkChatError,
    ConnectionError,
    ConnectionLostError,
    HeartbeatTimeoutError,
    MaxReconnectAttemptsError,
)

__all__ = [
    "ChzzkChatClient",
    "ChatMessage",
    "DonationMessage",
    "get_live_status",
    "get_chat_channel_id",
    "get_access_token",
    "ChzzkChatError",
    "ConnectionError",
    "ConnectionLostError",
    "HeartbeatTimeoutError",
    "MaxReconnectAttemptsError",
]

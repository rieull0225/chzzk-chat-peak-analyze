"""
Custom exceptions for Chzzk chat client.
"""


class ChzzkChatError(Exception):
    """Base exception for all Chzzk chat errors."""
    pass


class ConnectionError(ChzzkChatError):
    """Failed to establish WebSocket connection."""
    pass


class ConnectionLostError(ChzzkChatError):
    """WebSocket connection was lost."""
    pass


class HeartbeatTimeoutError(ConnectionLostError):
    """No PONG response received after PING."""
    pass


class MaxReconnectAttemptsError(ChzzkChatError):
    """Maximum reconnection attempts exceeded."""
    pass


class AuthenticationError(ChzzkChatError):
    """Failed to authenticate with chat server."""
    pass


class ChannelNotFoundError(ChzzkChatError):
    """Channel not found or not live."""
    pass

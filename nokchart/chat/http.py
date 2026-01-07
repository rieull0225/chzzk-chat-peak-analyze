"""
HTTP API for obtaining access tokens and chat channel IDs.
"""

import aiohttp
from typing import Optional, Dict, Any
import logging

from nokchart.chat.exceptions import ChannelNotFoundError, AuthenticationError

logger = logging.getLogger(__name__)


async def get_live_status(channel_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the full live status for a channel.

    Args:
        channel_id: The Chzzk channel ID

    Returns:
        Live status dictionary if available, None otherwise

    Raises:
        ChannelNotFoundError: If the channel doesn't exist or API error
    """
    url = f"https://api.chzzk.naver.com/polling/v2/channels/{channel_id}/live-status"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise ChannelNotFoundError(
                        f"Failed to get channel status: HTTP {response.status}"
                    )

                data = await response.json()

                if data.get("code") != 200:
                    raise ChannelNotFoundError(
                        f"API error: {data.get('message', 'Unknown error')}"
                    )

                content = data.get("content")
                if not content:
                    logger.warning(f"No content in live status for channel {channel_id}")
                    return None

                return content

    except aiohttp.ClientError as e:
        raise ChannelNotFoundError(f"Network error: {e}")


async def get_chat_channel_id(channel_id: str) -> Optional[str]:
    """
    Get the chat channel ID for a live stream.

    Args:
        channel_id: The Chzzk channel ID

    Returns:
        The chat channel ID if the channel is live, None otherwise

    Raises:
        ChannelNotFoundError: If the channel doesn't exist or API error
    """
    url = f"https://api.chzzk.naver.com/polling/v2/channels/{channel_id}/live-status"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise ChannelNotFoundError(
                        f"Failed to get channel status: HTTP {response.status}"
                    )

                data = await response.json()

                if data.get("code") != 200:
                    raise ChannelNotFoundError(
                        f"API error: {data.get('message', 'Unknown error')}"
                    )

                content = data.get("content", {})
                chat_channel_id = content.get("chatChannelId")

                if chat_channel_id:
                    logger.info(f"Got chat channel ID: {chat_channel_id}")
                else:
                    logger.warning(f"Channel {channel_id} is not live")

                return chat_channel_id

    except aiohttp.ClientError as e:
        raise ChannelNotFoundError(f"Network error: {e}")


async def get_access_token(chat_channel_id: str) -> str:
    """
    Get an access token for the chat channel.

    Args:
        chat_channel_id: The chat channel ID

    Returns:
        The access token

    Raises:
        AuthenticationError: If failed to obtain access token
    """
    url = "https://comm-api.game.naver.com/nng_main/v1/chats/access-token"
    params = {
        "channelId": chat_channel_id,
        "chatType": "STREAMING"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise AuthenticationError(
                        f"Failed to get access token: HTTP {response.status}"
                    )

                data = await response.json()

                if data.get("code") != 200:
                    raise AuthenticationError(
                        f"API error: {data.get('message', 'Unknown error')}"
                    )

                content = data.get("content", {})
                access_token = content.get("accessToken")

                if not access_token:
                    raise AuthenticationError("No access token in response")

                logger.info("Successfully obtained access token")
                return access_token

    except aiohttp.ClientError as e:
        raise AuthenticationError(f"Network error: {e}")

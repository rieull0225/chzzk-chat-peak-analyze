"""
Message models for Chzzk chat.
"""

import json
from typing import Optional, Any, Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """User profile information."""
    nickname: str
    user_id_hash: str
    badge: Optional[str] = None
    title: Optional[str] = None
    verified_mark: bool = False
    activity_badge: Optional[Dict[str, Any]] = None

    @classmethod
    def from_json_string(cls, json_str: Optional[str]) -> Optional["UserProfile"]:
        """
        Parse UserProfile from JSON string.

        Args:
            json_str: JSON string or None

        Returns:
            UserProfile instance or None if empty/invalid
        """
        if not json_str or json_str == "{}":
            return None

        try:
            data = json.loads(json_str)

            # Handle empty object
            if not data or data == {}:
                return None

            # Extract required fields
            nickname = data.get("nickname", "Unknown")
            user_id_hash = data.get("userIdHash", "")

            # Extract optional fields
            badge = None
            if "badge" in data and data["badge"]:
                badge_data = data["badge"]
                if isinstance(badge_data, dict):
                    badge = badge_data.get("imageUrl")

            title = None
            if "title" in data and data["title"]:
                title_data = data["title"]
                if isinstance(title_data, dict):
                    title = title_data.get("name")

            verified_mark = data.get("verifiedMark", False)

            activity_badge = None
            if "activityBadges" in data and data["activityBadges"]:
                activity_badges = data["activityBadges"]
                if isinstance(activity_badges, list) and len(activity_badges) > 0:
                    activity_badge = activity_badges[0]

            return cls(
                nickname=nickname,
                user_id_hash=user_id_hash,
                badge=badge,
                title=title,
                verified_mark=verified_mark,
                activity_badge=activity_badge,
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse profile JSON: {e}")
            return None


@dataclass
class ChatMessage:
    """Represents a chat message."""
    msg_id: str
    content: str
    profile: Optional[UserProfile]
    time: int
    extras: Optional[Dict[str, Any]] = None

    @classmethod
    def from_raw(cls, data: Dict[str, Any]) -> "ChatMessage":
        """
        Parse ChatMessage from raw WebSocket message.

        Args:
            data: Raw message dictionary from WebSocket (cmd=93101)

        Returns:
            Parsed ChatMessage instance
        """
        # Extract message ID (varies by field name)
        msg_id = data.get("msgId") or data.get("messageId") or ""

        # Extract content
        content = data.get("msg") or data.get("content") or ""

        # Parse profile from JSON string
        profile_json = data.get("profile")
        profile = UserProfile.from_json_string(profile_json)

        # Extract time
        time = data.get("msgTime") or data.get("messageTime") or 0

        # Parse extras from JSON string
        extras = None
        extras_json = data.get("extras")
        if extras_json and extras_json != "{}":
            try:
                extras = json.loads(extras_json)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse extras JSON: {e}")

        return cls(
            msg_id=msg_id,
            content=content,
            profile=profile,
            time=time,
            extras=extras,
        )


@dataclass
class DonationMessage:
    """Represents a donation/subscription message."""
    msg_id: str
    content: str
    profile: Optional[UserProfile]
    time: int
    donation_type: str
    amount: Optional[int] = None
    extras: Optional[Dict[str, Any]] = None

    @classmethod
    def from_raw(cls, data: Dict[str, Any]) -> "DonationMessage":
        """
        Parse DonationMessage from raw WebSocket message.

        Args:
            data: Raw message dictionary from WebSocket (cmd=93102, msgTypeCode=10)

        Returns:
            Parsed DonationMessage instance
        """
        # Extract message ID
        msg_id = data.get("msgId") or data.get("messageId") or ""

        # Extract content
        content = data.get("msg") or data.get("content") or ""

        # Parse profile from JSON string
        profile_json = data.get("profile")
        profile = UserProfile.from_json_string(profile_json)

        # Extract time
        time = data.get("msgTime") or data.get("messageTime") or 0

        # Parse extras from JSON string to extract donation info
        extras = None
        donation_type = "unknown"
        amount = None

        extras_json = data.get("extras")
        if extras_json and extras_json != "{}":
            try:
                extras = json.loads(extras_json)

                # Extract donation type and amount from extras
                if isinstance(extras, dict):
                    donation_type = extras.get("donationType", "unknown")

                    # Amount might be in different fields depending on donation type
                    amount = (
                        extras.get("payAmount") or
                        extras.get("donationAmount") or
                        extras.get("amount")
                    )

            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse donation extras JSON: {e}")

        return cls(
            msg_id=msg_id,
            content=content,
            profile=profile,
            time=time,
            donation_type=donation_type,
            amount=amount,
            extras=extras,
        )

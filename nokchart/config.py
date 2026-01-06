"""Configuration management."""

from pathlib import Path
from typing import Optional

import yaml

from nokchart.models import Config


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = Path("config.yaml")

    if not config_path.exists():
        # Return default config
        return Config()

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return Config(**data)


def load_channels(channels_path: Optional[Path] = None) -> list[str]:
    """Load channel IDs from YAML file."""
    if channels_path is None:
        channels_path = Path("channels.yaml")

    if not channels_path.exists():
        return []

    with open(channels_path) as f:
        data = yaml.safe_load(f)

    return data.get("channels", [])


def load_channel_names(channels_path: Optional[Path] = None) -> dict[str, str]:
    """Load channel ID to name mapping from YAML file.

    Parses comments in the format: "channel_id"  # streamer_name

    Returns:
        Dictionary mapping channel_id -> streamer_name
    """
    if channels_path is None:
        channels_path = Path("channels.yaml")

    if not channels_path.exists():
        return {}

    import re

    channel_names = {}

    with open(channels_path) as f:
        for line in f:
            # Match pattern: "channel_id"  # streamer_name
            match = re.match(r'\s*-\s*"([^"]+)"\s*#\s*(.+)', line)
            if match:
                channel_id = match.group(1)
                streamer_name = match.group(2).strip()
                channel_names[channel_id] = streamer_name

    return channel_names

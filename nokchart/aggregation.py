"""Aggregation module for creating time series from events."""

import json
import logging
from pathlib import Path

import pandas as pd

from nokchart.models import EventType

logger = logging.getLogger(__name__)


class Aggregator:
    """Aggregates events into time series."""

    def __init__(self, events_file: Path):
        self.events_file = events_file

    def build_time_series(
        self,
        output_dir: Path,
        bucket_sizes: list[int] = [1, 5, 60],
        rolling_window: int = 10,
    ) -> dict[str, Path]:
        """
        Build time series from events.

        Args:
            output_dir: Directory to save output files
            bucket_sizes: List of bucket sizes in seconds (default: 1s, 5s, 60s)
            rolling_window: Rolling average window in seconds

        Returns:
            Dictionary mapping bucket size to output file path
        """
        logger.info(f"Building time series from {self.events_file}")

        # Load events
        events = self._load_events()
        if not events:
            logger.warning("No events found")
            return {}

        # Convert to DataFrame
        df = pd.DataFrame(events)

        # Filter chat events
        chat_df = df[df["type"] == EventType.CHAT.value].copy()

        if chat_df.empty:
            logger.warning("No chat events found")
            return {}

        # Convert t_ms to seconds
        chat_df["sec"] = (chat_df["t_ms"] / 1000).astype(int)

        # Parse received_at timestamps for actual broadcast time
        chat_df["received_at"] = pd.to_datetime(chat_df["received_at"])
        # Get first event time as stream start reference
        stream_start_time = chat_df["received_at"].min()

        output_files = {}

        # Create time series for each bucket size
        for bucket_sec in bucket_sizes:
            ts_df = self._create_time_series(chat_df, bucket_sec, stream_start_time)

            # Add rolling average if requested (for 1-minute buckets)
            if rolling_window > 0 and bucket_sec == 60:
                # Convert rolling_window from seconds to minutes for 60s buckets
                rolling_minutes = max(1, rolling_window // 60)
                ts_df[f"chat_count_rolling_{rolling_window}s"] = (
                    ts_df["chat_count"].rolling(window=rolling_minutes, min_periods=1).mean()
                )

            # Save to CSV
            output_file = output_dir / f"chat_ts_{bucket_sec}s.csv"
            ts_df.to_csv(output_file, index=False)
            output_files[f"{bucket_sec}s"] = output_file

            logger.info(f"Created time series: {output_file} ({len(ts_df)} rows)")

        return output_files

    def _load_events(self) -> list[dict]:
        """Load events from JSONL file."""
        events = []

        if not self.events_file.exists():
            logger.error(f"Events file not found: {self.events_file}")
            return events

        with open(self.events_file) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON at line {line_num}: {e}")
                    continue

        logger.info(f"Loaded {len(events)} events")
        return events

    def _create_time_series(self, chat_df: pd.DataFrame, bucket_sec: int, stream_start_time: pd.Timestamp) -> pd.DataFrame:
        """Create time series with specified bucket size."""
        # Group by bucket
        if bucket_sec == 1:
            grouped = chat_df.groupby("sec").size().reset_index(name="chat_count")
            grouped.columns = ["sec", "chat_count"]
        else:
            # For larger buckets, create bucket column
            chat_df["bucket"] = (chat_df["sec"] / bucket_sec).astype(int)
            grouped = chat_df.groupby("bucket").size().reset_index(name="chat_count")
            # Convert bucket back to seconds (start of bucket)
            grouped["sec"] = grouped["bucket"] * bucket_sec
            grouped = grouped[["sec", "chat_count"]]

        # Fill gaps with zeros
        if not grouped.empty:
            min_sec = grouped["sec"].min()
            max_sec = grouped["sec"].max()
            all_secs = pd.DataFrame(
                {"sec": range(min_sec, max_sec + bucket_sec, bucket_sec)}
            )
            grouped = all_secs.merge(grouped, on="sec", how="left").fillna(0)
            grouped["chat_count"] = grouped["chat_count"].astype(int)

        # Add actual timestamp column (stream start + seconds elapsed)
        # Convert to KST (UTC+9)
        if not grouped.empty:
            grouped["timestamp"] = stream_start_time + pd.to_timedelta(grouped["sec"], unit="s")
            grouped["timestamp"] = grouped["timestamp"].dt.tz_convert("Asia/Seoul")

        return grouped

    def get_statistics(self) -> dict:
        """Get basic statistics from events."""
        events = self._load_events()
        if not events:
            return {}

        df = pd.DataFrame(events)

        chat_count = len(df[df["type"] == EventType.CHAT.value])
        donation_count = len(df[df["type"] == EventType.DONATION.value])

        # Get time range
        if "t_ms" in df.columns and not df.empty:
            min_t_ms = df["t_ms"].min()
            max_t_ms = df["t_ms"].max()
            duration_sec = (max_t_ms - min_t_ms) / 1000
        else:
            duration_sec = 0

        return {
            "total_events": len(events),
            "chat_events": chat_count,
            "donation_events": donation_count,
            "duration_sec": duration_sec,
        }

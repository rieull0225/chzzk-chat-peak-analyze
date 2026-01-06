"""Visualization module for creating charts."""

import logging
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd

from nokchart.models import PeaksOutput

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generates charts from time series data."""

    def __init__(self, time_series_file: Path):
        self.time_series_file = time_series_file

    def plot_chat_rate(
        self,
        output_file: Path,
        peaks: Optional[PeaksOutput] = None,
        title: Optional[str] = None,
        figsize: Optional[tuple[int, int]] = None,
    ):
        """
        Plot chat rate over time.

        Args:
            output_file: Path to save the plot
            peaks: Optional peaks to highlight on the chart
            title: Optional chart title
            figsize: Optional figure size (width, height). If None, auto-calculated based on duration.
        """
        logger.info(f"Plotting chat rate to {output_file}")

        # Load time series
        df = self._load_time_series()

        if df.empty:
            logger.warning("Empty time series, skipping plot")
            return

        # Calculate dynamic figure size based on duration
        if figsize is None:
            max_sec = df["sec"].max()
            # Base: 16 inches per hour, minimum 16 inches
            width = max(16, int((max_sec / 3600) * 16))
            # Cap at 100 inches to avoid extremely large images
            width = min(width, 100)
            figsize = (width, 6)
            logger.info(f"Auto-calculated figure size: {figsize} for {max_sec:.0f}s ({max_sec/3600:.1f}h)")

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Determine if we have timestamp data for actual broadcast time
        use_actual_time = "timestamp" in df.columns and not df["timestamp"].isna().all()

        if use_actual_time:
            # Convert timestamp to datetime if needed
            if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            x_data = df["timestamp"]
            x_label = "Broadcast Time (Local)"
        else:
            # Fallback to relative seconds
            x_data = df["sec"]
            x_label = "Time (seconds)"

        # Plot chat count
        ax.plot(x_data, df["chat_count"], linewidth=1, alpha=0.7, label="Chat Count")

        # Plot rolling average if available
        rolling_col = [col for col in df.columns if "rolling" in col]
        if rolling_col:
            ax.plot(
                x_data,
                df[rolling_col[0]],
                linewidth=2,
                alpha=0.9,
                label=rolling_col[0].replace("chat_count_", "").replace("_", " ").title(),
                color="red",
            )

        # Highlight peaks if provided
        if peaks and peaks.peaks:
            for peak in peaks.peaks[:10]:  # Highlight top 10 peaks
                if use_actual_time:
                    # Convert peak seconds to timestamps
                    stream_start = df["timestamp"].min()
                    peak_start = stream_start + pd.Timedelta(seconds=peak.start_sec)
                    peak_end = stream_start + pd.Timedelta(seconds=peak.end_sec)
                    ax.axvspan(
                        peak_start,
                        peak_end,
                        alpha=0.2,
                        color="yellow",
                        label=f"Peak #{peak.rank}" if peak.rank <= 3 else None,
                    )
                else:
                    ax.axvspan(
                        peak.start_sec,
                        peak.end_sec,
                        alpha=0.2,
                        color="yellow",
                        label=f"Peak #{peak.rank}" if peak.rank <= 3 else None,
                    )

        # Format chart
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel("Chat Count", fontsize=12)
        ax.set_title(title or "Chat Activity Over Time", fontsize=14, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right")

        # Format x-axis based on data type
        if use_actual_time:
            # Use matplotlib's date formatter for actual timestamps
            import matplotlib.dates as mdates

            # Determine time range for appropriate formatting
            time_range = (df["timestamp"].max() - df["timestamp"].min()).total_seconds()

            if time_range > 7200:  # More than 2 hours
                # Show HH:MM format, ticks every 30 minutes
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=30))
            elif time_range > 3600:  # More than 1 hour
                # Show HH:MM format, ticks every 15 minutes
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=15))
            else:
                # Show HH:MM format, ticks every 5 minutes
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))

            # Rotate labels for better readability
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        else:
            # Fallback to relative time formatting
            max_sec = df["sec"].max()
            if max_sec > 3600:
                # Show in hours
                tick_interval = 600  # Every 10 minutes
            elif max_sec > 600:
                # Show in minutes
                tick_interval = 60
            else:
                tick_interval = 30

            # Set x-axis ticks
            if max_sec > 0:
                ticks = range(0, int(max_sec) + tick_interval, tick_interval)
                ax.set_xticks(ticks)
                ax.set_xticklabels([self._format_time(t) for t in ticks], rotation=45)

        plt.tight_layout()

        # Save figure
        output_file.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_file, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info(f"Chart saved to {output_file}")

    def _load_time_series(self) -> pd.DataFrame:
        """Load time series from CSV file."""
        if not self.time_series_file.exists():
            logger.error(f"Time series file not found: {self.time_series_file}")
            return pd.DataFrame()

        return pd.read_csv(self.time_series_file)

    def _format_time(self, seconds: int) -> str:
        """Format seconds as HH:MM:SS or MM:SS."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

"""Visualization module for creating charts."""

import logging
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

from nokchart.models import PeaksOutput
from nokchart.topic_analysis import TopicsOutput

logger = logging.getLogger(__name__)

# Korean font configuration
plt.rcParams["font.family"] = ["AppleGothic", "Malgun Gothic", "NanumGothic", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False


class ChartGenerator:
    """Generates charts from time series data."""

    def __init__(self, time_series_file: Path):
        self.time_series_file = time_series_file

    def plot_chat_rate(
        self,
        output_file: Path,
        peaks: Optional[PeaksOutput] = None,
        topics: Optional[TopicsOutput] = None,
        title: Optional[str] = None,
        figsize: Optional[tuple[int, int]] = None,
    ):
        """
        Plot chat rate over time with optional topic labels.

        Args:
            output_file: Path to save the plot
            peaks: Optional peaks to highlight on the chart
            topics: Optional topics to show as labels above the chart
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
        max_sec = df["sec"].max()
        if figsize is None:
            # Base: 16 inches per hour, minimum 16 inches
            width = max(16, int((max_sec / 3600) * 16))
            # Cap at 100 inches to avoid extremely large images
            width = min(width, 100)
            # Add extra height for topic track if topics are provided
            height = 7 if topics and topics.segments else 6
            figsize = (width, height)
            logger.info(f"Auto-calculated figure size: {figsize} for {max_sec:.0f}s ({max_sec/3600:.1f}h)")

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Use relative time from broadcast start (not actual clock time)
        use_actual_time = False
        x_data = df["sec"]
        x_label = "Broadcast Elapsed Time"

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

        # Highlight peaks if provided (use volume-based peaks for chart)
        if peaks and peaks.peaks_by_volume:
            for peak in peaks.peaks_by_volume[:10]:  # Highlight top 10 peaks
                ax.axvspan(
                    peak.start_sec,
                    peak.end_sec,
                    alpha=0.2,
                    color="yellow",
                    label=f"Peak #{peak.rank}" if peak.rank <= 3 else None,
                )

        # Overlay topic labels on chart
        if topics and topics.segments:
            self._draw_topic_labels(ax, topics, df)

        # Format chart
        ax.set_xlabel(x_label, fontsize=12)
        ax.set_ylabel("Chat Count", fontsize=12)
        ax.set_title(title or "Chat Activity Over Time", fontsize=14, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right")

        # Format x-axis for relative time (broadcast elapsed time)
        max_sec = df["sec"].max()
        if max_sec > 3600:
            # Show in hours - Every 10 minutes for long streams
            tick_interval = 600  # Every 10 minutes
        elif max_sec > 600:
            # Show in minutes - Every 5 minutes for medium streams
            tick_interval = 300
        else:
            tick_interval = 60

        # Set x-axis ticks
        if max_sec > 0:
            ticks = range(0, int(max_sec) + tick_interval, tick_interval)
            ax.set_xticks(ticks)
            ax.set_xticklabels([self._format_time(t) for t in ticks], rotation=45, ha='right')

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

    def _draw_topic_labels(self, ax, topics: TopicsOutput, df):
        """
        Draw topic labels directly on the chart.

        Args:
            ax: Matplotlib axes
            topics: TopicsOutput with segments and sample chats
            df: Time series dataframe for y-axis reference
        """
        if df.empty:
            return

        # Get y-axis range for positioning
        y_max = df["chat_count"].max()

        # Alternating y positions to avoid overlap (3 levels)
        y_positions = [0.95, 0.75, 0.55]

        for i, segment in enumerate(topics.segments):
            if not segment.sample_chats:
                continue

            # Get up to 3 sample chats, truncate each if too long
            samples = []
            for chat in segment.sample_chats[:3]:
                if len(chat) > 25:
                    chat = chat[:22] + "..."
                samples.append(f"  {chat}")

            # Join with newlines
            label_text = "\n".join(samples)

            # Position: center of segment, alternating y position
            x_pos = (segment.start_sec + segment.end_sec) / 2
            y_ratio = y_positions[i % len(y_positions)]
            y_pos = y_max * y_ratio

            # Draw text with background box
            ax.text(
                x_pos,
                y_pos,
                label_text,
                ha="center",
                va="top",
                fontsize=6,
                color="#333333",
                linespacing=1.4,
                bbox=dict(
                    boxstyle="round,pad=0.4",
                    facecolor="white",
                    edgecolor="#AAAAAA",
                    alpha=0.9,
                ),
                zorder=10,
            )

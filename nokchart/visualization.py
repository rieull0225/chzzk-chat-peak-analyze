"""Visualization module for creating charts."""

import logging
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.font_manager as fm
import pandas as pd

from nokchart.models import PeaksOutput
from nokchart.topic_analysis import TopicsOutput

logger = logging.getLogger(__name__)

# Korean font configuration
def _setup_korean_font():
    """Setup Korean font for matplotlib."""
    # Try to find NanumGothic font (installed via fonts-nanum package)
    nanum_fonts = [f for f in fm.fontManager.ttflist if 'Nanum' in f.name]
    if nanum_fonts:
        font_name = nanum_fonts[0].name
        plt.rcParams["font.family"] = font_name
        logger.info(f"Using Korean font: {font_name}")
    else:
        # Fallback to system fonts
        plt.rcParams["font.family"] = ["AppleGothic", "Malgun Gothic", "NanumGothic", "sans-serif"]
        logger.warning("NanumGothic font not found, using fallback fonts")

    plt.rcParams["axes.unicode_minus"] = False

_setup_korean_font()


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
        max_hours_per_chart: float = 2.0,
    ):
        """
        Plot chat rate over time with optional topic labels.
        If broadcast is longer than max_hours_per_chart, splits into multiple images.

        Args:
            output_file: Path to save the plot
            peaks: Optional peaks to highlight on the chart
            topics: Optional topics to show as labels above the chart
            title: Optional chart title
            figsize: Optional figure size (width, height). If None, auto-calculated based on duration.
            max_hours_per_chart: Maximum hours per chart before splitting (default: 2.0)
        """
        logger.info(f"Plotting chat rate to {output_file}")

        # Load time series
        df = self._load_time_series()

        if df.empty:
            logger.warning("Empty time series, skipping plot")
            return

        max_sec = df["sec"].max()
        max_sec_per_chart = max_hours_per_chart * 3600

        # Split into multiple charts if needed
        if max_sec > max_sec_per_chart:
            num_charts = int(max_sec // max_sec_per_chart) + (1 if max_sec % max_sec_per_chart else 0)
            logger.info(f"Splitting into {num_charts} charts ({max_sec/3600:.1f}h total, {max_hours_per_chart}h per chart)")

            for i in range(num_charts):
                start_sec = i * max_sec_per_chart
                end_sec = min((i + 1) * max_sec_per_chart, max_sec)

                # Filter data for this segment
                segment_df = df[(df["sec"] >= start_sec) & (df["sec"] < end_sec)].copy()
                if segment_df.empty:
                    continue

                # Filter peaks for this segment
                segment_peaks = None
                if peaks and peaks.peaks_by_volume:
                    filtered_peaks = [p for p in peaks.peaks_by_volume if p.start_sec < end_sec and p.end_sec > start_sec]
                    if filtered_peaks:
                        segment_peaks = PeaksOutput(
                            stream_id=peaks.stream_id,
                            peaks_by_volume=filtered_peaks,
                            peaks_by_surge=[]
                        )

                # Filter topics for this segment
                segment_topics = None
                if topics and topics.segments:
                    filtered_segments = [s for s in topics.segments if s.start_sec < end_sec and s.end_sec > start_sec]
                    if filtered_segments:
                        segment_topics = TopicsOutput(stream_id=topics.stream_id, segments=filtered_segments)

                # Generate output filename with part number
                stem = output_file.stem
                suffix = output_file.suffix
                part_file = output_file.parent / f"{stem}_part{i+1}{suffix}"

                # Chart title with time range
                start_time = self._format_time(int(start_sec))
                end_time = self._format_time(int(end_sec))
                part_title = f"{title or 'Chat Activity'} ({start_time} - {end_time})"

                self._plot_single_chart(segment_df, part_file, segment_peaks, segment_topics, part_title, figsize, start_sec, end_sec)

            return

        # Single chart for short broadcasts
        self._plot_single_chart(df, output_file, peaks, topics, title, figsize, 0, max_sec)

    def _plot_single_chart(
        self,
        df: pd.DataFrame,
        output_file: Path,
        peaks: Optional[PeaksOutput],
        topics: Optional[TopicsOutput],
        title: Optional[str],
        figsize: Optional[tuple[int, int]],
        start_sec: float,
        end_sec: float,
    ):
        """Plot a single chart segment."""
        duration_sec = end_sec - start_sec

        # Calculate dynamic figure size based on duration
        if figsize is None:
            width = max(16, int((duration_sec / 3600) * 16))
            width = min(width, 50)
            height = 7 if topics and topics.segments else 6
            figsize = (width, height)

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
        min_sec = int(df["sec"].min())
        max_sec = int(df["sec"].max())
        duration = max_sec - min_sec

        if duration > 3600:
            tick_interval = 600  # Every 10 minutes
        elif duration > 600:
            tick_interval = 300  # Every 5 minutes
        else:
            tick_interval = 60

        # Set x-axis ticks starting from segment start
        if max_sec > 0:
            start_tick = (min_sec // tick_interval) * tick_interval
            ticks = range(start_tick, max_sec + tick_interval, tick_interval)
            ax.set_xticks(list(ticks))
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

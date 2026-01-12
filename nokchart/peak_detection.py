"""Peak detection module for finding chat activity peaks."""

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from nokchart.models import Peak, PeaksOutput

logger = logging.getLogger(__name__)


class PeakDetector:
    """Detects peaks in chat activity time series."""

    def __init__(self, time_series_file: Path):
        self.time_series_file = time_series_file

    def detect_peaks(
        self,
        stream_id: str,
        window_sec: int = 60,
        topk: int = 20,
        min_gap_sec: int = 120,
        events_file: Optional[Path] = None,
    ) -> PeaksOutput:
        """
        Detect peaks in chat activity using sliding window.

        Two-stage detection:
        1. First pass: 10-second sliding window to find rough peaks
        2. Second pass: 1-second precision refinement for exact peak timing

        Args:
            stream_id: Stream identifier
            window_sec: Window size in seconds for peak detection
            topk: Number of top peaks to return
            min_gap_sec: Minimum gap between peaks to avoid overlapping
            events_file: Optional path to events.jsonl for 1-second precision refinement

        Returns:
            PeaksOutput containing detected peaks by volume
        """
        logger.info(
            f"Detecting peaks: window={window_sec}s, topk={topk}, min_gap={min_gap_sec}s"
        )

        # Load time series and detect bucket size
        df, bucket_size = self._load_time_series()

        if df.empty:
            logger.warning("Empty time series")
            return PeaksOutput(
                stream_id=stream_id,
                window_sec=window_sec,
                peaks_by_volume=[],
                peaks_by_surge=[],
            )

        # Calculate sliding window sums and surge ratios
        window_sums = self._calculate_window_sums(df, window_sec, bucket_size)

        # Find top peaks by volume (first pass - 10-second precision)
        peaks_by_volume = self._find_top_peaks(
            window_sums, window_sec, topk, min_gap_sec, sort_by="volume"
        )
        logger.info(f"[1차] Detected {len(peaks_by_volume)} peaks by volume (10s precision)")

        # Second pass: Refine peaks with 1-second precision if events_file is provided
        if events_file and events_file.exists() and peaks_by_volume:
            logger.info(f"[2차] Refining peaks with 1-second precision...")
            peaks_by_volume = self._refine_peaks_with_events(
                peaks_by_volume, events_file, window_sec
            )
            logger.info(f"[2차] Refined {len(peaks_by_volume)} peaks to 1-second precision")

        # Find top peaks by surge ratio
        peaks_by_surge = self._find_top_peaks(
            window_sums, window_sec, topk, min_gap_sec, sort_by="surge"
        )
        logger.info(f"Detected {len(peaks_by_surge)} peaks by surge ratio")

        return PeaksOutput(
            stream_id=stream_id,
            window_sec=window_sec,
            peaks_by_volume=peaks_by_volume,
            peaks_by_surge=peaks_by_surge,
        )

    def _load_time_series(self) -> tuple[pd.DataFrame, int]:
        """Load time series from CSV file and detect bucket size.

        Returns:
            Tuple of (DataFrame, bucket_size_sec)
        """
        if not self.time_series_file.exists():
            logger.error(f"Time series file not found: {self.time_series_file}")
            return pd.DataFrame(), 1

        df = pd.read_csv(self.time_series_file)

        if "sec" not in df.columns or "chat_count" not in df.columns:
            logger.error("Invalid time series format: missing 'sec' or 'chat_count' columns")
            return pd.DataFrame(), 1

        # Detect bucket size from time series interval
        bucket_size = 1
        if len(df) >= 2:
            bucket_size = int(df["sec"].iloc[1] - df["sec"].iloc[0])
            if bucket_size <= 0:
                bucket_size = 1

        logger.info(f"Loaded time series: {len(df)} rows, bucket_size={bucket_size}s")
        return df, bucket_size

    def _calculate_window_sums(self, df: pd.DataFrame, window_sec: int, bucket_size: int) -> pd.DataFrame:
        """Calculate surge ratio based on chat volume increase.

        Args:
            df: Time series DataFrame
            window_sec: Window size in seconds
            bucket_size: Time series bucket size in seconds
        """
        df = df.copy()

        # Convert window_sec to number of rows based on bucket_size
        window_rows = max(1, window_sec // bucket_size)
        prev_window_rows = max(1, 60 // bucket_size)  # 60 seconds for previous average

        logger.info(f"Window: {window_sec}s = {window_rows} rows (bucket={bucket_size}s)")

        # 1. Absolute volume (rolling sum for window)
        df["window_sum"] = df["chat_count"].rolling(window=window_rows, min_periods=1).sum()

        # 2. Previous period average (60 seconds before)
        # Calculate rolling average for the period preceding each point
        df["prev_avg"] = df["chat_count"].shift(prev_window_rows).rolling(window=prev_window_rows, min_periods=1).mean()

        # 3. Current period average (for the window)
        df["curr_avg"] = df["chat_count"].rolling(window=window_rows, min_periods=1).mean()

        # 4. Surge ratio = current average / previous average
        # Use a small baseline to avoid division by zero and handle quiet periods
        baseline = 1.0  # baseline chat rate
        df["surge_ratio"] = df["curr_avg"] / (df["prev_avg"] + baseline)

        # Fill NaN values with 1.0 (no surge)
        df["surge_ratio"] = df["surge_ratio"].fillna(1.0)

        return df

    def _find_top_peaks(
        self,
        df: pd.DataFrame,
        window_sec: int,
        topk: int,
        min_gap_sec: int,
        sort_by: str = "volume",
    ) -> list[Peak]:
        """Find top K peaks with minimum gap constraint.

        Args:
            df: DataFrame with window_sum and surge_ratio columns
            window_sec: Window size in seconds
            topk: Number of top peaks to return
            min_gap_sec: Minimum gap between peaks
            sort_by: Sort criteria - "volume" or "surge"

        Returns:
            List of Peak objects sorted by rank
        """
        peaks = []

        # Sort by specified criteria
        if sort_by == "surge":
            sorted_df = df.sort_values("surge_ratio", ascending=False)
        else:  # "volume"
            sorted_df = df.sort_values("window_sum", ascending=False)

        for _, row in sorted_df.iterrows():
            start_sec = int(row["sec"])
            end_sec = start_sec + window_sec
            # Store the actual chat count as value (for compatibility)
            value = int(row["window_sum"])
            # Store surge ratio for analysis
            surge_ratio = float(row["surge_ratio"])

            # Check if this peak overlaps with existing peaks
            if self._is_valid_peak(peaks, start_sec, end_sec, min_gap_sec):
                rank = len(peaks) + 1
                peaks.append(
                    Peak(
                        start_sec=start_sec,
                        end_sec=end_sec,
                        value=value,
                        rank=rank,
                        surge_ratio=surge_ratio,
                    )
                )

                if len(peaks) >= topk:
                    break

        # Sort by rank
        peaks.sort(key=lambda p: p.rank)

        return peaks

    def _is_valid_peak(
        self,
        existing_peaks: list[Peak],
        start_sec: int,
        end_sec: int,
        min_gap_sec: int,
    ) -> bool:
        """Check if a peak is valid (doesn't overlap with existing peaks)."""
        for peak in existing_peaks:
            # Check if peaks are too close
            gap_start = abs(start_sec - peak.start_sec)
            gap_end = abs(start_sec - peak.end_sec)

            if gap_start < min_gap_sec or gap_end < min_gap_sec:
                return False

            # Check for overlap
            if not (end_sec <= peak.start_sec or start_sec >= peak.end_sec):
                return False

        return True

    def _refine_peaks_with_events(
        self,
        peaks: list[Peak],
        events_file: Path,
        window_sec: int,
    ) -> list[Peak]:
        """Refine peak timing with 1-second precision using raw events.

        Args:
            peaks: List of peaks from first pass (10-second precision)
            events_file: Path to events.jsonl file
            window_sec: Window size in seconds

        Returns:
            List of peaks with refined start times (1-second precision)
        """
        # Load events and extract t_ms for timing
        events_df = self._load_events_for_refinement(events_file)
        if events_df.empty:
            logger.warning("No events loaded for refinement, keeping original peaks")
            return peaks

        refined_peaks = []
        for peak in peaks:
            # Search region: ±60 seconds around original peak (wider for better precision)
            search_start = max(0, peak.start_sec - 60)
            search_end = peak.end_sec + 60

            # Extract events in search region
            region_events = events_df[
                (events_df["sec"] >= search_start) & (events_df["sec"] < search_end)
            ]

            if region_events.empty:
                refined_peaks.append(peak)
                continue

            # Build 1-second buckets for this region
            sec_counts = region_events.groupby("sec").size().reset_index(name="count")

            # Create full range of seconds (including zeros)
            all_secs = pd.DataFrame({"sec": range(search_start, search_end)})
            sec_counts = all_secs.merge(sec_counts, on="sec", how="left").fillna(0)
            sec_counts["count"] = sec_counts["count"].astype(int)

            # Find best 60-second window with 1-second sliding
            best_start = peak.start_sec
            best_value = 0

            for start in range(search_start, search_end - window_sec + 1):
                window_sum = sec_counts[
                    (sec_counts["sec"] >= start) & (sec_counts["sec"] < start + window_sec)
                ]["count"].sum()

                if window_sum > best_value:
                    best_value = window_sum
                    best_start = start

            # Create refined peak
            refined_peak = Peak(
                start_sec=best_start,
                end_sec=best_start + window_sec,
                value=int(best_value),
                rank=peak.rank,
                surge_ratio=peak.surge_ratio,
            )
            refined_peaks.append(refined_peak)

            if best_start != peak.start_sec:
                logger.info(
                    f"  Peak {peak.rank}: {peak.start_sec}s -> {best_start}s "
                    f"(+{best_start - peak.start_sec}s, value: {best_value})"
                )

        return refined_peaks

    def _load_events_for_refinement(self, events_file: Path) -> pd.DataFrame:
        """Load events from jsonl and extract timing information.

        Args:
            events_file: Path to events.jsonl

        Returns:
            DataFrame with 'sec' column (seconds from stream start)
        """
        events = []
        try:
            with open(events_file, "r") as f:
                for line in f:
                    if line.strip():
                        event = json.loads(line)
                        if "t_ms" in event:
                            events.append({"sec": event["t_ms"] // 1000})
        except Exception as e:
            logger.error(f"Error loading events for refinement: {e}")
            return pd.DataFrame()

        if not events:
            return pd.DataFrame()

        return pd.DataFrame(events)

    def save_peaks(self, peaks_output: PeaksOutput, output_file: Path):
        """Save peaks to JSON file."""
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(peaks_output.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        logger.info(f"Saved peaks to {output_file}")

    def generate_summary(self, peaks_output: PeaksOutput) -> dict:
        """Generate summary of detected peaks (based on volume)."""
        if not peaks_output.peaks_by_volume:
            return {
                "peak_count": 0,
                "total_activity": 0,
                "avg_peak_value": 0,
            }

        peak_values = [p.value for p in peaks_output.peaks_by_volume]

        return {
            "peak_count": len(peaks_output.peaks_by_volume),
            "total_activity": sum(peak_values),
            "avg_peak_value": sum(peak_values) / len(peak_values),
            "max_peak_value": max(peak_values),
            "min_peak_value": min(peak_values),
            "top_peak": {
                "rank": peaks_output.peaks_by_volume[0].rank,
                "start_sec": peaks_output.peaks_by_volume[0].start_sec,
                "end_sec": peaks_output.peaks_by_volume[0].end_sec,
                "value": peaks_output.peaks_by_volume[0].value,
            }
            if peaks_output.peaks_by_volume
            else None,
        }

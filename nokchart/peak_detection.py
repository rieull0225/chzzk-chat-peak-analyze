"""Peak detection module for finding chat activity peaks."""

import json
import logging
from pathlib import Path

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
        topk: int = 50,
        min_gap_sec: int = 120,
    ) -> PeaksOutput:
        """
        Detect peaks in chat activity using sliding window.

        Args:
            stream_id: Stream identifier
            window_sec: Window size in seconds for peak detection
            topk: Number of top peaks to return
            min_gap_sec: Minimum gap between peaks to avoid overlapping

        Returns:
            PeaksOutput containing detected peaks (both volume and surge based)
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

        # Find top peaks by volume
        peaks_by_volume = self._find_top_peaks(
            window_sums, window_sec, topk, min_gap_sec, sort_by="volume"
        )
        logger.info(f"Detected {len(peaks_by_volume)} peaks by volume")

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

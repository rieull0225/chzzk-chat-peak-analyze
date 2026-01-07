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
            PeaksOutput containing detected peaks
        """
        logger.info(
            f"Detecting peaks: window={window_sec}s, topk={topk}, min_gap={min_gap_sec}s"
        )

        # Load time series
        df = self._load_time_series()

        if df.empty:
            logger.warning("Empty time series")
            return PeaksOutput(stream_id=stream_id, window_sec=window_sec, peaks=[])

        # Calculate sliding window sums
        window_sums = self._calculate_window_sums(df, window_sec)

        # Find top peaks
        peaks = self._find_top_peaks(window_sums, window_sec, topk, min_gap_sec)

        logger.info(f"Detected {len(peaks)} peaks")

        return PeaksOutput(
            stream_id=stream_id,
            window_sec=window_sec,
            peaks=peaks,
        )

    def _load_time_series(self) -> pd.DataFrame:
        """Load time series from CSV file."""
        if not self.time_series_file.exists():
            logger.error(f"Time series file not found: {self.time_series_file}")
            return pd.DataFrame()

        df = pd.read_csv(self.time_series_file)

        if "sec" not in df.columns or "chat_count" not in df.columns:
            logger.error("Invalid time series format: missing 'sec' or 'chat_count' columns")
            return pd.DataFrame()

        logger.info(f"Loaded time series: {len(df)} rows")
        return df

    def _calculate_window_sums(self, df: pd.DataFrame, window_sec: int) -> pd.DataFrame:
        """Calculate surge scores combining rate of change and absolute volume."""
        df = df.copy()

        # 1. Absolute volume (rolling sum)
        df["window_sum"] = df["chat_count"].rolling(window=window_sec, min_periods=1).sum()

        # 2. Rate of change (급등 감지)
        # Use 5-second rolling average of chat count changes to smooth out noise
        df["chat_rate_change"] = df["chat_count"].diff().rolling(window=5, min_periods=1).mean()

        # 3. Normalize to 0-1 range (avoid division by zero)
        sum_max = df["window_sum"].max()
        sum_min = df["window_sum"].min()
        if sum_max > sum_min:
            df["norm_sum"] = (df["window_sum"] - sum_min) / (sum_max - sum_min)
        else:
            df["norm_sum"] = 0.0

        change_max = df["chat_rate_change"].max()
        change_min = df["chat_rate_change"].min()
        if change_max > change_min:
            df["norm_change"] = (df["chat_rate_change"] - change_min) / (change_max - change_min)
        else:
            df["norm_change"] = 0.0

        # 4. Surge score = 70% change rate + 30% absolute volume
        # This prioritizes sudden chat increases (급등) over sustained high volume
        df["surge_score"] = df["norm_change"] * 0.7 + df["norm_sum"] * 0.3

        return df

    def _find_top_peaks(
        self,
        df: pd.DataFrame,
        window_sec: int,
        topk: int,
        min_gap_sec: int,
    ) -> list[Peak]:
        """Find top K peaks with minimum gap constraint."""
        peaks = []

        # Sort by surge_score descending (급등 구간 우선)
        sorted_df = df.sort_values("surge_score", ascending=False)

        for _, row in sorted_df.iterrows():
            start_sec = int(row["sec"])
            end_sec = start_sec + window_sec
            # Store the actual chat count as value (for compatibility)
            value = int(row["window_sum"])

            # Check if this peak overlaps with existing peaks
            if self._is_valid_peak(peaks, start_sec, end_sec, min_gap_sec):
                rank = len(peaks) + 1
                peaks.append(
                    Peak(
                        start_sec=start_sec,
                        end_sec=end_sec,
                        value=value,
                        rank=rank,
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
        """Generate summary of detected peaks."""
        if not peaks_output.peaks:
            return {
                "peak_count": 0,
                "total_activity": 0,
                "avg_peak_value": 0,
            }

        peak_values = [p.value for p in peaks_output.peaks]

        return {
            "peak_count": len(peaks_output.peaks),
            "total_activity": sum(peak_values),
            "avg_peak_value": sum(peak_values) / len(peak_values),
            "max_peak_value": max(peak_values),
            "min_peak_value": min(peak_values),
            "top_peak": {
                "rank": peaks_output.peaks[0].rank,
                "start_sec": peaks_output.peaks[0].start_sec,
                "end_sec": peaks_output.peaks[0].end_sec,
                "value": peaks_output.peaks[0].value,
            }
            if peaks_output.peaks
            else None,
        }

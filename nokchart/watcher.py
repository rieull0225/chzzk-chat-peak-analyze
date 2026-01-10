"""Stream watcher that monitors channels and triggers collection."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from nokchart.collector import ChzzkChannelClient, Collector
from nokchart.models import Config, StreamStatus
from nokchart.aggregation import Aggregator
from nokchart.peak_detection import PeakDetector
from nokchart.visualization import ChartGenerator

logger = logging.getLogger(__name__)


class Watcher:
    """Watches channels for stream status changes and triggers collection."""

    def __init__(
        self,
        channel_ids: list[str],
        config: Config,
        channel_names: Optional[dict[str, str]] = None,
    ):
        self.channel_ids = channel_ids
        self.config = config
        self.channel_names = channel_names or {}

        # Create a ChzzkChannelClient for each channel
        self.clients: dict[str, ChzzkChannelClient] = {
            channel_id: ChzzkChannelClient(channel_id)
            for channel_id in channel_ids
        }

        self.active_collectors: dict[str, Collector] = {}
        self.previous_status: dict[str, StreamStatus] = {}
        self.running = False

    async def start(self):
        """Start watching channels."""
        self.running = True
        logger.info(f"Starting watcher for {len(self.channel_ids)} channels")

        try:
            while self.running:
                await self._check_all_channels()
                await asyncio.sleep(self.config.poll_interval_sec)
        except Exception as e:
            logger.error(f"Watcher error: {e}", exc_info=True)
            raise
        finally:
            await self._cleanup()

    async def stop(self):
        """Stop watching channels."""
        logger.info("Stopping watcher")
        self.running = False

    async def _check_all_channels(self):
        """Check status of all monitored channels."""
        tasks = [self._check_channel(channel_id) for channel_id in self.channel_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_channel(self, channel_id: str):
        """Check status of a single channel with retry logic."""
        retries = 0
        client = self.clients[channel_id]
        while retries < self.config.max_retries:
            try:
                stream_info = await client.get_stream_status()

                if stream_info is None:
                    logger.warning(f"Channel {channel_id} not found")
                    return

                previous = self.previous_status.get(channel_id, StreamStatus.OFFLINE)
                current = stream_info.status

                # Detect OFFLINE -> LIVE transition
                if previous == StreamStatus.OFFLINE and current == StreamStatus.LIVE:
                    logger.info(
                        f"Channel {channel_id} went live! Stream ID: {stream_info.stream_id}"
                    )
                    await self._start_collection(stream_info)

                # Detect LIVE -> OFFLINE transition
                elif previous == StreamStatus.LIVE and current == StreamStatus.OFFLINE:
                    logger.info(f"Channel {channel_id} went offline")
                    await self._stop_collection(channel_id)

                self.previous_status[channel_id] = current
                break

            except Exception as e:
                retries += 1
                wait_time = self.config.backoff_factor ** retries
                logger.warning(
                    f"Error checking channel {channel_id} (attempt {retries}): {e}. "
                    f"Retrying in {wait_time}s"
                )
                if retries < self.config.max_retries:
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to check channel {channel_id} after {retries} attempts")

    async def _start_collection(self, stream_info):
        """Start collecting chat events for a stream."""
        # Prevent duplicate collection
        if stream_info.stream_id in self.active_collectors:
            logger.warning(f"Collection already running for stream {stream_info.stream_id}")
            return

        # Create output directory with date folder
        from datetime import datetime, timezone
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Create directory name with streamer name if available
        streamer_name = self.channel_names.get(stream_info.channel_id)
        if streamer_name:
            # Remove "unknown_" prefix if present (when live_id is not available)
            clean_stream_id = stream_info.stream_id.replace("unknown_", "", 1)
            dir_name = f"{streamer_name}_{clean_stream_id}"
        else:
            dir_name = stream_info.stream_id

        output_dir = Path(self.config.outdir) / date_str / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get the client for this channel
        client = self.clients[stream_info.channel_id]

        # Create and start collector
        collector = Collector(
            stream_info=stream_info,
            output_dir=output_dir,
            client=client,
            idle_timeout_minutes=self.config.idle_timeout_minutes,
        )

        self.active_collectors[stream_info.stream_id] = collector

        # Run collector in background task
        asyncio.create_task(self._run_collector(collector, stream_info.stream_id))

    async def _run_collector(self, collector: Collector, stream_id: str):
        """Run collector and handle cleanup."""
        # Start collector in background
        collector_task = asyncio.create_task(collector.start())

        # Monitor for idle timeout with smart checking
        idle_detected = False
        stop_reason = None
        try:
            while not collector_task.done():
                # Check if collector is idle
                if collector.is_idle():
                    # Smart idle check: verify stream status and connection
                    should_stop, reason = await collector.check_stream_and_connection()

                    if should_stop:
                        logger.info(
                            f"Stream {stream_id} stopping: {reason}. "
                            "Stopping collection and processing data."
                        )
                        idle_detected = True
                        stop_reason = reason
                        await collector.stop()
                        break
                    else:
                        logger.info(
                            f"Stream {stream_id} idle check: {reason}. "
                            "Continuing collection (stream still active or reconnecting)."
                        )

                # Check every 10 seconds (more frequent for faster detection)
                await asyncio.sleep(10)

            # Wait for collector to finish
            await collector_task

        except Exception as e:
            logger.error(f"Collector error for stream {stream_id}: {e}", exc_info=True)
        finally:
            # Generate collection report
            report = collector.generate_report()
            if stop_reason:
                report["stop_reason"] = stop_reason
            report_path = collector.output_dir / "collection_report.json"

            import json

            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)

            logger.info(
                f"Collector for stream {stream_id} finished "
                f"(reason: {stop_reason or 'normal'}). Report: {report_path}"
            )

            # Process data if we have events
            if collector.event_count > 0:
                logger.info(f"Processing collected data for stream {stream_id}...")
                await self._process_stream_data(stream_id, collector.output_dir, idle_detected)

            # Remove from active collectors
            if stream_id in self.active_collectors:
                del self.active_collectors[stream_id]

    async def _process_stream_data(self, stream_id: str, output_dir: Path, idle_timeout: bool):
        """Process collected stream data: build time series, detect peaks, generate chart.

        Args:
            stream_id: Stream ID
            output_dir: Output directory containing events.jsonl
            idle_timeout: Whether processing was triggered by idle timeout
        """
        try:
            events_file = output_dir / "events.jsonl"
            if not events_file.exists():
                logger.error(f"events.jsonl not found in {output_dir}")
                return

            # Step 1: Build time series
            logger.info(f"[{stream_id}] Building time series...")
            aggregator = Aggregator(events_file)
            output_files = aggregator.build_time_series(
                output_dir=output_dir,
                bucket_sizes=[60, 300],  # 1분, 5분 단위
                rolling_window=self.config.rolling_sec,
            )

            if not output_files:
                logger.error(f"[{stream_id}] Failed to build time series")
                return

            ts_file = output_files.get("60s")  # Use 1-minute bucket for charts
            logger.info(f"[{stream_id}] Created time series: {ts_file}")

            # Step 2: Detect peaks
            logger.info(f"[{stream_id}] Detecting peaks...")
            detector = PeakDetector(ts_file)
            peaks_output = detector.detect_peaks(
                stream_id=stream_id,
                window_sec=self.config.peak_window_sec,
                topk=self.config.topk,
                min_gap_sec=self.config.min_peak_gap_sec,
            )

            peaks_file = output_dir / "peaks.json"
            detector.save_peaks(peaks_output, peaks_file)
            logger.info(
                f"[{stream_id}] Created peaks: {peaks_file} "
                f"({len(peaks_output.peaks_by_volume)} by volume, "
                f"{len(peaks_output.peaks_by_surge)} by surge)"
            )

            # Step 3: Generate chart
            logger.info(f"[{stream_id}] Generating chart...")
            chart_file = output_dir / "chart_chat_rate.png"
            generator = ChartGenerator(ts_file)
            generator.plot_chat_rate(
                output_file=chart_file,
                peaks=peaks_output,
            )
            logger.info(f"[{stream_id}] Created chart: {chart_file}")

            # Create report
            report_file = output_dir / "report.json"
            import json
            report = {
                "stream_id": stream_id,
                "processing_completed": datetime.now().isoformat(),
                "idle_timeout": idle_timeout,
                "peaks_count_by_volume": len(peaks_output.peaks_by_volume),
                "peaks_count_by_surge": len(peaks_output.peaks_by_surge),
                "files": {
                    "events": str(events_file),
                    "time_series": str(ts_file),
                    "peaks": str(peaks_file),
                    "chart": str(chart_file),
                }
            }
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)

            logger.info(f"[{stream_id}] Data processing completed! Report: {report_file}")

        except Exception as e:
            logger.error(f"[{stream_id}] Error processing stream data: {e}", exc_info=True)

    async def _stop_collection(self, channel_id: str):
        """Stop collection for a channel's active stream."""
        # Find active collector for this channel
        for stream_id, collector in list(self.active_collectors.items()):
            if collector.stream_info.channel_id == channel_id:
                logger.info(f"Stopping collection for stream {stream_id}")
                await collector.stop()

    async def _cleanup(self):
        """Clean up all active collectors."""
        logger.info("Cleaning up active collectors")
        for collector in list(self.active_collectors.values()):
            await collector.stop()

        # Wait a bit for collectors to finish
        await asyncio.sleep(2)

        # Close all channel clients
        for client in self.clients.values():
            await client.close()

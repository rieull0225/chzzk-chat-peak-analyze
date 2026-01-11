"""Command-line interface for NokChart."""

import asyncio
import json
import logging
import sys
from pathlib import Path

import click

from nokchart.aggregation import Aggregator
from nokchart.config import load_channels, load_channel_names, load_config
from nokchart.peak_detection import PeakDetector
from nokchart.topic_analysis import TopicAnalyzer, TopicsOutput
from nokchart.visualization import ChartGenerator
from nokchart.watcher import Watcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """NokChart - Chat trend collection and peak analysis tool for Chzzk streams."""
    pass


@cli.command()
@click.option(
    "--channels",
    type=click.Path(exists=True, path_type=Path),
    default="channels.yaml",
    help="Path to channels YAML file",
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default="config.yaml",
    help="Path to config YAML file",
)
def watch(channels: Path, config: Path):
    """Watch channels and automatically collect chat events when streams go live."""
    logger.info("Starting NokChart watcher")

    # Load configuration
    cfg = load_config(config)
    channel_ids = load_channels(channels)
    channel_names = load_channel_names(channels)

    if not channel_ids:
        logger.error("No channels configured. Please add channel IDs to channels.yaml")
        sys.exit(1)

    logger.info(f"Monitoring {len(channel_ids)} channels: {channel_ids}")

    # Create and start watcher
    watcher = Watcher(channel_ids=channel_ids, config=cfg, channel_names=channel_names)

    try:
        asyncio.run(watcher.start())
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, stopping watcher")
        asyncio.run(watcher.stop())


@cli.command()
@click.option("--channel", required=True, help="Channel ID to collect from")
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default="output",
    help="Output directory",
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default="config.yaml",
    help="Path to config YAML file",
)
def collect(channel: str, out: Path, config: Path):
    """Manually collect chat events from a live stream."""
    logger.info(f"Manual collection for channel: {channel}")
    logger.warning(
        "Manual collection requires the stream to be live. "
        "This is a manual trigger - use 'watch' for automatic collection."
    )

    # This would need actual implementation to get stream info
    click.echo("Manual collection not yet fully implemented.")
    click.echo("Please use 'nokchart watch' for automatic collection.")


@cli.command("build-ts")
@click.option(
    "--events",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to events.jsonl file",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    help="Output directory (defaults to same as events file)",
)
@click.option(
    "--buckets",
    default="1,5,60",
    help="Comma-separated bucket sizes in seconds",
)
@click.option(
    "--rolling",
    type=int,
    default=10,
    help="Rolling average window in seconds",
)
def build_ts(events: Path, out: Path, buckets: str, rolling: int):
    """Build time series from events.jsonl file."""
    logger.info(f"Building time series from {events}")

    # Parse bucket sizes
    bucket_sizes = [int(b.strip()) for b in buckets.split(",")]

    # Default output to same directory as events
    if out is None:
        out = events.parent

    out.mkdir(parents=True, exist_ok=True)

    # Create aggregator and build time series
    aggregator = Aggregator(events)
    output_files = aggregator.build_time_series(
        output_dir=out,
        bucket_sizes=bucket_sizes,
        rolling_window=rolling,
    )

    # Get statistics
    stats = aggregator.get_statistics()

    click.echo("\nTime series created:")
    for bucket, file_path in output_files.items():
        click.echo(f"  {bucket}: {file_path}")

    click.echo(f"\nStatistics:")
    click.echo(f"  Total events: {stats.get('total_events', 0)}")
    click.echo(f"  Chat events: {stats.get('chat_events', 0)}")
    click.echo(f"  Donation events: {stats.get('donation_events', 0)}")
    click.echo(f"  Duration: {stats.get('duration_sec', 0):.1f}s")


@cli.command()
@click.option(
    "--ts",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to time series CSV file",
)
@click.option(
    "--stream-id",
    required=True,
    help="Stream ID",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    help="Output file path for peaks.json",
)
@click.option(
    "--window",
    type=int,
    default=60,
    help="Peak detection window size in seconds",
)
@click.option(
    "--topk",
    type=int,
    default=50,
    help="Number of top peaks to extract",
)
@click.option(
    "--min-gap",
    type=int,
    default=120,
    help="Minimum gap between peaks in seconds",
)
def peaks(ts: Path, stream_id: str, out: Path, window: int, topk: int, min_gap: int):
    """Detect peaks in chat activity time series."""
    logger.info(f"Detecting peaks in {ts}")

    # Default output path
    if out is None:
        out = ts.parent / "peaks.json"

    # Create detector and find peaks
    detector = PeakDetector(ts)
    peaks_output = detector.detect_peaks(
        stream_id=stream_id,
        window_sec=window,
        topk=topk,
        min_gap_sec=min_gap,
    )

    # Save peaks
    detector.save_peaks(peaks_output, out)

    # Generate summary
    summary = detector.generate_summary(peaks_output)

    click.echo(f"\nPeaks saved to: {out}")
    click.echo(f"\nSummary:")
    click.echo(f"  Peak count: {summary['peak_count']}")
    click.echo(f"  Total activity: {summary['total_activity']}")
    if summary['peak_count'] > 0:
        click.echo(f"  Average peak value: {summary['avg_peak_value']:.1f}")
        click.echo(f"  Max peak value: {summary['max_peak_value']}")
        click.echo(f"\nTop peak:")
        top = summary['top_peak']
        click.echo(f"  Time: {top['start_sec']}s - {top['end_sec']}s")
        click.echo(f"  Value: {top['value']}")


@cli.command()
@click.option(
    "--events",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to events.jsonl file",
)
@click.option(
    "--stream-id",
    required=True,
    help="Stream ID",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    help="Output file path for topics.json",
)
@click.option(
    "--segment",
    type=int,
    default=300,
    help="Segment duration in seconds (default: 300 = 5 minutes)",
)
@click.option(
    "--topk",
    type=int,
    default=5,
    help="Number of top keywords per segment",
)
@click.option(
    "--min-freq",
    type=int,
    default=3,
    help="Minimum keyword frequency to include",
)
def topics(events: Path, stream_id: str, out: Path, segment: int, topk: int, min_freq: int):
    """Extract topic keywords from chat segments."""
    logger.info(f"Analyzing topics from {events}")

    # Default output path
    if out is None:
        out = events.parent / "topics.json"

    # Create analyzer and extract topics
    analyzer = TopicAnalyzer(segment_sec=segment, top_k=topk, min_keyword_freq=min_freq)
    topics_output = analyzer.analyze_events_file(events, stream_id)

    # Save topics
    with open(out, "w", encoding="utf-8") as f:
        f.write(topics_output.model_dump_json(indent=2))

    click.echo(f"\nTopics saved to: {out}")
    click.echo(f"\nSegments analyzed: {len(topics_output.segments)}")

    # Show sample topics
    if topics_output.segments:
        click.echo(f"\nSample topics:")
        for seg in topics_output.segments[:5]:
            if seg.keywords:
                click.echo(f"  {seg.start_time} - {seg.end_time}: {', '.join(seg.keywords[:3])}")


@cli.command()
@click.option(
    "--ts",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to time series CSV file",
)
@click.option(
    "--peaks",
    type=click.Path(exists=True, path_type=Path),
    help="Path to peaks.json file (optional)",
)
@click.option(
    "--topics",
    "topics_file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to topics.json file (optional)",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    help="Output file path for chart image",
)
@click.option(
    "--title",
    help="Chart title",
)
def plot(ts: Path, peaks: Path, topics_file: Path, out: Path, title: str):
    """Generate chat activity chart with optional topics track."""
    logger.info(f"Plotting chart from {ts}")

    # Default output path
    if out is None:
        out = ts.parent / "chart_chat_rate.png"

    # Load peaks if provided
    peaks_data = None
    if peaks:
        with open(peaks) as f:
            peaks_dict = json.load(f)
            from nokchart.models import PeaksOutput

            peaks_data = PeaksOutput(**peaks_dict)

    # Load topics if provided
    topics_data = None
    if topics_file:
        with open(topics_file, encoding="utf-8") as f:
            topics_dict = json.load(f)
            topics_data = TopicsOutput(**topics_dict)

    # Generate chart
    generator = ChartGenerator(ts)
    generator.plot_chat_rate(
        output_file=out,
        peaks=peaks_data,
        topics=topics_data,
        title=title,
    )

    click.echo(f"Chart saved to: {out}")


@cli.command()
@click.option(
    "--output",
    type=click.Path(exists=True, path_type=Path),
    default="output",
    help="Output directory to analyze",
)
@click.option(
    "--date",
    help="Specific date to analyze (YYYY-MM-DD). If not provided, shows all dates.",
)
def stats(output: Path, date: str):
    """Show collection statistics for all streams."""
    from datetime import datetime

    output_path = Path(output)
    if not output_path.exists():
        click.echo(f"❌ Output directory not found: {output_path}")
        sys.exit(1)

    # Find all stream directories
    stream_dirs = []
    if date:
        date_dir = output_path / date
        if date_dir.exists():
            stream_dirs = [d for d in date_dir.iterdir() if d.is_dir()]
    else:
        for date_dir in sorted(output_path.iterdir()):
            if date_dir.is_dir():
                stream_dirs.extend([d for d in date_dir.iterdir() if d.is_dir()])

    if not stream_dirs:
        click.echo("📭 No streams found")
        return

    click.echo(f"\n{'='*80}")
    click.echo(f"  📊 NokChart Collection Statistics")
    click.echo(f"{'='*80}\n")

    total_chats = 0
    total_donations = 0
    total_duration = 0

    for stream_dir in sorted(stream_dirs):
        events_file = stream_dir / "events.jsonl"
        if not events_file.exists():
            continue

        # Parse directory name
        dir_name = stream_dir.name
        date_str = stream_dir.parent.name

        # Load events
        events = []
        with open(events_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        if not events:
            continue

        # Calculate statistics
        chat_count = sum(1 for e in events if e.get('type') == 'chat')
        donation_count = sum(1 for e in events if e.get('type') == 'donation')

        # Parse timestamps (UTC -> KST)
        from datetime import datetime, timezone, timedelta
        kst = timezone(timedelta(hours=9))
        start_time_utc = datetime.fromisoformat(events[0]['received_at'].replace('Z', '+00:00'))
        end_time_utc = datetime.fromisoformat(events[-1]['received_at'].replace('Z', '+00:00'))
        start_time = start_time_utc.astimezone(kst)
        end_time = end_time_utc.astimezone(kst)
        duration_sec = (end_time - start_time).total_seconds()
        duration_min = duration_sec / 60

        # Chat rate
        chat_per_min = chat_count / duration_min if duration_min > 0 else 0

        # Load collection report if available
        report_file = stream_dir / "collection_report.json"
        reconnect_count = None
        error_count = None
        if report_file.exists():
            with open(report_file, 'r') as f:
                report = json.load(f)
                reconnect_count = report.get('reconnect_count', 0)
                error_count = report.get('error_count', 0)

        # Display
        click.echo(f"📅 {date_str}")
        click.echo(f"📁 {dir_name}")
        click.echo(f"")
        click.echo(f"  ⏱️  방송 시간: {start_time.strftime('%H:%M:%S')} ~ {end_time.strftime('%H:%M:%S')} ({duration_min:.1f}분)")
        click.echo(f"  💬 채팅 수: {chat_count:,}개")
        click.echo(f"  💰 후원 수: {donation_count}개")
        click.echo(f"  📈 분당 채팅: {chat_per_min:.1f}개/분")

        if reconnect_count is not None:
            status = "✅" if reconnect_count == 0 else "⚠️"
            click.echo(f"  {status} 재연결: {reconnect_count}회")

        if error_count is not None and error_count > 0:
            click.echo(f"  ❌ 에러: {error_count}회")

        click.echo(f"")
        click.echo(f"{'-'*80}\n")

        total_chats += chat_count
        total_donations += donation_count
        total_duration += duration_min

    # Summary
    if total_duration > 0:
        click.echo(f"{'='*80}")
        click.echo(f"  📊 전체 요약")
        click.echo(f"{'='*80}")
        click.echo(f"  총 방송 수: {len(stream_dirs)}개")
        click.echo(f"  총 방송 시간: {total_duration:.1f}분 ({total_duration/60:.1f}시간)")
        click.echo(f"  총 채팅 수: {total_chats:,}개")
        click.echo(f"  총 후원 수: {total_donations}개")
        click.echo(f"  평균 분당 채팅: {total_chats/total_duration:.1f}개/분")
        click.echo(f"{'='*80}\n")


@cli.command()
@click.option(
    "--stream-dir",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Stream output directory containing events.jsonl",
)
@click.option(
    "--stream-id",
    required=True,
    help="Stream ID",
)
@click.option(
    "--with-topics/--no-topics",
    default=True,
    help="Include topic analysis (default: enabled)",
)
@click.option(
    "--segment-sec",
    type=int,
    default=300,
    help="Topic segment duration in seconds (default: 300 = 5 minutes)",
)
def process(stream_dir: Path, stream_id: str, with_topics: bool, segment_sec: int):
    """Process a completed stream: build time series, detect peaks, analyze topics, and generate chart."""
    logger.info(f"Processing stream directory: {stream_dir}")

    events_file = stream_dir / "events.jsonl"
    if not events_file.exists():
        logger.error(f"events.jsonl not found in {stream_dir}")
        sys.exit(1)

    # Step 1: Build time series
    click.echo("Step 1: Building time series...")
    aggregator = Aggregator(events_file)
    output_files = aggregator.build_time_series(
        output_dir=stream_dir,
        bucket_sizes=[60, 300],  # 1분, 5분 단위
        rolling_window=600,  # 10분 rolling average
    )

    if not output_files:
        logger.error("Failed to build time series")
        sys.exit(1)

    ts_file = output_files.get("60s")  # Use 1-minute bucket
    click.echo(f"  Created: {ts_file}")

    # Step 2: Detect peaks
    click.echo("\nStep 2: Detecting peaks...")
    detector = PeakDetector(ts_file)
    peaks_output = detector.detect_peaks(
        stream_id=stream_id,
        window_sec=60,
        topk=20,
        min_gap_sec=120,
    )

    peaks_file = stream_dir / "peaks.json"
    detector.save_peaks(peaks_output, peaks_file)
    click.echo(f"  Created: {peaks_file}")
    click.echo(f"  Found {len(peaks_output.peaks_by_volume)} peaks (by volume), {len(peaks_output.peaks_by_surge)} peaks (by surge)")

    # Step 3: Analyze topics (optional)
    topics_output = None
    topics_file = None
    if with_topics:
        click.echo("\nStep 3: Analyzing topics...")
        analyzer = TopicAnalyzer(segment_sec=segment_sec, top_k=5, min_keyword_freq=3)
        topics_output = analyzer.analyze_events_file(events_file, stream_id)

        topics_file = stream_dir / "topics.json"
        with open(topics_file, "w", encoding="utf-8") as f:
            f.write(topics_output.model_dump_json(indent=2))

        click.echo(f"  Created: {topics_file}")
        click.echo(f"  Analyzed {len(topics_output.segments)} segments")

        # Show sample topics
        if topics_output.segments:
            click.echo(f"  Sample topics:")
            for seg in topics_output.segments[:3]:
                if seg.keywords:
                    click.echo(f"    {seg.start_time}: {', '.join(seg.keywords[:3])}")

    # Step 4: Generate chart
    step_num = 4 if with_topics else 3
    click.echo(f"\nStep {step_num}: Generating chart...")
    chart_file = stream_dir / "chart_chat_rate.png"
    generator = ChartGenerator(ts_file)
    generator.plot_chat_rate(
        output_file=chart_file,
        peaks=peaks_output,
        topics=topics_output,
    )
    click.echo(f"  Created: {chart_file}")

    # Generate report
    click.echo("\nGenerating report...")
    stats = aggregator.get_statistics()
    summary = detector.generate_summary(peaks_output)

    report = {
        "stream_id": stream_id,
        "processed_at": str(Path.cwd()),
        "files": {
            "events": str(events_file),
            "time_series": {k: str(v) for k, v in output_files.items()},
            "peaks": str(peaks_file),
            "chart": str(chart_file),
        },
        "statistics": stats,
        "peaks_summary": summary,
    }

    if topics_file:
        report["files"]["topics"] = str(topics_file)
        report["topics_segments"] = len(topics_output.segments) if topics_output else 0

    report_file = stream_dir / "report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    click.echo(f"  Created: {report_file}")
    click.echo("\nProcessing complete!")


if __name__ == "__main__":
    cli()

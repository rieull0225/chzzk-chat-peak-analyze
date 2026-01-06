"""Tests for data models."""

from nokchart.models import ChatEvent, EventType, Peak, PeaksOutput


def test_chat_event_creation():
    """Test creating a chat event."""
    event = ChatEvent(
        stream_id="test_stream",
        type=EventType.CHAT,
        t_ms=1000,
        user="test_user",
        text="test message",
    )

    assert event.stream_id == "test_stream"
    assert event.type == EventType.CHAT
    assert event.t_ms == 1000
    assert event.user == "test_user"
    assert event.text == "test message"


def test_donation_event_creation():
    """Test creating a donation event."""
    event = ChatEvent(
        stream_id="test_stream",
        type=EventType.DONATION,
        t_ms=2000,
        amount=5000,
        text="donation message",
    )

    assert event.type == EventType.DONATION
    assert event.amount == 5000


def test_peak_creation():
    """Test creating a peak."""
    peak = Peak(
        start_sec=100,
        end_sec=160,
        value=150,
        rank=1,
    )

    assert peak.start_sec == 100
    assert peak.end_sec == 160
    assert peak.value == 150
    assert peak.rank == 1


def test_peaks_output_creation():
    """Test creating peaks output."""
    peaks = [
        Peak(start_sec=100, end_sec=160, value=150, rank=1),
        Peak(start_sec=300, end_sec=360, value=120, rank=2),
    ]

    output = PeaksOutput(
        stream_id="test_stream",
        window_sec=60,
        peaks=peaks,
    )

    assert output.stream_id == "test_stream"
    assert output.window_sec == 60
    assert len(output.peaks) == 2
    assert output.peaks[0].rank == 1
    assert output.peaks[1].rank == 2

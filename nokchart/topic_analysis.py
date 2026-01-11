"""Topic analysis module for extracting keywords from chat segments."""

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Try to import kiwipiepy for Korean morphological analysis
try:
    from kiwipiepy import Kiwi

    KIWI_AVAILABLE = True
except ImportError:
    KIWI_AVAILABLE = False
    logger.warning("kiwipiepy not installed. Using simple word extraction.")


class TopicSegment(BaseModel):
    """A time segment with representative chat samples."""

    start_sec: int
    end_sec: int
    keywords: list[str]  # Top keywords for this segment (for reference)
    sample_chats: list[str]  # Representative chat messages
    chat_count: int  # Number of chats in this segment

    @property
    def start_time(self) -> str:
        """Format start time as HH:MM:SS."""
        h, m, s = self.start_sec // 3600, (self.start_sec % 3600) // 60, self.start_sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    @property
    def end_time(self) -> str:
        """Format end time as HH:MM:SS."""
        h, m, s = self.end_sec // 3600, (self.end_sec % 3600) // 60, self.end_sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    @property
    def label(self) -> str:
        """Get display label for this segment (first sample chat)."""
        if not self.sample_chats:
            return ""
        # Return first sample, truncated if too long
        first = self.sample_chats[0]
        if len(first) > 30:
            return first[:27] + "..."
        return first


class TopicsOutput(BaseModel):
    """Output model for topic analysis results."""

    stream_id: str
    segment_sec: int  # Segment duration in seconds
    segments: list[TopicSegment]


# Patterns to filter out
EMOJI_PATTERN = re.compile(r"\{:[^}]+:\}")  # Chzzk emojis like {:a11Aaaa2222:}
REPEAT_PATTERN = re.compile(r"(.)\1{3,}")  # Repeated characters like ㅋㅋㅋㅋ
URL_PATTERN = re.compile(r"https?://\S+")
SPECIAL_CHARS = re.compile(r"[^\w\s가-힣]")

# Common stopwords for Korean chat
STOPWORDS = {
    # Particles and connectors
    "은", "는", "이", "가", "을", "를", "의", "에", "에서", "로", "으로", "와", "과", "도", "만",
    "부터", "까지", "보다", "처럼", "같이", "한테", "에게", "께", "라고", "고", "면", "니까",
    # Common verbs/adjectives (too generic)
    "하다", "있다", "없다", "되다", "이다", "아니다", "같다", "보다", "알다", "모르다",
    "하는", "있는", "없는", "되는", "하고", "있고", "해서", "있어", "없어", "하면",
    # Chat noise
    "ㅋ", "ㅎ", "ㅠ", "ㅜ", "ㄱ", "ㄴ", "ㅇ", "ㅁ", "ㅅ", "ㄷ", "ㄹ", "ㅂ", "ㅈ", "ㅊ", "ㅍ",
    "ㅋㅋ", "ㅋㅋㅋ", "ㅎㅎ", "ㅎㅎㅎ", "ㅠㅠ", "ㅜㅜ", "ㅠㅠㅠ", "ㅜㅜㅜ",
    # Common interjections
    "아", "오", "우", "에", "이", "음", "흠", "헉", "헐", "와", "우와", "오오", "아아",
    "네", "응", "엉", "웅", "예", "ㅇㅇ", "ㄴㄴ", "ㅇㅋ", "ㄱㅇ",
    # Time/quantity
    "지금", "오늘", "내일", "어제", "이제", "아직", "벌써", "좀", "많이", "조금", "진짜", "정말",
    # Pronouns
    "나", "너", "저", "우리", "저희", "그", "이", "저", "여기", "거기", "저기",
    # Common stream chat
    "방송", "채팅", "시청", "구독",
}


@dataclass
class ChatEvent:
    """Simple chat event for topic analysis."""

    t_ms: int
    text: str


class TopicAnalyzer:
    """Analyzes chat messages to extract topic keywords per time segment."""

    def __init__(self, segment_sec: int = 300, top_k: int = 5, min_keyword_freq: int = 3):
        """
        Initialize topic analyzer.

        Args:
            segment_sec: Duration of each segment in seconds (default: 5 minutes)
            top_k: Number of top keywords to extract per segment
            min_keyword_freq: Minimum frequency for a keyword to be included
        """
        self.segment_sec = segment_sec
        self.top_k = top_k
        self.min_keyword_freq = min_keyword_freq

        # Initialize Kiwi if available
        self.kiwi: Optional["Kiwi"] = None
        if KIWI_AVAILABLE:
            self.kiwi = Kiwi()
            logger.info("Kiwi morphological analyzer initialized")

    def analyze_events_file(self, events_file: Path, stream_id: str) -> TopicsOutput:
        """
        Analyze events.jsonl file and extract topics.

        Args:
            events_file: Path to events.jsonl file
            stream_id: Stream ID for the output

        Returns:
            TopicsOutput with segments and keywords
        """
        logger.info(f"Analyzing topics from {events_file}")

        # Load events
        events = self._load_events(events_file)
        if not events:
            logger.warning("No events found")
            return TopicsOutput(stream_id=stream_id, segment_sec=self.segment_sec, segments=[])

        # Group events by segment
        segments = self._analyze_segments(events)

        return TopicsOutput(stream_id=stream_id, segment_sec=self.segment_sec, segments=segments)

    def _load_events(self, events_file: Path) -> list[ChatEvent]:
        """Load chat events from JSONL file."""
        events = []

        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    # Only process chat events with text
                    if data.get("type") == "chat" and data.get("text"):
                        events.append(ChatEvent(t_ms=data["t_ms"], text=data["text"]))
                except json.JSONDecodeError:
                    continue

        logger.info(f"Loaded {len(events)} chat events")
        return events

    def _analyze_segments(self, events: list[ChatEvent]) -> list[TopicSegment]:
        """Group events into segments and extract keywords + sample chats."""
        if not events:
            return []

        # Find time range
        max_ms = max(e.t_ms for e in events)
        max_sec = max_ms // 1000

        segments = []
        for start_sec in range(0, max_sec + 1, self.segment_sec):
            end_sec = start_sec + self.segment_sec

            # Get events in this segment
            segment_events = [e for e in events if start_sec * 1000 <= e.t_ms < end_sec * 1000]

            if not segment_events:
                continue

            texts = [e.text for e in segment_events]

            # Extract keywords
            keywords = self._extract_keywords(texts)

            # Extract representative sample chats
            sample_chats = self._select_sample_chats(texts, keywords)

            segments.append(
                TopicSegment(
                    start_sec=start_sec,
                    end_sec=end_sec,
                    keywords=keywords,
                    sample_chats=sample_chats,
                    chat_count=len(segment_events),
                )
            )

        logger.info(f"Analyzed {len(segments)} segments")
        return segments

    def _select_sample_chats(self, texts: list[str], keywords: list[str], max_samples: int = 3) -> list[str]:
        """
        Select representative sample chats from segment.

        Args:
            texts: All chat texts in segment
            keywords: Extracted keywords for this segment
            max_samples: Maximum number of samples to return

        Returns:
            List of representative chat messages
        """
        # Filter and score chats
        candidates = []

        for text in texts:
            # Skip emoji-only messages
            cleaned = EMOJI_PATTERN.sub("", text).strip()
            if not cleaned or len(cleaned) < 4:
                continue

            # Skip repetitive characters only (ㅋㅋㅋ, ㅠㅠㅠ, etc.)
            if REPEAT_PATTERN.match(cleaned):
                continue

            # Score by keyword matches
            score = sum(1 for kw in keywords if kw in text)

            # Bonus for reasonable length (not too short, not too long)
            if 5 <= len(cleaned) <= 50:
                score += 1

            candidates.append((text, score, len(cleaned)))

        if not candidates:
            return []

        # Sort by score (desc), then by length (prefer medium length)
        candidates.sort(key=lambda x: (-x[1], abs(x[2] - 20)))

        # Select diverse samples (avoid duplicates)
        selected = []
        seen_texts = set()

        for text, score, length in candidates:
            # Normalize for duplicate check
            normalized = text.lower().strip()
            if normalized in seen_texts:
                continue

            selected.append(text)
            seen_texts.add(normalized)

            if len(selected) >= max_samples:
                break

        return selected

    def _extract_keywords(self, texts: list[str]) -> list[str]:
        """Extract top keywords from a list of texts."""
        # Clean and tokenize
        all_words = []

        for text in texts:
            words = self._tokenize(text)
            all_words.extend(words)

        # Count frequencies
        counter = Counter(all_words)

        # Filter by minimum frequency
        filtered = [(word, count) for word, count in counter.items() if count >= self.min_keyword_freq]

        # Sort by frequency and get top K
        top_words = sorted(filtered, key=lambda x: x[1], reverse=True)[: self.top_k]

        return [word for word, _ in top_words]

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into meaningful words."""
        # Remove emojis and URLs
        text = EMOJI_PATTERN.sub("", text)
        text = URL_PATTERN.sub("", text)

        # Use Kiwi for morphological analysis if available
        if self.kiwi:
            return self._tokenize_with_kiwi(text)

        # Fallback: simple word extraction
        return self._tokenize_simple(text)

    def _tokenize_with_kiwi(self, text: str) -> list[str]:
        """Tokenize using Kiwi morphological analyzer."""
        words = []

        try:
            result = self.kiwi.tokenize(text)
            for token in result:
                word = token.form
                tag = token.tag

                # Only keep nouns (NNG, NNP), verbs (VV), adjectives (VA)
                if tag.startswith(("NNG", "NNP", "VV", "VA")):
                    # Skip short words and stopwords
                    if len(word) >= 2 and word not in STOPWORDS:
                        words.append(word)
        except Exception as e:
            logger.warning(f"Kiwi tokenization failed: {e}")
            return self._tokenize_simple(text)

        return words

    def _tokenize_simple(self, text: str) -> list[str]:
        """Simple tokenization without morphological analysis."""
        # Remove special characters except Korean/alphanumeric
        text = SPECIAL_CHARS.sub(" ", text)

        # Collapse repeated characters
        text = REPEAT_PATTERN.sub(r"\1\1", text)

        # Split into words
        words = text.split()

        # Filter
        result = []
        for word in words:
            word = word.strip()
            # Skip short words, stopwords, and pure numbers
            if len(word) >= 2 and word not in STOPWORDS and not word.isdigit():
                result.append(word)

        return result


def analyze_topics(
    events_file: Path,
    stream_id: str,
    segment_sec: int = 300,
    top_k: int = 5,
    min_freq: int = 3,
) -> TopicsOutput:
    """
    Convenience function to analyze topics from events file.

    Args:
        events_file: Path to events.jsonl
        stream_id: Stream ID
        segment_sec: Segment duration in seconds
        top_k: Number of top keywords per segment
        min_freq: Minimum keyword frequency

    Returns:
        TopicsOutput with topic segments
    """
    analyzer = TopicAnalyzer(segment_sec=segment_sec, top_k=top_k, min_keyword_freq=min_freq)
    return analyzer.analyze_events_file(events_file, stream_id)

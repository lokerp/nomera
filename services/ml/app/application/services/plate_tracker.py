from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.models import BoundingBox, DetectionEvent, PlateDetection
from app.domain.enums import CameraRole

logger = logging.getLogger(__name__)


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,
                prev_row[j + 1] + 1,
                prev_row[j] + cost,
            ))
        prev_row = curr_row

    return prev_row[-1]


@dataclass
class _TrackedPlate:
    """Internal state for a plate being tracked."""
    canonical_text: str
    text_votes: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    detections: list[PlateDetection] = field(default_factory=list)
    best_bbox: BoundingBox | None = None
    best_bbox_area: float = 0.0
    best_frame: int = 0
    best_timestamp: float = 0.0
    best_region_name: str = ""
    frame_width: int = 0
    frame_height: int = 0
    first_seen_time: float = 0.0
    last_seen_time: float = 0.0
    total_count: int = 0
    event_emitted: bool = False
    snapshot_jpeg: bytes | None = None


class PlateTracker:
    """
    Tracks license plates across frames with deduplication and voting.

    Logic:
    1. Groups detections by plate text (fuzzy matching with Levenshtein ≤ 1).
    2. Accumulates "votes" for each text variant over a sliding window.
    3. Emits a DetectionEvent once a plate reaches min_confirmations.
    4. Marks plates as "departed" if not seen for departure_timeout seconds.
    """

    def __init__(
        self,
        camera_id: str,
        camera_role: CameraRole,
        min_confirmations: int = 3,
        window_sec: float = 10.0,
        departure_sec: float = 5.0,
    ) -> None:
        self._camera_id = camera_id
        self._camera_role = camera_role
        self._min_confirmations = min_confirmations
        self._window_sec = window_sec
        self._departure_sec = departure_sec

        # key = canonical plate text, value = tracking state
        self._tracked: dict[str, _TrackedPlate] = {}
        self._events_emitted: int = 0

    def _find_matching_key(self, text: str) -> str | None:
        """Find an existing tracked plate with Levenshtein distance ≤ 1."""
        for key in self._tracked:
            if _levenshtein_distance(text, key) <= 1:
                return key
        return None

    def update(
        self,
        detections: list[PlateDetection],
        frame_width: int,
        frame_height: int,
        snapshot_getter: callable = None,
    ) -> list[DetectionEvent]:
        """
        Feed new detections from a frame. Returns any newly confirmed events.

        Args:
            detections: Filtered PlateDetection list from the current frame(s).
            snapshot_getter: Optional callable(frame_number) -> bytes (JPEG)
                             to capture the frame snapshot.

        Returns:
            List of newly emitted DetectionEvent objects.
        """
        now = time.monotonic()
        events: list[DetectionEvent] = []

        for det in detections:
            text = det.plate_text.strip().upper()
            if not text:
                continue

            # Try to match to an existing tracked plate
            existing_key = self._find_matching_key(text)

            if existing_key is not None:
                tracked = self._tracked[existing_key]
            else:
                tracked = _TrackedPlate(
                    canonical_text=text,
                    first_seen_time=now,
                )
                self._tracked[text] = tracked

            # Update tracking state
            tracked.text_votes[text] += 1
            tracked.last_seen_time = now
            tracked.total_count += 1

            # Keep track of best (largest) bbox for the snapshot
            if det.bbox.area > tracked.best_bbox_area:
                tracked.best_bbox = det.bbox
                tracked.best_bbox_area = det.bbox.area
                tracked.best_frame = det.frame_number
                tracked.best_timestamp = det.timestamp
                tracked.best_region_name = det.region_name
                tracked.frame_width = frame_width
                tracked.frame_height = frame_height
                if snapshot_getter is not None:
                    try:
                        tracked.snapshot_jpeg = snapshot_getter(det.frame_number)
                    except Exception:
                        pass

            # Check if we can emit an event
            if not tracked.event_emitted and tracked.total_count >= self._min_confirmations:
                event = self._create_event(tracked)
                events.append(event)
                tracked.event_emitted = True
                self._events_emitted += 1
                logger.info(
                    "Plate confirmed: %s (%d votes, camera=%s)",
                    event.plate_text,
                    tracked.total_count,
                    self._camera_id,
                )

        # Clean up departed plates
        self._cleanup_departed(now)

        return events

    def _create_event(self, tracked: _TrackedPlate) -> DetectionEvent:
        """Create a DetectionEvent from tracked plate state."""
        # Choose the text variant with most votes
        best_text = max(tracked.text_votes, key=tracked.text_votes.get)

        # Average confidence from votes
        avg_confidence = tracked.best_bbox.confidence if tracked.best_bbox else 0.0

        now_dt = datetime.now(timezone.utc)

        return DetectionEvent(
            plate_text=best_text,
            bbox=tracked.best_bbox,
            camera_id=self._camera_id,
            camera_role=self._camera_role,
            region_name=tracked.best_region_name,
            confidence=avg_confidence,
            first_seen=now_dt,
            last_seen=now_dt,
            occurrences=tracked.total_count,
            frame_number=tracked.best_frame,
            timestamp_seconds=tracked.best_timestamp,
            frame_width=tracked.frame_width,
            frame_height=tracked.frame_height,
            snapshot_jpeg=tracked.snapshot_jpeg,
        )

    def _cleanup_departed(self, now: float) -> None:
        """Remove plates that haven't been seen recently."""
        departed_keys = []
        for key, tracked in self._tracked.items():
            if now - tracked.last_seen_time > self._departure_sec:
                departed_keys.append(key)

        for key in departed_keys:
            tracked = self._tracked.pop(key)
            logger.debug(
                "Plate departed: %s (was seen %d times)",
                tracked.canonical_text,
                tracked.total_count,
            )

    @property
    def active_plates_count(self) -> int:
        return len(self._tracked)

    @property
    def events_emitted(self) -> int:
        return self._events_emitted

    def reset(self) -> None:
        """Clear all tracking state."""
        self._tracked.clear()
        self._events_emitted = 0

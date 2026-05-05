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


def _bbox_iou(a: BoundingBox, b: BoundingBox) -> float:
    """Intersection-over-Union for two bounding boxes."""
    x_left = max(a.x1, b.x1)
    y_top = max(a.y1, b.y1)
    x_right = min(a.x2, b.x2)
    y_bottom = min(a.y2, b.y2)

    inter_w = max(0.0, x_right - x_left)
    inter_h = max(0.0, y_bottom - y_top)
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0

    union = max(1e-6, a.area + b.area - inter_area)
    return inter_area / union


def _bbox_center_distance(a: BoundingBox, b: BoundingBox) -> float:
    ax, ay = a.center
    bx, by = b.center
    dx = ax - bx
    dy = ay - by
    return (dx * dx + dy * dy) ** 0.5


def _bbox_reference_size(a: BoundingBox, b: BoundingBox) -> float:
    # A stable per-pair scale used to normalize center distance.
    return max(1.0, (a.width + b.width + a.height + b.height) / 4.0)


@dataclass
class _TrackedPlate:
    """Internal state for a plate being tracked."""
    canonical_text: str
    text_votes: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    text_confidence_sum: dict[str, float] = field(default_factory=lambda: defaultdict(float))
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


@dataclass
class _RecentEvent:
    plate_text: str
    bbox: BoundingBox | None
    emitted_at: float


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
        max_text_distance: int = 1,
        spatial_match_iou: float = 0.45,
        spatial_match_window_sec: float = 1.5,
        max_spatial_text_distance: int = 10,
        spatial_match_center_distance_factor: float = 2.5,
        duplicate_event_iou: float = 0.35,
        duplicate_event_window_sec: float = 4.0,
        duplicate_event_text_distance: int = 2,
        duplicate_event_center_distance_factor: float = 3.0,
    ) -> None:
        self._camera_id = camera_id
        self._camera_role = camera_role
        self._min_confirmations = min_confirmations
        self._window_sec = window_sec
        self._departure_sec = departure_sec
        self._max_text_distance = max_text_distance
        self._spatial_match_iou = spatial_match_iou
        self._spatial_match_window_sec = spatial_match_window_sec
        self._max_spatial_text_distance = max_spatial_text_distance
        self._spatial_match_center_distance_factor = spatial_match_center_distance_factor
        self._duplicate_event_iou = duplicate_event_iou
        self._duplicate_event_window_sec = duplicate_event_window_sec
        self._duplicate_event_text_distance = duplicate_event_text_distance
        self._duplicate_event_center_distance_factor = duplicate_event_center_distance_factor

        # key = canonical plate text, value = tracking state
        self._tracked: dict[str, _TrackedPlate] = {}
        self._recent_events: list[_RecentEvent] = []
        self._events_emitted: int = 0

    def _find_matching_key(self, detection: PlateDetection, now: float) -> str | None:
        """
        Find an existing tracked plate.

        Matching strategy:
        1) strict text match by Levenshtein distance;
        2) fallback spatial match (IoU + recency) to merge OCR variants
           of the same physical plate.
        """
        text = detection.plate_text.strip().upper()

        strict_candidates: list[tuple[int, float, int, str]] = []
        for key, tracked in self._tracked.items():
            text_distance = _levenshtein_distance(text, key)
            if text_distance <= self._max_text_distance:
                age = now - tracked.last_seen_time
                strict_candidates.append((text_distance, age, -tracked.total_count, key))

        if strict_candidates:
            strict_candidates.sort()
            return strict_candidates[0][3]

        spatial_candidates: list[tuple[float, float, int, str]] = []
        for key, tracked in self._tracked.items():
            if tracked.best_bbox is None:
                continue

            age = now - tracked.last_seen_time
            if age > self._spatial_match_window_sec:
                continue

            text_distance = _levenshtein_distance(text, key)
            if text_distance > self._max_spatial_text_distance:
                continue

            iou = _bbox_iou(detection.bbox, tracked.best_bbox)
            center_distance = _bbox_center_distance(detection.bbox, tracked.best_bbox)
            ref_size = _bbox_reference_size(detection.bbox, tracked.best_bbox)
            center_factor = center_distance / ref_size
            spatially_close = center_factor <= self._spatial_match_center_distance_factor

            if iou < self._spatial_match_iou and not spatially_close:
                continue

            spatial_candidates.append((iou, -center_factor, -age, -text_distance, key))

        if not spatial_candidates:
            return None

        spatial_candidates.sort(reverse=True)
        return spatial_candidates[0][4]

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
            existing_key = self._find_matching_key(det, now)

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
            tracked.text_confidence_sum[text] += float(max(det.confidence, det.bbox.confidence))
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
                tracked.event_emitted = True
                if self._is_probable_duplicate_event(event, now):
                    logger.debug(
                        "Suppressed duplicate event: %s (camera=%s)",
                        event.plate_text,
                        self._camera_id,
                    )
                else:
                    events.append(event)
                    self._events_emitted += 1
                    self._recent_events.append(
                        _RecentEvent(
                            plate_text=event.plate_text,
                            bbox=event.bbox,
                            emitted_at=now,
                        )
                    )
                    logger.info(
                        "Plate confirmed: %s (%d votes, camera=%s)",
                        event.plate_text,
                        tracked.total_count,
                        self._camera_id,
                    )

        # Clean up departed plates
        self._cleanup_departed(now)
        self._cleanup_recent_events(now)

        return events

    def _is_probable_duplicate_event(self, event: DetectionEvent, now: float) -> bool:
        if event.bbox is None:
            return False

        for recent in self._recent_events:
            age = now - recent.emitted_at
            if age > self._duplicate_event_window_sec:
                continue
            if recent.bbox is None:
                continue

            text_distance = _levenshtein_distance(event.plate_text, recent.plate_text)
            if text_distance > self._duplicate_event_text_distance:
                continue

            iou = _bbox_iou(event.bbox, recent.bbox)
            center_distance = _bbox_center_distance(event.bbox, recent.bbox)
            ref_size = _bbox_reference_size(event.bbox, recent.bbox)
            center_factor = center_distance / ref_size
            spatially_close = center_factor <= self._duplicate_event_center_distance_factor

            if iou >= self._duplicate_event_iou or spatially_close:
                return True

        return False

    def _create_event(self, tracked: _TrackedPlate) -> DetectionEvent:
        """Create a DetectionEvent from tracked plate state."""
        # Choose text by votes first, then by accumulated confidence.
        best_text = max(
            tracked.text_votes,
            key=lambda t: (tracked.text_votes[t], tracked.text_confidence_sum.get(t, 0.0)),
        )

        best_text_votes = max(1, tracked.text_votes.get(best_text, 1))
        best_text_conf = tracked.text_confidence_sum.get(best_text, 0.0) / best_text_votes
        avg_confidence = max(best_text_conf, tracked.best_bbox.confidence if tracked.best_bbox else 0.0)

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

    def _cleanup_recent_events(self, now: float) -> None:
        self._recent_events = [
            item
            for item in self._recent_events
            if now - item.emitted_at <= self._duplicate_event_window_sec
        ]

    @property
    def active_plates_count(self) -> int:
        return len(self._tracked)

    @property
    def events_emitted(self) -> int:
        return self._events_emitted

    def reset(self) -> None:
        """Clear all tracking state."""
        self._tracked.clear()
        self._recent_events.clear()
        self._events_emitted = 0

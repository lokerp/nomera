from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.config import Settings
from app.domain.enums import CameraRole, PipelineStatus
from app.domain.interfaces import IEventSender, IPlateDetector
from app.domain.models import CameraConfig, PlateDetection
from app.application.filters.zone_filter import ZoneFilter
from app.application.filters.size_filter import SizeFilter
from app.application.services.plate_tracker import PlateTracker
from app.infrastructure.video.opencv_source import OpenCVSource

logger = logging.getLogger(__name__)


@dataclass
class CameraState:
    """Runtime state of a single camera processing task."""
    config: CameraConfig
    task: asyncio.Task | None = None
    is_active: bool = False
    frames_processed: int = 0
    detections_count: int = 0
    last_error: str | None = None
    started_at: float = field(default_factory=time.monotonic)


class DetectionService:
    """
    Main orchestrator: manages cameras, runs detection pipeline,
    applies filters, tracks plates, and pushes events to backend.
    """

    def __init__(
        self,
        detector: IPlateDetector,
        event_sender: IEventSender,
        settings: Settings,
    ) -> None:
        self._detector = detector
        self._sender = event_sender
        self._settings = settings
        self._cameras: dict[str, CameraState] = {}
        self._status = PipelineStatus.STOPPED
        self._start_time: float = 0.0

    @property
    def status(self) -> PipelineStatus:
        return self._status

    @property
    def cameras(self) -> dict[str, CameraState]:
        return self._cameras

    @property
    def uptime(self) -> float:
        if self._start_time == 0:
            return 0.0
        return time.monotonic() - self._start_time

    async def add_camera(self, config: CameraConfig) -> str:
        """Register a camera. Returns camera_id."""
        if config.camera_id in self._cameras:
            raise ValueError(f"Camera {config.camera_id} already exists")

        state = CameraState(config=config)
        self._cameras[config.camera_id] = state
        logger.info("Camera added: %s (%s) source=%s", config.camera_id, config.role.value, config.source)

        # Pipeline must work 24/7: keep it running and attach new cameras automatically.
        if self._status == PipelineStatus.RUNNING:
            await self._start_camera(config.camera_id)
        else:
            await self.start()

        return config.camera_id

    async def remove_camera(self, camera_id: str) -> None:
        """Stop and remove a camera."""
        if camera_id not in self._cameras:
            raise ValueError(f"Camera {camera_id} not found")

        await self._stop_camera(camera_id)
        del self._cameras[camera_id]
        logger.info("Camera removed: %s", camera_id)

    async def start(self) -> None:
        """Start processing all registered cameras."""
        if self._status == PipelineStatus.RUNNING:
            logger.warning("Pipeline is already running")
            return

        self._status = PipelineStatus.RUNNING
        self._start_time = time.monotonic()

        for camera_id in self._cameras:
            await self._start_camera(camera_id)

        logger.info("Pipeline started with %d camera(s)", len(self._cameras))

    async def stop(self) -> None:
        """Stop processing all cameras."""
        for camera_id in list(self._cameras.keys()):
            await self._stop_camera(camera_id)

        self._status = PipelineStatus.STOPPED
        logger.info("Pipeline stopped")

    async def _start_camera(self, camera_id: str) -> None:
        """Launch processing task for a single camera."""
        state = self._cameras[camera_id]
        if state.task is not None and not state.task.done():
            return

        state.is_active = True
        state.started_at = time.monotonic()
        state.task = asyncio.create_task(
            self._process_camera(camera_id),
            name=f"camera-{camera_id}",
        )
        logger.info("Camera processing started: %s", camera_id)

    async def _stop_camera(self, camera_id: str) -> None:
        """Cancel processing task for a single camera."""
        state = self._cameras.get(camera_id)
        if state is None:
            return

        state.is_active = False
        if state.task is not None and not state.task.done():
            state.task.cancel()
            try:
                await state.task
            except asyncio.CancelledError:
                pass
        state.task = None
        logger.info("Camera processing stopped: %s", camera_id)

    async def _process_camera(self, camera_id: str) -> None:
        """
        Main processing loop for a single camera.
        Runs in its own asyncio task.
        """
        state = self._cameras[camera_id]
        config = state.config

        try:
            source = OpenCVSource(config.source, frame_skip=self._settings.frame_skip)
        except RuntimeError as e:
            state.last_error = str(e)
            state.is_active = False
            logger.error("Failed to open camera %s: %s", camera_id, e)
            return

        frame_w, frame_h = source.get_frame_size()

        # Initialize filters
        zone_filter = ZoneFilter(
            roi=config.roi_zone,
            frame_width=frame_w,
            frame_height=frame_h,
        )
        size_filter = SizeFilter(
            min_area_pct=self._settings.min_bbox_area_pct,
            frame_width=frame_w,
            frame_height=frame_h,
        )

        # Initialize tracker
        tracker = PlateTracker(
            camera_id=camera_id,
            camera_role=config.role,
            min_confirmations=self._settings.tracker_min_confirmations,
            window_sec=self._settings.tracker_window_sec,
            departure_sec=self._settings.tracker_departure_sec,
            max_text_distance=self._settings.tracker_max_text_distance,
            spatial_match_iou=self._settings.tracker_spatial_match_iou,
            spatial_match_window_sec=self._settings.tracker_spatial_match_window_sec,
            max_spatial_text_distance=self._settings.tracker_max_spatial_text_distance,
            spatial_match_center_distance_factor=self._settings.tracker_spatial_match_center_distance_factor,
            duplicate_event_iou=self._settings.tracker_duplicate_event_iou,
            duplicate_event_window_sec=self._settings.tracker_duplicate_event_window_sec,
            duplicate_event_text_distance=self._settings.tracker_duplicate_event_text_distance,
            duplicate_event_center_distance_factor=self._settings.tracker_duplicate_event_center_distance_factor,
            winner_min_margin=self._settings.tracker_winner_min_margin,
        )

        # Frame buffer for batch processing
        batch_frames: list[np.ndarray] = []
        batch_meta: list[tuple[int, float]] = []  # (frame_no, timestamp)
        last_frame_cache: dict[int, np.ndarray] = {}  # small cache for snapshots
        _log_every = 200  # log a heartbeat every N frames processed

        try:
            for frame_no, timestamp, frame in source.frames():
                if not state.is_active:
                    break

                batch_frames.append(frame)
                batch_meta.append((frame_no, timestamp))
                last_frame_cache[frame_no] = frame

                # Keep cache small
                if len(last_frame_cache) > self._settings.batch_size * 2:
                    oldest_keys = sorted(last_frame_cache.keys())[:-self._settings.batch_size]
                    for k in oldest_keys:
                        del last_frame_cache[k]

                if len(batch_frames) >= self._settings.batch_size:
                    events = await self._process_batch(
                        camera_id,
                        config.role,
                        batch_frames,
                        batch_meta,
                        zone_filter,
                        size_filter,
                        tracker,
                        last_frame_cache,
                        frame_w,
                        frame_h,
                    )
                    state.frames_processed += len(batch_frames)

                    if state.frames_processed % _log_every < self._settings.batch_size:
                        logger.info(
                            "Camera %s heartbeat: %d frames processed, %d total detections",
                            camera_id,
                            state.frames_processed,
                            state.detections_count,
                        )

                    # Send events to backend
                    for event in events:
                        state.detections_count += 1
                        await self._sender.send(event)

                    batch_frames.clear()
                    batch_meta.clear()

                    # Yield to event loop so API stays responsive
                    await asyncio.sleep(0)

            # Process remaining frames in buffer
            if batch_frames:
                events = await self._process_batch(
                    camera_id,
                    config.role,
                    batch_frames,
                    batch_meta,
                    zone_filter,
                    size_filter,
                    tracker,
                    last_frame_cache,
                    frame_w,
                    frame_h,
                )
                state.frames_processed += len(batch_frames)
                for event in events:
                    state.detections_count += 1
                    await self._sender.send(event)

        except asyncio.CancelledError:
            logger.info("Camera %s processing cancelled", camera_id)
            raise
        except Exception as e:
            state.last_error = str(e)
            logger.exception("Error processing camera %s", camera_id)
        finally:
            source.release()
            state.is_active = False
            logger.info(
                "Camera %s finished: %d frames, %d detections",
                camera_id,
                state.frames_processed,
                state.detections_count,
            )

    async def _process_batch(
        self,
        camera_id: str,
        camera_role: CameraRole,
        frames: list[np.ndarray],
        meta: list[tuple[int, float]],
        zone_filter: ZoneFilter,
        size_filter: SizeFilter,
        tracker: PlateTracker,
        frame_cache: dict[int, np.ndarray],
        frame_w: int,
        frame_h: int,
    ) -> list["DetectionEvent"]:
        """Process a batch of frames through the full pipeline."""
        loop = asyncio.get_event_loop()

        # Run detector in thread pool to avoid blocking event loop
        batch_detections = await loop.run_in_executor(
            None,
            self._detector.detect,
            frames,
        )

        all_events = []

        for i, frame_dets in enumerate(batch_detections):
            frame_no, timestamp = meta[i]
            frame_dets = frame_dets or []

            # Enrich detections with frame metadata
            for det in frame_dets:
                det.frame_number = frame_no
                det.timestamp = timestamp

            # Apply filters
            filtered = zone_filter.apply(frame_dets)
            filtered = size_filter.apply(filtered)

            if filtered:
                logger.info(
                    "Raw detections camera=%s frame=%d count=%d plates=%s",
                    camera_id,
                    frame_no,
                    len(filtered),
                    ", ".join(f"{item.plate_text}:{item.confidence:.2f}" for item in filtered),
                )

            await self._sender.send_raw(
                camera_id=camera_id,
                camera_role=camera_role,
                frame_number=frame_no,
                timestamp_seconds=timestamp,
                frame_width=frame_w,
                frame_height=frame_h,
                detections=filtered,
            )

            if not filtered:
                continue

            # Snapshot getter for the tracker
            def make_snapshot(fn: int, cache=frame_cache, w=frame_w) -> bytes | None:
                f = cache.get(fn)
                if f is None:
                    return None
                _, jpeg = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return jpeg.tobytes()

            # Update tracker and get confirmed events
            events = tracker.update(
                filtered,
                frame_width=frame_w,
                frame_height=frame_h,
                snapshot_getter=make_snapshot,
            )
            for event in events:
                logger.info(
                    "Confirmed plate camera=%s plate=%s conf=%.2f occurrences=%d",
                    camera_id,
                    event.plate_text,
                    event.confidence,
                    event.occurrences,
                )
            all_events.extend(events)

        return all_events

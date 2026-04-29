"""
Download and verify official nomeroff-net models.

The nomeroff-net package downloads model configs and weights lazily when its
pipeline is created. Keep this script intentionally small: it exercises that
official path and avoids maintaining local hand-written model configs.
"""
from __future__ import annotations

import argparse
import logging
import sys

import cv2

from app.infrastructure.detector.nomeroff_detector import NomeroffDetector


def main() -> int:
    parser = argparse.ArgumentParser(description="Warm up nomeroff-net model cache")
    parser.add_argument(
        "--source",
        help="Optional video/image path for one-frame inference after warmup",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    detector = NomeroffDetector()
    detector.warmup()

    if args.source:
        cap = cv2.VideoCapture(args.source)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            print(f"Could not read first frame from {args.source}", file=sys.stderr)
            return 1

        detections = detector.detect([frame])[0]
        print(f"Warmup ok. First-frame detections: {len(detections)}")
        for detection in detections:
            print(
                f"  {detection.plate_text} "
                f"bbox=({detection.bbox.x1:.0f},{detection.bbox.y1:.0f},"
                f"{detection.bbox.x2:.0f},{detection.bbox.y2:.0f}) "
                f"confidence={detection.confidence:.3f}"
            )
        return 0

    print("Warmup ok. Official nomeroff-net models are cached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

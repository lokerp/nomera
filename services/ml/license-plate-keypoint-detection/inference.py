"""
License Plate Keypoint Detection - Inference Pipeline
Model: YOLOv8m-Pose fine-tuned for license plate corner detection
Keypoints: 4 corners (Top-Left, Top-Right, Bottom-Right, Bottom-Left)
"""

import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO


class LicensePlateKeypointDetector:
    """
    Detects license plate corner keypoints and supports blur, logo replacement,
    and video processing.
    """

    def __init__(
        self,
        model_path="license_plate_keypoint.pt",
        conf_threshold=0.25,
        keypoint_conf_threshold=0.5,
        min_avg_keypoint_conf=0.6,
        min_plate_area=100,
    ):
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.keypoint_conf_threshold = keypoint_conf_threshold
        self.min_avg_keypoint_conf = min_avg_keypoint_conf
        self.min_plate_area = min_plate_area

    def detect(self, image):
        """
        Detect license plate and return 4 corner keypoints.

        Args:
            image: file path (str/Path) or numpy BGR image array

        Returns:
            dict with keys:
                success (bool)
                keypoints (list of 4 [x,y] points, TL/TR/BR/BL order)
                confidence (float) — detection confidence
                bbox (list [x1,y1,x2,y2])
                message (str)
        """
        if isinstance(image, (str, Path)):
            img = cv2.imread(str(image))
            if img is None:
                return {"success": False, "message": f"Cannot load image: {image}"}
        else:
            img = image

        results = self.model(img, conf=self.conf_threshold, verbose=False)
        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            return {"success": False, "message": "No license plate detected"}

        result = results[0]
        if result.keypoints is None or len(result.keypoints) == 0:
            return {"success": False, "message": "No keypoints detected"}

        box = result.boxes[0]
        kpts = result.keypoints[0]

        confidence = float(box.conf[0])
        bbox = box.xyxy[0].cpu().numpy().tolist()
        coords = kpts.xy[0].cpu().numpy()

        # Filter keypoints by confidence if available
        if kpts.conf is not None:
            kpt_confs = kpts.conf[0].cpu().numpy()
            valid = [(c, v) for c, v in zip(coords, kpt_confs) if v > self.keypoint_conf_threshold]
            if len(valid) != 4:
                return {"success": False, "message": f"Only {len(valid)}/4 keypoints confident enough"}
            avg_conf = sum(v for _, v in valid) / 4
            if avg_conf < self.min_avg_keypoint_conf:
                return {"success": False, "message": f"Low avg keypoint confidence: {avg_conf:.3f}"}
            keypoints = [list(map(float, c)) for c, _ in valid]
        else:
            keypoints = [list(map(float, c)) for c in coords if c[0] > 0 and c[1] > 0]
            if len(keypoints) != 4:
                return {"success": False, "message": f"Expected 4 keypoints, got {len(keypoints)}"}

        # Check minimum area
        area = cv2.contourArea(np.array(keypoints, dtype=np.float32))
        if area < self.min_plate_area:
            return {"success": False, "message": f"Plate area too small: {area:.1f}px"}

        return {
            "success": True,
            "keypoints": keypoints,
            "confidence": confidence,
            "bbox": bbox,
            "message": "Detection successful",
        }

    @staticmethod
    def _order_points(pts):
        """Order 4 points: TL, TR, BR, BL."""
        pts = np.array(pts, dtype="float32")
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # TL: smallest sum
        rect[2] = pts[np.argmax(s)]   # BR: largest sum
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # TR: smallest diff
        rect[3] = pts[np.argmax(diff)]  # BL: largest diff
        return rect

    def blur_plate(self, image, blur_strength=21, output_path=None):
        """
        Detect plate and apply Gaussian blur over the plate region.

        Args:
            image: file path or numpy array
            blur_strength: Gaussian kernel size (must be odd, default 21)
            output_path: optional path to save result

        Returns:
            numpy array of the result image, or None if detection failed
        """
        if isinstance(image, (str, Path)):
            img = cv2.imread(str(image))
        else:
            img = image.copy()

        result = self.detect(img)
        if not result["success"]:
            print(f"Blur skipped: {result['message']}")
            return None

        pts = self._order_points(result["keypoints"])
        mask = np.zeros(img.shape[:2], dtype=np.uint8)
        cv2.fillConvexPoly(mask, pts.astype(np.int32), 255)

        blurred = cv2.GaussianBlur(img, (blur_strength, blur_strength), 0)
        output = img.copy()
        output[mask == 255] = blurred[mask == 255]

        if output_path:
            cv2.imwrite(str(output_path), output)
        return output

    def replace_logo(self, image, logo_path, output_path=None, feather=5, enhance=True):
        """
        Detect plate and replace it with a logo using perspective transform.

        Args:
            image: file path or numpy array
            logo_path: path to logo image (PNG with alpha supported)
            output_path: optional path to save result
            feather: edge feathering amount (pixels)
            enhance: apply sharpening to logo before placement

        Returns:
            numpy array of the result image, or None if detection failed
        """
        if isinstance(image, (str, Path)):
            img = cv2.imread(str(image))
        else:
            img = image.copy()

        logo = cv2.imread(str(logo_path), cv2.IMREAD_UNCHANGED)
        if logo is None:
            raise ValueError(f"Cannot load logo: {logo_path}")
        if logo.shape[2] == 4:
            logo = logo[:, :, :3]

        result = self.detect(img)
        if not result["success"]:
            print(f"Logo replace skipped: {result['message']}")
            return None

        dst_pts = self._order_points(result["keypoints"])

        w1 = int(np.linalg.norm(dst_pts[1] - dst_pts[0]))
        w2 = int(np.linalg.norm(dst_pts[2] - dst_pts[3]))
        h1 = int(np.linalg.norm(dst_pts[3] - dst_pts[0]))
        h2 = int(np.linalg.norm(dst_pts[2] - dst_pts[1]))
        W, H = max(w1, w2), max(h1, h2)

        if W < 20 or H < 10:
            print("Warning: plate region too small for logo placement")
            return img

        logo_resized = cv2.resize(logo, (W * 2, H * 2), interpolation=cv2.INTER_LANCZOS4)
        if enhance:
            kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
            logo_resized = np.clip(cv2.filter2D(logo_resized, -1, kernel), 0, 255).astype(np.uint8)
        logo_final = cv2.resize(logo_resized, (W, H), interpolation=cv2.INTER_AREA)

        src_pts = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], dtype="float32")
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(
            logo_final, M, (img.shape[1], img.shape[0]),
            flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT
        )

        mask = np.zeros(img.shape[:2], dtype=np.uint8)
        cv2.fillConvexPoly(mask, dst_pts.astype(np.int32), 255)
        if feather > 0:
            mask = cv2.GaussianBlur(mask, (feather * 2 + 1, feather * 2 + 1), 0)

        mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR).astype(float) / 255.0
        output = (img.astype(float) * (1 - mask_3ch) + warped.astype(float) * mask_3ch)
        output = np.clip(output, 0, 255).astype(np.uint8)

        if output_path:
            cv2.imwrite(str(output_path), output)
        return output

    def process_video(self, video_path, output_path=None, blur=True, logo_path=None, blur_strength=21):
        """
        Process a video: detect and blur/replace plates frame by frame.

        Args:
            video_path: path to input video
            output_path: path to save output video (default: input_blurred.mp4)
            blur: if True, blur the plate; if False, use logo_path for replacement
            logo_path: path to logo image (required if blur=False)
            blur_strength: Gaussian blur kernel size
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if output_path is None:
            p = Path(video_path)
            output_path = p.parent / f"{p.stem}_processed.mp4"

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        processed = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if blur:
                out_frame = self.blur_plate(frame, blur_strength=blur_strength)
            else:
                out_frame = self.replace_logo(frame, logo_path)

            writer.write(out_frame if out_frame is not None else frame)
            processed += 1
            if processed % 50 == 0:
                print(f"Processed {processed}/{frame_count} frames")

        cap.release()
        writer.release()
        print(f"Saved: {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="License Plate Keypoint Detection")
    parser.add_argument("input", help="Path to image or video")
    parser.add_argument("--model", default="license_plate_keypoint.pt", help="Model path")
    parser.add_argument("--output", default=None, help="Output path")
    parser.add_argument("--mode", choices=["detect", "blur", "logo"], default="blur")
    parser.add_argument("--logo", default=None, help="Logo path (for --mode logo)")
    parser.add_argument("--conf", type=float, default=0.25)
    args = parser.parse_args()

    detector = LicensePlateKeypointDetector(args.model, conf_threshold=args.conf)
    input_path = Path(args.input)

    if input_path.suffix.lower() in [".mp4", ".avi", ".mov", ".mkv"]:
        detector.process_video(
            args.input,
            output_path=args.output,
            blur=(args.mode != "logo"),
            logo_path=args.logo,
        )
    else:
        if args.mode == "detect":
            result = detector.detect(args.input)
            print(result)
        elif args.mode == "blur":
            out = detector.blur_plate(args.input, output_path=args.output or "blurred.jpg")
            print("Saved blurred image." if out is not None else "Detection failed.")
        elif args.mode == "logo":
            if not args.logo:
                print("Error: --logo required for logo mode")
            else:
                out = detector.replace_logo(args.input, args.logo, output_path=args.output or "replaced.jpg")
                print("Saved logo-replaced image." if out is not None else "Detection failed.")

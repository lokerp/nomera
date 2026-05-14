---
license: apache-2.0
tags:
  - object-detection
  - keypoint-detection
  - license-plate
  - yolov8
  - pose-estimation
  - computer-vision
  - ultralytics
datasets:
  - roboflow
model-index:
  - name: license-plate-keypoint-detection
    results:
      - task:
          type: keypoint-detection
        metrics:
          - type: mAP
            value: 0.9875
            name: "Box mAP@50"
          - type: mAP
            value: 0.8412
            name: "Box mAP@50-95"
          - type: mAP
            value: 0.9264
            name: "Pose mAP@50"
          - type: mAP
            value: 0.9137
            name: "Pose mAP@50-95"
language:
  - en
pipeline_tag: object-detection
---

# License Plate Keypoint Detection

A fine-tuned **YOLOv8m-Pose** model that detects vehicle license plates and precisely localizes their **4 corner keypoints** (top-left, top-right, bottom-right, bottom-left). Designed for downstream tasks like logo replacement, plate anonymization, and perspective-corrected OCR.

---

## Model Details

| Property | Value |
|---|---|
| **Base Model** | YOLOv8m-Pose (Ultralytics) |
| **Task** | Object Detection + Keypoint Estimation |
| **Classes** | 1 (`Plate`) |
| **Keypoints** | 4 corners per plate (TL, TR, BR, BL) |
| **Input Size** | 640 × 640 px |
| **Model Size** | ~101 MB |
| **Framework** | PyTorch / Ultralytics |

---

## Performance Metrics

Evaluated on the held-out validation set (24 images):

| Metric | Value |
|---|---|
| Box Precision | 0.977 |
| Box Recall | 0.947 |
| **Box mAP@50** | **0.9875** |
| Box mAP@50-95 | 0.8412 |
| Pose Precision | 0.934 |
| Pose Recall | 0.898 |
| **Pose mAP@50** | **0.9264** |
| Pose mAP@50-95 | 0.9137 |

> Model fully trained for all 150 epochs, achieving best-in-class performance at the final checkpoint.

---

## Training Details

| Parameter | Value |
|---|---|
| Epochs | 150 |
| Batch Size | 16 |
| Image Size | 640 × 640 |
| Optimizer | SGD (auto) |
| Learning Rate | 0.01 → 0.01 |
| Momentum | 0.937 |
| Weight Decay | 0.0005 |
| Pose Loss Weight | 12.0 |
| Keypoint Object Loss | 2.0 |
| Warmup Epochs | 3 |
| Augmentations | Mosaic, HSV, Flip-LR, Scale, Shear, Rotation |
| Device | CUDA GPU |

### Dataset

- **Source**: Roboflow — `license-plate-new` dataset (v3)
- **License**: CC BY 4.0
- **Train**: 19000 images
- **Validation**: 2400 images
- **Test**: 2400 images
- **Annotation**: YOLO Pose format, 4 keypoints per plate (x, y, visibility)

---

## Quick Start

### Installation

```bash
pip install ultralytics opencv-python numpy
```

### Basic Inference

```python
from ultralytics import YOLO
import cv2

# Load model
model = YOLO("license_plate_keypoint.pt")

# Run inference on an image
results = model("car.jpg", conf=0.25)

for result in results:
    if result.keypoints is not None:
        for kpts in result.keypoints:
            # kpts.xy shape: [4, 2]  — (x, y) for each of the 4 corners
            corners = kpts.xy[0].cpu().numpy()
            print("TL:", corners[0])
            print("TR:", corners[1])
            print("BR:", corners[2])
            print("BL:", corners[3])
```

### Using the Full Inference Pipeline

```python
from inference import LicensePlateKeypointDetector

detector = LicensePlateKeypointDetector("license_plate_keypoint.pt")

# Detect keypoints only
result = detector.detect("car.jpg")
if result["success"]:
    print("Keypoints:", result["keypoints"])
    print("Confidence:", result["confidence"])

# Detect and blur the plate
blurred = detector.blur_plate("car.jpg", output_path="blurred.jpg")

# Detect and replace with a logo
replaced = detector.replace_logo("car.jpg", "logo.png", output_path="out.jpg")
```

### Batch Processing

```python
from inference import LicensePlateKeypointDetector
from pathlib import Path

detector = LicensePlateKeypointDetector("license_plate_keypoint.pt")

for img_path in Path("input_images").glob("*.jpg"):
    result = detector.detect(str(img_path))
    if result["success"]:
        print(f"{img_path.name}: {result['keypoints']}")
```

### Video Processing

```python
from inference import LicensePlateKeypointDetector

detector = LicensePlateKeypointDetector("license_plate_keypoint.pt")
detector.process_video("input.mp4", output_path="output.mp4", blur=True)
```

---

## Keypoint Order

The model outputs **4 keypoints per detected plate** in this fixed order:

```
0: Top-Left     (TL)
1: Top-Right    (TR)
2: Bottom-Right (BR)
3: Bottom-Left  (BL)
```

Each keypoint has `(x, y, visibility)` values. Visibility > 0.5 means the point is reliably detected.

---

## Use Cases

- **Plate Anonymization** — Blur or mask license plates for privacy compliance
- **Logo Replacement** — Replace plates with custom logos using perspective transform
- **OCR Pre-processing** — Extract and warp plate regions for accurate text recognition
- **Dataset Annotation** — Auto-annotate corner keypoints for further training
- **Traffic Monitoring** — Track vehicle plates in video streams

---

## Limitations

- Trained primarily on clear, front-facing license plate images
- Performance may degrade on heavily occluded, night-time, or extreme-angle plates
- Best results at image resolution ≥ 640px
- Optimized for standard rectangular license plates

---

## Files

| File | Description |
|---|---|
| `license_plate_keypoint.pt` | Fine-tuned YOLOv8m-Pose model weights (~101 MB) |
| `inference.py` | Full inference pipeline with blur, logo replacement, video support |
| `requirements.txt` | Python dependencies |
| `config.json` | Default inference configuration |

---

## Citation

If you use this model, please cite:

```bibtex
@misc{prasanna2024licenseplatepose,
  title   = {License Plate Keypoint Detection using YOLOv8 Pose},
  author  = {Prasanna B},
  year    = {2025},
  publisher = {Hugging Face},
  url     = {https://huggingface.co/PrasannaBAImodel/license-plate-keypoint-detection}
}
```

---

## License

This model is released under the **Apache 2.0 License**.  
Base model (YOLOv8) is © Ultralytics, released under AGPL-3.0.  
Training data from Roboflow under CC BY 4.0.

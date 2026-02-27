# FloodWatch AI — Multimodal Flood Scene Analysis

The multimodal AI and computer vision layer of the FloodWatch disaster intelligence system. Processes citizen-captured flood media (video or image) and extracts structured flood intelligence using **Amazon Bedrock Nova** and **YOLOv8**.

## Architecture

```
input (video/image)
    │
    ▼
┌──────────────┐
│ video_utils  │  Extract representative frame
└──────┬───────┘
       │
   ┌───┴───┐
   ▼       ▼
┌──────┐ ┌──────────┐
│ Nova │ │ YOLOv8s  │  Semantic analysis + depth estimation
└──┬───┘ └────┬─────┘
   │          │
   ▼          ▼
┌──────────────────┐
│    pipeline.py   │  Fuse results → unified JSON
└──────────────────┘
```

## Setup

```bash
pip install -r requirements.txt
```

**AWS credentials** must be configured for Bedrock access (`aws configure` or environment variables).

## Usage

```bash
# Analyze a flood image
python main.py flood_photo.jpg

# Analyze a flood video with JSON output
python main.py flood_video.mp4 --output result.json

# Verbose logging
python main.py input.mp4 -v --output result.json
```

## Output Format

```json
{
  "input_file": "flood_video.mp4",
  "submergence_ratio": 0.5,
  "severity": "high",
  "people_trapped": false,
  "vehicles_submerged": true,
  "infrastructure_damage": false,
  "reference_object": "car",
  "confidence": 0.87,
  "description": "Severe urban flooding with vehicles partially submerged."
}
```

## YOLO Model Training

### High-Accuracy Training (v2)

Upgrade from YOLOv8n baseline (mAP50≈0.69) to YOLOv8s (target mAP50 ≥ 0.80):

| Setting | Baseline | High-Accuracy |
|---------|----------|---------------|
| Model | YOLOv8n | **YOLOv8s** |
| Resolution | 640px | **768px** |
| Epochs | 40 | **100** |
| Augmentations | Default | Mosaic + HSV + Flip + Scale + Mixup |

**Train locally (GPU required):**
```bash
python scripts/audit_labels.py --fix          # Clean annotations
python scripts/balance_classes.py --balance   # Balance class distribution
python train_flood_yolo_highacc.py            # Train YOLOv8s
```

**Train on Google Colab (recommended):**
Upload `train_flood_colab.ipynb` → set GPU runtime → run all cells.

### Dataset Tools

```bash
# Expand dataset (Roboflow API)
python scripts/download_additional_floods.py --api-key YOUR_KEY

# Audit label quality
python scripts/audit_labels.py --fix --report audit_report.json

# Analyze/balance class distribution
python scripts/balance_classes.py --balance
```

## Model Fallback Chain

The detector automatically selects the best available model:

1. `models/yolov8_flood_highacc.pt` — High-accuracy flood-tuned
2. `models/yolov8_flood.pt` — Baseline flood-tuned
3. `yolov8s.pt` — COCO-pretrained (auto-downloaded)

## Project Structure

```
flood-watch-ai/
├── main.py                        # CLI entry point
├── requirements.txt               # Dependencies
├── train_flood_yolo_highacc.py    # High-accuracy training script
├── train_flood_colab.ipynb        # Google Colab training notebook
├── evaluate_flood_model.py        # Model evaluation & comparison
├── src/
│   ├── __init__.py
│   ├── video_utils.py             # Frame extraction (OpenCV)
│   ├── nova_client.py             # Amazon Bedrock Nova client
│   ├── yolo_detector.py           # YOLOv8 detection + depth estimation
│   ├── pipeline.py                # Fusion pipeline
│   ├── validation.py              # Depth detection validation
│   └── lambda_handler.py          # Lambda wrapper
├── scripts/
│   ├── download_additional_floods.py  # Dataset expansion
│   ├── audit_labels.py                # Label quality auditing
│   └── balance_classes.py             # Class distribution balancing
├── data/
│   ├── flood_dataset.yaml         # Dataset config
│   └── flood_dataset/             # YOLO-format dataset
├── models/                        # Trained model weights
└── tests/
    ├── test_video_utils.py
    ├── test_yolo_detector.py
    ├── test_pipeline.py
    ├── test_phase2_completion.py
    └── test_lambda_handler.py
```

## Testing

```bash
python -m pytest tests/ -v
```

Tests use mocks and synthetic data — no AWS credentials or GPU required.

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
│ Nova │ │ YOLOv8   │  Semantic analysis + depth estimation
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
  "water_depth_cm": 37.5,
  "severity": "high",
  "people_trapped": false,
  "vehicles_submerged": true,
  "infrastructure_damage": false,
  "reference_object": "car",
  "confidence": 0.87,
  "description": "Severe urban flooding with vehicles partially submerged."
}
```

## Project Structure

```
flood-watch-ai/
├── main.py              # CLI entry point
├── requirements.txt     # Dependencies
├── src/
│   ├── __init__.py
│   ├── video_utils.py   # Frame extraction (OpenCV)
│   ├── nova_client.py   # Amazon Bedrock Nova client
│   ├── yolo_detector.py # YOLOv8 detection + depth estimation
│   └── pipeline.py      # Fusion pipeline
└── tests/
    ├── __init__.py
    ├── test_video_utils.py
    ├── test_yolo_detector.py
    └── test_pipeline.py
```

## Testing

```bash
python -m pytest tests/ -v
```

Tests use mocks and synthetic data — no AWS credentials or GPU required.

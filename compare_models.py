"""
compare_models.py — Side-by-side comparison of YOLO vs Bedrock Nova Lite.

Usage:
    python compare_models.py test_flood_image.jpg

Runs:
  1. YOLOv8 (local) using best.pt
  2. Bedrock Nova Lite (cloud) via AWS SDK
  
Prints both results for comparison.
"""

import json
import sys
import os
import logging
import base64

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("compare")

# ================================================================
#  YOLO LOCAL INFERENCE
# ================================================================

def run_yolo(image_path, model_path="best.pt"):
    """Run YOLOv8 detection and submergence estimation locally."""
    import cv2
    from src.yolo_detector import estimate_depth

    logger.info(f"[YOLO] Loading image: {image_path}")
    frame = cv2.imread(image_path)
    if frame is None:
        return {"error": "Failed to load image"}

    logger.info(f"[YOLO] Running inference with {model_path}...")
    result = estimate_depth(frame, model_path=model_path)

    return {
        "model": "YOLOv8 (best.pt — local)",
        "submergence_ratio": result.get("submergence_ratio"),
        "reference_object": result.get("reference_object"),
        "confidence": result.get("confidence"),
    }


# ================================================================
#  BEDROCK NOVA LITE INFERENCE
# ================================================================

def run_nova_lite(image_path):
    """Call Bedrock Nova Lite with the flood image."""
    import boto3

    logger.info(f"[Nova Lite] Encoding image to base64...")
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    ext = os.path.splitext(image_path)[1].lower()
    fmt = "png" if ext == ".png" else "jpeg"

    prompt = """Analyze this flood image and respond strictly in JSON:
{
  "people_trapped": boolean,
  "infrastructure_damage": boolean,
  "severity": "low" or "medium" or "high",
  "submergence_ratio": float between 0 and 1
}"""

    client = boto3.client("bedrock-runtime", region_name="us-east-1")

    logger.info("[Nova Lite] Invoking amazon.nova-lite-v1:0...")
    try:
        response = client.converse(
            modelId="amazon.nova-lite-v1:0",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": fmt,
                                "source": {"bytes": image_bytes},
                            }
                        },
                        {"text": prompt},
                    ],
                }
            ],
            inferenceConfig={
                "maxTokens": 120,
                "temperature": 0.1,
            },
        )

        # Extract text
        raw_text = ""
        for block in response["output"]["message"]["content"]:
            if "text" in block:
                raw_text += block["text"]

        # Clean markdown fencing
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(l for l in lines if not l.strip().startswith("```"))

        result = json.loads(cleaned)
        result["model"] = "Amazon Nova Lite (Bedrock — cloud)"
        return result

    except Exception as e:
        logger.error(f"[Nova Lite] Error: {e}")
        return {"model": "Amazon Nova Lite", "error": str(e)}


# ================================================================
#  MAIN
# ================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python compare_models.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.isfile(image_path):
        print(f"File not found: {image_path}")
        sys.exit(1)

    print("=" * 60)
    print("  FloodWatch — Model Comparison")
    print(f"  Input: {image_path}")
    print("=" * 60)

    # Run YOLO
    print("\n--- Running YOLOv8 (local) ---")
    yolo_result = run_yolo(image_path)
    print(json.dumps(yolo_result, indent=2))

    # Run Nova Lite
    print("\n--- Running Nova Lite (Bedrock) ---")
    nova_result = run_nova_lite(image_path)
    print(json.dumps(nova_result, indent=2))

    # Side-by-side comparison table
    print("\n" + "=" * 60)
    print("  COMPARISON TABLE")
    print("=" * 60)
    print(f"{'Metric':<25} {'YOLO (local)':<20} {'Nova Lite (cloud)':<20}")
    print("-" * 65)
    print(f"{'submergence_ratio':<25} {str(yolo_result.get('submergence_ratio', 'N/A')):<20} {str(nova_result.get('submergence_ratio', 'N/A')):<20}")
    print(f"{'people_trapped':<25} {'N/A':<20} {str(nova_result.get('people_trapped', 'N/A')):<20}")
    print(f"{'infrastructure_damage':<25} {'N/A':<20} {str(nova_result.get('infrastructure_damage', 'N/A')):<20}")
    print(f"{'severity':<25} {'N/A':<20} {str(nova_result.get('severity', 'N/A')):<20}")
    print(f"{'reference_object':<25} {str(yolo_result.get('reference_object', 'N/A')):<20} {'N/A':<20}")
    print(f"{'confidence':<25} {str(yolo_result.get('confidence', 'N/A')):<20} {'N/A':<20}")
    print("=" * 60)


if __name__ == "__main__":
    main()

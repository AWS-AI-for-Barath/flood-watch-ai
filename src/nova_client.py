"""
nova_client.py — Amazon Bedrock Nova multimodal flood scene analysis.

Sends a flood image frame to Amazon Bedrock's Nova Lite model and returns
structured semantic context about the flood scene.
"""

import base64
import json
import logging

import boto3
import cv2
import numpy as np
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# System prompt instructs Nova to return structured JSON only
SYSTEM_PROMPT = """You are a flood damage assessment AI. Analyze the provided flood image and return ONLY a valid JSON object with these exact keys:

{
  "people_trapped": <boolean — true if people appear trapped or stranded>,
  "vehicles_submerged": <boolean — true if vehicles are partially or fully submerged>,
  "infrastructure_damage": <boolean — true if roads, bridges, or buildings show damage>,
  "severity": "<string — one of: low, medium, high>",
  "description": "<string — 1-2 sentence description of the flood scene>"
}

Return ONLY the JSON object. No markdown, no explanation, no extra text."""

DEFAULT_MODEL_ID = "amazon.nova-lite-v1:0"


def analyze_flood_scene(
    frame: np.ndarray,
    model_id: str = DEFAULT_MODEL_ID,
    region_name: str = "us-east-1",
) -> dict:
    """
    Send a frame to Amazon Bedrock Nova for flood scene analysis.

    Args:
        frame: BGR numpy array (OpenCV format) of the flood scene.
        model_id: Bedrock model identifier.
        region_name: AWS region for the Bedrock runtime client.

    Returns:
        Dict with keys: people_trapped, vehicles_submerged,
        infrastructure_damage, severity, description.

    Raises:
        RuntimeError: If the Bedrock call fails or returns unparseable output.
    """
    # Encode frame to JPEG bytes
    success, buffer = cv2.imencode(".jpg", frame)
    if not success:
        raise RuntimeError("Failed to encode frame to JPEG for Bedrock.")

    image_bytes = buffer.tobytes()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Build the Bedrock converse request
    client = boto3.client("bedrock-runtime", region_name=region_name)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "image": {
                        "format": "jpeg",
                        "source": {"bytes": image_bytes},
                    }
                },
                {
                    "text": "Analyze this flood scene image and assess the damage."
                },
            ],
        }
    ]

    system = [{"text": SYSTEM_PROMPT}]

    try:
        response = client.converse(
            modelId=model_id,
            messages=messages,
            system=system,
            inferenceConfig={
                "maxTokens": 512,
                "temperature": 0.1,
            },
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        raise RuntimeError(
            f"Bedrock API error ({error_code}): {error_msg}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Failed to call Bedrock: {e}") from e

    # Extract text from response
    try:
        output_message = response["output"]["message"]
        raw_text = ""
        for block in output_message["content"]:
            if "text" in block:
                raw_text += block["text"]

        if not raw_text.strip():
            raise RuntimeError("Bedrock returned an empty response.")

        # Clean potential markdown fencing
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last line (``` markers)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        result = json.loads(cleaned)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Nova response as JSON: {raw_text}")
        raise RuntimeError(
            f"Nova returned non-JSON response: {raw_text[:200]}"
        ) from e
    except KeyError as e:
        raise RuntimeError(
            f"Unexpected Bedrock response structure: {e}"
        ) from e

    # Validate expected keys
    required_keys = {
        "people_trapped",
        "vehicles_submerged",
        "infrastructure_damage",
        "severity",
        "description",
    }
    missing = required_keys - set(result.keys())
    if missing:
        logger.warning(f"Nova response missing keys: {missing}")
        # Fill missing keys with defaults
        defaults = {
            "people_trapped": False,
            "vehicles_submerged": False,
            "infrastructure_damage": False,
            "severity": "medium",
            "description": "Unable to fully assess flood scene.",
        }
        for key in missing:
            result[key] = defaults[key]

    return result

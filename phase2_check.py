"""
phase2_check.py — Phase-2 completion check for FloodWatch AI.

Usage:
    python phase2_check.py sample.jpg

Validates:
  - Depth detection (YOLO reference object present/absent)
  - Schema compliance (all keys, severity enum)
  - Lambda wrapper stability (success envelope)
"""

import json
import logging
import sys

from src.lambda_handler import handle_media_input
from src.pipeline import REQUIRED_KEYS, VALID_SEVERITIES, enforce_schema
from src.validation import validate_depth_detection


def main():
    if len(sys.argv) < 2:
        print("Usage: python phase2_check.py <image_or_video>")
        sys.exit(1)

    input_path = sys.argv[1]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 50)
    print("  FloodWatch AI — Phase-2 Completion Check")
    print("=" * 50)
    print()

    all_passed = True

    # 1. Depth detection
    print("[1/3] Depth Detection")
    try:
        depth_result = validate_depth_detection(input_path)
        detected = depth_result["depth_detected"]
        print(f"  Depth detected: {detected}")
        if detected:
            print(f"  Reference object: {depth_result['reference_object']}")
            print(f"  Water depth: {depth_result['water_depth_cm']} cm")
        else:
            print("  No reference object found (depth is null)")
    except Exception as e:
        print(f"  FAILED: {e}")
        detected = False
        all_passed = False
    print()

    # 2. Schema validation
    print("[2/3] Schema Validation")
    try:
        response = handle_media_input(input_path)
        if response["status"] == "success":
            data = response["data"]
            keys_ok = set(data.keys()) == set(REQUIRED_KEYS.keys())
            severity_ok = data.get("severity") in VALID_SEVERITIES
            schema_valid = keys_ok and severity_ok
            print(f"  All keys present: {keys_ok}")
            print(f"  Severity valid: {severity_ok} ({data.get('severity')})")
            print(f"  Schema valid: {schema_valid}")
            if not schema_valid:
                all_passed = False
        else:
            print(f"  Pipeline error: {response['message']}")
            schema_valid = False
            all_passed = False
    except Exception as e:
        print(f"  FAILED: {e}")
        schema_valid = False
        all_passed = False
    print()

    # 3. Lambda wrapper
    print("[3/3] Lambda Wrapper")
    try:
        has_status = "status" in response
        has_data = "data" in response
        has_message = "message" in response
        envelope_ok = has_status and has_data and has_message
        print(f"  Envelope keys (status/data/message): {envelope_ok}")
        print(f"  Lambda wrapper: {'OK' if envelope_ok else 'FAIL'}")
        if not envelope_ok:
            all_passed = False
    except Exception as e:
        print(f"  FAILED: {e}")
        all_passed = False
    print()

    # Summary
    print("=" * 50)
    status = "COMPLETE" if all_passed else "INCOMPLETE"
    print(f"  Phase-2 multimodal: {status}")
    print("=" * 50)

    if all_passed:
        # Print full result
        print()
        print("Pipeline output:")
        print(json.dumps(response.get("data", {}), indent=2))

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()

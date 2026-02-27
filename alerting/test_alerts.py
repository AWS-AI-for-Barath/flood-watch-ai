"""
test_alerts.py — Local tests for Phase 5 flood alert generation.

Creates mock GeoJSON polygons (with varying submergence ratios) and mock
users (inside and outside the zones), then runs the full alert pipeline
and dispatches via SMS and voice mocks.
"""

import json
import sys
import os

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so the package import works
# when running this file directly with `python alerting/test_alerts.py`.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from alerting.alert_generator import generate_alerts
from alerting.aws_mock import dispatch_alerts

# ---------------------------------------------------------------------------
# Mock flood GeoJSON — three zones with different submergence ratios
# ---------------------------------------------------------------------------
MOCK_FLOOD_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "zone_id": "zone_1",
                "submergence_ratio": 0.25,  # low — below default threshold
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.20, 13.00],
                        [80.25, 13.00],
                        [80.25, 13.05],
                        [80.20, 13.05],
                        [80.20, 13.00],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "zone_id": "zone_2",
                "submergence_ratio": 0.62,  # high
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.25, 13.05],
                        [80.30, 13.05],
                        [80.30, 13.10],
                        [80.25, 13.10],
                        [80.25, 13.05],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "zone_id": "zone_3",
                "submergence_ratio": 0.78,  # severe
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [80.30, 13.10],
                        [80.35, 13.10],
                        [80.35, 13.15],
                        [80.30, 13.15],
                        [80.30, 13.10],
                    ]
                ],
            },
        },
    ],
}

# ---------------------------------------------------------------------------
# Mock users — some inside flood zones, one outside
# ---------------------------------------------------------------------------
MOCK_USERS = [
    {
        "user_id": "U101",
        "phone": "+919876543210",
        "lat": 13.02,
        "lon": 80.22,
    },  # inside zone_1 (low, below threshold → no alert)
    {
        "user_id": "U102",
        "phone": "+919876543211",
        "lat": 13.08,
        "lon": 80.27,
    },  # inside zone_2 (high → alert)
    {
        "user_id": "U103",
        "phone": "+919876543212",
        "lat": 13.12,
        "lon": 80.32,
    },  # inside zone_3 (severe → alert)
    {
        "user_id": "U104",
        "phone": "+919876543213",
        "lat": 13.50,
        "lon": 80.50,
    },  # outside all zones → no alert
]


def main():
    print("=" * 60)
    print(" FloodWatch Phase 5 — Alert Generation Test")
    print("=" * 60)

    # ---- Generate alerts ------------------------------------------------
    alerts = generate_alerts(MOCK_FLOOD_GEOJSON, MOCK_USERS)

    print(f"\n[OK] Generated {len(alerts)} alert(s) from {len(MOCK_USERS)} user(s)\n")
    print(json.dumps(alerts, indent=2))

    # ---- Assert expected behaviour --------------------------------------
    affected_ids = {a["user_id"] for a in alerts}
    assert "U102" in affected_ids, "U102 should be alerted (zone_2, high)"
    assert "U103" in affected_ids, "U103 should be alerted (zone_3, severe)"
    assert "U101" not in affected_ids, "U101 should NOT be alerted (below threshold)"
    assert "U104" not in affected_ids, "U104 should NOT be alerted (outside zones)"

    # Verify schema fields
    for alert in alerts:
        for key in (
            "user_id", "phone", "lat", "lon",
            "severity", "submergence_ratio", "flood_zone_id", "message",
        ):
            assert key in alert, f"Missing key '{key}' in alert: {alert}"

    print("\n[OK] All assertions passed!\n")

    # ---- Dispatch via mock AWS ------------------------------------------
    dispatch_alerts(alerts, mode="sms")
    dispatch_alerts(alerts, mode="voice")

    print("=" * 60)
    print(" All tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()

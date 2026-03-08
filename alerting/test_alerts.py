"""
test_alerts.py -- Test suite for Phase 5 alerting module.

Run via:
    python -m pytest alerting/test_alerts.py -v
"""

import os
import pytest
from unittest import mock

# Force mock mode for all tests
os.environ["FLOODWATCH_ALERT_MODE"] = "mock"

from alerting.severity import get_severity, SEVERITY_RANK
from alerting.message_templates import get_alert_message, get_polly_voice
from alerting.user_store import get_affected_users, _MOCK_USERS
from alerting.alert_history import store_alert, check_rate_limit, get_recent_alerts, clear_mock_history
from alerting.dispatcher import dispatch_alerts


@pytest.fixture(autouse=True)
def run_before_and_after_tests():
    """Clear mock history before and after each test."""
    clear_mock_history()
    yield
    clear_mock_history()


# -- 1. Severity Tests ----------------------------------------------------

def test_get_severity():
    """Verify numeric ratio maps to correct 4-tier threat level."""
    assert get_severity(0.1) == "advisory"
    assert get_severity(0.25) == "warning"
    assert get_severity(0.5) == "danger"
    assert get_severity(0.8) == "emergency"

def test_severity_rank():
    """Verify logic used for rate-limit severity escalation logic."""
    assert SEVERITY_RANK["warning"] > SEVERITY_RANK["advisory"]
    assert SEVERITY_RANK["emergency"] > SEVERITY_RANK["danger"]


# -- 2. Message Templates Tests -------------------------------------------

def test_get_alert_message_en():
    """Verify English message templating includes severity context."""
    msg = get_alert_message("danger", "en")
    assert "FloodWatch Danger" in msg
    assert "higher ground" in msg

def test_get_alert_message_ta_hi():
    """Verify fallback mechanisms for known/unknown languages."""
    msg_ta = get_alert_message("warning", "ta")
    assert "echcharikkai" in msg_ta
    
    msg_hi = get_alert_message("emergency", "hi")
    assert "aapaatkaal" in msg_hi
    
    # Fallback to English for unknown language
    msg_unknown = get_alert_message("danger", "fr")
    assert "FloodWatch Danger" in msg_unknown

def test_polly_voice_mappings():
    """Verify Polly voice IDs for languages."""
    assert get_polly_voice("en")["VoiceId"] == "Joanna"
    assert get_polly_voice("ta")["VoiceId"] == "Aditi"
    assert get_polly_voice("hi")["LanguageCode"] == "hi-IN"


# -- 3. User Store (Mock) Tests -------------------------------------------

def test_get_affected_users_no_polygon():
    """If no polygons provided, returns mock users list."""
    affected = get_affected_users({})
    assert len(affected) == len(_MOCK_USERS)

def test_get_affected_users_empty_geojson():
    """Empty geojson block returns empty list of affected."""
    geojson = {"type": "FeatureCollection", "features": []}
    affected = get_affected_users(geojson)
    assert len(affected) == len(_MOCK_USERS) # By spec, mock returns all if empty

def test_get_affected_users_mock_intersect():
    """Test the Shapely fallback logic for mock spatial detection."""
    # Create a polygon explicitly around U001 (13.0827, 80.2707)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[80.26, 13.07], [80.28, 13.07], [80.28, 13.09], [80.26, 13.09], [80.26, 13.07]]]
                },
                "properties": {"submergence_ratio": 0.5, "zone_id": "z_test"}
            }
        ]
    }
    affected = get_affected_users(geojson)
    # Only U001 should be inside this bounding box
    assert len(affected) == 1
    assert affected[0]["user_id"] == "U001"
    assert affected[0]["flood_zone_id"] == "z_test"


# -- 4. Alert History & Rate Limiting Tests -------------------------------

def test_rate_limit_same_user_same_severity():
    """Successive alerts within 15min of same severity are rate-limited."""
    assert not check_rate_limit("userA", SEVERITY_RANK["warning"])
    # Next call should be suppressed
    assert check_rate_limit("userA", SEVERITY_RANK["warning"])

def test_rate_limit_same_user_escalation():
    """Successive alerts within 15min of HIGHER severity are NOT limited."""
    assert not check_rate_limit("userA", SEVERITY_RANK["warning"])
    # Escalation to emergency -> allow pass-through
    assert not check_rate_limit("userA", SEVERITY_RANK["emergency"])

def test_store_and_retrieve_history():
    """Verify mock append logic for recent alerts dashboard."""
    store_alert({"user_id": "u1", "severity": "danger", "message": "msg1"})
    store_alert({"user_id": "u2", "severity": "warning", "message": "msg2"}, "failed")
    
    recent = get_recent_alerts(limit=5)
    assert len(recent) == 2
    assert recent[0]["user_id"] == "u2" # Most recent first (due to insertion order here)
    assert recent[0]["delivery_status"] == "failed"


# -- 5. Dispatcher Tests --------------------------------------------------

def test_dispatch_alerts(capsys):
    """Verify end-to-end alert dispatch calls correct mocks."""
    alerts = [
        {
            "user_id": "u1",
            "phone_number": "+12345",
            "severity": "emergency",
            "preferred_language": "en",
            "message": "Evacuate!",
            "flood_zone_id": "z1"
        },
        {
            "user_id": "u2",
            "phone_number": "+67890",
            "severity": "advisory",
            "preferred_language": "ta",
            "message": "Watch out.",
            "flood_zone_id": "z1"
        }
    ]
    
    summary = dispatch_alerts(alerts)
    
    assert summary["attempted"] == 2
    assert summary["sent"] == 2
    assert summary["failed"] == 0
    assert summary["rate_limited"] == 0
    
    # Capture print output from aws_mock.py
    captured = capsys.readouterr()
    # Emergency sends both SMS and Voice
    assert "[SMS -> +12345]" in captured.out
    assert "[VOICE -> +12345]" in captured.out
    assert "+12345" in captured.out
    assert "+67890" in captured.out

    # Re-dispatching same alerts immediately should trigger rate limit
    summary_2 = dispatch_alerts(alerts)
    assert summary_2["attempted"] == 2
    assert summary_2["rate_limited"] == 2
    assert summary_2["sent"] == 0

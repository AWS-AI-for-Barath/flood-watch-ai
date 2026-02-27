"""
aws_mock.py — Mock AWS integration for Pinpoint (SMS) and Polly (voice).

Used for local testing without calling real AWS services.
"""


def send_sms_mock(alert: dict) -> None:
    """Simulate sending an SMS via Amazon Pinpoint."""
    print(
        f"  [SMS → {alert['phone']}]  "
        f"User {alert['user_id']} | "
        f"Severity: {alert['severity'].upper()} | "
        f"Zone: {alert['flood_zone_id']}\n"
        f"    \"{alert['message']}\""
    )


def send_voice_mock(alert: dict) -> None:
    """Simulate a voice call via Amazon Polly."""
    print(
        f"  [VOICE → {alert['phone']}]  "
        f"User {alert['user_id']} | "
        f"Severity: {alert['severity'].upper()} | "
        f"Zone: {alert['flood_zone_id']}\n"
        f"    Polly TTS: \"{alert['message']}\""
    )


def dispatch_alerts(alerts: list, mode: str = "sms") -> None:
    """
    Dispatch a list of alerts using the specified mode.

    Args:
        alerts: List of alert dicts from ``generate_alerts()``.
        mode: ``"sms"`` for Pinpoint SMS mock, ``"voice"`` for Polly mock.
    """
    handler = send_sms_mock if mode == "sms" else send_voice_mock
    channel = "SMS (Pinpoint)" if mode == "sms" else "Voice (Polly)"

    print(f"\n{'=' * 60}")
    print(f" Dispatching {len(alerts)} alert(s) via {channel}")
    print(f"{'=' * 60}\n")

    for alert in alerts:
        handler(alert)
        print()

"""
alert_history.py -- DynamoDB alert logging and rate limiting.

Table: alert_history
    alert_id (PK), user_id, phone_number, severity, timestamp,
    delivery_status

Rate-limiting: suppress duplicate alerts to the same user within
15 minutes unless severity increases.
"""

import logging
import os
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# -- Rate-limit config ---------------------------------------------------
RATE_LIMIT_SECONDS = 15 * 60  # 15 minutes

# -- In-memory store for mock mode ---------------------------------------
_mock_history: list = []
_mock_rate_tracker: dict = {}  # user_id -> {timestamp, severity_rank}


def _get_dynamodb_table():
    """Return the DynamoDB alert_history Table resource."""
    import boto3

    dynamodb = boto3.resource(
        "dynamodb",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )
    return dynamodb.Table(
        os.environ.get("ALERT_HISTORY_TABLE", "alert_history")
    )


def store_alert(alert: dict, delivery_status: str = "sent") -> str:
    """
    Store an alert record in DynamoDB (or in-memory for mock mode).

    Args:
        alert: Alert dict from generate_alerts().
        delivery_status: "sent", "failed", or "rate_limited".

    Returns:
        The generated alert_id.
    """
    alert_id = f"alert_{uuid.uuid4().hex[:12]}"
    record = {
        "alert_id": alert_id,
        "user_id": alert["user_id"],
        "phone_number": alert.get("phone", alert.get("phone_number", "")),
        "severity": alert["severity"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "delivery_status": delivery_status,
        "flood_zone_id": alert.get("flood_zone_id", ""),
        "message": alert.get("message", ""),
    }

    mode = os.environ.get("FLOODWATCH_ALERT_MODE", "production")

    if mode == "mock":
        _mock_history.append(record)
        logger.info("Mock stored alert %s for user %s", alert_id, alert["user_id"])
        return alert_id

    try:
        table = _get_dynamodb_table()
        table.put_item(Item=record)
        logger.info("Stored alert %s in DynamoDB", alert_id)
    except Exception as e:
        logger.error("DynamoDB put_item failed for %s: %s", alert_id, e)

    return alert_id


def check_rate_limit(user_id: str, severity_rank: int) -> bool:
    """
    Check if an alert should be suppressed due to rate limiting.

    Rules:
        - No alert to same user within 15 minutes
        - UNLESS the new severity_rank is higher than the last sent

    Args:
        user_id: Target user identifier.
        severity_rank: Numeric severity rank (0-3).

    Returns:
        True if the alert should be suppressed (rate-limited).
        False if the alert should proceed.
    """
    mode = os.environ.get("FLOODWATCH_ALERT_MODE", "production")

    if mode == "mock":
        return _check_rate_limit_mock(user_id, severity_rank)

    return _check_rate_limit_dynamodb(user_id, severity_rank)


def _check_rate_limit_mock(user_id: str, severity_rank: int) -> bool:
    """In-memory rate limiting for mock mode."""
    now = time.time()

    if user_id in _mock_rate_tracker:
        last = _mock_rate_tracker[user_id]
        time_diff = now - last["timestamp"]

        if time_diff < RATE_LIMIT_SECONDS:
            # Within window: allow only if severity increased
            if severity_rank <= last["severity_rank"]:
                logger.info(
                    "Rate-limited user %s (last alert %ds ago, same/lower severity)",
                    user_id, int(time_diff),
                )
                return True

    # Update tracker
    _mock_rate_tracker[user_id] = {
        "timestamp": now,
        "severity_rank": severity_rank,
    }
    return False


def _check_rate_limit_dynamodb(user_id: str, severity_rank: int) -> bool:
    """DynamoDB-backed rate limiting for production mode."""
    try:
        import boto3
        from boto3.dynamodb.conditions import Key

        table = _get_dynamodb_table()

        # Query recent alerts for this user (last 15 minutes)
        cutoff = datetime.now(timezone.utc).timestamp() - RATE_LIMIT_SECONDS
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()

        # Scan for recent alerts (for hackathon scale; use GSI for production)
        response = table.scan(
            FilterExpression=(
                Key("user_id").eq(user_id)
            ),
            Limit=10,
        )

        items = response.get("Items", [])
        if not items:
            return False

        # Find most recent alert
        recent = max(items, key=lambda x: x.get("timestamp", ""))
        if recent.get("timestamp", "") > cutoff_iso:
            from .severity import SEVERITY_RANK as SR

            last_rank = SR.get(recent.get("severity", "advisory"), 0)
            if severity_rank <= last_rank:
                return True

        return False

    except Exception as e:
        logger.error("Rate-limit check failed for %s: %s", user_id, e)
        return False  # fail-open: send the alert


def get_recent_alerts(limit: int = 50) -> list:
    """
    Fetch recent alerts for the responder dashboard.

    Args:
        limit: Maximum number of alerts to return.

    Returns:
        List of alert dicts sorted by timestamp descending.
    """
    mode = os.environ.get("FLOODWATCH_ALERT_MODE", "production")

    if mode == "mock":
        sorted_alerts = sorted(
            _mock_history, key=lambda x: x.get("timestamp", ""), reverse=True
        )
        return sorted_alerts[:limit]

    try:
        table = _get_dynamodb_table()
        response = table.scan(Limit=limit)
        items = response.get("Items", [])
        return sorted(items, key=lambda x: x.get("timestamp", ""), reverse=True)
    except Exception as e:
        logger.error("Failed to fetch recent alerts: %s", e)
        return []


def clear_mock_history():
    """Reset mock stores (for testing)."""
    _mock_history.clear()
    _mock_rate_tracker.clear()

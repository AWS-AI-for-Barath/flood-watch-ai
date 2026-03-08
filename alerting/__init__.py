"""
Phase 5 -- Alerting Module

Consumes flood polygons from Phase 4 and generates mass alerts
via SMS (Pinpoint) and Voice (Polly).
"""

from .severity import get_severity
from .message_templates import get_alert_message
from .user_store import get_affected_users, register_user
from .alert_history import store_alert, get_recent_alerts, check_rate_limit
from .dispatcher import dispatch_alerts

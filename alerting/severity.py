"""
severity.py -- Map submergence_ratio to threat classification.

Threat Tiers (Phase 5 spec)
-----------------------------
  Ratio       Severity
  < 0.2       advisory
  0.2 - 0.4   warning
  0.4 - 0.7   danger
  >= 0.7      emergency
"""


def get_severity(submergence_ratio: float) -> str:
    """
    Return the severity label for a given submergence_ratio (0-1).

    Args:
        submergence_ratio: Predicted fraction of area submerged.

    Returns:
        One of "advisory", "warning", "danger", or "emergency".
    """
    if submergence_ratio >= 0.7:
        return "emergency"
    if submergence_ratio >= 0.4:
        return "danger"
    if submergence_ratio >= 0.2:
        return "warning"
    return "advisory"


# Reverse map: severity string -> numeric rank (for rate-limit comparisons)
SEVERITY_RANK = {
    "advisory": 0,
    "warning": 1,
    "danger": 2,
    "emergency": 3,
}

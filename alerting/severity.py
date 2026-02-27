"""
severity.py — Map submergence_ratio to a human-readable severity string.

Severity tiers
--------------
  Ratio       Severity
  0   – 0.3   low
  0.3 – 0.5   moderate
  0.5 – 0.7   high
  ≥ 0.7       severe
"""


def get_severity(submergence_ratio: float) -> str:
    """
    Return the severity label for a given *submergence_ratio* (0–1).

    Args:
        submergence_ratio: Predicted fraction of area submerged.

    Returns:
        One of ``"low"``, ``"moderate"``, ``"high"``, or ``"severe"``.
    """
    if submergence_ratio >= 0.7:
        return "severe"
    if submergence_ratio >= 0.5:
        return "high"
    if submergence_ratio >= 0.3:
        return "moderate"
    return "low"

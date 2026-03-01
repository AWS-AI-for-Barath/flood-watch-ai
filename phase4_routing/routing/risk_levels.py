"""
risk_levels.py — Weight mapping constants and compute_weight() function.

Tiered weight multipliers based on road submergence ratio:

    Submergence      Multiplier   Risk Level
    ──────────────   ──────────   ──────────
    < 0.2            base × 1     low
    0.2 – 0.4        base × 2     moderate
    0.4 – 0.7        base × 5     high
    > 0.7            ∞ (closed)   severe
"""

import math

# ── Weight tier thresholds ──────────────────────────────────────────

TIER_LOW = 0.2
TIER_MODERATE = 0.4
TIER_HIGH = 0.7

# Multipliers
MULTIPLIER_LOW = 1.0
MULTIPLIER_MODERATE = 2.0
MULTIPLIER_HIGH = 5.0
MULTIPLIER_CLOSED = math.inf

# Risk level labels
RISK_LOW = "low"
RISK_MODERATE = "moderate"
RISK_HIGH = "high"
RISK_SEVERE = "severe"


def compute_weight(base_weight: float, submergence_ratio: float) -> float:
    """
    Calculate the dynamic weight for a road segment.

    Args:
        base_weight:       Original edge weight (typically 1.0).
        submergence_ratio: Fraction of the segment area under water (0–1).

    Returns:
        Adjusted weight.  ``math.inf`` if the road is closed.
    """
    if submergence_ratio > TIER_HIGH:
        return MULTIPLIER_CLOSED  # road closed
    if submergence_ratio > TIER_MODERATE:
        return base_weight * MULTIPLIER_HIGH
    if submergence_ratio > TIER_LOW:
        return base_weight * MULTIPLIER_MODERATE
    return base_weight * MULTIPLIER_LOW


def get_risk_level(submergence_ratio: float) -> str:
    """
    Map a submergence ratio to a human-readable risk label.

    Args:
        submergence_ratio: Fraction of area submerged (0–1).

    Returns:
        One of ``"low"``, ``"moderate"``, ``"high"``, or ``"severe"``.
    """
    if submergence_ratio > TIER_HIGH:
        return RISK_SEVERE
    if submergence_ratio > TIER_MODERATE:
        return RISK_HIGH
    if submergence_ratio > TIER_LOW:
        return RISK_MODERATE
    return RISK_LOW


def is_road_closed(submergence_ratio: float) -> bool:
    """Return True if the submergence ratio means the road is impassable."""
    return submergence_ratio > TIER_HIGH

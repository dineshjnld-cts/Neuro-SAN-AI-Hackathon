"""Configurable risk-tier policy for adaptive investigation depth."""

from __future__ import annotations

from typing import Any
from typing import Dict

from coded_tools.fraud_defense.models import RiskLevel


DEFAULT_THRESHOLDS = {"medium": 0.30, "high": 0.52, "critical": 0.75}


def risk_level(score: float, thresholds: Dict[str, float] | None = None) -> RiskLevel:
    """Map a deterministic score to a configured risk tier."""
    values = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if score >= values["critical"]:
        return RiskLevel.CRITICAL
    if score >= values["high"]:
        return RiskLevel.HIGH
    if score >= values["medium"]:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def investigation_plan(level: RiskLevel) -> Dict[str, Any]:
    """Return the bounded set of work appropriate for a risk tier."""
    if level == RiskLevel.LOW:
        return {"agents": ["case_investigation"], "models": 1, "approval_required": False, "simulation_required": False}
    if level == RiskLevel.MEDIUM:
        return {"agents": ["case_investigation", "control_assurance"], "models": 1, "approval_required": False, "simulation_required": True}
    if level == RiskLevel.HIGH:
        return {"agents": ["case_investigation", "control_assurance", "decision_governance"], "models": 3, "approval_required": True, "simulation_required": True}
    return {"agents": ["case_investigation", "control_assurance", "decision_governance", "human_approval"], "models": 3, "approval_required": True, "simulation_required": True, "autonomous_execution": False}

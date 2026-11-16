"""Aggregate explicit Harness judgments; never call a model or claim benchmark execution."""
from __future__ import annotations

import math

WEIGHTS = {
    "faithfulness": 10, "coverage": 10, "density": 15, "visual_evidence": 10,
    "layout": 20, "readability": 25, "aesthetics": 10,
}
PROTOCOL = "posfoxgen-harness-seven-dimension-v1"


def assess(review: dict) -> dict:
    """Validate evidence-backed 0–100 judgments and return a disclosed local score."""
    if not review.get("reviewer") or not review.get("evidence"):
        raise ValueError("named reviewer and inspected evidence are required")
    dimensions = review.get("dimensions", {})
    if set(dimensions) != set(WEIGHTS):
        raise ValueError("all seven dimensions, and only those dimensions, are required")
    score = 0.0
    for name, weight in WEIGHTS.items():
        item = dimensions[name]
        value = item.get("score")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"{name} score must be finite and between 0 and 100")
        if not str(item.get("reason", "")).strip():
            raise ValueError(f"{name} requires a source/render-grounded reason")
        score += weight * value / 100
    blockers = review.get("blockers")
    if not isinstance(blockers, list):
        raise ValueError("an explicit blockers list is required")
    return {
        "protocol": PROTOCOL, "official_posterbench": False,
        "score": round(score, 4), "valid": not blockers,
        "dimensions": dimensions, "blockers": blockers,
        "reviewer": review["reviewer"], "evidence": review["evidence"],
    }


def reward(before: dict, after: dict) -> dict:
    """Whole-poster quality is the reward; a new blocker vetoes acceptance."""
    delta = round(float(after["score"]) - float(before["score"]), 4)
    valid = bool(after.get("valid"))
    return {"score_change": delta, "reward": delta if valid else -100.0,
            "accepted": valid and delta > 0, "valid": valid}

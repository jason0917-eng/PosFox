import pytest


def test_score_uses_frozen_seven_dimension_weights():
    from posfoxgen.quality import assess
    review = {
        "reviewer": "harness-critic", "evidence": ["poster.png", "paper.pdf"],
        "dimensions": {k: {"score": 80, "reason": "inspected against source and render"}
                       for k in ("faithfulness", "coverage", "density", "visual_evidence", "layout", "readability", "aesthetics")},
        "blockers": [],
    }
    result = assess(review)
    assert result["score"] == 80
    assert result["valid"] is True
    assert result["official_posterbench"] is False


def test_missing_dimension_cannot_be_silently_averaged():
    from posfoxgen.quality import assess
    with pytest.raises(ValueError, match="seven"):
        assess({"reviewer": "critic", "evidence": ["preview.png"], "dimensions": {}, "blockers": []})


def test_blocking_factual_error_overrides_high_score():
    from posfoxgen.quality import assess
    result = assess({
        "reviewer": "critic", "evidence": ["preview.png", "paper.pdf"],
        "dimensions": {k: {"score": 99, "reason": "visible evidence"}
                       for k in ("faithfulness", "coverage", "density", "visual_evidence", "layout", "readability", "aesthetics")},
        "blockers": [{"type": "factual", "issue": "wrong experimental direction"}],
    })
    assert result["valid"] is False
    assert result["score"] == 99


def test_reward_only_accepts_valid_improvement():
    from posfoxgen.quality import reward
    result = reward({"score": 60, "valid": True}, {"score": 90, "valid": False})
    assert result["accepted"] is False
    assert result["reward"] < 0


def test_unsupported_score_has_no_quality_claim():
    from posfoxgen.quality import assess
    with pytest.raises(ValueError, match="evidence"):
        assess({"reviewer": "critic", "evidence": [], "dimensions": {}, "blockers": []})

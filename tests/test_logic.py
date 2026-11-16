import copy

from posfoxgen.logic import canonical_hash, validate_logic


def valid_inputs():
    assets = {"assets": [{"id": "a1", "source": {"page": 2, "locator": "Figure 1"}}]}
    logic = {"planner": "planner", "claims": [{"id": "c1", "text": "Observed result", "evidence_asset_ids": ["a1"]}], "relations": []}
    panels = {"panels": [{"id": "p1", "claim_ids": ["c1"], "asset_ids": ["a1"], "reading_order": 1}]}
    review = {"reviewer": "independent-review", "independent": True, "decision": "pass", "checked_claim_ids": ["c1"], "checked_relation_ids": [], "findings": [], "evidence_notes": [{"claim_id": "c1", "source_locator": "page 2 Figure 1", "assessment": "Supported by source"}]}
    review["input_hashes"] = {"asset_table": canonical_hash(assets), "logic_plan": canonical_hash(logic), "panel_plan": canonical_hash(panels)}
    return assets, logic, panels, review


def test_structurally_valid_inputs_without_independent_review_stay_pending():
    a, l, p, _ = valid_inputs()
    result = validate_logic(a, l, p, None)
    assert result["status"] == "pending"
    assert result["pass"] is False


def test_unknown_evidence_and_uncovered_claim_cannot_pass():
    a, l, p, r = valid_inputs()
    l["claims"][0]["evidence_asset_ids"] = ["absent"]
    p["panels"][0]["claim_ids"] = []
    result = validate_logic(a, l, p, r)
    assert not result["pass"]
    assert {x["code"] for x in result["blockers"]} >= {"unknown_evidence", "unplaced_claim"}


def test_reviewer_must_cover_every_claim_and_relation_with_evidence():
    a, l, p, r = valid_inputs()
    l["relations"] = [{"id": "r1", "source": "c1", "target": "c1", "type": "supports"}]
    r["checked_claim_ids"] = []
    r["evidence_notes"] = []
    result = validate_logic(a, l, p, r)
    assert not result["pass"]
    assert "review_coverage" in {x["code"] for x in result["blockers"]}


def test_supported_source_bound_plan_passes():
    assert validate_logic(*valid_inputs())["pass"] is True


def test_review_of_different_inputs_is_rejected():
    a, l, p, r = valid_inputs()
    r["input_hashes"] = {"asset_table": "wrong", "logic_plan": "wrong", "panel_plan": "wrong"}
    result = validate_logic(a, l, p, r)
    assert "review_hash_mismatch" in {x["code"] for x in result["blockers"]}


def test_same_planner_and_reviewer_is_not_independent():
    a, l, p, r = valid_inputs()
    r["reviewer"] = l["planner"]
    assert not validate_logic(a, l, p, r)["pass"]


def test_unbound_legacy_review_cannot_approve_a_plan():
    a, l, p, r = valid_inputs()
    r.pop("input_hashes")
    result = validate_logic(a, l, p, r)
    assert not result["pass"]
    assert "review_hash_mismatch" in {x["code"] for x in result["blockers"]}


def test_old_review_cannot_approve_changed_claim_with_same_id():
    a, l, p, r = valid_inputs()
    l["claims"][0]["text"] = "An entirely different unreviewed scientific claim"
    assert not validate_logic(a, l, p, r)["pass"]

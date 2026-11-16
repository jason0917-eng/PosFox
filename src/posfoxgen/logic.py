"""Source-reference checks and an explicit independent Harness review gate.

The deterministic checks establish coverage and provenance, not scientific truth.
Only a source-grounded review supplied by the Harness can approve semantic content.
"""

import hashlib
import json
from pathlib import Path


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def read_object(value):
    if isinstance(value, (str, Path)):
        return json.loads(Path(value).read_text())
    return value


def _records(value, key, aliases=()):
    if isinstance(value, list):
        return value
    for name in (key, *aliases):
        if isinstance(value.get(name), list):
            return value[name]
    return []


def _source_present(asset):
    source = asset.get("source", asset.get("source_location", asset.get("provenance")))
    if isinstance(source, dict):
        return any(source.get(k) is not None for k in ("page", "source_page", "locator", "section", "figure", "table"))
    return bool(source or asset.get("source_page") or asset.get("page"))


def _evidence_ids(claim):
    return claim.get("evidence_asset_ids", claim.get("asset_ids", claim.get("evidence_ids", [])))


def validate_logic(asset_table, logic_plan, panel_plan, review=None):
    a, l, p = map(read_object, (asset_table, logic_plan, panel_plan))
    r = read_object(review) if review is not None else None
    blockers, warnings = [], []

    def block(code, message, **details):
        blockers.append({"code": code, "message": message, **details})

    assets = _records(a, "assets", ("items",))
    claims = _records(l, "claims")
    relations = _records(l, "relations")
    panels = _records(p, "panels", ("blocks",))
    for records, kind in ((assets, "asset"), (claims, "claim"), (panels, "panel")):
        ids = [x.get("id") for x in records]
        if not ids or any(not isinstance(i, str) or not i.strip() for i in ids):
            block("missing_ids", f"Nonempty {kind} records with stable IDs are required")
        if len(set(ids)) != len(ids):
            block("duplicate_ids", f"Duplicate {kind} IDs")
    asset_ids = {x.get("id") for x in assets}
    claim_ids = {x.get("id") for x in claims}
    relation_ids = {x.get("id", f"relation-{i + 1}") for i, x in enumerate(relations)}
    for asset in assets:
        if not _source_present(asset):
            block("missing_source", "Asset requires an exact paper source location", asset_id=asset.get("id"))
    for claim in claims:
        if not claim.get("text", claim.get("claim")):
            block("missing_claim_text", "Claim requires exact planned wording", claim_id=claim.get("id"))
        evidence = _evidence_ids(claim)
        if not evidence:
            block("missing_evidence", "Claim requires supporting asset IDs", claim_id=claim.get("id"))
        for ref in evidence:
            if ref not in asset_ids:
                block("unknown_evidence", "Claim references an unknown asset", claim_id=claim.get("id"), asset_id=ref)
    for i, relation in enumerate(relations):
        source = relation.get("source", relation.get("source_id", relation.get("from")))
        target = relation.get("target", relation.get("target_id", relation.get("to")))
        if source not in claim_ids or target not in claim_ids:
            block("unknown_relation_endpoint", "Relation must connect known claim IDs", relation_id=relation.get("id", f"relation-{i + 1}"))
        if not relation.get("type", relation.get("relation")):
            block("missing_relation_type", "Relation needs a semantic type")
        if source == target:
            block("self_relation", "A claim cannot substantiate itself")
    placed = set()
    orders = []
    for panel in panels:
        panel_claims = panel.get("claim_ids", [])
        panel_assets = panel.get("asset_ids", [])
        placed.update(panel_claims)
        for claim_id in panel_claims:
            if claim_id not in claim_ids:
                block("unknown_panel_claim", "Panel references an unknown claim", panel_id=panel.get("id"), claim_id=claim_id)
        for asset_id in panel_assets:
            if asset_id not in asset_ids:
                block("unknown_panel_asset", "Panel references an unknown asset", panel_id=panel.get("id"), asset_id=asset_id)
        order = panel.get("reading_order", panel.get("order"))
        if not isinstance(order, (int, float)):
            block("missing_reading_order", "Panel requires a numeric reading order", panel_id=panel.get("id"))
        else:
            orders.append(order)
    if len(set(orders)) != len(orders):
        block("ambiguous_reading_order", "Panel reading-order values must be unique")
    for claim_id in claim_ids - placed:
        block("unplaced_claim", "Planned claim is not placed in a panel", claim_id=claim_id)
    input_hashes = {"asset_table": canonical_hash(a), "logic_plan": canonical_hash(l), "panel_plan": canonical_hash(p)}
    if r is None:
        block("independent_review_required", "A Harness reviewer must inspect the paper evidence, claims, relations and panel plan")
    elif not isinstance(r, dict):
        block("invalid_review", "Review must be an object")
    else:
        if not r.get("reviewer") or r.get("independent") is not True or r.get("reviewer") == l.get("planner"):
            block("independent_review_required", "Reviewer identity must be distinct from the planner and declare an independent pass")
        if r.get("decision") != "pass":
            block("review_not_passed", "Semantic review did not pass")
        missing_claims = claim_ids - set(r.get("checked_claim_ids", []))
        missing_relations = relation_ids - set(r.get("checked_relation_ids", []))
        if missing_claims or missing_relations:
            block("review_coverage", "Independent review omitted planned claims or relations", claim_ids=sorted(missing_claims), relation_ids=sorted(missing_relations))
        notes = r.get("evidence_notes", [])
        grounded = {n.get("claim_id") for n in notes if n.get("source_locator") and n.get("assessment")}
        if claim_ids - grounded:
            block("review_evidence_required", "Every claim needs a source-grounded review note", claim_ids=sorted(claim_ids - grounded))
        for finding in r.get("findings", []):
            if finding.get("resolved") is not True and finding.get("severity", "blocking") in {"blocking", "error", "critical"}:
                block("unresolved_semantic_issue", "Review contains an unresolved content or logic issue", finding=finding)
        if r.get("input_hashes") != input_hashes:
            block("review_hash_mismatch", "Review must bind exactly the current canonical input document hashes")
    passed = not blockers
    status = "pass" if passed else "pending" if r is None and {b["code"] for b in blockers} == {"independent_review_required"} else "blocked"
    return {"pass": passed, "status": status, "blockers": blockers, "warnings": warnings, "input_hashes": input_hashes, "semantic_assurance": "Harness independent review recorded" if passed else "not approved"}

"""Executable v2 workflow gates, using actual files and native delivery fixtures."""
import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from posfoxgen.delivery import create_delivery_manifest
from posfoxgen.logic import canonical_hash
from posfoxgen.state import accept_stage, file_hash, init_run, status_run, validate_delivery
from test_delivery import valid_package
from test_generation_contract import generation_inputs
from test_reconstruction_audit import audit_inputs


def write(path, value):
    path.write_text(json.dumps(value))
    return path


def inputs(tmp_path):
    paper = tmp_path / "paper.pdf"; paper.write_bytes(b"source paper for v2 gates")
    root = tmp_path / "run"; run = init_run(root, paper, profile="posfoxgen-v2")
    a, _, h, _ = generation_inputs()
    p, m, e, _ = audit_inputs()
    a["source"] = {"path": str(paper), "paper_sha256": run["paper"]["sha256"]}
    from PIL import Image
    source_root = root / "source"; source_root.mkdir()
    source_image = source_root / "fig1.png"
    Image.new("RGB", (180, 120), "white").save(source_image)
    a["root"] = str(source_root)
    next(asset for asset in a["assets"] if asset["id"] == "fig1").update(type="figure", path="fig1.png", sha256=file_hash(source_image))
    e.update(title="A source-grounded design poster", width=200, height=200, background="#ffffff")
    e["panels"][0].update(x=0, y=0, width=200, height=200)
    for asset in a["assets"]: asset["source"] = {"page": 1, "locator": asset["id"]}
    h["paper_source"] = copy.deepcopy(a["source"])
    for component in h["content_plan"]: component["panel_id"] = "method"
    h["image_slots"] = h["image_slots"][:1]
    l = {"planner": "paper-planner", "claims": [{"id": "c1", "text": "The method uses source-grounded iteration.", "evidence_asset_ids": ["text1"]}], "relations": []}
    p["panels"][0].update(claim_ids=["c1"], asset_ids=["text1", "fig1"], reading_order=1)
    lr = {"reviewer": "independent-source-reviewer", "independent": True, "decision": "pass", "checked_claim_ids": ["c1"], "checked_relation_ids": [], "findings": [], "evidence_notes": [{"claim_id": "c1", "source_locator": "page 1", "assessment": "Supported"}], "input_hashes": {"asset_table": canonical_hash(a), "logic_plan": canonical_hash(l), "panel_plan": canonical_hash(p)}}
    values = {"asset_table": a, "logic_plan": l, "panel_plan": p, "logic_review": lr, "technical_story": h["technical_story"], "content_debate": h["debate"], "generation_handoff": h}
    paths = {key: write(root / (key + ".json"), value) for key, value in values.items()}
    accept_stage(root, "assets", {"asset_table": paths["asset_table"]})
    return root, paths, p, m, e


def approve_logic(root, paths):
    accept_stage(root, "planned", {key: paths[key] for key in ("logic_plan", "panel_plan", "technical_story", "content_debate")})
    accept_stage(root, "logic_approved", {"logic_review": paths["logic_review"]}, paths["logic_review"])


def image_ready(tmp_path):
    root, paths, p, m, e = inputs(tmp_path)
    approve_logic(root, paths)
    image = root / "generated.png"
    from PIL import Image
    Image.new("RGB", (200, 200), "white").save(image)
    paths["image"] = image
    review = {"reviewer": "independent-image-reviewer", "independent": True, "decision": "pass", "findings": [], "checked_image_slot_ids": ["diagram"], "all_planned_visuals_drawn": True, "input_hashes": {key: file_hash(paths[key]) for key in ("image", "logic_plan", "panel_plan")}}
    paths["image_review"] = write(root / "image_review.json", review)
    return root, paths, p, m, e


def approve_image(root, paths):
    return accept_stage(root, "image_reviewed", {key: paths[key] for key in ("image", "generation_handoff")}, paths["image_review"])


def final_ready_v2(tmp_path):
    root, paths, p, m, e = image_ready(tmp_path)
    approve_image(root, paths)
    package = valid_package(root)
    from posfoxgen.editable import build_poster, export_svg
    source_assets = json.loads(paths["asset_table"].read_text())
    build_poster(e, source_assets, package)
    export_svg(e, source_assets, package)
    for stage in ("reconstructed", "repairing"):
        accept_stage(root, stage, {"poster_svg": package / "poster.svg"})
    artifacts = {"poster_" + suffix: package / ("poster." + suffix) for suffix in ("html", "svg", "png", "pdf")}
    artifacts["render_report"] = write(package / "render_report.json", {"rendered": True, "layout_pass": True, "blockers": []})
    artifacts["quality_assessment"] = write(package / "quality_assessment.json", {"valid": True, "blockers": []})
    # This binds the actual reviewed generation and the delivery PNG, rather
    # than allowing an unrelated pair of audit images to satisfy the gate.
    m.update(generated_image_path=str(paths["image"]), generated_image_sha256=file_hash(paths["image"]), render_path=str(artifacts["poster_png"]), render_sha256=file_hash(artifacts["poster_png"]))
    artifacts["poster_spec"] = write(package / "poster_spec.json", e)
    artifacts["reconstruction_manifest"] = write(package / "reconstruction_manifest.json", m)
    fidelity = {"reviewer": "independent-fidelity-reviewer", "independent": True, "decision": "pass", "checked_panel_ids": ["method"], "checked_object_ids": ["explanation", "method-diagram", "divider"], "whole_poster_checked": True, "evidence": {"generated_image": m["generated_image_path"], "rendered_image": m["render_path"], "actually_viewed": True}, "findings": [], "input_hashes": {"panel_plan": canonical_hash(p), "manifest": canonical_hash(m), "exported_spec": canonical_hash(e)}}
    artifacts["fidelity_review"] = write(package / "fidelity_review.json", fidelity)
    artifacts["manifest"] = package / "manifest.json"
    review = {"reviewer": "independent-final-reviewer", "decision": "pass", "findings": [], "input_hashes": {key: file_hash(artifacts[key]) for key in ("poster_html", "poster_svg", "poster_png", "poster_pdf", "render_report")}}
    review["input_hashes"].update({key: file_hash(paths[key]) for key in ("logic_plan", "panel_plan")})
    final_review = write(package / "reviews/final_review.json", review)
    create_delivery_manifest(package, ["."])
    return root, paths, artifacts, final_review


def test_v2_planned_requires_debate_and_technical_story(tmp_path):
    root, paths, *_ = inputs(tmp_path)
    with pytest.raises(ValueError, match="technical_story|content_debate"):
        accept_stage(root, "planned", {key: paths[key] for key in ("logic_plan", "panel_plan")})
    assert status_run(root)["stage"] == "assets"


def test_v2_planned_executes_real_source_grounded_debate_validator(tmp_path):
    root, paths, *_ = inputs(tmp_path)
    debate = json.loads(paths["content_debate"].read_text()); debate["participants"].pop()
    write(paths["content_debate"], debate)
    with pytest.raises(ValueError, match="missing_debate_role"):
        approve_logic(root, paths)


def test_v2_image_gate_requires_handoff_and_executes_actual_contract(tmp_path):
    root, paths, *_ = image_ready(tmp_path)
    with pytest.raises(ValueError, match="generation_handoff"):
        accept_stage(root, "image_reviewed", {"image": paths["image"]}, paths["image_review"])
    handoff = json.loads(paths["generation_handoff"].read_text()); handoff["image_slots"][0]["render_mode"] = "placeholder"
    write(paths["generation_handoff"], handoff)
    with pytest.raises(ValueError, match="source_not_drawn"):
        approve_image(root, paths)


@pytest.mark.parametrize("key,value", [("checked_image_slot_ids", []), ("all_planned_visuals_drawn", False), ("independent", False)])
def test_v2_image_review_must_independently_inspect_all_drawn_slots(tmp_path, key, value):
    root, paths, *_ = image_ready(tmp_path)
    review = json.loads(paths["image_review"].read_text()); review[key] = value
    write(paths["image_review"], review)
    with pytest.raises(ValueError, match="visual|slot|independent"):
        approve_image(root, paths)


def test_v2_handoff_cannot_substitute_another_content_debate(tmp_path):
    root, paths, *_ = image_ready(tmp_path)
    handoff = json.loads(paths["generation_handoff"].read_text())
    handoff["technical_story"]["model"]["text"] = "A different model not in the approved content debate"
    write(paths["generation_handoff"], handoff)
    with pytest.raises(ValueError, match="approved|technical_story"):
        approve_image(root, paths)


def test_v2_finalize_requires_native_spec_fidelity_review_and_manifest(tmp_path):
    root, paths, artifacts, review = final_ready_v2(tmp_path)
    for key in ("poster_spec", "fidelity_review", "reconstruction_manifest"): artifacts.pop(key)
    with pytest.raises(ValueError, match="poster_spec|fidelity_review|reconstruction_manifest"):
        accept_stage(root, "finalized", artifacts, review)


def test_v2_finalize_runs_reconstruction_audit_and_rejects_wrong_asset(tmp_path):
    root, paths, artifacts, review = final_ready_v2(tmp_path)
    spec = json.loads(artifacts["poster_spec"].read_text()); spec["panels"][0]["objects"][1]["asset_id"] = "unrelated-crop"
    write(artifacts["poster_spec"], spec)
    create_delivery_manifest(artifacts["manifest"].parent, ["."])
    with pytest.raises(ValueError, match="object_mismatch"):
        accept_stage(root, "finalized", artifacts, review)


def test_v2_native_package_can_complete_and_revalidation_checks_upstream_image_review(tmp_path):
    root, paths, artifacts, review = final_ready_v2(tmp_path)
    accept_stage(root, "finalized", artifacts, review)
    assert validate_delivery(root)["pass"]
    # Old or externally written state can have matching file receipts but an
    # image review that never checked the planned figures. Revalidation must
    # execute v2 checks, rather than accepting its complete label.
    image_review = json.loads(paths["image_review"].read_text()); image_review["all_planned_visuals_drawn"] = False
    write(paths["image_review"], image_review)
    run_path = root / "run.json"; run = json.loads(run_path.read_text())
    run["receipts"]["image_reviewed"]["artifact_hashes"]["acceptance_review"]["sha256"] = file_hash(paths["image_review"])
    previous = run["paper"]["sha256"]
    from posfoxgen.state import STAGES
    for stage in STAGES[1:]:
        receipt = run["receipts"][stage]
        receipt["upstream_receipt_hash"] = previous
        previous = canonical_hash(receipt)
    write(run_path, run)
    result = validate_delivery(root)
    assert not result["pass"]
    assert "v2_image_review_invalid" in {b["code"] for b in result["blockers"]}


def test_legacy_run_without_profile_keeps_legacy_compatibility(tmp_path):
    from test_state import final_ready
    root, _, artifacts, review = final_ready(tmp_path)
    run_path = root / "run.json"; run = json.loads(run_path.read_text()); run.pop("profile")
    write(run_path, run)
    accept_stage(root, "finalized", artifacts, review)
    assert validate_delivery(root)["pass"]


def test_v2_cannot_approve_audited_object_ids_missing_from_actual_exports(tmp_path):
    root, paths, artifacts, review = final_ready_v2(tmp_path)
    # Delete the actual image object, retaining the old metadata.spec and
    # audit JSON. Rebinding final file hashes must not approve that deletion.
    html = artifacts["poster_html"].read_text()
    artifacts["poster_html"].write_text(re.sub(r'<img [^>]*id="method-diagram"[^>]*>', '', html))
    # Keep a second valid image so the generic package format check passes;
    # only the new object/spec binding check should reject the missing ID.
    html = artifacts["poster_html"].read_text().replace('</section>', '<img data-asset-id="fig1" data-source-sha256="' + file_hash(artifacts["poster_html"].parent / "assets/fig1.png") + '" src="assets/fig1.png"></section>')
    artifacts["poster_html"].write_text(html)
    rebind_final(artifacts, review)
    assert '<img id="method-diagram"' not in artifacts["poster_html"].read_text()
    with pytest.raises(ValueError, match="export|binding"):
        accept_stage(root, "finalized", artifacts, review)


def rebind_final(artifacts, review_path):
    # Re-accept the changed native SVG through its legitimate intermediate
    # stages so the negative test reaches the actual final acceptance gate.
    root = artifacts["poster_html"].parent.parent
    stage = status_run(root)["stage"]
    if stage == "image_reviewed":
        accept_stage(root, "reconstructed", {"poster_svg": artifacts["poster_svg"]})
        accept_stage(root, "repairing", {"poster_svg": artifacts["poster_svg"]})
    review = json.loads(review_path.read_text())
    for key in ("poster_html", "poster_svg", "poster_png", "poster_pdf", "render_report"):
        review["input_hashes"][key] = file_hash(artifacts[key])
    write(review_path, review)
    create_delivery_manifest(artifacts["manifest"].parent, ["."])


@pytest.mark.parametrize("format", ["html", "svg"])
def test_v2_real_rule_deletion_is_blocked_despite_unchanged_metadata(tmp_path, format):
    root, paths, artifacts, review = final_ready_v2(tmp_path)
    path = artifacts["poster_" + format]
    if format == "html":
        path.write_text(re.sub(r'<svg [^>]*id="divider"[^>]*>.*?</svg>', '', path.read_text(), flags=re.S))
    else:
        tree = ET.parse(path); parents = {c: parent for parent in tree.iter() for c in parent}
        for node in list(tree.iter()):
            if node.get("id") == "divider": parents[node].remove(node)
        tree.write(path, encoding="unicode")
    rebind_final(artifacts, review)
    with pytest.raises(ValueError, match="export|binding"):
        accept_stage(root, "finalized", artifacts, review)


@pytest.mark.parametrize("change", ["native_text", "native_line_break", "image_geometry", "rule_style", "svg_image_identity", "metadata_spec"])
def test_v2_real_rendered_objects_cannot_disagree_with_audited_spec(tmp_path, change):
    root, paths, artifacts, review = final_ready_v2(tmp_path)
    if change == "native_text":
        path = artifacts["poster_html"]; value = path.read_text()
        # Replace rendered prose only, leaving the copy inside metadata intact.
        path.write_text(value.replace('>The method iterates using a verifiable design objective.</div>', '>An unreviewed replacement claim.</div>', 1))
    elif change == "native_line_break":
        path = artifacts["poster_html"]; value = path.read_text()
        path.write_text(value.replace('>The method iterates using a verifiable design objective.</div>', '>The method\niterates using a verifiable design objective.</div>', 1))
    elif change == "image_geometry":
        path = artifacts["poster_html"]; value = path.read_text()
        value = re.sub(r'(<img [^>]*id="method-diagram"[^>]*style=")([^"]*)', lambda m: m[1] + m[2].replace('width:180px', 'width:0px'), value)
        path.write_text(value)
    elif change == "rule_style":
        path = artifacts["poster_svg"]; tree = ET.parse(path)
        next(n for n in tree.iter() if n.get("id") == "divider").set("stroke", "none")
        tree.write(path, encoding="unicode")
    elif change == "svg_image_identity":
        path = artifacts["poster_svg"]; value = path.read_text()
        path.write_text(value.replace('data-asset-id="fig1"', 'data-asset-id="unrelated"'))
    else:
        spec = json.loads(artifacts["poster_spec"].read_text()); spec["title"] = "A different unexported title"
        write(artifacts["poster_spec"], spec)
        fidelity = json.loads(artifacts["fidelity_review"].read_text()); fidelity["input_hashes"]["exported_spec"] = canonical_hash(spec)
        write(artifacts["fidelity_review"], fidelity)
    rebind_final(artifacts, review)
    with pytest.raises(ValueError, match="export|binding"):
        accept_stage(root, "finalized", artifacts, review)


def test_reconstruction_intake_does_not_require_an_extra_independent_image_reviewer(tmp_path):
    root, paths, *_ = image_ready(tmp_path)
    review=json.loads(paths['image_review'].read_text())
    review.update(review_mode='reconstruction_intake',reviewer='reconstruction-executor',independent=False)
    write(paths['image_review'],review)
    approve_image(root,paths)


def test_no_visual_issues_can_finalize_without_entering_repair_stage(tmp_path):
    root, paths, artifacts, review = final_ready_v2(tmp_path)
    run_path=root/'run.json';run=json.loads(run_path.read_text())
    run['receipts'].pop('repairing');run['stage']='reconstructed'
    write(run_path,run)
    accept_stage(root,'finalized',artifacts,review)
    assert status_run(root)['stage']=='finalized'

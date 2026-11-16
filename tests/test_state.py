import json
from pathlib import Path

import pytest

from posfoxgen.state import accept_stage, file_hash, init_run, status_run, validate_delivery
from posfoxgen.delivery import create_delivery_manifest
from test_delivery import valid_package


def start(tmp_path):
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"test paper bytes")
    root = tmp_path / "run"
    init_run(root, paper)
    return root


def test_cannot_skip_stages(tmp_path):
    root = start(tmp_path)
    with pytest.raises(ValueError, match="transition"):
        accept_stage(root, "reconstructed", [])
    assert status_run(root)["stage"] == "input"


def test_changed_upstream_artifact_invalidates_descendants(tmp_path):
    root = start(tmp_path)
    artifact = root / "asset_table.json"
    artifact.write_text('{"assets": []}')
    accept_stage(root, "assets", [artifact])
    plan = root / "logic_plan.json"
    plan.write_text('{"claims": []}')
    accept_stage(root, "planned", [plan])
    artifact.write_text('{"assets": [{"id": "changed"}]}')
    result = status_run(root)
    assert result["stage"] == "input"
    assert result["status"] == "pending"
    assert set(result["invalidated_stages"]) >= {"assets", "planned"}


def test_missing_review_does_not_promote_logic_stage(tmp_path):
    root = start(tmp_path)
    artifact = root / "a.json"
    artifact.write_text('{}')
    accept_stage(root, "assets", [artifact])
    accept_stage(root, "planned", [artifact])
    with pytest.raises(ValueError, match="logic"):
        accept_stage(root, "logic_approved", [artifact])


def test_pending_interruption_never_means_pass(tmp_path):
    root = start(tmp_path)
    result = status_run(root)
    assert result["status"] == "pending"
    assert result["stage"] == "input"
    events = [json.loads(l) for l in (root / "events.jsonl").read_text().splitlines()]
    assert events[0]["event"] == "run_initialized"


def test_profile_is_explicit_persisted_and_cannot_be_overridden_on_resume(tmp_path):
    root = start(tmp_path)
    assert status_run(root)["profile"] == "legacy-v1"
    second = tmp_path / "v2"
    init_run(second, tmp_path / "paper.pdf", profile="posfoxgen-v2")
    assert status_run(second)["profile"] == "posfoxgen-v2"
    with pytest.raises(ValueError, match="already exists"):
        init_run(second, tmp_path / "paper.pdf", profile="legacy-v1")


def test_unknown_profile_is_rejected(tmp_path):
    root = start(tmp_path)
    with pytest.raises(ValueError, match="profile"):
        init_run(tmp_path / "other", tmp_path / "paper.pdf", profile="typo-v2")


def approved_logic_run(tmp_path):
    from test_logic import valid_inputs

    root = start(tmp_path)
    a, l, p, r = valid_inputs()
    paths = {}
    for key, value in (("asset_table", a), ("logic_plan", l), ("panel_plan", p), ("logic_review", r)):
        path = root / (key + ".json")
        path.write_text(json.dumps(value))
        paths[key] = path
    accept_stage(root, "assets", {"asset_table": paths["asset_table"]})
    accept_stage(root, "planned", {key: paths[key] for key in ("logic_plan", "panel_plan")})
    accept_stage(root, "logic_approved", {"logic_review": paths["logic_review"]}, review=paths["logic_review"])
    return root


def test_nonlocal_semantic_error_cannot_be_promoted_by_high_score(tmp_path):
    root = approved_logic_run(tmp_path)
    image = root / "candidate.png"
    image.write_bytes(b"candidate image")
    review = {"reviewer": "harness-review", "decision": "pass", "score": 99, "findings": [{"id": "wrong-causal-order", "severity": "error", "repairable": False}]}
    with pytest.raises(ValueError, match="gate failed"):
        accept_stage(root, "image_reviewed", {"image": image}, review)
    assert status_run(root)["stage"] == "logic_approved"


def test_image_review_has_no_two_attempt_limit(tmp_path):
    root = approved_logic_run(tmp_path)
    image = root / "candidate.png"
    image.write_bytes(b"candidate image")
    review = image_review(root, image)
    for _ in range(5):
        accept_stage(root, "image_reviewed", {"image": image}, review)
    assert status_run(root)["stage"] == "image_reviewed"


def test_finalization_requires_html_and_preview_before_marking_complete(tmp_path):
    root = approved_logic_run(tmp_path)
    image = root / "candidate.png"
    image.write_bytes(b"candidate image")
    review = image_review(root, image)
    accept_stage(root, "image_reviewed", {"image": image}, review)
    svg = root / "reconstruction.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    accept_stage(root, "reconstructed", [svg])
    accept_stage(root, "repairing", [svg])
    with pytest.raises(ValueError, match="Finalization requires"):
        accept_stage(root, "finalized", [svg], review)
    assert status_run(root)["status"] == "pending"


def test_review_path_relative_to_run_reads_and_binds_same_file(tmp_path, monkeypatch):
    root = approved_logic_run(tmp_path)
    image = root / "candidate.png"
    image.write_bytes(b"candidate image")
    review_path = root / "image_review.json"
    review_path.write_text(json.dumps(image_review(root, image, "run-local-reviewer")))
    monkeypatch.chdir(tmp_path)
    receipt = accept_stage(root, "image_reviewed", {"image": image}, "image_review.json")
    assert receipt["reviewer"] == "run-local-reviewer"
    assert receipt["artifact_hashes"]["acceptance_review"]["path"] == str(review_path.resolve())


def test_existing_cwd_review_path_is_not_prefixed_twice(tmp_path, monkeypatch):
    root = approved_logic_run(tmp_path)
    image = root / "candidate.png"
    image.write_bytes(b"candidate image")
    review_path = root / "image_review.json"
    review_path.write_text(json.dumps(image_review(root, image, "cwd-reviewer")))
    monkeypatch.chdir(tmp_path)
    receipt = accept_stage(root, "image_reviewed", {"image": image}, "run/image_review.json")
    assert receipt["artifact_hashes"]["acceptance_review"]["path"] == str(review_path.resolve())
    assert receipt["reviewer"] == "cwd-reviewer"


def test_run_relative_review_takes_priority_over_cwd_namesake(tmp_path, monkeypatch):
    root = approved_logic_run(tmp_path)
    image = root / "candidate.png"
    image.write_bytes(b"candidate image")
    review_path = root / "image_review.json"
    review_path.write_text(json.dumps(image_review(root, image, "run-reviewer")))
    (tmp_path / "image_review.json").write_text(json.dumps({"reviewer": "different-cwd-reviewer", "decision": "reject", "findings": []}))
    monkeypatch.chdir(tmp_path)
    receipt = accept_stage(root, "image_reviewed", {"image": image}, "image_review.json")
    assert receipt["reviewer"] == "run-reviewer"
    assert receipt["artifact_hashes"]["acceptance_review"]["path"] == str(review_path.resolve())



def image_review(root, image, reviewer="harness-review"):
    return {"reviewer": reviewer, "decision": "pass", "findings": [], "input_hashes": {
        "image": file_hash(image), "logic_plan": file_hash(root / "logic_plan.json"),
        "panel_plan": file_hash(root / "panel_plan.json")}}


@pytest.mark.parametrize("key", ["image", "logic_plan", "panel_plan"])
def test_image_review_must_bind_each_actual_input(tmp_path, key):
    root = approved_logic_run(tmp_path)
    image = root / "candidate.png"
    image.write_bytes(b"candidate")
    review = image_review(root, image)
    review["input_hashes"][key] = "old-review-hash"
    with pytest.raises(ValueError, match="hash"):
        accept_stage(root, "image_reviewed", {"image": image}, review)
    assert status_run(root)["stage"] == "logic_approved"


def test_image_review_missing_input_hashes_is_rejected(tmp_path):
    root = approved_logic_run(tmp_path)
    image = root / "candidate.png"
    image.write_bytes(b"candidate")
    review = image_review(root, image)
    review.pop("input_hashes")
    with pytest.raises(ValueError, match="hash"):
        accept_stage(root, "image_reviewed", {"image": image}, review)


def final_ready(tmp_path):
    root = approved_logic_run(tmp_path)
    package = valid_package(root)
    image = package / "poster.png"
    accept_stage(root, "image_reviewed", {"image": image}, image_review(root, image))
    accept_stage(root, "reconstructed", {"poster_svg": package / "poster.svg"})
    accept_stage(root, "repairing", {"poster_svg": package / "poster.svg"})
    render = package / "render_report.json"
    render.write_text(json.dumps({"rendered": True, "layout_pass": True, "blockers": []}))
    quality = package / "quality_assessment.json"
    quality.write_text(json.dumps({"valid": True, "blockers": []}))
    artifacts = {"poster_" + suffix: package / ("poster." + suffix) for suffix in ("html", "svg", "png", "pdf")}
    artifacts.update(render_report=render, quality_assessment=quality, manifest=package / "manifest.json")
    review = {"reviewer": "independent-final-reviewer", "decision": "pass", "findings": [], "input_hashes": {k: file_hash(v) for k, v in artifacts.items() if k not in {"quality_assessment", "manifest"}}}
    review["input_hashes"].update({key: file_hash(root / (key + ".json")) for key in ("logic_plan", "panel_plan")})
    review_path = package / "reviews/final_review.json"
    review_path.write_text(json.dumps(review))
    create_delivery_manifest(package, ["."])
    return root, package, artifacts, review_path


def test_actual_native_four_format_delivery_is_required_and_passes(tmp_path):
    root, package, artifacts, review = final_ready(tmp_path)
    accept_stage(root, "finalized", artifacts, review)
    result = validate_delivery(root)
    assert result["pass"], result
    assert result["scientific_quality_pass"] is None


@pytest.mark.parametrize("key", ["poster_html", "poster_svg", "poster_png", "poster_pdf", "render_report", "logic_plan", "panel_plan"])
def test_final_review_must_bind_each_actual_input(tmp_path, key):
    root, package, artifacts, review_path = final_ready(tmp_path)
    review = json.loads(review_path.read_text())
    review["input_hashes"][key] = "stale-final-review"
    review_path.write_text(json.dumps(review))
    create_delivery_manifest(package, ["."])
    with pytest.raises(ValueError, match="hash"):
        accept_stage(root, "finalized", artifacts, review_path)


@pytest.mark.parametrize("document,key,value", [("render_report", "rendered", False), ("render_report", "layout_pass", False), ("render_report", "blockers", ["overflow"]), ("quality_assessment", "valid", False), ("quality_assessment", "blockers", ["logic error"])])
def test_render_and_quality_hard_gates_cannot_be_overridden(tmp_path, document, key, value):
    root, package, artifacts, review_path = final_ready(tmp_path)
    target = artifacts[document]
    report = json.loads(target.read_text()); report[key] = value
    target.write_text(json.dumps(report))
    review = json.loads(review_path.read_text())
    if document == "render_report":
        review["input_hashes"][document] = file_hash(target)
    review_path.write_text(json.dumps(review))
    create_delivery_manifest(package, ["."])
    with pytest.raises(ValueError, match="render|quality"):
        accept_stage(root, "finalized", artifacts, review_path)


def test_fake_export_cannot_pass_after_rebinding_review_and_manifest(tmp_path):
    root, package, artifacts, review_path = final_ready(tmp_path)
    artifacts["poster_pdf"].write_bytes(b"not a PDF")
    review = json.loads(review_path.read_text())
    review["input_hashes"]["poster_pdf"] = file_hash(artifacts["poster_pdf"])
    review_path.write_text(json.dumps(review))
    create_delivery_manifest(package, ["."])
    with pytest.raises(ValueError, match="package"):
        accept_stage(root, "finalized", artifacts, review_path)


def test_current_receipt_deliverable_must_be_manifest_bound_in_same_package(tmp_path):
    root, package, artifacts, review_path = final_ready(tmp_path)
    unbound = package / "unbound.html"
    unbound.write_text(artifacts["poster_html"].read_text())
    artifacts["poster_html"] = unbound
    review = json.loads(review_path.read_text()); review["input_hashes"]["poster_html"] = file_hash(unbound)
    review_path.write_text(json.dumps(review))
    create_delivery_manifest(package, ["poster.html", "poster.svg", "poster.png", "poster.pdf", "assets", "reviews", "source", "render_report.json", "quality_assessment.json"])
    with pytest.raises(ValueError, match="manifest"):
        accept_stage(root, "finalized", artifacts, review_path)


def test_final_review_must_be_a_manifest_bound_file(tmp_path):
    root, package, artifacts, review_path = final_ready(tmp_path)
    with pytest.raises(ValueError, match="review"):
        accept_stage(root, "finalized", artifacts, json.loads(review_path.read_text()))


def test_validate_delivery_rechecks_package_and_reports_in_legacy_complete_receipt(tmp_path):
    root, package, artifacts, review_path = final_ready(tmp_path)
    accept_stage(root, "finalized", artifacts, review_path)
    # Simulate a legacy/externally written complete receipt with internally matching
    # file hashes, yet an actual corrupt export and failed quality/render report.
    artifacts["poster_pdf"].write_bytes(b"invalid PDF")
    artifacts["render_report"].write_text(json.dumps({"rendered": False, "layout_pass": False, "blockers": []}))
    artifacts["quality_assessment"].write_text(json.dumps({"valid": False, "blockers": []}))
    review = json.loads(review_path.read_text())
    for key in ("poster_pdf", "render_report"):
        review["input_hashes"][key] = file_hash(artifacts[key])
    review_path.write_text(json.dumps(review))
    create_delivery_manifest(package, ["."])
    run_path = root / "run.json"; run = json.loads(run_path.read_text())
    receipt = run["receipts"]["finalized"]; receipt["review"] = review
    for record in receipt["artifact_hashes"].values():
        record["sha256"] = file_hash(record["path"])
    run_path.write_text(json.dumps(run))
    result = validate_delivery(root)
    assert not result["pass"]
    assert {b["code"] for b in result["blockers"]} >= {"package_invalid", "render_invalid", "quality_invalid"}


def test_image_stage_requires_current_named_image_artifact(tmp_path):
    root = approved_logic_run(tmp_path)
    image = root / "candidate.png"; image.write_bytes(b"candidate")
    review = image_review(root, image)
    with pytest.raises(ValueError, match="image"):
        accept_stage(root, "image_reviewed", {"unrelated": image}, review)


@pytest.mark.parametrize("stage", ["image_reviewed", "finalized"])
def test_later_review_cannot_override_approved_upstream_plan(tmp_path, stage):
    if stage == "finalized":
        root, package, artifacts, review_path = final_ready(tmp_path)
        review = json.loads(review_path.read_text())
    else:
        root = approved_logic_run(tmp_path)
        image = root / "candidate.png"; image.write_bytes(b"candidate")
        artifacts = {"image": image}; review = image_review(root, image)
    substitute = root / "unapproved-plan.json"
    substitute.write_text('{"claims": [{"id": "c1", "text": "not independently approved"}]}')
    artifacts["logic_plan"] = substitute
    review["input_hashes"]["logic_plan"] = file_hash(substitute)
    if stage == "finalized":
        review_path.write_text(json.dumps(review)); create_delivery_manifest(package, ["."])
        review = review_path
    with pytest.raises(ValueError, match="upstream"):
        accept_stage(root, stage, artifacts, review)

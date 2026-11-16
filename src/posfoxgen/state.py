"""Hash-bound stage receipts for an interrupted/resumable Harness workflow."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from .logic import canonical_hash, read_object, validate_logic
from .delivery import validate_package
from .generation_contract import validate_content_debate, validate_generation_handoff
from .reconstruction_audit import validate_reconstruction_audit
from .export_bindings import validate_export_bindings

STAGES = ("input", "assets", "planned", "logic_approved", "image_reviewed", "reconstructed", "repairing", "finalized")


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _save(root, run):
    temporary = root / "run.json.tmp"
    temporary.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(root / "run.json")


def _event(root, event, **details):
    with (root / "events.jsonl").open("a") as handle:
        handle.write(json.dumps({"at": _now(), "event": event, **details}, ensure_ascii=False) + "\n")


def init_run(run_dir, paper, split="development", profile="legacy-v1"):
    root = Path(run_dir).resolve()
    source = Path(paper).resolve(strict=True)
    if split not in {"development", "train", "training", "heldout", "test", "validation", "independent"}:
        raise ValueError("Unknown dataset split")
    if profile not in {"legacy-v1", "posfoxgen-v2"}:
        raise ValueError("Unknown run profile")
    root.mkdir(parents=True, exist_ok=True)
    if (root / "run.json").exists():
        raise ValueError("Run already exists; resume it with status")
    run = {"schema_version": 1, "run_id": uuid.uuid4().hex, "created_at": _now(), "paper": {"path": str(source), "sha256": file_hash(source)}, "split": split, "profile": profile, "stage": "input", "status": "pending", "receipts": {}, "invalidated_stages": [], "model_execution": "external Harness tools only; no model API client"}
    _save(root, run)
    _event(root, "run_initialized", paper=run["paper"], split=split, profile=profile)
    return run


def status_run(run_dir):
    root = Path(run_dir).resolve()
    run = json.loads((root / "run.json").read_text())
    first_invalid = None
    source = Path(run["paper"]["path"])
    if not source.exists() or file_hash(source) != run["paper"]["sha256"]:
        first_invalid = 1
    previous = run["paper"]["sha256"]
    for i, stage in enumerate(STAGES[1:], 1):
        receipt = run["receipts"].get(stage)
        if receipt is None:
            continue
        stale = receipt.get("upstream_receipt_hash") != previous
        for record in receipt.get("artifact_hashes", {}).values():
            path = Path(record["path"])
            if not path.exists() or file_hash(path) != record["sha256"]:
                stale = True
        if stale and (first_invalid is None or i < first_invalid):
            first_invalid = i
        previous = canonical_hash(receipt)
    if first_invalid is not None:
        invalidated = [s for s in STAGES[first_invalid:] if s in run["receipts"]]
        for stage in invalidated:
            del run["receipts"][stage]
        run.update(stage=STAGES[first_invalid - 1], status="pending", invalidated_stages=invalidated)
        _save(root, run)
        _event(root, "receipts_invalidated", stages=invalidated, reason="source, upstream receipt or bound artifact changed")
    return run


def _artifact_records(root, artifacts):
    if isinstance(artifacts, dict):
        items = artifacts.items()
    else:
        items = ((Path(p).stem, p) for p in artifacts)
    records = {}
    for name, value in items:
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        path = path.resolve(strict=True)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Artifact is not a nonempty file: {path}")
        records[str(name)] = {"path": str(path), "sha256": file_hash(path)}
    return records


def _review_blockers(review, allow_local=False):
    if not isinstance(review, dict) or review.get("decision") != "pass":
        return ["Harness review must explicitly pass"]
    if not review.get("reviewer"):
        return ["Harness reviewer identity is required"]
    blockers = list(review.get("blockers", [])) + list(review.get("hard_blockers", []))
    for finding in review.get("findings", []):
        if finding.get("resolved") is True:
            continue
        severity = finding.get("severity", "blocking")
        if severity in {"blocking", "error", "critical"} and not (allow_local and finding.get("repairable") is True):
            blockers.append(finding)
        if finding.get("repairable") is False:
            blockers.append(finding)
    return blockers


def _resolve_review_path(root, value):
    """Resolve once so the read and receipt always refer to the same file.

    Absolute paths are used directly. A relative path inside the run takes
    priority; an existing cwd-relative path is supported for CLI callers that
    already prefix the run directory.
    """
    path = Path(value)
    if path.is_absolute():
        return path.resolve(strict=True)
    run_relative = root / path
    if run_relative.exists():
        return run_relative.resolve(strict=True)
    if path.exists():
        return path.resolve(strict=True)
    return run_relative.resolve(strict=True)



IMAGE_REVIEW_INPUTS = ("image", "logic_plan", "panel_plan")
FINAL_REVIEW_INPUTS = ("poster_html", "poster_svg", "poster_png", "poster_pdf", "render_report", "logic_plan", "panel_plan")
FINAL_ARTIFACTS = ("poster_html", "poster_svg", "poster_png", "poster_pdf", "render_report", "quality_assessment", "manifest", "acceptance_review")


def _review_hash_blockers(review, records, keys):
    hashes = review.get("input_hashes") if isinstance(review, dict) else None
    blockers = []
    for key in keys:
        record = records.get(key)
        try:
            actual = file_hash(record["path"]) if record else None
        except (OSError, TypeError):
            actual = None
        if actual is None or not isinstance(hashes, dict) or hashes.get(key) != actual:
            blockers.append({"code": "review_hash_mismatch", "message": f"Review input hash must match the current {key} file", "key": key})
    return blockers


def _finalization_blockers(records, all_records, review, extra_artifacts=()):
    """Recheck real bytes and reports both on acceptance and later validation."""
    blockers = []
    required_artifacts = FINAL_ARTIFACTS + tuple(extra_artifacts)
    missing = [key for key in required_artifacts if key not in records]
    if missing:
        blockers.append({"code": "missing_delivery_artifact", "message": "Finalization requires current named files including a manifest-bound acceptance review", "keys": missing})
    blockers.extend(_review_hash_blockers(review, all_records, FINAL_REVIEW_INPUTS))
    for key, required, code in (("render_report", ("rendered", "layout_pass"), "render_invalid"), ("quality_assessment", ("valid",), "quality_invalid")):
        try:
            report = read_object(records[key]["path"])
            if not isinstance(report, dict) or any(report.get(flag) is not True for flag in required) or report.get("blockers") != []:
                raise ValueError("Required success flags must be true and blockers must be []")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            blockers.append({"code": code, "message": f"{key} failed: {exc}"})
    manifest_record = records.get("manifest")
    if manifest_record:
        manifest_path = Path(manifest_record["path"])
        package_root = manifest_path.parent
        try:
            package = validate_package(package_root, manifest_path)
            if not package["pass"]:
                blockers.append({"code": "package_invalid", "message": "Actual delivery package validation failed", "details": package["blockers"]})
            manifest = read_object(manifest_path)
            bound = {(package_root / r["path"]).resolve(): r for r in manifest.get("files", []) if isinstance(r, dict) and isinstance(r.get("path"), str)}
            for key in required_artifacts:
                if key == "manifest" or key not in records:
                    continue
                path = Path(records[key]["path"]).resolve()
                binding = bound.get(path)
                expected_suffix = {"poster_html": ".html", "poster_svg": ".svg", "poster_png": ".png", "poster_pdf": ".pdf"}.get(key)
                if not path.is_relative_to(package_root) or binding is None or binding.get("sha256") != file_hash(path):
                    blockers.append({"code": "manifest_binding_mismatch", "message": f"{key} must be an exact manifest-bound file in the same package"})
                elif expected_suffix and (path.suffix.lower() != expected_suffix or binding.get("role") != "deliverable"):
                    blockers.append({"code": "manifest_binding_mismatch", "message": f"{key} must bind the actual {expected_suffix} deliverable in the manifest"})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            blockers.append({"code": "package_invalid", "message": f"Delivery package validation failed: {exc}"})
    return blockers


def _approved_plan_records(run):
    records = {}
    for stage in ("assets", "planned", "logic_approved"):
        records.update(run["receipts"].get(stage, {}).get("artifact_hashes", {}))
    return {key: records[key] for key in ("logic_plan", "panel_plan", "technical_story", "content_debate") if key in records}


V2_FINAL_ARTIFACTS = ("reconstruction_manifest", "fidelity_review", "poster_spec")


def _v2_documents(records, keys):
    documents = {}
    for key in keys:
        if key not in records:
            raise ValueError(f"v2 acceptance requires named {key} artifact")
        documents[key] = read_object(records[key]["path"])
    return documents


def _v2_planning_blockers(run, records):
    try:
        docs = _v2_documents(records, ("asset_table", "logic_plan", "panel_plan", "technical_story", "content_debate"))
        if docs["asset_table"].get("source", {}).get("paper_sha256") != run["paper"]["sha256"]:
            raise ValueError("asset_table source must bind this run's actual source paper SHA256")
        result = validate_content_debate(docs["asset_table"], docs["technical_story"], docs["content_debate"])
        return [] if result["pass"] else [{"code": "v2_content_debate_invalid", "message": "Source-grounded content debate did not pass", "details": result["blockers"]}]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [{"code": "v2_planning_invalid", "message": str(exc)}]


def _v2_image_blockers(run, records, image_records, review):
    blockers = _v2_planning_blockers(run, records)
    try:
        _v2_documents(image_records, ("generation_handoff", "acceptance_review"))
        if "image" not in image_records:
            raise ValueError("v2 acceptance requires named image artifact")
        docs = _v2_documents(records, ("asset_table", "logic_plan", "panel_plan", "technical_story", "content_debate", "generation_handoff"))
        handoff = docs["generation_handoff"]
        for handoff_key, approved_key in (("technical_story", "technical_story"), ("debate", "content_debate")):
            if canonical_hash(handoff.get(handoff_key)) != canonical_hash(docs[approved_key]):
                blockers.append({"code": "v2_handoff_plan_mismatch", "message": f"Generation handoff {handoff_key} must equal the approved {approved_key}"})
        result = validate_generation_handoff(docs["asset_table"], docs["panel_plan"], handoff, handoff.get("requirements"))
        if not result["pass"]:
            blockers.append({"code": "v2_generation_handoff_invalid", "message": "Generation handoff contract failed", "details": result["blockers"]})
        slots = {slot["id"] for panel in docs["panel_plan"].get("panels", []) for slot in panel.get("image_slots", [])}
        intake = isinstance(review, dict) and review.get("review_mode") == "reconstruction_intake" and bool(review.get("reviewer"))
        independent = isinstance(review, dict) and review.get("independent") is True and review.get("reviewer") not in {docs["logic_plan"].get("planner"), handoff.get("generator")}
        if not isinstance(review, dict) or not (intake or independent) or review.get("all_planned_visuals_drawn") is not True or not slots <= set(review.get("checked_image_slot_ids", [])):
            blockers.append({"code": "v2_image_review_invalid", "message": "Reconstruction intake or independent visual review must inspect every planned slot and declare all planned visuals fully drawn"})
        if _review_blockers(review, allow_local=True):
            blockers.append({"code": "v2_image_review_invalid", "message": "Independent image review must pass without nonlocal or unresolved hard blockers"})
        blockers.extend(_review_hash_blockers(review, records, IMAGE_REVIEW_INPUTS))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        blockers.append({"code": "v2_generation_handoff_invalid", "message": str(exc)})
    return blockers


def _v2_final_blockers(run, records, all_records):
    """Recheck actual upstream generation and current reconstruction artifacts."""
    blockers = []
    upstream = {}
    for stage in ("assets", "planned", "logic_approved"):
        upstream.update(run["receipts"].get(stage, {}).get("artifact_hashes", {}))
    image_records = run["receipts"].get("image_reviewed", {}).get("artifact_hashes", {})
    image_inputs = {**upstream, **image_records}
    try:
        image_review = read_object(image_records["acceptance_review"]["path"])
    except (OSError, ValueError, TypeError, KeyError):
        image_review = None
    blockers.extend(_v2_image_blockers(run, image_inputs, image_records, image_review))
    try:
        docs = _v2_documents(records, V2_FINAL_ARTIFACTS)
        panel_plan = read_object(all_records["panel_plan"]["path"])
        intended = docs["reconstruction_manifest"]
        if intended.get("generated_image_sha256") != file_hash(image_records["image"]["path"]) or intended.get("render_sha256") != file_hash(records["poster_png"]["path"]):
            blockers.append({"code": "v2_fidelity_image_mismatch", "message": "Fidelity manifest must bind the accepted generated image and actual current delivery PNG"})
        result = validate_reconstruction_audit(panel_plan, intended, docs["poster_spec"], docs["fidelity_review"])
        if not result["pass"]:
            blockers.append({"code": "v2_reconstruction_invalid", "message": "Independent panel and full-poster reconstruction audit failed", "details": result["blockers"]})
        # The assets-stage mapping is authoritative. A final-stage file with
        # the same key cannot redefine the scientific image an ID refers to.
        source_assets = run["receipts"]["assets"]["artifact_hashes"]["asset_table"]["path"]
        exported = validate_export_bindings(docs["poster_spec"], records["poster_html"]["path"], records["poster_svg"]["path"], source_assets)
        if not exported["pass"]:
            blockers.append({"code": "v2_export_binding_invalid", "message": "Actual HTML/SVG must match the audited native spec and authoritative source image bytes", "details": exported["blockers"]})
    except (OSError, ValueError, TypeError, KeyError) as exc:
        blockers.append({"code": "v2_reconstruction_invalid", "message": str(exc)})
    return blockers


def accept_stage(run_dir, stage, artifacts, review=None, reviewer="harness"):
    root = Path(run_dir).resolve()
    run = status_run(root)
    if stage not in STAGES[1:]:
        raise ValueError("Unknown acceptance stage")
    current_index, next_index = STAGES.index(run["stage"]), STAGES.index(stage)
    direct_delivery = run["stage"] == "reconstructed" and stage == "finalized"
    if next_index > current_index + 1 and not direct_delivery:
        raise ValueError(f"Invalid stage transition: {run['stage']} -> {stage}")
    records = _artifact_records(root, artifacts)
    if not records:
        raise ValueError("Stage acceptance requires actual artifact files")
    if isinstance(review, (str, Path)):
        review_path = _resolve_review_path(root, review)
        resolved_review = read_object(review_path)
        records.update(_artifact_records(root, {"acceptance_review": review_path}))
    else:
        resolved_review = review
    all_records = {}
    for name in STAGES[1:next_index]:
        all_records.update(run["receipts"].get(name, {}).get("artifact_hashes", {}))
    if next_index > STAGES.index("logic_approved"):
        approved_plans = _approved_plan_records(run)
        for key, approved in approved_plans.items():
            if key in records and records[key] != approved:
                raise ValueError(f"Cannot override upstream approved {key}; return to planning and logic review")
        all_records.update(approved_plans)
    all_records.update(records)
    profile_v2 = run.get("profile", "legacy-v1") == "posfoxgen-v2"
    if profile_v2 and stage == "planned":
        blockers = _v2_planning_blockers(run, all_records)
        if blockers:
            raise ValueError("v2 planning gate failed: " + json.dumps(blockers, ensure_ascii=False))
    if stage == "logic_approved":
        needed = {}
        for key in ("asset_table", "logic_plan", "panel_plan"):
            record = all_records.get(key)
            if record is None:
                raise ValueError(f"logic acceptance requires {key}.json")
            needed[key] = read_object(record["path"])
        if resolved_review is None:
            record = all_records.get("logic_review")
            resolved_review = read_object(record["path"]) if record else None
        result = validate_logic(**needed, review=resolved_review)
        if not result["pass"]:
            raise ValueError("logic gate failed: " + json.dumps(result["blockers"], ensure_ascii=False))
    elif stage in {"image_reviewed", "finalized"}:
        blockers = _review_blockers(resolved_review, allow_local=stage == "image_reviewed")
        if blockers:
            raise ValueError(stage + " gate failed: " + json.dumps(blockers, ensure_ascii=False))
        if stage == "image_reviewed":
            blockers = _review_hash_blockers(resolved_review, all_records, IMAGE_REVIEW_INPUTS)
            if profile_v2:
                blockers.extend(_v2_image_blockers(run, all_records, records, resolved_review))
        else:
            blockers = _finalization_blockers(records, all_records, resolved_review, V2_FINAL_ARTIFACTS if profile_v2 else ())
            if profile_v2:
                blockers.extend(_v2_final_blockers(run, records, all_records))
        if blockers:
            raise ValueError(stage + " gate failed: " + json.dumps(blockers, ensure_ascii=False))
    previous_stage = "reconstructed" if stage == "finalized" and "repairing" not in run["receipts"] else STAGES[next_index - 1]
    previous = run["paper"]["sha256"] if previous_stage == "input" else canonical_hash(run["receipts"][previous_stage])
    receipt = {"stage": stage, "accepted_at": _now(), "artifact_hashes": records, "upstream_receipt_hash": previous, "reviewer": (resolved_review or {}).get("reviewer", reviewer), "decision": "pass", "blockers": [], "review": resolved_review}
    invalidated = [s for s in STAGES[next_index + 1:] if s in run["receipts"]]
    for name in invalidated:
        del run["receipts"][name]
    run["receipts"][stage] = receipt
    run.update(stage=stage, status="complete" if stage == "finalized" else "pending", invalidated_stages=invalidated)
    _save(root, run)
    _event(root, "stage_accepted", stage=stage, receipt_hash=canonical_hash(receipt), invalidated_stages=invalidated)
    return receipt


def validate_delivery(run_dir):
    """Revalidate the current package, reviews and reports, not just stage labels."""
    run = status_run(run_dir)
    blockers = []
    if run["stage"] != "finalized" or run["status"] != "complete":
        blockers.append({"code": "not_finalized", "message": "Run is pending or blocked, not a completed delivery"})
    receipt = run["receipts"].get("finalized", {})
    records = receipt.get("artifact_hashes", {})
    all_records = {}
    for stage in STAGES[1:]:
        all_records.update(run["receipts"].get(stage, {}).get("artifact_hashes", {}))
    all_records.update(_approved_plan_records(run))
    try:
        review_record = records.get("acceptance_review")
        review = read_object(review_record["path"]) if review_record else None
    except (OSError, ValueError, TypeError):
        review = None
    if _review_blockers(review):
        blockers.append({"code": "final_review_invalid", "message": "Current final review must explicitly pass without blockers"})
    profile_v2 = run.get("profile", "legacy-v1") == "posfoxgen-v2"
    blockers.extend(_finalization_blockers(records, all_records, review, V2_FINAL_ARTIFACTS if profile_v2 else ()))
    if profile_v2:
        blockers.extend(_v2_final_blockers(run, records, all_records))
    return {"pass": not blockers, "status": "pass" if not blockers else "pending", "blockers": blockers, "run_id": run["run_id"], "stage": run["stage"], "scientific_quality_pass": None}

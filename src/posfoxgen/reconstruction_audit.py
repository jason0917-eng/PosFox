"""Compare explicit intended objects with native exports and bind visual review.

These checks prove specification coverage and byte binding. Only the independent
Harness reviewer can judge fidelity to the actual generated and rendered images.
"""

import hashlib
import math
from pathlib import Path

from .generation_contract import AUXILIARY_ROLES
from .logic import canonical_hash, read_object


RENDER_FIELDS = {"emphasis", "align", "allow_distortion", "asset_id", "background", "background_policy", "color", "column_widths", "fill", "fit", "font_family", "font_size", "font_style", "font_weight", "header_fill", "header_rows", "line_height", "linecap", "padding", "position", "radius", "row_heights", "rows", "row_font_weights", "column_aligns", "row_fills", "source_ids", "stroke", "stroke_width", "svg", "text", "x", "y", "width", "height", "x1", "x2", "y1", "y2"}


def _positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def validate_reconstruction_audit(panel_plan, manifest, exported_spec, review=None):
    """Check intended panel objects and a real exported poster_spec.

manifest.panels[].objects[] uses the existing poster_spec object fields. Every
panel also supplies reference_evidence {path,region,assessment} and style
{background,alignment,decoration_lines:[object IDs]}. Objects add near_background;
    images add image_slot_id, fit='contain', aspect_ratio='preserve'. Explicit
    fill/distort is forbidden even with legacy allow_distortion permission. Native
    tables can fill source slots using explicit rows, column widths, row heights
    and font attributes, without stretching their text. Text explicitly
declares font_family/weight/size/color/align and a main-text typography_role.

The manifest binds actual generated_image_path/generated_image_sha256 and
render_path/render_sha256. Review binds canonical panel_plan, manifest and
exported_spec; declares independent panel/object/whole-poster inspection and
the two actual evidence paths, with actually_viewed=True. Pending review never
becomes approval merely because the machine checks pass.
"""
    panel_plan, manifest, exported_spec = map(read_object, (panel_plan, manifest, exported_spec))
    review = read_object(review) if review is not None else None
    blockers = []

    def block(code, message, **details):
        blockers.append({"code": code, "message": message, **details})

    image_paths = {}
    for name, path_key, hash_key in (("generated_image", "generated_image_path", "generated_image_sha256"), ("rendered_image", "render_path", "render_sha256")):
        try:
            path = Path(manifest[path_key]).resolve(strict=True)
            if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.get(hash_key):
                raise ValueError("actual bytes differ")
            image_paths[name] = path
        except (KeyError, ValueError, OSError, TypeError) as exc:
            block("image_hash_mismatch", f"Manifest must bind the actual {name} bytes: {exc}")
    planned = {p["id"]: p for p in panel_plan.get("panels", [])}
    intended = {p["id"]: p for p in manifest.get("panels", [])}
    actual = {p["id"]: p for p in exported_spec.get("panels", [])}
    if len(intended) != len(manifest.get("panels", [])) or len(actual) != len(exported_spec.get("panels", [])):
        block("duplicate_panel", "Panel IDs must be unique")
    # Header or bibliography panels may be explicitly added to a poster spec.
    # They too must be included in the intended manifest and visual review.
    for panel_id in planned.keys() | actual.keys():
        if panel_id not in intended:
            block("panel_omitted", f"Intended reconstruction omits panel {panel_id}")
    expected_object_ids = set()
    for panel_id, panel in intended.items():
        evidence = panel.get("reference_evidence", {})
        region = evidence.get("region", [])
        if not evidence.get("path") or not evidence.get("assessment") or not isinstance(region, list) or len(region) != 4 or not all(isinstance(n, (float, int)) and math.isfinite(n) for n in region) or not all(_positive(n) for n in region[2:]):
            block("missing_style_evidence", f"Panel {panel_id} needs an explicit reference region and reconstruction assessment")
        style = panel.get("style", {})
        if not style.get("background") or not style.get("alignment") or not isinstance(style.get("decoration_lines"), list):
            block("missing_style", f"Panel {panel_id} requires background, alignment and explicit decoration line IDs (or [])")
        exported_panel = actual.get(panel_id)
        if exported_panel is None:
            block("panel_omitted", f"Native export omits panel {panel_id}")
            exported_panel = {}
        if exported_panel.get("background", exported_spec.get("background")) != style.get("background"):
            block("panel_style_mismatch", f"Panel {panel_id} background differs from its intended style")
        if any(key in panel and exported_panel.get(key) != panel[key] for key in ("x", "y", "width", "height")):
            block("panel_geometry_mismatch", f"Panel {panel_id} differs from its explicitly planned rectangle")
        objects = panel.get("objects", [])
        native_objects = {o.get("id"): o for o in exported_panel.get("objects", [])}
        intended_ids = {o.get("id") for o in objects}
        if None in intended_ids or len(intended_ids) != len(objects) or len(native_objects) != len(exported_panel.get("objects", [])):
            block("duplicate_object", f"Panel {panel_id} needs unique stable object IDs")
        if expected_object_ids & intended_ids:
            block("duplicate_object", "Object IDs must be unique across the whole poster")
        expected_object_ids.update(intended_ids)
        for object_id in native_objects.keys() - intended_ids:
            block("unplanned_object", f"Native object {object_id} is absent from the intended reconstruction manifest")
        for line in style.get("decoration_lines", []):
            if line not in intended_ids:
                block("decoration_omitted", f"Intended decorative line {line} is missing")
        for slot in planned.get(panel_id, {}).get("image_slots", []):
            matching = [o for o in objects if o.get("image_slot_id") == slot.get("id") and o.get("type") in {"image", "table"}]
            sources = set(slot.get("source_ids", slot.get("asset_ids", [slot.get("asset_id")])))
            if not matching or not any(sources <= set(o.get("source_ids", [])) for o in matching):
                block("image_slot_omitted", f"Panel {panel_id} must reconstruct complete source slot {slot.get('id')}")
        for obj in objects:
            object_id, kind = obj.get("id"), obj.get("type")
            required = ["type", "x", "y", "width", "height", "align", "near_background"]
            if not _positive(obj.get("width")) or not _positive(obj.get("height")) or any(not isinstance(obj.get(n), (int, float)) or isinstance(obj.get(n), bool) or not math.isfinite(obj[n]) for n in ("x", "y")):
                block("invalid_rect", f"Object {object_id} requires a finite rectangle with positive dimensions")
            if not obj.get("align") or not obj.get("near_background"):
                block("missing_style", f"Object {object_id} requires alignment and nearby background color")
            if kind == "text":
                required += ["text", "font_family", "font_weight", "font_size", "color", "typography_role", "source_ids"]
                if any(not obj.get(k) for k in ("font_family", "font_weight", "font_size", "color", "typography_role")) or not _positive(obj.get("font_size")):
                    block("missing_style", f"Text {object_id} requires explicit font family, weight, size, color and typography role")
                if obj.get("typography_role") in AUXILIARY_ROLES:
                    block("auxiliary_text_forbidden", f"Text {object_id} cannot be a tiny auxiliary footnote or AI explanatory note")
            elif kind == "image":
                required += ["asset_id", "source_ids", "image_slot_id", "fit", "aspect_ratio"]
                if not obj.get("source_ids"):
                    block("missing_source", f"Image {object_id} requires original source IDs")
                if not obj.get("asset_id") or obj.get("asset_id") not in obj.get("source_ids", []):
                    block("asset_source_mismatch", f"Image {object_id} must declare its actual rendered asset_id among its mapped source IDs")
                preserved = obj.get("fit") in {"contain", "scale-down"} and obj.get("aspect_ratio") == "preserve"
                if not preserved:
                    block("invalid_image_geometry", f"Image {object_id} must preserve aspect; distortion permission cannot override this rule")
            elif kind == "table":
                required += ["rows", "column_widths", "row_heights", "font_family", "font_weight", "font_size", "color", "source_ids", "image_slot_id"]
                rows, widths, heights = obj.get("rows", []), obj.get("column_widths", []), obj.get("row_heights", [])
                if not rows or not isinstance(rows, list) or any(not isinstance(row, list) or not row or len(row) != len(widths) for row in rows) or len(heights) != len(rows) or not all(_positive(n) for n in widths + heights):
                    block("invalid_table_geometry", f"Table {object_id} needs explicit rectangular rows, positive column widths and row heights")
                if not obj.get("font_family") or not obj.get("font_weight") or not _positive(obj.get("font_size")) or not obj.get("color"):
                    block("missing_style", f"Table {object_id} requires explicit font family, weight, size and color")
                if not obj.get("source_ids"):
                    block("missing_source", f"Table {object_id} requires exact original source IDs and a selected-row source locator where appropriate")
                required += [key for key in ("header_rows", "header_fill", "fill", "stroke", "stroke_width", "source_locator") if key in obj]
            elif kind in {"line", "rect", "svg"}:
                required += [key for key in ("color", "fill", "stroke", "stroke_width", "radius", "svg", "x1", "x2", "y1", "y2") if key in obj]
            else:
                block("unknown_object_type", f"Unsupported native object type for {object_id}: {kind}")
            required += sorted(RENDER_FIELDS & obj.keys())
            native = native_objects.get(object_id)
            if native is None:
                block("object_omitted", f"Native export omits intended object {object_id}")
            elif any(key not in obj or native.get(key) != obj[key] for key in required):
                block("object_mismatch", f"Native object {object_id} differs from its intended geometry, typography, source or style")
    machine_pass = not blockers
    if review is None:
        block("independent_visual_review_required", "An independent reviewer must compare every panel and the whole actual poster")
    elif not isinstance(review, dict):
        block("independent_visual_review_required", "Independent visual review must be an object")
    else:
        if not review.get("reviewer") or review.get("independent") is not True or review.get("reviewer") == manifest.get("reconstructor") or review.get("decision") != "pass":
            block("independent_visual_review_required", "An independent named visual reviewer must explicitly pass")
        if not set(intended) <= set(review.get("checked_panel_ids", [])) or not expected_object_ids <= set(review.get("checked_object_ids", [])) or review.get("whole_poster_checked") is not True:
            block("incomplete_visual_review", "Review must cover every intended panel/object and the full poster")
        hashes = {"panel_plan": canonical_hash(panel_plan), "manifest": canonical_hash(manifest), "exported_spec": canonical_hash(exported_spec)}
        if review.get("input_hashes") != hashes:
            block("review_hash_mismatch", "Visual review must bind these exact canonical plans, intended manifest and native export")
        evidence = review.get("evidence", {})
        try:
            seen = {key: Path(evidence[key]).resolve(strict=True) for key in ("generated_image", "rendered_image")}
        except (KeyError, OSError, ValueError, TypeError):
            seen = {}
        if evidence.get("actually_viewed") is not True or seen != image_paths or len(image_paths) != 2:
            block("review_image_evidence_required", "Reviewer must declare actual inspection of both hash-bound generated and rendered images")
        if review.get("blockers", []) != []:
            block("unresolved_visual_finding", "Independent reviewer reports unresolved blockers")
        for finding in review.get("findings", []):
            if finding.get("resolved") is not True and finding.get("severity", "blocking") in {"blocking", "error", "critical"}:
                block("unresolved_visual_finding", "Independent visual finding remains unresolved", finding=finding)
    passed = not blockers
    return {"pass": passed, "machine_pass": machine_pass, "status": "pass" if passed else "pending" if machine_pass and review is None else "blocked", "blockers": blockers, "visual_fidelity_pass": True if passed else None, "semantic_assurance": "independent visual reviewer declaration recorded" if passed else "not approved"}

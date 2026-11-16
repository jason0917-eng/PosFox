import copy
import hashlib
from pathlib import Path
import tempfile

import pytest

from posfoxgen.logic import canonical_hash
from posfoxgen.reconstruction_audit import validate_reconstruction_audit


def audit_inputs():
    panels = {"panels": [{"id": "method", "image_slots": [{"id": "diagram", "asset_id": "fig1"}]}]}
    body = {"id": "explanation", "type": "text", "x": 5, "y": 5, "width": 180, "height": 35, "text": "The method iterates using a verifiable design objective.", "source_ids": ["text1"], "font_family": "Arial", "font_weight": 400, "font_size": 22, "color": "#162d46", "align": "left", "typography_role": "body", "near_background": "#f5f7f8"}
    image = {"id": "method-diagram", "type": "image", "asset_id": "fig1", "x": 5, "y": 50, "width": 180, "height": 120, "source_ids": ["fig1"], "image_slot_id": "diagram", "fit": "contain", "aspect_ratio": "preserve", "align": "center", "near_background": "#f5f7f8"}
    line = {"id": "divider", "type": "line", "x": 5, "y": 43, "width": 180, "height": 1, "color": "#bdcbd2", "stroke_width": 1, "align": "left", "near_background": "#f5f7f8"}
    manifest = {"panels": [{"id": "method", "reference_evidence": {"path": "best-poster.png", "region": [0, 0, 200, 200], "assessment": "Match the method panel typography, divider and diagram placement."}, "style": {"background": "#f5f7f8", "alignment": "left", "decoration_lines": ["divider"]}, "objects": [body, image, line]}]}
    exported = {"panels": [{"id": "method", "background": "#f5f7f8", "objects": copy.deepcopy(manifest["panels"][0]["objects"])}]}
    image_root = Path(tempfile.mkdtemp(prefix="posfoxgen-audit-test-"))
    # Audit binds the bytes independently inspected by the visual reviewer.
    from PIL import Image
    Image.new("RGB", (200, 200), "white").save(image_root / "best.png")
    Image.new("RGB", (200, 200), "navy").save(image_root / "render.png")
    manifest.update(generated_image_path=str(image_root / "best.png"), generated_image_sha256=hashlib.sha256((image_root / "best.png").read_bytes()).hexdigest(), render_path=str(image_root / "render.png"), render_sha256=hashlib.sha256((image_root / "render.png").read_bytes()).hexdigest())
    review = {"reviewer": "independent-visual-reviewer", "independent": True, "decision": "pass", "checked_panel_ids": ["method"], "checked_object_ids": ["explanation", "method-diagram", "divider"], "whole_poster_checked": True, "evidence": {"generated_image": manifest["generated_image_path"], "rendered_image": manifest["render_path"], "actually_viewed": True}, "findings": [], "input_hashes": {"panel_plan": canonical_hash(panels), "manifest": canonical_hash(manifest), "exported_spec": canonical_hash(exported)}}
    return panels, manifest, exported, review


def codes(result):
    return {x["code"] for x in result["blockers"]}


def test_complete_manifest_needs_independent_panel_and_whole_poster_review():
    p, m, e, _ = audit_inputs()
    result = validate_reconstruction_audit(p, m, e)
    assert result["machine_pass"] and not result["pass"]
    assert result["status"] == "pending"
    assert result["visual_fidelity_pass"] is None
    approved = validate_reconstruction_audit(*audit_inputs())
    assert approved["pass"] and approved["visual_fidelity_pass"] is True


def test_panel_omission_and_source_slot_omission_block_audit():
    p, m, e, r = audit_inputs(); m["panels"][0]["objects"].pop(1)
    assert "image_slot_omitted" in codes(validate_reconstruction_audit(p, m, e, r))
    m["panels"] = []
    assert "panel_omitted" in codes(validate_reconstruction_audit(p, m, e, r))


def test_exported_object_omission_is_detected_even_if_manifest_lists_it():
    p, m, e, r = audit_inputs(); e["panels"][0]["objects"].pop(1)
    assert "object_omitted" in codes(validate_reconstruction_audit(p, m, e, r))


@pytest.mark.parametrize("field", ["font_family", "font_weight", "font_size", "color", "align", "near_background"])
def test_missing_typography_or_style_fields_are_not_silently_defaulted(field):
    p, m, e, r = audit_inputs(); m["panels"][0]["objects"][0].pop(field)
    assert "missing_style" in codes(validate_reconstruction_audit(p, m, e, r))


@pytest.mark.parametrize("field,value", [("fit", "stretch"), ("aspect_ratio", "distort")])
def test_figure_unknown_fit_or_distortion_is_blocked(field, value):
    p, m, e, r = audit_inputs(); m["panels"][0]["objects"][1][field] = value
    assert "invalid_image_geometry" in codes(validate_reconstruction_audit(p, m, e, r))


def test_exported_font_rect_color_or_source_change_requires_new_plan():
    p, m, e, r = audit_inputs(); e["panels"][0]["objects"][0]["font_family"] = "unplanned-font"
    e["panels"][0]["objects"][1]["width"] = 20
    assert "object_mismatch" in codes(validate_reconstruction_audit(p, m, e, r))


def test_decorative_line_and_reference_evidence_cannot_be_lost():
    p, m, e, r = audit_inputs(); m["panels"][0].pop("reference_evidence")
    m["panels"][0]["objects"].pop()
    assert {"missing_style_evidence", "decoration_omitted"} <= codes(validate_reconstruction_audit(p, m, e, r))


def test_auxiliary_ai_notes_and_small_qualifiers_are_forbidden_by_role():
    p, m, e, r = audit_inputs(); m["panels"][0]["objects"][0]["typography_role"] = "tiny_gray_footnote"
    assert "auxiliary_text_forbidden" in codes(validate_reconstruction_audit(p, m, e, r))


@pytest.mark.parametrize("change", ["missing_panel", "missing_whole", "unbound", "same_reviewer", "unresolved_visual_finding"])
def test_no_scientific_or_visual_approval_without_full_independent_review(change):
    p, m, e, r = audit_inputs()
    if change == "missing_panel": r["checked_panel_ids"] = []
    elif change == "missing_whole": r["whole_poster_checked"] = False
    elif change == "unbound": r.pop("input_hashes")
    elif change == "same_reviewer": r["independent"] = False
    else: r["findings"] = [{"severity": "blocking", "resolved": False, "message": "The reconstructed diagram reverses the feedback arrow."}]
    result = validate_reconstruction_audit(p, m, e, r)
    assert not result["pass"] and result["machine_pass"]
    assert result["visual_fidelity_pass"] is not True


def test_actual_image_byte_changes_invalidate_manifest_and_review():
    p, m, e, r = audit_inputs()
    Path(m["render_path"]).write_bytes(b"different image bytes")
    result = validate_reconstruction_audit(p, m, e, r)
    assert "image_hash_mismatch" in codes(result)
    assert not result["machine_pass"]


def test_review_must_declare_both_actual_images_were_viewed():
    p, m, e, r = audit_inputs(); r["evidence"]["actually_viewed"] = False
    assert "review_image_evidence_required" in codes(validate_reconstruction_audit(p, m, e, r))


def test_empty_auxiliary_note_cannot_hide_by_changing_only_native_role():
    p, m, e, r = audit_inputs(); e["panels"][0]["objects"][0]["typography_role"] = "ai_explanatory_note"
    assert "object_mismatch" in codes(validate_reconstruction_audit(p, m, e, r))


def test_native_table_can_reconstruct_a_planned_source_slot_without_image_stretching():
    p, m, e, r = audit_inputs()
    table = {"id": "method-diagram", "type": "table", "x": 5, "y": 50, "width": 180, "height": 120, "source_ids": ["fig1"], "image_slot_id": "diagram", "source_locator": "Table 1, selected rows A and B", "rows": [["Method", "Score"], ["A", "91.4"]], "column_widths": [100, 80], "row_heights": [60, 60], "font_family": "Arial", "font_size": 20, "font_weight": 400, "color": "#162d46", "header_fill": "#bdcbd2", "fill": "#f5f7f8", "stroke": "#162d46", "align": "left", "near_background": "#f5f7f8"}
    m["panels"][0]["objects"][1] = table
    e["panels"][0]["objects"][1] = copy.deepcopy(table)
    result = validate_reconstruction_audit(p, m, e)
    assert result["machine_pass"], result
    e["panels"][0]["objects"][1]["column_widths"] = [90, 90]
    assert "object_mismatch" in codes(validate_reconstruction_audit(p, m, e))


def test_legacy_explicit_distortion_permission_is_no_longer_accepted():
    p, m, e, _ = audit_inputs(); image = m['panels'][0]['objects'][1]
    image.update(fit='fill',aspect_ratio='distort',allow_distortion=True,distortion_reason='Legacy explicit permission')
    e['panels'][0]['objects'][1]=copy.deepcopy(image)
    assert 'invalid_image_geometry' in codes(validate_reconstruction_audit(p,m,e))


def test_native_shape_color_change_is_not_ignored():
    p, m, e, _ = audit_inputs()
    m["panels"][0]["objects"][2].update(stroke="#162d46")
    e["panels"][0]["objects"][2].update(stroke="#ff0000")
    assert "object_mismatch" in codes(validate_reconstruction_audit(p, m, e))


def test_actual_asset_id_swap_cannot_hide_behind_same_source_ids():
    p, m, e, _ = audit_inputs()
    e["panels"][0]["objects"][1]["asset_id"] = "unrelated-rendered-crop"
    assert "object_mismatch" in codes(validate_reconstruction_audit(p, m, e))


def test_actual_crop_id_must_be_declared_among_semantic_sources():
    p, m, e, _ = audit_inputs()
    for spec in (m, e): spec["panels"][0]["objects"][1]["asset_id"] = "fig1-crop"
    assert "asset_source_mismatch" in codes(validate_reconstruction_audit(p, m, e))
    for spec in (m, e): spec["panels"][0]["objects"][1]["source_ids"].append("fig1-crop")
    assert validate_reconstruction_audit(p, m, e)["machine_pass"]


@pytest.mark.parametrize("field,value", [("font_style", "italic"), ("line_height", 1.4), ("background", "#ffffff"), ("emphasis", [{"text": "source", "font_weight": 700}])])
def test_declared_rendering_text_fields_are_compared(field, value):
    p, m, e, _ = audit_inputs(); m["panels"][0]["objects"][0][field] = value
    assert "object_mismatch" in codes(validate_reconstruction_audit(p, m, e))


@pytest.mark.parametrize("field,value", [("position", "center"), ("background", "#ffffff"), ("background_policy", "preserve")])
def test_declared_rendering_image_fields_are_compared(field, value):
    p, m, e, _ = audit_inputs(); m["panels"][0]["objects"][1][field] = value
    assert "object_mismatch" in codes(validate_reconstruction_audit(p, m, e))


def test_declared_linecap_is_compared():
    p, m, e, _ = audit_inputs(); m["panels"][0]["objects"][2]["linecap"] = "round"
    assert "object_mismatch" in codes(validate_reconstruction_audit(p, m, e))


def test_explicit_panel_rectangle_cannot_change_around_unchanged_objects():
    p, m, e, _ = audit_inputs(); m["panels"][0].update(x=10, y=20, width=200, height=200)
    e["panels"][0].update(x=80, y=20, width=200, height=200)
    assert "panel_geometry_mismatch" in codes(validate_reconstruction_audit(p, m, e))


@pytest.mark.parametrize("field,value", [("row_font_weights", [700, 400]), ("column_aligns", ["left", "right"]), ("row_fills", ["#eeeeee", "#ffffff"])])
def test_declared_per_row_and_column_table_styles_are_compared(field, value):
    p, m, e, _ = audit_inputs()
    table = {"id": "method-diagram", "type": "table", "x": 5, "y": 50, "width": 180, "height": 120, "source_ids": ["fig1"], "image_slot_id": "diagram", "rows": [["Model", "Score"], ["A", "91.4"]], "column_widths": [100, 80], "row_heights": [60, 60], "font_family": "Arial", "font_weight": 400, "font_size": 20, "color": "#162d46", "align": "left", "near_background": "#f5f7f8"}
    m["panels"][0]["objects"][1] = copy.deepcopy(table)
    e["panels"][0]["objects"][1] = copy.deepcopy(table)
    m["panels"][0]["objects"][1][field] = value
    assert "object_mismatch" in codes(validate_reconstruction_audit(p, m, e))


def roster_inputs():
    p, m, e, r = audit_inputs()
    p['panels'][0].update(x=0,y=0,width=200,height=200)
    e.update(width=200,height=200)
    e['panels'][0].update(x=0,y=0,width=200,height=200)
    # A visually required orange bullet is recorded before native construction.
    bullet={'id':'orange-bullet','type':'rect','x':2,'y':2,'width':2,'height':2,'fill':'#ef7c26','align':'left','near_background':'#f5f7f8'}
    m['panels'][0]['objects'].append(copy.deepcopy(bullet));e['panels'][0]['objects'].append(copy.deepcopy(bullet))
    roster={'generated_image_sha256':m['generated_image_sha256'],'canvas':[200,200],'modules':[{'id':'method','native_panel_ids':['method'],'region':[0,0,200,200],'area_ratio':1.0,'area_tolerance':0.02,'frame_tolerance':0.02,'background':'#f5f7f8','text_area_ratio':0.3,'text_area_tolerance':0.03,'text_measurement':'Inspected text bounding-box area / module area, same method for each paired view','features':[{'id':'bullet','kind':'bullet','count':1,'color':'#ef7c26','native_object_ids':['orange-bullet']}]}]}
    m['design_roster']=roster
    r['checked_object_ids'].append('orange-bullet')
    r['roster_checks']=[{'module_id':'method','background_observed':'#f5f7f8','text_area_ratio_observed':0.3,'paired_window_path':m['generated_image_path'],'redline_path':m['render_path'],'assessment':'Compared module proportions and native orange bullet against frozen generated design.','feature_checks':[{'feature_id':'bullet','count_observed':1,'color_observed':'#ef7c26'}]}]
    from posfoxgen.visual_windows import build_windows
    directory=Path(m['render_path']).parent/'windows'
    records=build_windows(m['generated_image_path'],m['render_path'],[{'id':'method','generated_region':[0,0,200,200],'native_region':[0,0,200,200],'marks':[{'side':'native','bbox':[0,0,200,200],'kind':'checked','label':'module'}]}],directory)
    check=r['roster_checks'][0];check.update({k:records[0][k] for k in ('paired_window_path','redline_path')});check.update(window_id='method',window_manifest_path=str(directory/'windows.json'),window_manifest_sha256=hashlib.sha256((directory/'windows.json').read_bytes()).hexdigest())
    return p,m,e,r


def test_frozen_roster_catches_module_dropped_from_both_manifest_and_native():
    p,m,e,r=roster_inputs()
    m['panels']=[]; e['panels']=[];p['panels']=[]
    assert 'roster_module_omitted' in codes(validate_reconstruction_audit(p,m,e,r))


def test_frozen_roster_catches_bullet_removed_from_both_native_and_manifest():
    p,m,e,r=roster_inputs()
    for d in (m,e):d['panels'][0]['objects']=[o for o in d['panels'][0]['objects'] if o['id']!='orange-bullet']
    assert 'roster_feature_omitted' in codes(validate_reconstruction_audit(p,m,e,r))


def test_roster_catches_color_and_module_height_drift():
    p,m,e,r=roster_inputs();e['panels'][0]['height']=100
    assert 'roster_area_mismatch' in codes(validate_reconstruction_audit(p,m,e,r))
    p,m,e,r=roster_inputs();e['panels'][0]['objects'][-1]['fill']='#ffffff'
    assert 'roster_color_mismatch' in codes(validate_reconstruction_audit(p,m,e,r))


def test_text_coverage_drift_and_unmarked_windows_cannot_pass_roster():
    p,m,e,r=roster_inputs();r['roster_checks'][0]['text_area_ratio_observed']=0.1
    assert 'roster_text_area_mismatch' in codes(validate_reconstruction_audit(p,m,e,r))
    p,m,e,r=roster_inputs();r['roster_checks'][0].pop('redline_path')
    assert 'roster_window_evidence_required' in codes(validate_reconstruction_audit(p,m,e,r))


def test_source_aspect_exception_cannot_excuse_missing_bullets():
    p,m,e,r=roster_inputs();m['design_roster']['modules'][0]['exception']='source_aspect_contain'
    for d in (m,e):d['panels'][0]['objects'].pop()
    assert 'roster_feature_omitted' in codes(validate_reconstruction_audit(p,m,e,r))


def test_complete_frozen_roster_and_bound_visual_evidence_pass():
    p,m,e,r=roster_inputs()
    r['input_hashes']={'panel_plan':canonical_hash(p),'manifest':canonical_hash(m),'exported_spec':canonical_hash(e)}
    assert validate_reconstruction_audit(p,m,e,r,require_design_roster=True)['pass']


def test_strict_reconstruction_cannot_omit_intake_roster():
    p,m,e,r=audit_inputs()
    assert 'missing_design_roster' in codes(validate_reconstruction_audit(p,m,e,r,require_design_roster=True))


def test_repeated_modules_cannot_reuse_one_surviving_native_occurrence():
    p,m,e,r=roster_inputs()
    first=m['design_roster']['modules'][0];first.update(region=[0,0,200,100],area_ratio=.5)
    second=copy.deepcopy(first);second.update(id='duplicate',region=[0,100,200,100]);second['features'][0]['id']='second-bullet'
    m['design_roster']['modules'].append(second);e['panels'][0]['height']=100
    assert 'roster_occurrence_reused' in codes(validate_reconstruction_audit(p,m,e,r))


def test_module_moved_to_wrong_stack_position_is_not_hidden_by_equal_area():
    p,m,e,r=roster_inputs()
    m['design_roster']['modules'][0].update(region=[0,0,200,100],area_ratio=.5)
    e['panels'][0].update(y=100,height=100)
    assert 'roster_frame_mismatch' in codes(validate_reconstruction_audit(p,m,e,r))


def test_nonimage_or_changed_paired_evidence_is_rejected(tmp_path):
    p,m,e,r=roster_inputs();bogus=tmp_path/'text.txt';bogus.write_text('not a paired image')
    r['roster_checks'][0].update(paired_window_path=str(bogus),redline_path=str(bogus))
    assert 'roster_window_evidence_required' in codes(validate_reconstruction_audit(p,m,e,r))


def test_reviewed_redline_bytes_cannot_change_after_binding():
    p,m,e,r=roster_inputs();path=Path(r['roster_checks'][0]['redline_path'])
    from PIL import Image
    Image.new('RGB',(400,200),'yellow').save(path)
    assert 'roster_window_evidence_required' in codes(validate_reconstruction_audit(p,m,e,r))

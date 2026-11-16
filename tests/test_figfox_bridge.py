from pathlib import Path
import pytest

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300"><rect id="canvas_bg" width="400" height="300" fill="white"/><g id="panel-method"><text id="method-label" x="20" y="40">draft</text></g><text id="other-panel" x="200" y="40">keep</text></svg>'


def test_native_figfox_edit_is_scoped_and_records_execution(tmp_path):
    from posfoxgen.figfox_bridge import apply_native_plan
    findings = {"regions": [
        {"id": x, "status": "differences" if x == "A" else "no_confirmed_difference", "evidence": "paired source and candidate inspected"}
        for x in "ABCD"], "issues": [{"id": "i1", "region": "A", "bbox": [10, 10, 140, 80],
        "source_evidence": "approved method label", "initial_evidence": "draft is visible", "repair": "replace label"}]}
    plan = {"transactions": [{"id": "t1", "issue_ids": ["i1"], "target_ids": ["panel-method"],
        "depends_on": [], "instructions": "Restore the approved source-bound label", "parameters": {}}], "unresolved": []}
    edits = {"transactions": [{"id": "t1", "edits": [{"op": "text", "id": "method-label", "text": "grounded method"}]}]}
    output = apply_native_plan(SVG, findings, plan, edits, tmp_path)
    assert "grounded method" in output["svg"]
    assert '>keep<' in output["svg"]
    assert output["receipt"]["engine"] == "FigFox factual.contracts"
    assert output["receipt"]["execution_accepted"] is True
    assert output["receipt"]["visual_quality_pass"] is None
    assert (tmp_path / "native-receipt.json").is_file()


def test_native_figfox_rejects_edits_outside_declared_panel(tmp_path):
    from posfoxgen.figfox_bridge import apply_native_plan
    findings = {"regions": [{"id": x, "status": "differences" if x == "A" else "no_confirmed_difference", "evidence": "inspected"} for x in "ABCD"],
        "issues": [{"id": "i1", "region": "A", "bbox": [10, 10, 100, 80], "source_evidence": "source", "initial_evidence": "candidate", "repair": "repair"}]}
    plan = {"transactions": [{"id": "t1", "issue_ids": ["i1"], "target_ids": ["panel-method"], "depends_on": [], "instructions": "repair panel", "parameters": {}}], "unresolved": []}
    edits = {"transactions": [{"id": "t1", "edits": [{"op": "text", "id": "other-panel", "text": "should fail"}]}]}
    with pytest.raises(ValueError, match="outside"):
        apply_native_plan(SVG, findings, plan, edits, tmp_path)

import base64
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import pytest

from PIL import Image

from posfoxgen.delivery import create_delivery_manifest, validate_package
from posfoxgen.editable import export_svg
from posfoxgen.export_bindings import validate_export_bindings
from posfoxgen.state import accept_stage, file_hash, validate_delivery
from test_v2_state import inputs, final_ready_v2, rebind_final, write


def test_real_native_table_and_source_svg_internal_ids_are_supported(tmp_path):
    root, paths, _, _, spec = inputs(tmp_path)
    spec["height"] = 350; spec["panels"][0]["height"] = 350
    spec["panels"][0]["objects"] += [
        {"id": "summary", "type": "table", "x": 5, "y": 180, "width": 180, "height": 100, "rows": [["Model", "Score"], ["A", "91.4"]], "column_widths": [100, 80], "row_heights": [50, 50], "font_family": "Arial", "font_size": 12, "font_weight": 400, "row_font_weights": [700, 400], "column_aligns": ["left", "right"], "row_fills": ["#eeeeee", "#ffffff"], "source_ids": ["text1"]},
        {"id": "ornament", "type": "svg", "x": 5, "y": 300, "width": 180, "height": 20, "source_ids": [], "svg": '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="20"><defs><linearGradient id="paint"><stop offset="0%" stop-color="#ffffff"/><stop offset="100%" stop-color="#273b5d"/></linearGradient></defs><rect width="180" height="20" fill="url(#paint)"/><text x="5" y="14" font-size="10">Native source decoration</text></svg>'},
    ]
    out = root / "export"
    export_svg(spec, paths["asset_table"], out)
    result = validate_export_bindings(spec, out / "poster.html", out / "poster.svg", paths["asset_table"])
    assert result["pass"], result
    # Internal cell IDs are generated support nodes, not additional planned
    # objects. Coherent renaming does not change rendered table content.
    for suffix in ("html", "svg"):
        path = out / ("poster." + suffix)
        path.write_text(path.read_text().replace('id="summary-cell-', 'id="internal-cell-'))
    assert validate_export_bindings(spec, out / "poster.html", out / "poster.svg", paths["asset_table"])["pass"]


def test_scientific_image_byte_swap_and_final_asset_alias_cannot_redefine_source(tmp_path):
    root, paths, artifacts, review = final_ready_v2(tmp_path)
    package = artifacts["poster_html"].parent
    image = package / "assets/fig1.png"; old_hash = file_hash(image)
    Image.new("RGB", (180, 120), "red").save(image)
    new_hash = file_hash(image)
    artifacts["poster_html"].write_text(artifacts["poster_html"].read_text().replace(old_hash, new_hash))
    tree = ET.parse(artifacts["poster_svg"])
    node = next(n for n in tree.iter() if n.get("id") == "method-diagram")
    node.set("href", "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode())
    tree.write(artifacts["poster_svg"], encoding="unicode")
    # The final-stage alias is deliberately plausible, but it is not the
    # authoritative source map accepted before planning and generation.
    alias = json.loads(paths["asset_table"].read_text())
    alias["root"] = str(package / "assets")
    next(a for a in alias["assets"] if a["id"] == "fig1").update(sha256=new_hash)
    artifacts["asset_table"] = write(package / "source/alternate-asset-table.json", alias)
    rebind_final(artifacts, review)
    assert validate_package(package, "manifest.json")["pass"]
    import pytest
    with pytest.raises(ValueError, match="v2_export_binding_invalid"):
        accept_stage(root, "finalized", artifacts, review)


def test_revalidation_executes_real_export_binding_checks_again(tmp_path):
    root, paths, artifacts, review = final_ready_v2(tmp_path)
    accept_stage(root, "finalized", artifacts, review)
    html = artifacts["poster_html"]
    html.write_text(re.sub(r'<svg [^>]*id="divider"[^>]*>.*?</svg>', '', html.read_text(), flags=re.S))
    final_review = json.loads(review.read_text()); final_review["input_hashes"]["poster_html"] = file_hash(html)
    write(review, final_review)
    create_delivery_manifest(html.parent, ["."])
    # Even internally matching legacy receipts cannot certify a missing real
    # object. The actual exports must be checked on every delivery validation.
    run_path = root / "run.json"; run = json.loads(run_path.read_text())
    for record in run["receipts"]["finalized"]["artifact_hashes"].values():
        record["sha256"] = file_hash(record["path"])
    write(run_path, run)
    result = validate_delivery(root)
    assert not result["pass"]
    assert "v2_export_binding_invalid" in {b["code"] for b in result["blockers"]}


@pytest.mark.parametrize("format", ["html", "svg"])
def test_source_svg_gradient_reference_identity_is_rendering_evidence(tmp_path, format):
    root, paths, _, _, spec = inputs(tmp_path)
    spec["panels"][0]["objects"].append({"id": "accent", "type": "svg", "x": 5, "y": 180, "width": 180, "height": 10, "source_ids": [], "svg": '<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="paint"><stop offset="0%" stop-color="#ffffff"/><stop offset="100%" stop-color="#273b5d"/></linearGradient></defs><rect width="180" height="10" fill="url(#paint)"/></svg>'})
    out = root / "export"; export_svg(spec, paths["asset_table"], out)
    path = out / ("poster." + format)
    path.write_text(path.read_text().replace('id="paint"', 'id="broken-paint"'))
    result = validate_export_bindings(spec, out / "poster.html", out / "poster.svg", paths["asset_table"])
    assert not result["pass"]
    assert "export_rendering_mismatch" in {b["code"] for b in result["blockers"]}

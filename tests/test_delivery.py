import base64
import hashlib
import json
from pathlib import Path

import fitz
from PIL import Image
import pytest

from posfoxgen.delivery import create_delivery_manifest, validate_package


def valid_package(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    (root / "assets").mkdir()
    source = root / "assets/figure.png"
    Image.new("RGB", (40, 30), "navy").save(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    (root / "poster.html").write_text('<html><body><div contenteditable="true">A source-grounded poster claim.</div>' + f'<img data-asset-id="figure-1" data-source-sha256="{source_hash}" src="assets/figure.png"></body></html>')
    raster = base64.b64encode(source.read_bytes()).decode()
    (root / "poster.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100"><text x="5" y="20">Native poster claim</text>' + f'<image x="10" y="30" width="40" height="30" data-asset-id="figure-1" href="data:image/png;base64,{raster}"/></svg>')
    Image.new("RGB", (200, 100), "white").save(root / "poster.png")
    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((10, 20), "Poster proof")
    doc.save(root / "poster.pdf")
    doc.close()
    (root / "reviews").mkdir()
    (root / "reviews/final_review.json").write_text('{"decision":"pass"}')
    (root / "source").mkdir()
    (root / "source/asset_table.json").write_text(json.dumps({"assets": [{"id": "figure-1", "sha256": source_hash}]}))
    return root


def manifest(root):
    return create_delivery_manifest(root, ["poster.html", "poster.svg", "poster.png", "poster.pdf", "assets", "reviews", "source"])


def codes(result):
    return {x["code"] for x in result["blockers"]}


def test_actual_package_passes_and_scientific_judgment_is_not_claimed(tmp_path):
    root = valid_package(tmp_path)
    result = manifest(root)
    assert (root / "manifest.json").exists()
    assert all(not Path(x["path"]).is_absolute() for x in result["files"])
    check = validate_package(root, "manifest.json")
    assert check["pass"], check
    assert check["scientific_quality_pass"] is None


def test_bound_source_receipt_change_is_detected(tmp_path):
    root = valid_package(tmp_path)
    manifest(root)
    (root / "reviews/final_review.json").write_text('{"decision":"changed"}')
    assert "hash_mismatch" in codes(validate_package(root, "manifest.json"))


def test_manifest_rejects_parent_traversal_and_symlink_escape(tmp_path):
    root = valid_package(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    with pytest.raises(ValueError, match="outside"):
        create_delivery_manifest(root, ["../outside.txt"])
    (root / "escape.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        create_delivery_manifest(root, ["escape.txt"])


def test_validator_rejects_forged_manifest_path_escape(tmp_path):
    root = valid_package(tmp_path)
    value = manifest(root)
    value["files"].append({"path": "../outside", "sha256": "0" * 64})
    (root / "manifest.json").write_text(json.dumps(value))
    assert "path_outside_package" in codes(validate_package(root, "manifest.json"))


def test_corrupt_png_fails_after_rebinding_hash(tmp_path):
    root = valid_package(tmp_path)
    (root / "poster.png").write_bytes(b"not a PNG")
    manifest(root)
    assert "invalid_png" in codes(validate_package(root, "manifest.json"))


def test_two_page_pdf_is_rejected(tmp_path):
    root = valid_package(tmp_path)
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    (root / "poster.pdf").unlink()
    doc.save(root / "poster.pdf")
    doc.close()
    manifest(root)
    assert "pdf_page_count" in codes(validate_package(root, "manifest.json"))


def test_svg_full_canvas_bitmap_with_tiny_native_label_is_rejected(tmp_path):
    root = valid_package(tmp_path)
    path = root / "poster.svg"
    path.write_text(path.read_text().replace('width="40" height="30"', 'width="200" height="100"'))
    manifest(root)
    assert "full_canvas_bitmap" in codes(validate_package(root, "manifest.json"))


def test_svg_without_native_text_is_rejected(tmp_path):
    root = valid_package(tmp_path)
    path = root / "poster.svg"
    path.write_text(path.read_text().replace('<text x="5" y="20">Native poster claim</text>', ""))
    manifest(root)
    assert "missing_native_svg_text" in codes(validate_package(root, "manifest.json"))


def test_html_requires_editable_text_and_matching_source_hash(tmp_path):
    root = valid_package(tmp_path)
    path = root / "poster.html"
    path.write_text(path.read_text().replace('contenteditable="true"', 'contenteditable="false"').replace('data-source-sha256="', 'data-source-sha256="wrong'))
    manifest(root)
    result = validate_package(root, "manifest.json")
    assert {"missing_editable_html_text", "source_hash_mismatch"} <= codes(result)


def test_html_external_or_unbound_asset_is_not_self_contained(tmp_path):
    root = valid_package(tmp_path)
    path = root / "poster.html"
    path.write_text(path.read_text().replace('src="assets/figure.png"', 'src="https://example.com/figure.png"'))
    manifest(root)
    assert "external_asset_reference" in codes(validate_package(root, "manifest.json"))


def test_all_four_deliverable_formats_are_required(tmp_path):
    root = valid_package(tmp_path)
    create_delivery_manifest(root, ["poster.html", "assets"])
    assert "missing_required_format" in codes(validate_package(root, "manifest.json"))


def test_svg_percentage_screenshot_is_not_mistaken_for_native_content(tmp_path):
    root = valid_package(tmp_path)
    path = root / "poster.svg"
    path.write_text(path.read_text().replace('width="40" height="30"', 'width="100%" height="100%"'))
    manifest(root)
    assert "full_canvas_bitmap" in codes(validate_package(root, "manifest.json"))


def test_svg_nested_transform_cannot_hide_full_canvas_bitmap(tmp_path):
    root = valid_package(tmp_path)
    path = root / "poster.svg"
    value = path.read_text().replace('<image x=', '<g transform="scale(5)"><image x=').replace('/></svg>', '/></g></svg>')
    path.write_text(value)
    manifest(root)
    assert "full_canvas_bitmap" in codes(validate_package(root, "manifest.json"))


def test_matching_hash_alone_does_not_make_html_source_a_real_image(tmp_path):
    root = valid_package(tmp_path)
    fake = root / "assets/not-an-image.bin"
    fake.write_bytes(b"plausible bytes, not an actual image")
    digest = hashlib.sha256(fake.read_bytes()).hexdigest()
    (root / "poster.html").write_text(f'<div contenteditable="true">Claim</div><img data-asset-id="fake" data-source-sha256="{digest}" src="assets/not-an-image.bin">')
    manifest(root)
    assert "invalid_source_image" in codes(validate_package(root, "manifest.json"))

import hashlib
import fitz
import pytest
from PIL import Image, ImageChops, ImageDraw
from posfoxgen.figure_labels import render_labels


@pytest.fixture
def chart(tmp_path):
    p = tmp_path / "source.png"
    image = Image.new("RGB", (120, 40), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 16, 13, 21), fill="#555555")   # protected swatch
    draw.text((18, 10), "10%", fill="black")
    image.save(p)
    font = tmp_path / "font.cff"
    font.write_bytes(fitz.Font("helv").buffer)
    req = {"source_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
           "labels": [{"text": "10%", "size": 15, "box": [16, 4, 56, 32], "align": "left"}]}
    return p, font, req, tmp_path / "display.png"


def test_label_change_stays_inside_box_and_preserves_source(chart):
    source, font, request, out = chart
    request["labels"][0]["baseline"] = 24
    render_labels(source, request, font, out)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == request["source_sha256"]
    with Image.open(source) as a, Image.open(out) as b:
        delta = ImageChops.difference(a, b)
        assert delta.getbbox()
        ImageDraw.Draw(delta).rectangle((17, 5, 54, 30), fill="black")
        assert delta.getbbox() is None
    with pytest.raises(ValueError, match="new PNG"):
        render_labels(source, request, font, out)


@pytest.mark.parametrize("fault", ["wrong source", "overlap", "swatch on border", "no label", "too wide", "clipped descenders"])
def test_rejects_unusable_request_without_writing(chart, fault):
    source, font, req, out = chart
    item = req["labels"][0]
    if fault == "wrong source":
        req["source_sha256"] = "0"*64
    elif fault == "overlap":
        req["labels"].append(dict(item))
    elif fault == "swatch on border":
        item["box"] = [10, 4, 56, 32]
    elif fault == "no label":
        item["box"] = [61, 4, 119, 32]
    elif fault == "too wide":
        item["size"] = 80
    elif fault == "clipped descenders":
        item.update(text="Entry", baseline=31)
    with pytest.raises(ValueError):
        render_labels(source, req, font, out)
    assert not out.exists()

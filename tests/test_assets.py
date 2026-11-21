import importlib
import io
import sys
from pathlib import Path
import fitz
import pytest
from PIL import Image
sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))


def fixture_pdf(path):
    d = fitz.open(); p = d.new_page(width=400, height=500)
    p.insert_text((35, 40), 'Methods: measured 24 samples with Model A.')
    p.insert_text((35, 260), 'Figure 1. Source evidence, n=24.')
    image = Image.new('RGB', (90, 50), '#267a8c'); data=io.BytesIO(); image.save(data, format='PNG')
    p.insert_image(fitz.Rect(35, 100, 215, 200), stream=data.getvalue())
    d.save(path); d.close()


def test_pdf_assets_preserve_real_page_positions_and_hashes(tmp_path):
    module = importlib.import_module('posfoxgen.assets')
    pdf=tmp_path/'source.pdf';fixture_pdf(pdf)
    out=tmp_path/'assets';table=module.extract_assets(pdf,out)
    assert table['source']['paper_sha256'] and table['source']['page_count']==1
    assert '24 samples' in table['pages'][0]['text']
    text=next(a for a in table['assets'] if a['type']=='text' and '24 samples' in a['text'])
    assert text['page']==text['source']['page']==1
    assert 0 <= text['bbox'][0] < text['bbox'][2] <= 400
    fig=next(a for a in table['assets'] if a['type']=='figure')
    assert (out/fig['path']).is_file() and fig['sha256']
    assert fig['bbox']==[35.0,100.0,215.0,200.0]
    assert (out/'asset_table.json').is_file()


def test_explicit_crop_is_original_page_evidence_and_rejects_outside_page(tmp_path):
    module=importlib.import_module('posfoxgen.assets')
    pdf=tmp_path/'source.pdf';fixture_pdf(pdf)
    table=module.extract_assets(pdf,tmp_path/'crop',crops=[{'id':'table-results','type':'table','page':1,'bbox':[30,30,350,80],'caption':'Results crop'}])
    a=next(a for a in table['assets'] if a['id']=='table-results')
    assert a['type']=='table' and a['source']['page']==1
    assert Image.open(tmp_path/'crop'/a['path']).width==640
    with pytest.raises(ValueError,match='bounds'):
        module.extract_assets(pdf,tmp_path/'bad',crops=[{'id':'bad','page':1,'bbox':[-1,0,30,30]}])


def test_high_resolution_crop_records_actual_pixels_scale_and_pdf_bounds(tmp_path):
    module=importlib.import_module('posfoxgen.assets')
    pdf=tmp_path/'source.pdf';fixture_pdf(pdf)
    crops=[{'id':'four-x','page':1,'bbox':[30,30,350,80]},{'id':'three-x','page':1,'bbox':[30,30,350,80],'render_scale':3}]
    table=module.extract_assets(pdf,tmp_path/'crop',crops=crops,render_scale=4)
    assets={a['id']:a for a in table['assets']}
    a=assets['four-x'];b=assets['three-x']
    assert a['render_scale']==4 and a['width']==1280 and a['height']==200
    assert a['render_dpi']==288 and a['source_bounds_verified'] is True
    assert Image.open(tmp_path/'crop'/a['path']).size==(1280,200)
    assert b['render_scale']==3 and b['width']==960
    for scale in (0,-1,True,float('inf')):
        with pytest.raises(ValueError,match='render_scale'):
            module.extract_assets(pdf,tmp_path/'bad',crops=crops,render_scale=scale)


def test_crop_geometry_is_ready_for_generation_layout_not_just_dpi(tmp_path):
    from posfoxgen.assets import extract_assets
    pdf = tmp_path / 'paper.pdf'; fixture_pdf(pdf)
    table = extract_assets(pdf, tmp_path / 'out', [{'id': 'wide', 'page': 1, 'bbox': [30, 30, 350, 80]}], render_scale=4)
    figure = next(a for a in table['assets'] if a['id'] == 'wide')
    assert figure['geometry'] == {'pdf_size_pt': [320.0, 50.0], 'pixel_size': [1280, 200], 'aspect_ratio': 6.4}

@pytest.mark.parametrize("rotation", [0, 90])
def test_figure_review_keeps_complete_native_region_and_original_bytes(tmp_path, rotation):
    import hashlib
    import json
    from posfoxgen.figure_candidates import inspect_figure_page
    from PIL import ImageChops

    pdf = tmp_path / "layout.pdf"
    with fitz.open() as paper, fitz.open() as diagram:
        page = paper.new_page(width=400, height=500)
        page.insert_text((40, 40), "Running title")
        panel = diagram.new_page(width=300, height=100)
        panel.insert_text((8, 16), "A legitimate chart title")
        panel.draw_rect(fitz.Rect(3, 22, 297, 97))
        panel.insert_text((10, 91), "Bottom legend")
        placed = fitz.Rect(40, 100, 340, 200)
        page.show_pdf_page(placed, diagram, 0)
        page.insert_text((40, 224), "Figure 1: external caption")
        page.set_rotation(rotation)
        paper.save(pdf)
    original = pdf.read_bytes()
    out = inspect_figure_page(pdf, 1, tmp_path, render_scale=2)
    manifest = json.loads(out.read_text("utf-8"))
    assert pdf.read_bytes() == original
    assert manifest["paper_sha256"] == hashlib.sha256(original).hexdigest()
    assert (out.parent / manifest["preview"]).is_file()
    assert len(manifest["assets"]) == 1
    candidate = manifest["assets"][0]
    with fitz.open(pdf) as doc:
        placement = placed * doc[0].rotation_matrix
        assert candidate["bbox"] == pytest.approx(tuple(placement), abs=.05)
        expected = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), clip=placement)
    with Image.open(out.parent / candidate["path"]) as pixels:
        assert ImageChops.difference(pixels.convert("RGB"), expected.pil_image().convert("RGB")).getbbox() is None


def test_text_only_page_does_not_guess_a_crop(tmp_path):
    from posfoxgen.figure_candidates import inspect_figure_page
    import json
    pdf = tmp_path / "text.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 60), "Figure 1. A reference in running text.")
        doc.save(pdf)
    manifest = inspect_figure_page(pdf, 1, tmp_path)
    assert json.loads(manifest.read_text("utf-8"))["assets"] == []
    assert (manifest.parent / "page.png").is_file()
    with pytest.raises(ValueError, match="outside"):
        inspect_figure_page(pdf, 2, tmp_path)

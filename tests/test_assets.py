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

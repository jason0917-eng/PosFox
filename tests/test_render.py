import importlib
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))


def test_actual_browser_render_and_dom_audit_detect_text_overflow(tmp_path):
    m=importlib.import_module('posfoxgen.render')
    path=tmp_path/'poster.html'
    path.write_text('<!doctype html><html><body style="margin:0"><main id="poster" style="width:300px;height:220px;background:white"><div id="too-small" data-object-type="text" style="width:20px;height:10px;overflow:hidden;font-size:25px">Too much text for this rectangle</div></main></body></html>')
    report=m.render_poster(path,tmp_path/'render')
    assert Image.open(tmp_path/'render/poster.png').size==(300,220)
    assert (tmp_path/'render/poster.pdf').is_file()
    assert report['engine']=='chromium' and report['rendered'] is True
    assert any(x['object_id']=='too-small' and x['code']=='text_overflow' for x in report['blockers'])


def test_browser_audits_font_failure_cropping_and_native_table_overflow(tmp_path):
    m=importlib.import_module('posfoxgen.render')
    Image.new('RGB',(80,40),'blue').save(tmp_path/'figure.png')
    path=tmp_path/'poster.html'
    path.write_text('''<!doctype html><html><body style="margin:0"><main id="poster" style="position:relative;width:400px;height:260px;background:#e8f0f4">
<div id="missing-font" data-object-type="text" data-font-family="Definitely Missing" data-font-available="false" data-font-required="true" style="font-family:Definitely Missing;width:300px;height:30px">Font check</div>
<img id="cropped" data-object-type="image" src="figure.png" style="width:100px;height:100px;object-fit:cover">
<table id="native-table" data-object-type="table" style="width:60px;height:30px"><tr><td><div data-table-cell="tiny" style="height:10px;width:20px;font-size:24px">This value does not fit</div></td></tr></table>
</main></body></html>''')
    report=m.render_poster(path,tmp_path/'render')
    codes={x['code'] for x in report['blockers']}
    assert {'font_unavailable','image_semantic_crop','table_cell_overflow'}<=codes
    assert report['fonts'][0]['requested_family']=='Definitely Missing'
    image=next(o for o in report['objects'] if o['object_id']=='cropped')
    assert image['natural_width']==80 and image['object_fit']=='cover'


def test_real_native_background_table_rules_and_font_survive_render(tmp_path):
    from posfoxgen.editable import build_poster,export_svg
    m=importlib.import_module('posfoxgen.render')
    spec={'width':420,'height':260,'background':'#e8f0f4','font_policy':{'require_available':True},'panels':[{'id':'p','x':10,'y':10,'width':400,'height':240,'objects':[
      {'id':'title','type':'text','x':0,'y':0,'width':390,'height':40,'text':'Native Times','font_family':'Times New Roman','font_size':24},
      {'id':'rule','type':'line','x':0,'y':45,'width':390,'height':2,'x1':0,'y1':1,'x2':390,'y2':1,'stroke':'#163c60','stroke_width':2},
      {'id':'table','type':'table','x':0,'y':60,'width':390,'height':120,'rows':[['Model','Score'],['A','91.4']],'font_family':'Arial','font_size':20,'fill':'#e8f0f4','header_fill':'#b9d0df','stroke':'#163c60','row_heights':[60,60],'column_widths':[230,160]}
    ]}]}
    table={'assets':[]};html=build_poster(spec,table,tmp_path/'out');export_svg(spec,table,tmp_path/'out')
    report=m.render_poster(html,tmp_path/'render')
    assert report['blockers']==[]
    assert any(f['requested_family']=='Times New Roman' and f['available'] for f in report['fonts'])
    image=Image.open(tmp_path/'render/poster.png').convert('RGB')
    assert image.getpixel((1,1))==(232,240,244)
    assert image.getpixel((200,80))==(185,208,223)
    assert image.getpixel((200,150))==(232,240,244)
    assert image.getpixel((30,56))==(22,60,96)


def test_declared_bold_font_loads_real_face_and_table_header_alignment_is_not_browser_default(tmp_path):
    from posfoxgen.editable import build_poster
    m=importlib.import_module('posfoxgen.render')
    font=Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')
    spec={'width':400,'height':220,'font_policy':{'require_available':True},'fonts':[{'family':'Exact Local Bold','path':str(font),'weight':700}], 'panels':[{'id':'p','width':400,'height':220,'objects':[
      {'id':'label','type':'text','width':390,'height':40,'text':'Bold face test','font_family':'Exact Local Bold','font_weight':700},
      {'id':'t','type':'table','x':10,'y':60,'width':380,'height':100,'rows':[['Model','Score'],['A','24']],'align':'left','font_size':20}
    ]}]}
    path=build_poster(spec,{'assets':[]},tmp_path/'out');report=m.render_poster(path,tmp_path/'render')
    assert not report['blockers']
    face=next(f for f in report['fonts'] if f['object_id']=='label')
    assert face['faces'][0]['status']=='loaded' and face['faces'][0]['weight']=='700'
    from PIL import ImageFont
    expected=ImageFont.truetype(str(font),96).getlength('Experimental results')/4
    assert abs(face['sample_advance_px']-expected)<1
    table=next(o for o in report['objects'] if o['object_id']=='t')
    assert table['cells'][0]['text_align']=='left'


def test_browser_blocks_visible_stretch_even_when_explicitly_permitted(tmp_path):
    from posfoxgen.render import render_poster
    Image.new('RGB',(80,40),'blue').save(tmp_path/'figure.png')
    p=tmp_path/'poster.html'
    p.write_text('''<html><body style="margin:0"><main id="poster" style="width:500px;height:300px">
<img id="large" data-object-type="image" data-distortion-explicit="true" src="figure.png" style="width:250px;height:100px;object-fit:fill">
<img id="tiny" data-object-type="image" data-distortion-explicit="true" src="figure.png" style="width:200.5px;height:100px;object-fit:fill">
</main></body></html>''')
    r=render_poster(p,tmp_path/'render')
    issues=[b['object_id'] for b in r['blockers'] if b['code']=='image_distortion_forbidden']
    assert issues==['large','tiny']

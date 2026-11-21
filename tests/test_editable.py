import importlib
import json
import sys
from pathlib import Path
from PIL import Image
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))


def data(tmp_path):
    assets=tmp_path/'input'; assets.mkdir();Image.new('RGB',(80,40),'blue').save(assets/'figure.png')
    import hashlib
    return {'source':{'paper_sha256':'abc'},'root':str(assets),'assets':[{'id':'figure-1','type':'figure','path':'figure.png','sha256':hashlib.sha256((assets/'figure.png').read_bytes()).hexdigest(),'source':{'page':1,'locator':'Figure 1'}}]}, {'title':'Source-grounded poster','width':600,'height':400,'panels':[{'id':'results','x':20,'y':20,'width':560,'height':360,'objects':[{'id':'claim','type':'text','x':15,'y':15,'width':500,'height':70,'font_size':22,'text':'Model A < Model B: 24 samples','source_ids':['figure-1']},{'id':'evidence','type':'image','x':15,'y':100,'width':500,'height':200,'asset_id':'figure-1','fit':'contain'}]}]}


def test_native_text_and_replaced_source_asset_are_editable(tmp_path):
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    output=m.build_poster(spec,table,tmp_path/'out');html=Path(output).read_text()
    assert 'id="results"' in html and 'id="claim"' in html and 'id="evidence"' in html
    assert 'Model A &lt; Model B: 24 samples' in html and 'contenteditable="true"' in html
    assert 'object-fit:scale-down' in html and (tmp_path/'out/assets/figure-1.png').is_file()
    assert '<canvas' not in html and 'background-image' not in html
    assert (tmp_path/'out/poster_spec.json').is_file()


def test_invalid_id_reference_and_modified_source_are_blocked(tmp_path):
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    spec['panels'][0]['objects'][1]['asset_id']='missing'
    with pytest.raises(ValueError,match='asset'):
        m.build_poster(spec,table,tmp_path/'out')
    spec['panels'][0]['objects'][1]['asset_id']='figure-1'
    (Path(table['root'])/'figure.png').write_bytes(b'wrong')
    with pytest.raises(ValueError,match='hash'):
        m.build_poster(spec,table,tmp_path/'out2')


def test_duplicate_ids_and_active_svg_are_blocked(tmp_path):
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    spec['panels'][0]['objects'][1]['id']='claim'
    with pytest.raises(ValueError,match='duplicate'):
        m.build_poster(spec,table,tmp_path/'out')
    spec['panels'][0]['objects'][1]={'id':'graphic','type':'svg','x':0,'y':0,'width':20,'height':20,'svg':'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'}
    with pytest.raises(ValueError,match='SVG'):
        m.build_poster(spec,table,tmp_path/'out2')


def test_export_svg_preserves_native_ids_text_and_embeds_real_source_image(tmp_path):
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    spec['panels'][0]['objects'][0]['text']='First line\nSecond line'
    assert hasattr(m,'export_svg'), 'native SVG export is required'
    svg=m.export_svg(spec,table,tmp_path/'svg').read_text()
    import xml.etree.ElementTree as ET
    root=ET.fromstring(svg);nodes={n.get('id'):n for n in root.iter() if n.get('id')}
    assert nodes['claim'].tag.endswith('text') and len(list(nodes['claim']))==2
    assert nodes['evidence'].tag.endswith('image')
    assert nodes['evidence'].get('href').startswith('data:image/png;base64,')
    assert 'foreignObject' not in svg and 'First line' in svg


def test_local_gradient_rule_survives_native_export_and_actual_render(tmp_path):
    from posfoxgen.editable import export_svg
    from posfoxgen.render import render_poster
    table,spec=data(tmp_path)
    obj={'id':'section-rule','type':'svg','x':15,'y':320,'width':500,'height':20,
         'svg':'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 20"><defs><linearGradient id="local-paint"><stop offset="0" stop-color="#102c52"/><stop offset="1" stop-color="#50748b"/></linearGradient></defs><rect width="500" height="20" rx="5" fill="url(#local-paint)"/></svg>'}
    spec['panels'][0]['objects'].append(obj)
    svg=export_svg(spec,table,tmp_path/'out').read_text()
    assert 'linearGradient' in svg and 'url(#local-paint)' in svg
    render_poster(tmp_path/'out/poster.html',tmp_path/'rendered')
    picture=Image.open(tmp_path/'rendered/poster.png').convert('RGB')
    assert picture.getpixel((50,350))[2] < picture.getpixel((500,350))[2]


@pytest.mark.parametrize('paint',['url(https://example.test/external.svg#paint)','url(#missing-paint)'])
def test_gradient_reference_must_be_declared_in_same_svg(tmp_path,paint):
    from posfoxgen.editable import build_poster
    table,spec=data(tmp_path)
    spec['panels'][0]['objects'].append({'id':'bad-gradient','type':'svg','x':0,'y':320,'width':100,'height':10,'svg':f'<svg xmlns="http://www.w3.org/2000/svg"><rect width="100" height="10" fill="{paint}"/></svg>'})
    with pytest.raises(ValueError,match='SVG reference'):
        build_poster(spec,table,tmp_path/'out')


def test_font_inventory_and_strict_family_check_without_copying_system_fonts(tmp_path):
    from posfoxgen.fonts import font_inventory
    inventory=font_inventory()
    assert any(f['family']=='Arial' and Path(f['path']).is_file() for f in inventory)
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    spec['font_policy']={'require_available':True}
    spec['panels'][0]['objects'][0]['font_family']='Definitely Absent POSFOX Font'
    with pytest.raises(ValueError,match='font.*unavailable'):
        m.build_poster(spec,table,tmp_path/'bad-font')
    spec['panels'][0]['objects'][0]['font_family']='Times New Roman'
    out=m.build_poster(spec,table,tmp_path/'out')
    report=json.loads((out.parent/'fidelity_report.json').read_text())
    assert report['fonts'][0]['resolved_family']=='Times New Roman'
    assert not list((out.parent/'assets').glob('*.ttf'))


def test_explicit_font_embedding_is_opt_in_and_bound_to_font_hash(tmp_path):
    import hashlib
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    font=Path('/System/Library/Fonts/Supplemental/Arial.ttf')
    spec['fonts']=[{'family':'Poster Own Font','path':str(font),'sha256':hashlib.sha256(font.read_bytes()).hexdigest(),'embed':True}]
    spec['panels'][0]['objects'][0]['font_family']='Poster Own Font'
    with pytest.raises(ValueError,match='embedding.*authoriz'):
        m.build_poster(spec,table,tmp_path/'unapproved')
    spec['fonts'][0]['embedding_authorized']=True
    svg=m.export_svg(spec,table,tmp_path/'out').read_text()
    html=(tmp_path/'out/poster.html').read_text()
    assert '@font-face' in html and 'data:font/ttf;base64,' in html
    assert '@font-face' in svg and 'Poster Own Font' in svg
    spec['fonts'][0]['sha256']='wrong'
    with pytest.raises(ValueError,match='font.*hash'):
        m.build_poster(spec,table,tmp_path/'wrong')


def test_svg_wrap_measures_the_requested_font_instead_of_arial(tmp_path):
    from PIL import ImageFont
    import xml.etree.ElementTree as ET
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    times=ImageFont.truetype('/System/Library/Fonts/Supplemental/Times New Roman.ttf',24)
    arial=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',24)
    text='MMMM MMMM';width=(times.getlength(text)+arial.getlength(text))/2
    obj=spec['panels'][0]['objects'][0];obj.update(text=text,font_size=24,font_family='Times New Roman',width=width)
    svg=ET.parse(m.export_svg(spec,table,tmp_path/'out'))
    node=next(n for n in svg.iter() if n.get('id')=='claim')
    assert len(list(node))==(1 if times.getlength(text)<=width else 2)


def test_native_rect_line_and_table_preserve_geometry_fills_and_editable_cells(tmp_path):
    import xml.etree.ElementTree as ET
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    spec['panels'][0]['background']='#e8f0f4'
    spec['panels'][0]['objects']=[
      {'id':'highlight','type':'rect','x':5,'y':5,'width':530,'height':120,'fill':'#d6e7ef','stroke':'#163c60','stroke_width':2,'radius':8},
      {'id':'rule','type':'line','x':5,'y':145,'width':530,'height':2,'stroke':'#163c60','stroke_width':2,'x1':0,'y1':1,'x2':530,'y2':1},
      {'id':'results-table','type':'table','x':5,'y':165,'width':530,'height':120,'rows':[['Model','Score'],['Ours','91.4']],'column_widths':[330,200],'row_heights':[60,60],'font_size':22,'header_rows':1,'header_fill':'#b9d0df','fill':'#e8f0f4','stroke':'#163c60','source_ids':['figure-1']}
    ]
    svg=ET.parse(m.export_svg(spec,table,tmp_path/'out'));nodes={n.get('id'):n for n in svg.iter() if n.get('id')}
    assert nodes['highlight'].tag.endswith('rect') and nodes['highlight'].get('rx')=='8'
    assert nodes['rule'].tag.endswith('line') and nodes['rule'].get('x1')=='5' and nodes['rule'].get('x2')=='535'
    assert nodes['results-table'].tag.endswith('g')
    assert nodes['results-table-cell-1-1-text'].tag.endswith('text')
    html=(tmp_path/'out/poster.html').read_text()
    assert '<table' in html and 'contenteditable="true"' in html and '91.4' in html
    assert 'background:#e8f0f4' in html and 'height:60px' in html
    spec['panels'][0]['objects'][2]['column_widths']=[330,190]
    with pytest.raises(ValueError,match='column_widths'):
        m.build_poster(spec,table,tmp_path/'bad-table')


def test_image_fit_rejects_distortion_permission_and_preserves_source_bytes(tmp_path):
    import hashlib
    import xml.etree.ElementTree as ET
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    obj=spec['panels'][0]['objects'][1]
    obj.update(fit='fill',allow_distortion=True,distortion_reason='Legacy explicit approval')
    with pytest.raises(ValueError,match='distortion'):
        m.build_poster(spec,table,tmp_path/'bad')
    obj['fit']='contain'
    svg=ET.parse(m.export_svg(spec,table,tmp_path/'out'))
    image=next(n for n in svg.iter() if n.get('id')=='evidence')
    assert image.get('preserveAspectRatio')!='none'
    report=json.loads((tmp_path/'out/fidelity_report.json').read_text())
    assert report['images'][0]['display_pixels']==[80,40]
    assert hashlib.sha256((tmp_path/'out/assets/figure-1.png').read_bytes()).hexdigest()==table['assets'][0]['sha256']


def test_paper_white_matte_is_flagged_and_strict_background_match_is_checked(tmp_path):
    import hashlib
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    image=Path(table['root'])/'figure.png';Image.new('RGB',(80,40),'white').save(image)
    table['assets'][0]['sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
    spec['panels'][0]['background']='#e8f0f4'
    out=m.build_poster(spec,table,tmp_path/'out')
    report=json.loads((out.parent/'fidelity_report.json').read_text())
    assert any(w['code']=='image_background_mismatch' for w in report['warnings'])
    spec['image_policy']={'require_background_decision':True}
    with pytest.raises(ValueError,match='background'):
        m.build_poster(spec,table,tmp_path/'no-decision')
    obj=spec['panels'][0]['objects'][1];obj['background_policy']='match'
    with pytest.raises(ValueError,match='background'):
        m.build_poster(spec,table,tmp_path/'false-match')
    obj['background_policy']='preserve'
    m.build_poster(spec,table,tmp_path/'preserve')
    obj['fit']='contain';obj['crop']=[1,1,40,20]
    with pytest.raises(ValueError,match='crop'):
        m.build_poster(spec,table,tmp_path/'hidden-crop')


def test_font_inventory_accepts_extra_roots_without_installing_or_copying(tmp_path):
    from posfoxgen.fonts import font_inventory
    link=tmp_path/'local-font.ttf';link.symlink_to('/System/Library/Fonts/Supplemental/Arial.ttf')
    inventory=font_inventory(extra_roots=[tmp_path])
    assert any(f['path']==str(link) and f['family']=='Arial' for f in inventory)
    assert not any(f['path']==str(link) for f in font_inventory())


def test_local_font_declaration_uses_exact_bold_face_and_source_url():
    from posfoxgen.fonts import font_declarations
    font=Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')
    _,css=font_declarations({'fonts':[{'family':'Exact Local Bold','path':str(font),'weight':700}]})
    assert 'Arial-BoldMT' in css
    assert font.as_uri() in css
    assert 'local("Arial")' not in css


def test_native_table_header_alignment_is_shared_by_html_and_svg(tmp_path):
    import re
    import xml.etree.ElementTree as ET
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    spec['panels'][0]['objects']=[{'id':'tbl','type':'table','x':10,'y':10,'width':400,'height':120,'rows':[['Header','Value'],['A','24']],'align':'left','font_size':20}]
    svg=ET.parse(m.export_svg(spec,table,tmp_path/'out'))
    html=(tmp_path/'out/poster.html').read_text()
    header=re.search(r'<th[^>]+style="([^"]+)"',html).group(1)
    assert 'text-align:left' in header
    node=next(n for n in svg.iter() if n.get('id')=='tbl-cell-0-0-text')
    assert node.get('text-anchor')=='start'


def test_native_table_row_emphasis_column_alignment_and_row_fills_match_svg_and_browser(tmp_path):
    import re
    import fitz
    import xml.etree.ElementTree as ET
    from posfoxgen.render import render_poster
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    obj={'id':'matched-table','type':'table','x':20,'y':20,'width':500,'height':300,'rows':[['System','Score'],['AutoDesign','78.32'],['Claude Design','70.87'],['Claude Code','70.01'],['OpenDesign','69.45']],'font_family':'Arial','font_size':22,'column_widths':[340,160],'row_heights':[60]*5,'row_font_weights':[700,700,400,400,400],'column_aligns':['left','right'],'row_fills':['#e2effc','#dfe7f7','#ffffff','#ffffff','#ffffff']}
    spec['panels'][0]['objects']=[obj];svg=ET.parse(m.export_svg(spec,table,tmp_path/'out'));html=(tmp_path/'out/poster.html').read_text()
    nodes={n.get('id'):n for n in svg.iter() if n.get('id')}
    assert nodes['matched-table-cell-1-1-text'].get('font-weight')=='700'
    assert nodes['matched-table-cell-2-1-text'].get('font-weight')=='400'
    assert nodes['matched-table-cell-1-1-text'].get('text-anchor')=='end'
    assert nodes['matched-table-cell-1-0-text'].get('text-anchor')=='start'
    assert nodes['matched-table-cell-1-0'].get('fill')=='#dfe7f7'
    assert 'font-weight:700' in re.search(r'<td id="matched-table-cell-1-1" style="([^"]+)"',html).group(1)
    report=render_poster(tmp_path/'out/poster.html',tmp_path/'render')
    assert not report['blockers']
    actual=next(o for o in report['objects'] if o['object_id']=='matched-table')
    assert [c['text_align'] for c in actual['cells']]==['left','right']*5
    image=Image.open(tmp_path/'render/poster.png').convert('RGB')
    assert image.getpixel((300,50))==(226,239,252)
    assert image.getpixel((300,110))==(223,231,247)
    assert image.getpixel((300,170))==(255,255,255)
    doc=fitz.open(tmp_path/'render/poster.pdf')
    spans=[s for block in doc[0].get_text('dict')['blocks'] if block['type']==0 for line in block['lines'] for s in line['spans']]
    bold=next(s for s in spans if s['text']=='78.32');regular=next(s for s in spans if s['text']=='70.87')
    assert bold['flags']&16 and not regular['flags']&16
    doc.close()


@pytest.mark.parametrize('field,value',[
 ('row_font_weights',[700]),('row_font_weights',[700,333]),('row_font_weights',[700,True]),
 ('column_aligns',['left']),('column_aligns',['left','diagonal']),('column_aligns','left'),
 ('row_fills',['#ffffff']),('row_fills',['#ffffff','url(external)']),('row_fills','white')])
def test_native_table_explicit_row_and_column_styles_are_validated(tmp_path,field,value):
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    obj={'id':'t','type':'table','x':10,'y':10,'width':400,'height':120,'rows':[['System','Score'],['AutoDesign','78.32']],field:value}
    spec['panels'][0]['objects']=[obj]
    with pytest.raises(ValueError,match=field):m.build_poster(spec,table,tmp_path/'bad')


def test_inline_emphasis_preserves_one_native_paragraph_and_bold_wrap_metrics(tmp_path):
    import xml.etree.ElementTree as ET
    from PIL import ImageFont
    from html.parser import HTMLParser
    from posfoxgen.render import render_poster
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    regular=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',96)
    bold=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf',96)
    text='Experimental results';width=(regular.getlength(text)+bold.getlength(text))/8
    obj=spec['panels'][0]['objects'][0];obj.update(text=text,font_size=24,font_family='Arial',width=width,height=90,emphasis=[{'text':text,'font_weight':700}])
    spec['panels'][0]['objects']=[obj]
    svg=ET.parse(m.export_svg(spec,table,tmp_path/'out'));node=next(n for n in svg.iter() if n.get('id')=='claim')
    assert len(list(node))==2,'bold widths must force two lines at this width'
    assert all(n.get('font-weight')=='700' for n in node.iter() if n is not node)
    report=render_poster(tmp_path/'out/poster.html',tmp_path/'render');assert not report['blockers']
    import fitz
    pdf=fitz.open(tmp_path/'render/poster.pdf');spans=[s for block in pdf[0].get_text('dict')['blocks'] if block['type']==0 for line in block['lines'] for s in line['spans']]
    assert len(spans)==2 and all(s['flags']&16 for s in spans);pdf.close()
    # Mixed styles retain exact underlying text in one contenteditable paragraph.
    obj.update(text='Input: mean 54.99 to 67.39.',width=500,height=70,emphasis=[{'text':'Input:','font_weight':700},{'text':'54.99','font_weight':700},{'text':'67.39','font_weight':700}])
    svg=ET.parse(m.export_svg(spec,table,tmp_path/'mixed'));node=next(n for n in svg.iter() if n.get('id')=='claim')
    assert ''.join(node.itertext())==obj['text']
    assert [n.text for n in node.iter() if n.get('font-weight')=='700']==['Input:','54.99','67.39']
    html=(tmp_path/'mixed/poster.html').read_text()
    assert html.count('contenteditable="true"')==1 and html.count('data-emphasis="700"')==3


@pytest.mark.parametrize('emphasis',[
 [{'text':'missing phrase','font_weight':700}], [{'text':'','font_weight':700}],
 [{'text':'Model','font_weight':400}], [{'text':'Model','font_weight':700},{'text':'Model A','font_weight':700}],
 'Input:'
])
def test_inline_emphasis_rejects_missing_overlapping_or_unsupported_requests(tmp_path,emphasis):
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    spec['panels'][0]['objects'][0]['emphasis']=emphasis
    with pytest.raises(ValueError,match='emphasis'):m.build_poster(spec,table,tmp_path/'invalid')


@pytest.mark.parametrize("width,height", [(401.1,200), (80.5,40), (400,250)])
def test_image_distortion_limit_cannot_be_bypassed_by_permission(tmp_path,width,height):
    m=importlib.import_module('posfoxgen.editable');table,spec=data(tmp_path)
    obj=spec['panels'][0]['objects'][1]
    obj.update(width=width,height=height,fit='fill',allow_distortion=True,distortion_reason='Explicit approval cannot override the limit')
    with pytest.raises(ValueError,match='distortion'):
        m.build_poster(spec,table,tmp_path/'blocked')


def test_filled_rect_does_not_invent_an_outline_but_explicit_frames_survive(tmp_path):
    import xml.etree.ElementTree as ET
    from posfoxgen.editable import export_svg
    assets,spec=data(tmp_path)
    spec['panels'][0]['objects']=[
      {'id':'fill-only','type':'rect','x':5,'y':5,'width':200,'height':50,'fill':'#f5e5e8'},
      {'id':'source-frame','type':'rect','x':5,'y':65,'width':200,'height':50,'fill':'#ffffff','stroke':'#567baa','stroke_width':.7},
      {'id':'connection','type':'line','x':5,'y':125,'width':200,'height':1}]
    target=export_svg(spec,assets,tmp_path/'out')
    nodes={n.get('id'):n for n in ET.parse(target).iter() if n.get('id')}
    assert nodes['fill-only'].get('stroke')=='none'
    assert nodes['source-frame'].get('stroke')=='#567baa'
    assert nodes['connection'].get('stroke')=='#17232b'
    assert 'stroke="none"' in (tmp_path/'out/poster.html').read_text()


def test_source_bound_emphasis_color_survives_native_and_html_export(tmp_path):
    import xml.etree.ElementTree as ET
    from posfoxgen.editable import export_svg
    assets,spec=data(tmp_path);obj=spec['panels'][0]['objects'][0]
    obj['emphasis']=[{'text':'24 samples','font_weight':700,'color':'#e98a05'}]
    target=export_svg(spec,assets,tmp_path/'out')
    assert any(n.get('fill')=='#e98a05' and '24 samples' in ''.join(n.itertext()) for n in ET.parse(target).iter())
    assert 'color:#e98a05' in (tmp_path/'out/poster.html').read_text()

import json
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest


def fixture(tmp_path):
    obj={'id':'body','type':'text','x':10,'y':10,'width':180,'height':140,'font_family':'Arial','font_size':20,'font_weight':400,'text':'A long scientific paragraph needs several visible lines to fit its fixed frame.'}
    spec={'width':240,'height':200,'panels':[{'id':'panel','width':240,'height':200,'objects':[obj]}]}
    svg=tmp_path/'input.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="200"><rect id="background" width="240" height="200" fill="white"/><g id="panel"><text id="body" x="10" y="30" font-family="Arial" font-size="20">'+obj['text']+'</text></g></svg>')
    return svg,spec


def test_existing_svg_is_reflowed_using_actual_browser_metrics(tmp_path):
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    result=repair_svg(svg,spec,tmp_path/'fixed')
    tree=ET.parse(result['svg']);node=next(n for n in tree.iter() if n.get('id')=='body')
    assert len(list(node))>1
    assert node.get('font-size')=='20'
    assert ''.join(node.itertext()).replace(' ','')==spec['panels'][0]['objects'][0]['text'].replace(' ','')
    assert not result['svg_width_blockers']
    assert tree.find('.//{*}rect').attrib==ET.parse(svg).find('.//{*}rect').attrib


def test_weight_levels_and_typeset_formula_survive_native_svg(tmp_path):
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    spec['panels'][0]['objects'][0]['text']='A long scientific paragraph needs several visible lines to fit its fixed frame.'
    issues={'body':{'emphasis':[{'text':'scientific','font_weight':600},{'text':'paragraph','font_weight':800}], 'math_runs':[{'text':'fixed frame', 'latex':r'\frac{QK^{T}}{\sqrt{d_k}}'}]}}
    result=repair_svg(svg,spec,tmp_path/'fixed',issues=issues)
    tree=ET.parse(result['svg']);nodes=list(tree.iter())
    weights={n.get('font-weight') for n in nodes}
    assert {'600','800'}<=weights
    math=next(n for n in nodes if n.get('data-latex'))
    assert math.get('data-latex')==r'\frac{QK^{T}}{\sqrt{d_k}}'
    assert any(n.tag.endswith('path') for n in math.iter())
    assert not any(n.tag.endswith('foreignObject') for n in nodes)


def test_invalid_math_is_reported_not_silently_replaced(tmp_path):
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    with pytest.raises(ValueError,match='formula'):
        repair_svg(svg,spec,tmp_path/'fixed',issues={'body':{'math_runs':[{'text':'fixed frame','latex':r'\unknowncommand{X}'}]}})


def test_core_export_accepts_distinct_emphasis_levels(tmp_path):
    from posfoxgen.editable import build_poster, export_svg
    svg,spec=fixture(tmp_path)
    obj=spec['panels'][0]['objects'][0]
    obj['emphasis']=[{'text':'scientific','font_weight':600},{'text':'paragraph','font_weight':800}]
    output=build_poster(spec,{'assets':[]},tmp_path/'core')
    assert 'data-emphasis="600"' in output.read_text()
    assert 'data-emphasis="800"' in output.read_text()
    tree=ET.parse(export_svg(spec,{'assets':[]},tmp_path/'core'))
    assert {'600','800'}<={n.get('font-weight') for n in tree.iter()}


def test_supplementary_unicode_is_not_split_into_invalid_surrogates(tmp_path):
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    spec['panels'][0]['objects'][0]['text']='A mathematical variable 𝑛 is preserved in this scientific paragraph.'
    result=repair_svg(svg,spec,tmp_path/'fixed',issues={'body':{'emphasis':[{'text':'scientific','font_weight':600}]}})
    assert '𝑛' in Path(result['svg']).read_text()


def test_healthy_svg_is_preserved_without_an_issue_trigger(tmp_path):
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    spec['panels'][0]['objects'][0]['width']=220
    spec['panels'][0]['objects'][0]['text']='Short healthy text'
    root=ET.parse(svg);node=next(n for n in root.iter() if n.get('id')=='body');node.text='Short healthy text';root.write(svg,encoding='unicode')
    before=ET.tostring(node)
    result=repair_svg(svg,spec,tmp_path/'fixed')
    assert result['triggered_object_ids']==[]
    after=next(n for n in ET.parse(result['svg']).iter() if n.get('id')=='body')
    assert ET.tostring(after)==before


def test_text_repair_export_is_replayable_by_the_formal_binding_gate(tmp_path):
    from posfoxgen.editable import export_svg
    from posfoxgen.export_bindings import validate_export_bindings
    svg,spec=fixture(tmp_path)
    spec['typography_repair']={'format':'posfoxgen-svg-text-repair-v1','issues':{'body':{'math_runs':[{'text':'fixed frame','latex':r'\frac{QK^T}{\sqrt{d_k}}'}]}}}
    out=tmp_path/'bound';target=export_svg(spec,{'assets':[]},out)
    assert 'data-latex=' in target.read_text()
    assert '<svg' in (out/'poster.html').read_text()
    report=validate_export_bindings(out/'poster_spec.json',out/'poster.html',target,{'assets':[]})
    assert report['pass'],report['blockers']
    target.write_text(target.read_text().replace('data-latex=', 'transform="translate(100 0)" data-latex=',1))
    assert not validate_export_bindings(out/'poster_spec.json',out/'poster.html',target,{'assets':[]})['pass']


def test_repairing_an_already_typeset_svg_does_not_duplicate_formulae(tmp_path):
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    issues={'body':{'math_runs':[{'text':'fixed frame','latex':r'm_H'}]}}
    first=repair_svg(svg,spec,tmp_path/'one',issues=issues)
    second=repair_svg(first['svg'],spec,tmp_path/'two',issues=issues)
    a=[n for n in ET.parse(first['svg']).iter() if n.get('data-latex')]
    b=[n for n in ET.parse(second['svg']).iter() if n.get('data-latex')]
    assert len(a)==len(b)==1


def test_partial_italic_style_is_preserved_without_italicizing_the_whole_paragraph(tmp_path):
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    result=repair_svg(svg,spec,tmp_path/'mixed',issues={'body':{'style_runs':[{'text':'scientific paragraph','font_style':'italic'}]}})
    node=next(n for n in ET.parse(result['svg']).iter() if n.get('id')=='body')
    italics=[n for n in node if n.get('font-style')=='italic']
    assert 'scientificparagraph'==''.join(n.text or '' for n in italics).replace(' ','')
    assert any(n.get('font-style')=='normal' for n in node)


def test_html_preview_audits_native_svg_frames_instead_of_html_scroll_metrics(tmp_path):
    from posfoxgen.editable import export_svg
    from posfoxgen.render import render_poster
    svg,spec=fixture(tmp_path)
    spec['typography_repair']={'format':'posfoxgen-svg-text-repair-v1','issues':{}}
    export_svg(spec,{'assets':[]},tmp_path/'native')
    report=render_poster(tmp_path/'native/poster.html',tmp_path/'render')
    assert report['layout_pass'],report['blockers']
    assert report['svg_text_checks']
    assert not any(c['horizontal'] or c['vertical'] for c in report['svg_text_checks'])


def test_typeset_formula_use_references_render_in_inline_html(tmp_path):
    from posfoxgen.editable import export_svg
    from posfoxgen.render import render_poster
    from posfoxgen.render import find_browser
    from playwright.sync_api import sync_playwright
    svg,spec=fixture(tmp_path)
    spec['typography_repair']={'format':'posfoxgen-svg-text-repair-v1','issues':{'body':{'math_runs':[{'text':'fixed frame','latex':r'm_H'}]}}}
    target=export_svg(spec,{'assets':[]},tmp_path/'formula')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=find_browser(),headless=True)
        try:
            page=browser.new_page();page.goto(target.with_suffix('.html').as_uri())
            refs=page.evaluate("() => [...document.querySelectorAll('g[data-latex] use')].map(n=>({ref:n.href.baseVal,exists:!!document.getElementById(n.href.baseVal.slice(1))}))")
            assert refs and all(r['ref'].startswith('#') and r['exists'] for r in refs),refs
        finally:browser.close()


def test_reference_lines_are_never_rewrapped_when_too_wide(tmp_path):
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    text=spec['panels'][0]['objects'][0]['text']
    result=repair_svg(svg,spec,tmp_path/'strict',issues={'body':{'lines':[text]}})
    assert result['text_objects'][0]['line_count']==1
    assert result['svg_width_blockers'], 'Report the mismatch instead of inventing more lines'


def test_reference_mode_requires_evidence_and_leaves_other_overflow_untouched(tmp_path):
    import hashlib
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    with pytest.raises(ValueError,match='reference evidence'):
        repair_svg(svg,spec,tmp_path/'invalid',issues={'body':{'lines':[spec['panels'][0]['objects'][0]['text']]}},mode='reference-guided')
    proof=tmp_path/'reference.png'
    from PIL import Image
    Image.new('RGB',(20,20),'white').save(proof)
    obj=spec['panels'][0]['objects'][0];other={**obj,'id':'other','y':160,'text':'An overflowing unconfirmed object must stay unchanged'}
    spec['panels'][0]['objects'].append(other)
    tree=ET.parse(svg);root=tree.getroot();g=root.find('.//{*}g');node=ET.SubElement(g,'{http://www.w3.org/2000/svg}text',{'id':'other','x':'10','y':'180','font-size':'20'});node.text=other['text'];before=ET.tostring(node);tree.write(svg,encoding='unicode')
    issue={'lines':['A long scientific paragraph','needs several visible lines','to fit its fixed frame.'],'reference':{'path':str(proof),'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()},'reason':'paired source confirms wrong line breaks'}
    result=repair_svg(svg,spec,tmp_path/'scoped',issues={'body':issue},mode='reference-guided')
    assert result['triggered_object_ids']==['body']
    after=next(n for n in ET.parse(result['svg']).iter() if n.get('id')=='other')
    assert ET.tostring(after)==before


def test_reference_containers_are_audited_but_never_resized():
    from posfoxgen.reference_layout import check_containers
    root=ET.fromstring('<svg><g><rect id="box" x="0" y="0" width="100" height="20"/></g></svg>')
    checks=[{'object_id':'body','x':5,'y':5,'width':80,'height':30}]
    issues={'body':{'container':{'id':'box','reference_frame':[0,0,100,40]}}}
    before=ET.tostring(root)
    result=check_containers(root,checks,issues,{'body':(0,0,{})})
    assert result[0]['status']=='blocked_container_overflow'
    assert ET.tostring(root)==before


def test_native_title_at_page_top_uses_ink_bounds_not_em_box(tmp_path):
    from posfoxgen.editable import export_svg
    from posfoxgen.render import render_poster
    svg,spec=fixture(tmp_path)
    obj=spec['panels'][0]['objects'][0];obj.update(y=0,text='A title\nSecond title',font_size=40,line_height=1.02,height=85,width=220)
    spec['typography_repair']={'format':'posfoxgen-svg-text-repair-v1','issues':{'body':{'lines':['A title','Second title']}}}
    export_svg(spec,{'assets':[]},tmp_path/'title')
    result=render_poster(tmp_path/'title/poster.html',tmp_path/'render')
    assert result['layout_pass'],result['blockers']


def test_reference_spacing_compacts_text_without_touching_frames_or_font_size(tmp_path):
    import hashlib
    from PIL import Image
    from posfoxgen.svg_text_repair import repair_svg
    from posfoxgen.editable import export_svg
    svg,spec=fixture(tmp_path);obj=spec['panels'][0]['objects'][0]
    obj.update(text='A scientific title\nAnother title',width=150,height=38,font_size=20,line_height=1.5)
    proof=tmp_path/'reference.png';Image.new('RGB',(200,100),'white').save(proof)
    svg=export_svg(spec,{'assets':[]},tmp_path/'base')
    issue={'lines':['A scientific title','Another title'],'reason':'reference confirms two lines and fixed title frame','reference':{'path':str(proof),'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()},'panel_frame':[0,0,240,200]}
    result=repair_svg(svg,spec,tmp_path/'compact',issues={'body':issue},mode='reference-guided')
    assert not result['svg_width_blockers']
    assert not result['svg_height_blockers']
    assert result['spacing_adjustments']
    node=next(n for n in ET.parse(result['svg']).iter() if n.get('id')=='body')
    assert node.get('font-size')=='20'
    assert result['text_objects'][0]['line_count']==2
    assert obj['width']==150 and obj['height']==38 and obj['line_height']==1.5


def test_reference_rejects_et_al_split_across_lines(tmp_path):
    import hashlib
    from PIL import Image
    from posfoxgen.reference_layout import validate_reference
    image=tmp_path/'source.png';Image.new('RGB',(20,20),'white').save(image)
    issue={'reason':'reference citation','lines':['B. P. Abbott et','al. (LIGO)'],'reference':{'path':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}}
    with pytest.raises(ValueError,match='protected phrase'):
        validate_reference({'citation':issue})


def test_et_al_returns_to_one_line_without_invading_doi(tmp_path):
    import hashlib
    from PIL import Image
    from posfoxgen.editable import export_svg
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path);obj=spec['panels'][0]['objects'][0]
    obj.update(text='Abbott et al.',width=96,height=24,font_size=20,line_height=1.2)
    spec['panels'][0]['objects'].append({**obj,'id':'doi','y':36,'width':210,'text':'DOI: 10.1103/example'})
    svg=export_svg(spec,{'assets':[]},tmp_path/'initial')
    proof=tmp_path/'reference.png';Image.new('RGB',(240,200),'white').save(proof)
    issue={'reason':'severe protected-phrase break above DOI','lines':['Abbott et al.'],'reference':{'path':str(proof),'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()},'panel_frame':[0,0,240,200]}
    before=next(n for n in ET.parse(svg).iter() if n.get('id')=='doi');frozen=ET.tostring(before)
    result=repair_svg(svg,spec,tmp_path/'final',issues={'body':issue},mode='reference-guided')
    assert not result['svg_width_blockers'] and not result['svg_height_blockers']
    assert not result['container_blockers']
    assert result['reference_line_findings'][0]['severity']=='severe'
    after=ET.parse(result['svg']);node=next(n for n in after.iter() if n.get('id')=='body')
    assert ''.join(node.itertext())=='Abbott et al.'
    assert len({t.get('y') for t in node})==1
    assert ET.tostring(next(n for n in after.iter() if n.get('id')=='doi'))==frozen


def test_inline_render_blocks_collision_between_fixed_text_frames(tmp_path):
    import hashlib
    from PIL import Image
    from posfoxgen.editable import export_svg
    from posfoxgen.render import render_poster
    svg,spec=fixture(tmp_path);obj=spec['panels'][0]['objects'][0];obj.update(text='A title',height=25)
    spec['panels'][0]['objects'].append({**obj,'id':'author','text':'An author'})
    proof=tmp_path/'ref.png';Image.new('RGB',(240,200),'white').save(proof)
    issue={'reason':'reference','lines':['A title'],'reference':{'path':str(proof),'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()},'panel_frame':[0,0,240,200]}
    spec['typography_repair']={'format':'posfoxgen-svg-text-repair-v1','mode':'reference-guided','issues':{'body':issue}}
    export_svg(spec,{'assets':[]},tmp_path/'overlap')
    report=render_poster(tmp_path/'overlap/poster.html',tmp_path/'render')
    assert not report['layout_pass']
    assert any(b['code']=='reference_text_collision' for b in report['blockers'])


def test_reference_inspection_reads_relative_dy_lines_and_inline_runs():
    from posfoxgen.reference_layout import inspect_reference_lines
    root=ET.fromstring('<svg><text id="title" y="20"><tspan x="0" dy="0">First line</tspan><tspan x="0" dy="24"><tspan>Second </tspan><tspan>line</tspan></tspan></text></svg>')
    result=inspect_reference_lines(root,{'title':{'lines':['First line','Second line']}})
    assert result[0]['actual_lines']==['First line','Second line']
    assert not result[0]['line_mismatch']


def test_confirmed_reference_color_survives_measured_repair(tmp_path):
    from posfoxgen.svg_text_repair import repair_svg
    svg,spec=fixture(tmp_path)
    result=repair_svg(svg,spec,tmp_path/'color',issues={'body':{'emphasis':[{'text':'scientific','font_weight':700,'color':'#e98a05'}]}})
    node=next(n for n in ET.parse(result['svg']).iter() if n.get('id')=='body')
    assert any(n.get('fill')=='rgb(233, 138, 5)' and 'scientific' in ''.join(n.itertext()) for n in node)


def test_editable_cli_runs_native_export_and_reference_guided_contract(tmp_path):
    import hashlib
    from PIL import Image
    from posfoxgen.editable import main
    svg,spec=fixture(tmp_path);obj=spec['panels'][0]['objects'][0]
    obj['text']='Scientific title'
    reference=tmp_path/'reference.png';Image.new('RGB',(240,200),'white').save(reference)
    spec['typography_repair']={'format':'posfoxgen-svg-text-repair-v1','issues':{'body':{'reason':'confirmed source line','lines':['Scientific title'],'reference':{'path':str(reference),'sha256':hashlib.sha256(reference.read_bytes()).hexdigest()},'panel_frame':[0,0,240,200]}}}
    spec_path=tmp_path/'spec.json';spec_path.write_text(json.dumps(spec));asset_path=tmp_path/'assets.json';asset_path.write_text(json.dumps({'assets':[]}))
    main([str(spec_path),'--assets',str(asset_path),'--out',str(tmp_path/'out')])
    assert (tmp_path/'out/poster.svg').is_file()
    assert (tmp_path/'out/poster.html').is_file()
    report=json.loads((tmp_path/'out/text-repair-report.json').read_text())
    assert report['mode']=='reference-guided'
    assert 'mode' not in json.loads(spec_path.read_text())['typography_repair']

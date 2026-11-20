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

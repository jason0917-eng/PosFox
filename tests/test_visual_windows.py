from pathlib import Path
import json
from PIL import Image
import pytest


def test_semantic_windows_preserve_inputs_and_separate_redline_overlay(tmp_path):
    from posfoxgen.visual_windows import build_windows
    g=tmp_path/'g.png';n=tmp_path/'n.png'
    Image.new('RGB',(100,80),'white').save(g);Image.new('RGB',(100,80),'blue').save(n)
    before=g.read_bytes(),n.read_bytes()
    records=build_windows(g,n,[{'id':'mechanism','generated_region':[10,20,50,30],'native_region':[10,20,50,30],'marks':[{'side':'native','bbox':[5,5,10,10],'label':'missing orange bullet','kind':'issue'}]}],tmp_path/'review')
    assert before==(g.read_bytes(),n.read_bytes())
    assert Image.open(records[0]['paired_window_path']).size==(100,30)
    red=Image.open(records[0]['redline_path']);assert red.getpixel((55,5))[:3]==(220,35,35)
    assert Path(records[0]['redline_path'])!=g and Path(records[0]['redline_path'])!=n
    assert json.loads((tmp_path/'review/windows.json').read_text())['windows'][0]['id']=='mechanism'


def test_window_generator_rejects_clipping_context_or_overwriting_sources(tmp_path):
    from posfoxgen.visual_windows import build_windows
    g=tmp_path/'g.png';Image.new('RGB',(100,80),'white').save(g)
    with pytest.raises(ValueError,match='bounds'):
        build_windows(g,g,[{'id':'bad','generated_region':[-1,0,50,20],'native_region':[0,0,50,20],'marks':[]}],tmp_path/'out')

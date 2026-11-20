from pathlib import Path
import json
from PIL import Image
import pytest


def test_planner_covers_repeated_modules_and_small_features():
    from posfoxgen.visual_windows import plan_windows
    roster = {'canvas': [100, 80], 'modules': [
        {'id': 'first', 'region': [0, 0, 20, 20], 'features': [
            {'id': 'dot', 'region': [18, 18, 2, 2]}]},
        {'id': 'repeat', 'region': [20, 0, 20, 20]}]}
    windows = plan_windows(roster)
    assert len(windows) == 4
    assert windows[1]['generated_region'] == [0, 0, 23, 23]
    assert windows[2]['feature_id'] == 'dot'
    assert windows[3]['module_id'] == 'repeat'
    assert all(w['marks'] == [] for w in windows)
    assert windows[3]['generated_region'][0] < 20


@pytest.mark.parametrize('region', [[-1, 0, 4, 4], [0, 0, 101, 1], [0, 0, 0, 1]])
def test_planner_rejects_invalid_regions(region):
    from posfoxgen.visual_windows import plan_windows
    with pytest.raises(ValueError):
        plan_windows({'canvas': [100, 80], 'modules': [{'id': 'bad', 'region': region}]})


def test_hash_bound_detail_crop_cannot_stand_in_for_full_module(tmp_path):
    import hashlib
    from posfoxgen.visual_windows import build_windows
    from posfoxgen.design_roster import _check_window_evidence
    g = tmp_path/'g.png'; n = tmp_path/'n.png'
    Image.new('RGB', (100, 80), 'white').save(g)
    Image.new('RGB', (100, 80), 'blue').save(n)
    record = build_windows(g, n, [{'id': 'detail',
        'generated_region': [10, 10, 10, 10], 'native_region': [10, 10, 10, 10],
        'marks': [{'side': 'native', 'bbox': [1, 1, 5, 5],
                   'kind': 'checked', 'label': 'detail'}]}], tmp_path/'review')[0]
    manifest = tmp_path/'review/windows.json'
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    check = {**record, 'window_id': 'detail', 'window_manifest_path': str(manifest),
             'window_manifest_sha256': digest(manifest)}
    with pytest.raises(ValueError, match='complete frozen module'):
        _check_window_evidence(check, digest(g), digest(n), [0, 0, 40, 40], [100, 80])
    _check_window_evidence(check, digest(g), digest(n), [10, 10, 10, 10], [100, 80])


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

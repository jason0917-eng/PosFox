"""V3 keeps the generated design roster independent of native reconstruction."""
import json
import pytest
from posfoxgen.state import init_run,accept_stage
from test_v2_state import image_ready,write,final_ready_v2


def test_v3_profile_is_supported(tmp_path):
    paper=tmp_path/'paper.pdf';paper.write_bytes(b'paper')
    assert init_run(tmp_path/'v3',paper,profile='posfoxgen-v3')['profile']=='posfoxgen-v3'


def test_v3_image_gate_requires_geometry_before_roster_freeze(tmp_path):
    root,paths,*_=image_ready(tmp_path)
    run=json.loads((root/'run.json').read_text());run['profile']='posfoxgen-v3';write(root/'run.json',run)
    with pytest.raises(ValueError,match='missing_source_geometry'):
        accept_stage(root,'image_reviewed',{k:paths[k] for k in ('image','generation_handoff')},paths['image_review'])


def test_v3_final_gate_cannot_accept_a_manifest_without_frozen_roster(tmp_path):
    root,paths,artifacts,review=final_ready_v2(tmp_path)
    run=json.loads((root/'run.json').read_text());run['profile']='posfoxgen-v3';write(root/'run.json',run)
    with pytest.raises(ValueError,match='design_roster'):
        accept_stage(root,'finalized',artifacts,review)


def test_v3_image_gate_accepts_real_geometry_and_freezes_roster(tmp_path):
    from test_v2_state import inputs,approve_logic,file_hash
    from posfoxgen.logic import canonical_hash
    from PIL import Image
    root,paths,p,m,e=inputs(tmp_path)
    run=json.loads((root/'run.json').read_text());run['profile']='posfoxgen-v3';write(root/'run.json',run)
    a=json.loads(paths['asset_table'].read_text());asset=next(a for a in a['assets'] if a['id']=='fig1');asset.update(width=180,height=120)
    write(paths['asset_table'],a);accept_stage(root,'assets',{'asset_table':paths['asset_table']})
    lr=json.loads(paths['logic_review'].read_text());lr['input_hashes']['asset_table']=canonical_hash(a);write(paths['logic_review'],lr)
    h=json.loads(paths['generation_handoff'].read_text());h['image_slots'][0].update(source_geometry=[{'asset_id':'fig1','sha256':asset['sha256'],'pixel_size':[180,120],'aspect_ratio':1.5}],planned_frame=[5,50,180,120],geometry_policy='preserve_source_aspect');write(paths['generation_handoff'],h)
    approve_logic(root,paths)
    image=root/'generated.png';Image.new('RGB',(200,200),'white').save(image)
    roster={'generated_image_sha256':file_hash(image),'canvas':[200,200],'modules':[{'id':'method','native_panel_ids':['method'],'region':[0,0,200,200],'area_ratio':1.0,'area_tolerance':.02,'frame_tolerance':.02,'background':'#ffffff','text_area_ratio':.3,'text_area_tolerance':.03,'text_measurement':'Manual paired text rectangles','features':[{'id':'diagram','kind':'image','count':1,'native_object_ids':['method-diagram']}]}]}
    rp=write(root/'design_roster.json',roster)
    review={'reviewer':'reconstructor','independent':False,'review_mode':'reconstruction_intake','decision':'pass','findings':[],'blockers':[],'all_planned_visuals_drawn':True,'checked_image_slot_ids':['diagram'],'input_hashes':{'image':file_hash(image),'logic_plan':file_hash(paths['logic_plan']),'panel_plan':file_hash(paths['panel_plan'])}}
    receipt=accept_stage(root,'image_reviewed',{'image':image,'generation_handoff':paths['generation_handoff'],'design_roster':rp},write(root/'image_review.json',review))
    assert receipt['artifact_hashes']['design_roster']['sha256']==file_hash(rp)

import copy
from posfoxgen.design_roster import validate_design_roster


def roster():
 return {'generated_image_sha256':'source','canvas':[200,200],'modules':[{'id':'p','native_panel_ids':['p'],'region':[0,0,200,200],'area_ratio':1.,'area_tolerance':.02,'frame_tolerance':[.001,.002,.003,.004],'background':'#ffffff','text_area_ratio':.3,'text_area_tolerance':.03,'text_measurement':'manual reference text rectangles','features':[{'id':'no-bullets','kind':'bullet','count':0,'native_object_ids':[]}]}]}


def test_source_frozen_per_axis_tolerances_and_explicit_zero_occurrences_are_valid():
 assert validate_design_roster(roster())==[]


def test_bad_tolerance_vector_or_missing_required_occurrence_stays_invalid():
 r=roster();r['modules'][0]['frame_tolerance']=[.01,float('nan'),.01,.01]
 assert validate_design_roster(r)
 r=roster();r['modules'][0]['features'][0]['count']=1
 assert validate_design_roster(r)

"""Frozen generated-design coverage checks; pixel observations remain Harness work."""
import math
import hashlib
import json
from PIL import Image
from pathlib import Path


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_design_roster(roster, exported=None, review=None, *, native_image_sha256=None):
    """Compare native output to an intake roster, not a post-hoc native inventory.

    Module/text area tolerances come from the frozen design, not universal poster
    density targets. Source-image contain fitting never exempts other features.
    Text-area/color observations are declarations backed by inspected windows;
    this deterministic function cannot perform OCR or infer missing orange dots.
    """
    blockers = []
    def block(code, message): blockers.append({'code': code, 'message': message})
    if not isinstance(roster, dict):
        return [{'code':'missing_design_roster','message':'Freeze the generated design roster before reconstruction'}]
    canvas = roster.get('canvas', [])
    if not isinstance(canvas, list) or len(canvas) != 2 or not all(_number(n) and n > 0 for n in canvas):
        return [{'code':'invalid_design_roster','message':'Roster needs measured canvas width and height'}]
    modules = roster.get('modules', [])
    if not isinstance(modules, list) or not modules:
        return [{'code':'invalid_design_roster','message':'Roster must enumerate the actual generated modules'}]
    if not roster.get('generated_image_sha256'):
        block('invalid_design_roster','Roster must bind the actual generated image')
    seen, feature_ids, used_panels, used_objects = set(), set(), set(), set()
    native = {p['id']: p for p in exported.get('panels', [])} if exported is not None else None
    checks = {c.get('module_id'):c for c in review.get('roster_checks', [])} if isinstance(review, dict) else {}
    for module in modules:
        if not isinstance(module, dict):
            block('invalid_design_roster','Each module must be an object'); continue
        mid=module.get('id');region=module.get('region',[])
        if not mid or mid in seen:
            block('invalid_design_roster','Module IDs must be unique')
        seen.add(mid)
        valid_region=isinstance(region,list) and len(region)==4 and all(_number(n) for n in region) and all(n>0 for n in region[2:])
        if not valid_region or not module.get('native_panel_ids') or not module.get('background'):
            block('invalid_design_roster',f'{mid}: measured region, background and panel correspondence required'); continue
        if region[0]<0 or region[1]<0 or region[0]+region[2]>canvas[0] or region[1]+region[3]>canvas[1]:
            block('invalid_design_roster',f'{mid}: reference region outside canvas')
        ratio=region[2]*region[3]/(canvas[0]*canvas[1])
        if not _number(module.get('area_ratio')) or not math.isclose(ratio,module['area_ratio'],abs_tol=1e-6):
            block('invalid_design_roster',f'{mid}: area ratio must match measured region')
        for key in ('area_tolerance','frame_tolerance','text_area_ratio','text_area_tolerance'):
            if not _number(module.get(key)) or not 0<=module[key]<=1:
                block('invalid_design_roster',f'{mid}: {key} must be a frozen finite proportion')
        if not module.get('text_measurement') or not isinstance(module.get('features'),list) or not module['features']:
            block('invalid_design_roster',f'{mid}: comparable text measurement and visual features required');continue
        ids = module['native_panel_ids']
        if not isinstance(ids,list) or not all(isinstance(i,str) for i in ids):
            block('invalid_design_roster',f'{mid}: native_panel_ids must be a list of stable strings');continue
        if len(set(ids))!=len(ids) or used_panels.intersection(ids):
            block('roster_occurrence_reused',f'{mid}: each generated module needs a distinct native occurrence')
        used_panels.update(ids)
        selected=[];objects={} 
        if native is not None:
            if any(pid not in native for pid in module['native_panel_ids']):
                block('roster_module_omitted',f'{mid}: generated module missing from native output'); continue
            selected=[native[pid] for pid in module['native_panel_ids']]
            objects={o['id']:o for p in selected for o in p.get('objects',[])}
            if all(all(_number(p.get(k)) for k in ('x','y','width','height')) for p in selected) and all(_number(exported.get(k)) and exported[k]>0 for k in ('width','height')):
                x=min(p['x'] for p in selected);y=min(p['y'] for p in selected)
                width=max(p['x']+p['width'] for p in selected)-x;height=max(p['y']+p['height'] for p in selected)-y
                expected_frame=[region[0]/canvas[0],region[1]/canvas[1],region[2]/canvas[0],region[3]/canvas[1]]
                actual_frame=[x/exported['width'],y/exported['height'],width/exported['width'],height/exported['height']]
                if _number(module.get('frame_tolerance')) and any(abs(a-b)>module['frame_tolerance'] for a,b in zip(expected_frame,actual_frame)):
                    block('roster_frame_mismatch',f'{mid}: native module position/order/shape differs from frozen design')
                actual=width*height/(exported['width']*exported['height'])
                if _number(module.get('area_tolerance')) and abs(actual-ratio)>module['area_tolerance']:
                    block('roster_area_mismatch',f'{mid}: native module area differs from frozen design')
            else: block('roster_area_mismatch',f'{mid}: native module geometry unavailable')
            if any(p.get('background',exported.get('background'))!=module['background'] for p in selected):
                block('roster_color_mismatch',f'{mid}: module background changed')
        check=checks.get(mid,{})
        observations={c.get('feature_id'):c for c in check.get('feature_checks',[])}
        for feature in module.get('features',[]):
            if not isinstance(feature,dict):
                block('invalid_design_roster',f'{mid}: each feature must be an object');continue
            fid=feature.get('id');ids=feature.get('native_object_ids',[]);count=feature.get('count')
            if not fid or fid in feature_ids or not feature.get('kind') or not isinstance(count,int) or isinstance(count,bool) or count<1 or not isinstance(ids,list) or not all(isinstance(i,str) for i in ids) or len(set(ids))!=count:
                block('invalid_design_roster',f'{mid}: enumerate each feature occurrence with stable unique native IDs'); continue
            feature_ids.add(fid)
            if used_objects.intersection(ids):
                block('roster_occurrence_reused',f'{mid}/{fid}: a native occurrence cannot satisfy multiple generated features')
            used_objects.update(ids)
            if native is None: continue
            if any(oid not in objects for oid in ids):
                block('roster_feature_omitted',f'{mid}/{fid}: required native feature missing')
            color=feature.get('color')
            if color and any(color not in {objects[oid].get(k) for k in ('fill','stroke','color')} for oid in ids if oid in objects):
                block('roster_color_mismatch',f'{mid}/{fid}: required feature color changed')
            obs=observations.get(fid,{})
            if obs.get('count_observed')!=count or (color and obs.get('color_observed')!=color):
                block('roster_feature_observation_required',f'{mid}/{fid}: visual count/color not verified')
        if native is None: continue
        if check.get('background_observed')!=module['background']:
            block('roster_color_mismatch',f'{mid}: rendered background differs or was not inspected')
        area=check.get('text_area_ratio_observed')
        if not _number(area) or not 0<=area<=1 or not _number(module.get('text_area_tolerance')) or not _number(module.get('text_area_ratio')) or abs(area-module['text_area_ratio'])>module['text_area_tolerance']:
            block('roster_text_area_mismatch',f'{mid}: rendered text proportion differs or was not measured')
        if not check.get('assessment'):
            block('roster_window_evidence_required',f'{mid}: actual paired-window assessment required')
        try:
            _check_window_evidence(check,roster.get('generated_image_sha256'),native_image_sha256,region,canvas)
        except (KeyError,ValueError,TypeError,AssertionError,OSError,json.JSONDecodeError) as exc:
            block('roster_window_evidence_required',f'{mid}: {exc}')
    return blockers


def _check_window_evidence(check,generated_hash,native_hash,module_region=None,canvas=None):
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=Path(check['window_manifest_path']).resolve(strict=True)
    if digest(manifest)!=check['window_manifest_sha256']:
        raise ValueError('window manifest hash changed')
    data=json.loads(manifest.read_text());window=next((w for w in data['windows'] if w['id']==check['window_id']),None)
    if window is None:raise ValueError('reviewed window absent from source-bound manifest')
    sources=[]
    for role,expected in [('generated',generated_hash),('native',native_hash)]:
        path=Path(data[role]).resolve(strict=True);sources.append(path)
        if not expected or digest(path)!=expected or data['input_sha256'].get(str(path))!=expected:
            raise ValueError('paired window source hash mismatch')
    paths=[];dimensions=[];hashes=[]
    for key,hashkey in [('paired_window_path','paired_window_sha256'),('redline_path','redline_sha256')]:
        path=Path(check[key]).resolve(strict=True)
        if path in sources or path!=Path(window[key]).resolve(strict=True):raise ValueError('require separate actual paired/marked images')
        h=digest(path)
        if h!=window[hashkey]:raise ValueError('paired/marked image hash changed')
        with Image.open(path) as image:dimensions.append(image.size);image.verify()
        paths.append(path);hashes.append(h)
    if paths[0]==paths[1] or hashes[0]==hashes[1] or dimensions[0]!=dimensions[1]:
        raise ValueError('clean pair and redline must be distinct same-sized images')
    a,b=window['generated_region'],window['native_region']
    if module_region is not None:
        # Compare in normalized canvas coordinates, allowing different render DPI.
        for path, bounds in zip(sources, (a, b)):
            with Image.open(path) as source:
                sw, sh = source.size
            if not isinstance(bounds, list) or len(bounds) != 4 or not all(_number(v) for v in bounds):
                raise ValueError('invalid window bounds')
            x,y,w,h=bounds
            mx,my,mw,mh=module_region
            if min(x,y)<0 or min(w,h)<=0 or x+w>sw or y+h>sh:
                raise ValueError('window outside source')
            if (x/sw > mx/canvas[0] or y/sh > my/canvas[1]
                    or (x+w)/sw < (mx+mw)/canvas[0]
                    or (y+h)/sh < (my+mh)/canvas[1]):
                raise ValueError('window must cover the complete frozen module on both sides')
    expected_width=round(a[0]+a[2])-round(a[0])+round(b[0]+b[2])-round(b[0])
    expected_height=max(round(a[1]+a[3])-round(a[1]),round(b[1]+b[3])-round(b[1]))
    if dimensions[0]!=(expected_width,expected_height):
        raise ValueError('paired image size differs from recorded semantic windows')

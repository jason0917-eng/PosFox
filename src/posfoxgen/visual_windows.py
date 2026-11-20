"""Build paired semantic crops and separate red-pen inspection overlays.

The Harness supplies inspected regions/marks; this tool never detects defects.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from PIL import Image, ImageDraw


def plan_windows(roster, *, context=0.15):
    """Plan full-module context crops; both renders must use the roster canvas.

    Semantic overlap follows module bounds, not a grid. Optional feature regions
    are absolute canvas coordinates, and receive their own detail windows.
    Marks remain empty until a reviewer actually inspects the image pair.
    """
    width, height = roster['canvas']
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError('positive finite canvas required')
    if not isinstance(context, (int, float)) or isinstance(context, bool) or not math.isfinite(context) or not 0 <= context <= 1:
        raise ValueError('context must be between zero and one')
    result = [{'id': 'overview', 'generated_region': [0, 0, width, height],
               'native_region': [0, 0, width, height], 'marks': []}]
    def add(region, module_id, feature_id=None):
        if not isinstance(region, list) or len(region) != 4 or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in region
        ):
            raise ValueError('finite region required')
        x, y, w, h = region
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
            raise ValueError('region outside canvas')
        left, top = max(0, math.floor(x-w*context)), max(0, math.floor(y-h*context))
        right, bottom = min(width, math.ceil(x+w+w*context)), min(height, math.ceil(y+h+h*context))
        bounds = [left, top, right-left, bottom-top]
        result.append({'id': f'window-{len(result)}', 'module_id': module_id,
                       'feature_id': feature_id, 'generated_region': bounds,
                       'native_region': list(bounds), 'marks': []})
    for module in roster['modules']:
        add(module['region'], module['id'])
        for feature in module.get('features', []):
            if 'region' in feature:
                add(feature['region'], module['id'], feature['id'])
    return result


def build_windows(generated, native, windows, out_dir):
    generated=Path(generated).resolve();native=Path(native).resolve();out=Path(out_dir).resolve()
    sources={generated,native};out.mkdir(parents=True,exist_ok=True)
    g=Image.open(generated).convert('RGB');n=Image.open(native).convert('RGB')
    records=[];seen=set()
    def crop(image,region):
        if not isinstance(region,list) or len(region)!=4 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in region):
            raise ValueError('window bounds need finite x,y,width,height')
        x,y,w,h=region
        if min(x,y)<0 or min(w,h)<=0 or x+w>image.width or y+h>image.height:
            raise ValueError('window bounds outside image; do not clip away context')
        return image.crop((round(x),round(y),round(x+w),round(y+h)))
    for window in windows:
        name=window.get('id','')
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_.-]*',name) or name in seen:
            raise ValueError('unique stable window id required')
        seen.add(name)
        a=crop(g,window['generated_region']);b=crop(n,window['native_region'])
        # Equal pixel scale for the two windows; users choose common-scale inputs.
        pair=Image.new('RGB',(a.width+b.width,max(a.height,b.height)),'white')
        pair.paste(a,(0,0));pair.paste(b,(a.width,0));redline=pair.copy();draw=ImageDraw.Draw(redline)
        for mark in window.get('marks',[]):
            side=mark.get('side');image=a if side=='generated' else b
            if side not in {'generated','native'} or mark.get('kind') not in {'issue','checked'} or not mark.get('label'):
                raise ValueError('mark needs generated/native side, issue/checked kind and actual observation label')
            region=mark.get('bbox',[]);crop(image,region)
            x,y,w,h=region;offset=0 if side=='generated' else a.width
            draw.rectangle((offset+x,y,offset+x+w-1,y+h-1),outline=(220,35,35),width=2)
            draw.text((offset+x,max(0,y-12)),mark['kind']+': '+mark['label'],fill=(220,35,35))
        paired=out/(name+'-paired.png');annotated=out/(name+'-redline.png')
        if paired in sources or annotated in sources:raise ValueError('cannot overwrite source images')
        pair.save(paired);redline.save(annotated)
        records.append({**window,'paired_window_path':str(paired),'redline_path':str(annotated),'paired_window_sha256':hashlib.sha256(paired.read_bytes()).hexdigest(),'redline_sha256':hashlib.sha256(annotated.read_bytes()).hexdigest()})
    manifest=out/'windows.json'
    if manifest in sources:raise ValueError('cannot overwrite source images')
    manifest.write_text(json.dumps({'generated':str(generated),'native':str(native),'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'pixel_judgment':'Harness-supplied marks; deterministic crops are not a review','windows':records},indent=2)+'\n')
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('generated','native','windows','out'):parser.add_argument('--'+key,required=True)
    args=parser.parse_args();print(json.dumps(build_windows(args.generated,args.native,json.loads(Path(args.windows).read_text()),args.out),indent=2))


if __name__=='__main__':main()

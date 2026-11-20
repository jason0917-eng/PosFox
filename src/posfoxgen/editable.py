"""Build a source-backed editable HTML poster from a Harness-authored spec."""
from __future__ import annotations
import argparse
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
from .fonts import family_list, font_declarations, resolve_font, wrap_lines


def _number(value, positive=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or (value<=0 if positive else value<0):
        raise ValueError('geometry must be finite and '+('positive' if positive else 'nonnegative'))
    return value


def _colour(value):
    if not re.fullmatch(r'#[a-fA-F0-9]{3}(?:[a-fA-F0-9]{3})?',value):raise ValueError('colour must be hexadecimal')
    return value


def _safe_svg(svg):
    try:root=ET.fromstring(svg)
    except ET.ParseError as exc:raise ValueError('invalid SVG') from exc
    if root.tag.rsplit('}',1)[-1]!='svg':raise ValueError('SVG root required')
    paints={n.get('id') for n in root.iter() if n.tag.rsplit('}',1)[-1] in {'linearGradient','radialGradient'} and n.get('id')}
    for node in root.iter():
        if node.tag.rsplit('}',1)[-1] in {'script','foreignObject','iframe','image','use','style'}:raise ValueError('active or external SVG content forbidden')
        for k,v in node.attrib.items():
            if k.lower().startswith('on') or 'href' in k.lower() or 'javascript:' in v.lower():raise ValueError('active SVG reference forbidden')
            if 'url(' in v.lower():
                local=re.fullmatch(r'url\(#([A-Za-z][\w.-]*)\)',v)
                if k not in {'fill','stroke'} or not local or local.group(1) not in paints:raise ValueError('active SVG reference forbidden')
    return svg


def _paint(value, default='none'):
    return 'none' if value is None or value=='none' else _colour(value or default)


def _text_style(obj):
    fs=_number(obj.get('font_size',24),True);colour=_colour(obj.get('color','#17232b'))
    family=obj.get('font_family','Arial, sans-serif');family_list(family)
    weight=obj.get('font_weight',400)
    if weight not in {400,500,600,700,800,900}:raise ValueError('invalid font weight')
    font_style=obj.get('font_style','normal')
    if font_style not in {'normal','italic'}:raise ValueError('invalid font style')
    align=obj.get('align','left')
    if align not in {'left','center','right','justify'}:raise ValueError('invalid text alignment')
    lh=obj.get('line_height',1.25)
    if isinstance(lh,bool) or not isinstance(lh,(int,float)) or not .8<=lh<=3:raise ValueError('invalid line height')
    return f'font-size:{fs}px;color:{colour};font-family:{family};font-weight:{weight};font-style:{font_style};line-height:{lh};text-align:{align};'


def _emphasis_runs(obj):
    """Return exact text segments; emphasis adds style, never scientific text."""
    text=obj.get('text','');requests=obj.get('emphasis',[])
    if not isinstance(requests,list):raise ValueError('emphasis must be a list of exact-text requests')
    intervals=[]
    for item in requests:
        if not isinstance(item,dict) or set(item)!={'text','font_weight'} or not isinstance(item.get('text'),str) or not item['text'] or type(item.get('font_weight')) is not int or item.get('font_weight') not in {500,600,700,800,900}:raise ValueError('emphasis supports exact text and font_weight 500–900')
        phrase=item['text'];start=0;found=False
        while True:
            index=text.find(phrase,start)
            if index<0:break
            found=True;intervals.append((index,index+len(phrase),item['font_weight']));start=index+len(phrase)
        if not found:raise ValueError('emphasis text does not match the paragraph')
    intervals.sort()
    if any(intervals[i][0]<intervals[i-1][1] for i in range(1,len(intervals))):raise ValueError('emphasis requests overlap')
    runs=[];offset=0;normal=obj.get('font_weight',400)
    for start,end,weight in intervals:
        if start>offset:runs.append((text[offset:start],normal,False))
        runs.append((text[start:end],weight,True));offset=end
    if offset<len(text) or not runs:runs.append((text[offset:],normal,False))
    return runs


def _emphasis_lines(obj,width,declarations):
    """Wrap native SVG using the actual regular/bold font for each run."""
    from .fonts import measurement_font
    runs=_emphasis_runs(obj);text=obj.get('text','');weights=[];marks=[];fonts={}
    for value,weight,marked in runs:
        weights.extend([weight]*len(value));marks.extend([marked]*len(value))
        if weight not in fonts:fonts[weight]=measurement_font({**obj,'font_weight':weight},declarations)
    def sliced(start,end):
        result=[];cursor=start
        while cursor<end:
            finish=cursor+1
            while finish<end and weights[finish]==weights[cursor] and marks[finish]==marks[cursor]:finish+=1
            result.append((text[cursor:finish],weights[cursor],marks[cursor]));cursor=finish
        return result or [('',obj.get('font_weight',400),False)]
    def measured(start,end):
        return sum(fonts[weight][0].getlength(value)/fonts[weight][1] for value,weight,_ in sliced(start,end))
    lines=[];offset=0
    for paragraph in text.split('\n'):
        line_start=offset;previous_end=None
        for word in re.finditer(r'\S+',paragraph):
            end=offset+word.end()
            if previous_end is not None and measured(line_start,end)>width:
                lines.append(sliced(line_start,previous_end));line_start=offset+word.start()
            previous_end=end
        lines.append(sliced(line_start,offset+len(paragraph)));offset+=len(paragraph)+1
    return lines

def _table_layout(obj):
    rows=obj.get('rows')
    if not isinstance(rows,list) or not rows or not isinstance(rows[0],list) or not rows[0]:raise ValueError('table rows must be a nonempty rectangular list')
    count=len(rows[0])
    if any(not isinstance(row,list) or len(row)!=count or any(not isinstance(v,(str,int,float)) or isinstance(v,bool) for v in row) for row in rows):raise ValueError('table rows must be rectangular scalar values')
    columns=obj.get('column_widths',[obj['width']/count]*count);heights=obj.get('row_heights',[obj['height']/len(rows)]*len(rows))
    if len(columns)!=count or any(_number(v,True)<=0 for v in columns) or abs(sum(columns)-obj['width'])>.01:raise ValueError('column_widths must match the table width')
    if len(heights)!=len(rows) or any(_number(v,True)<=0 for v in heights) or abs(sum(heights)-obj['height'])>.01:raise ValueError('row_heights must match the table height')
    padding=_number(obj.get('padding',8));stroke=_number(obj.get('stroke_width',1))
    header=obj.get('header_rows',1)
    if isinstance(header,bool) or not isinstance(header,int) or not 0<=header<=len(rows):raise ValueError('invalid header_rows')
    if min(columns)<=padding*2+stroke or min(heights)<=padding*2+stroke:raise ValueError('table padding leaves no text space')
    _text_style(obj)
    row_weights=obj.get('row_font_weights',[700 if ri<header else obj.get('font_weight',400) for ri in range(len(rows))])
    if not isinstance(row_weights,list) or len(row_weights)!=len(rows) or any(isinstance(w,bool) or not isinstance(w,int) or w not in {400,500,600,700,800,900} for w in row_weights):raise ValueError('row_font_weights must contain one valid font weight per row')
    column_aligns=obj.get('column_aligns',[obj.get('align','left')]*count)
    if not isinstance(column_aligns,list) or len(column_aligns)!=count or any(a not in ('left','center','right','justify') for a in column_aligns):raise ValueError('column_aligns must contain one valid alignment per column')
    row_fills=obj.get('row_fills',[obj.get('header_fill',obj.get('fill')) if ri<header else obj.get('fill') for ri in range(len(rows))])
    if not isinstance(row_fills,list) or len(row_fills)!=len(rows):raise ValueError('row_fills must contain one fill per row')
    try:row_fills=[_paint(fill) for fill in row_fills]
    except (ValueError,TypeError) as exc:raise ValueError('row_fills must contain hexadecimal colours or none') from exc
    return rows,columns,heights,padding,stroke,header,row_weights,column_aligns,row_fills


def _shape(obj):
    stroke=_paint(obj.get('stroke','#17232b'));sw=_number(obj.get('stroke_width',1))
    if obj['type']=='rect':
        return 'rect',{'x':0,'y':0,'width':obj['width'],'height':obj['height'],'rx':_number(obj.get('radius',0)),'fill':_paint(obj.get('fill')),'stroke':stroke,'stroke-width':sw}
    coords={k:_number(obj.get(k,d)) for k,d in [('x1',0),('y1',0),('x2',obj['width']),('y2',obj['height'])]}
    if max(coords['x1'],coords['x2'])>obj['width'] or max(coords['y1'],coords['y2'])>obj['height']:raise ValueError('line endpoints outside object bounds')
    return 'line',{**coords,'stroke':stroke,'stroke-width':sw,'stroke-linecap':obj.get('linecap','butt')}


def _image_contract(obj,asset,path,panel,spec,asset_table):
    from PIL import Image,ImageColor
    if any(k in obj for k in ('crop','clip','clip_path')):raise ValueError('object cropping is forbidden; use an independently verified source crop asset')
    fit=obj.get('fit','contain')
    if fit not in {'contain','scale-down'}:raise ValueError('image distortion/cropping is forbidden; use contain (scale-down) and adjust the layout')
    fit='scale-down'
    position=obj.get('position','center')
    if position not in {'center','top','bottom','left','right','top left','top right','bottom left','bottom right'}:raise ValueError('invalid image position')
    background=_colour(obj.get('background',panel.get('background',spec.get('background','#ffffff'))))
    with Image.open(path) as opened:
        image=opened.convert('RGBA');iw,ih=image.size
        corners=[image.getpixel((x,y)) for x,y in [(0,0),(iw-1,0),(0,ih-1),(iw-1,ih-1)]]
    transparent=all(c[3]<8 for c in corners);opaque=all(c[3]>247 for c in corners)
    uniform=all(max(abs(a-b) for a,b in zip(c[:3],corners[0][:3]))<=8 for c in corners)
    mismatch=opaque and uniform and max(abs(a-b) for a,b in zip(corners[0][:3],ImageColor.getrgb(background)))>8
    policy=obj.get('background_policy','unspecified')
    if policy not in {'unspecified','preserve','match','transparent'}:raise ValueError('invalid background_policy')
    if policy=='match' and not (transparent or (opaque and uniform and not mismatch)):raise ValueError('image background does not match its destination; no pixels were modified')
    if policy=='transparent' and not transparent:raise ValueError('image background is not transparent at its corners')
    if spec.get('image_policy',{}).get('require_background_decision') and mismatch and policy=='unspecified':raise ValueError('image background requires an explicit preserve/match/transparent decision')
    w=obj['width'];h=obj['height'];factor=min(1,w/iw,h/ih);display=[iw*factor,ih*factor]
    ratio=[iw/display[0],ih/display[1]];warnings=[]
    if mismatch:warnings.append({'code':'image_background_mismatch','object_id':obj['id'],'explicitly_preserved':policy=='preserve','message':'Opaque uniform source corners differ from the poster background; original pixels are preserved.'})
    if min(ratio)<spec.get('image_policy',{}).get('min_pixels_per_css_pixel',1):warnings.append({'code':'image_resolution_below_display','object_id':obj['id'],'message':'Raster pixels are fewer than planned display pixels; obtain a higher resolution source crop.'})
    bbox=asset.get('bbox');crop_dpi=None;bounds_check='not_available'
    if bbox and len(bbox)==4:
        if bbox[2]>bbox[0] and bbox[3]>bbox[1]:crop_dpi=[iw/(bbox[2]-bbox[0])*72,ih/(bbox[3]-bbox[1])*72]
        page=next((p for p in asset_table.get('pages',[]) if p.get('page')==asset.get('page')),None)
        if page:
            complete=0<=bbox[0]<bbox[2]<=page['width'] and 0<=bbox[1]<bbox[3]<=page['height'];bounds_check='within_page' if complete else 'outside_page'
            if not complete:warnings.append({'code':'source_crop_outside_page','object_id':obj['id']})
    print_width=spec.get('print',{}).get('width_inches');print_height=spec.get('print',{}).get('height_inches');print_dpi=None
    if print_width and print_height:
        _number(print_width,True);_number(print_height,True)
        print_dpi=[iw/(display[0]/spec['width']*print_width),ih/(display[1]/spec['height']*print_height)]
    return {'object_id':obj['id'],'asset_id':asset['id'],'fit':fit,'position':position,'distortion_explicit':False,'native_pixels':[iw,ih],'display_pixels':display,'pixels_per_display_pixel':ratio,'planned_print_dpi':print_dpi,'source_crop_dpi':crop_dpi,'source_bbox':bbox,'source_bounds_check':bounds_check,'semantic_crop_complete':None,'background_policy':policy,'destination_background':background,'source_corner_rgba':corners,'source_sha256':asset['sha256'],'warnings':warnings}

def build_poster(spec, asset_table, out_dir):
    """Render a structured spec to editable HTML; native text is never flattened."""
    if isinstance(spec,(str,Path)):spec=json.loads(Path(spec).read_text())
    if isinstance(asset_table,(str,Path)):
        source=Path(asset_table).resolve();asset_table=json.loads(source.read_text());asset_table.setdefault('root',str(source.parent))
    out=Path(out_dir).resolve();root=Path(asset_table.get('root','.')).resolve()
    assets={a['id']:a for a in asset_table.get('assets',[])}
    if len(assets)!=len(asset_table.get('assets',[])):raise ValueError('duplicate asset id')
    width=_number(spec['width'],True);height=_number(spec['height'],True)
    ids=set();html=[];required_images={}
    declarations,font_css=font_declarations(spec);font_reports=[];image_reports=[];warnings=[]
    def font_contract(obj):
        resolved=resolve_font(obj.get('font_family','Arial, sans-serif'),obj.get('font_weight',400),obj.get('font_style','normal'),declarations)
        resolved={**resolved,'object_id':obj['id']}
        strict=spec.get('font_policy',{}).get('require_available',False)
        if strict and (not resolved['available'] or resolved.get('fallback_used')):raise ValueError('requested font unavailable: '+resolved['requested_family'])
        if not resolved['available'] or resolved.get('fallback_used'):warnings.append({'code':'font_fallback','object_id':obj['id'],'requested':resolved['requested_family'],'resolved':resolved['resolved_family']})
        font_reports.append(resolved)
        return f'data-font-family="{escape(resolved["requested_family"],quote=True)}" data-font-available="{str(resolved["available"]).lower()}" data-font-required="{str(bool(strict)).lower()}" data-font-embedded="{str(resolved.get("embedded",False)).lower()}" data-font-declared="{str(resolved.get("font_face_declared",False)).lower()}"'
    def identity(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z][\w.-]*',value):raise ValueError('invalid object id')
        if value in ids:raise ValueError('duplicate object id: '+value)
        ids.add(value);return value
    def box(obj,parent_width,parent_height):
        x=_number(obj.get('x',0));y=_number(obj.get('y',0));w=_number(obj['width'],True);h=_number(obj['height'],True)
        if x+w>parent_width+.01 or y+h>parent_height+.01:raise ValueError('object geometry outside parent bounds')
        return x,y,w,h
    def style_box(values):
        x,y,w,h=values;return f'left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
    for panel in spec.get('panels',[]):
        pid=identity(panel['id']);pbox=box(panel,width,height)
        panel_style=style_box(pbox)
        if panel.get('background'):panel_style+='background:'+_colour(panel['background'])+';'
        html.append(f'<section id="{pid}" class="panel" data-panel-id="{pid}" style="{panel_style}" aria-label="{escape(panel.get("title",pid),quote=True)}">')
        for obj in panel.get('objects',[]):
            oid=identity(obj['id']);bounds=box(obj,pbox[2],pbox[3]);kind=obj['type']
            source_ids=obj.get('source_ids',[])
            if any(i not in assets for i in source_ids):raise ValueError('text/SVG source asset does not exist')
            evidence=escape(json.dumps(source_ids),quote=True)
            common=f'id="{oid}" class="object" data-object-type="{kind}" data-source-ids="{evidence}"'
            style=style_box(bounds)
            if kind=='text':
                style+=_text_style(obj)
                font_attributes=font_contract(obj)
                if obj.get('background'):style+='background:'+_colour(obj['background'])+';'
                text_runs=_emphasis_runs(obj)
                content=''.join(f'<span data-emphasis="{weight}" style="font-weight:{weight}">{escape(value)}</span>' if marked else escape(value) for value,weight,marked in text_runs)
                html.append(f'<div {common} {font_attributes} contenteditable="true" spellcheck="false" style="{escape(style,quote=True)}">{content}</div>')
            elif kind=='image':
                aid=obj.get('asset_id');asset=assets.get(aid)
                if not asset or asset.get('type') not in {'figure','table'} or not asset.get('path'):raise ValueError('image asset must reference an extracted source figure or table')
                if asset.get('source_kind')=='generated' or asset.get('role') in {'poster_layout','generated_poster'}:raise ValueError('generated poster image cannot replace editable objects')
                image_path=(root/asset['path']).resolve()
                if not image_path.is_relative_to(root) or not image_path.is_file():raise ValueError('asset path escapes source root or is missing')
                digest=hashlib.sha256(image_path.read_bytes()).hexdigest()
                if not asset.get('sha256') or asset['sha256']!=digest:raise ValueError('source asset hash mismatch: '+aid)
                ext=image_path.suffix.lower();dest=f'assets/{aid}{ext}';required_images[dest]=image_path
                contract=_image_contract(obj,asset,image_path,panel,spec,asset_table);image_reports.append(contract);warnings.extend(contract['warnings'])
                fit=contract['fit'];style+=f'object-fit:{fit};object-position:{contract["position"]};'
                if obj.get('background'):style+='background:'+_colour(obj['background'])+';'
                html.append(f'<img {common} data-asset-id="{escape(aid,quote=True)}" data-source-sha256="{digest}" data-image-fit="{fit}" data-distortion-explicit="{str(contract["distortion_explicit"]).lower()}" data-background-policy="{contract["background_policy"]}" src="{escape(dest,quote=True)}" alt="{escape(obj.get("alt",asset.get("caption",aid)),quote=True)}" style="{escape(style,quote=True)}">')
            elif kind in {'rect','line'}:
                tag,attrs=_shape(obj)
                if tag=='line' and attrs['stroke-linecap'] not in {'butt','round','square'}:raise ValueError('invalid linecap')
                markup=' '.join(f'{k}="{escape(str(v),quote=True)}"' for k,v in attrs.items())
                html.append(f'<svg xmlns="http://www.w3.org/2000/svg" {common} style="{style}overflow:visible" viewBox="0 0 {bounds[2]} {bounds[3]}"><{tag} {markup}/></svg>')
            elif kind=='table':
                rows,columns,heights,padding,stroke,header,row_weights,column_aligns,row_fills=_table_layout(obj)
                font_attributes=font_contract(obj);_text_style(obj)
                header_fill=_paint(obj.get('header_fill',obj.get('fill')));fill=_paint(obj.get('fill'));border=_paint(obj.get('stroke','#17232b'))
                table_style=style+_text_style(obj)+'table-layout:fixed;border-collapse:collapse;border-spacing:0;'
                html.append(f'<table {common} {font_attributes} style="{escape(table_style,quote=True)}"><colgroup>')
                for cw in columns:html.append(f'<col style="width:{cw}px">')
                html.append('</colgroup><tbody>')
                for ri,row in enumerate(rows):
                    html.append(f'<tr style="height:{heights[ri]}px">')
                    for ci,value in enumerate(row):
                        cid=identity(f'{oid}-cell-{ri}-{ci}');identity(cid+'-text');tag='th' if ri<header else 'td';cell_fill=row_fills[ri]
                        cell_style=f'height:{heights[ri]}px;padding:{padding}px;border:{stroke}px solid {border};font-weight:{row_weights[ri]};vertical-align:middle;text-align:{column_aligns[ci]};'
                        if cell_fill!='none':cell_style+='background:'+cell_fill+';'
                        html.append(f'<{tag} id="{cid}" style="{cell_style}"><div id="{cid}-text" data-table-cell="{cid}" contenteditable="true" spellcheck="false" style="height:{heights[ri]-padding*2-stroke}px;white-space:pre-wrap;overflow:visible">{escape(str(value))}</div></{tag}>')
                    html.append('</tr>')
                html.append('</tbody></table>')
            elif kind=='svg':
                html.append(f'<div {common} style="{escape(style,quote=True)}">{_safe_svg(obj["svg"])}</div>')
            else:raise ValueError('unsupported object type: '+str(kind))
        html.append('</section>')
    title=escape(spec.get('title','Scientific poster'));background=_colour(spec.get('background','#ffffff'))
    metadata=json.dumps({'format':'posfoxgen-editable-v1','paper_sha256':asset_table.get('source',{}).get('paper_sha256'),'native_object_count':sum(len(p.get('objects',[])) for p in spec.get('panels',[])),'spec':spec},ensure_ascii=False).replace('<','\\u003c')
    document=f'''<!doctype html><html lang="{escape(spec.get('language','en'),quote=True)}"><head><meta charset="utf-8"><title>{title}</title><style>
{font_css}
*{{box-sizing:border-box}}html,body{{margin:0;padding:0;background:{background}}}#poster{{position:relative;width:{width}px;height:{height}px;overflow:hidden;background:{background};}}.panel,.object{{position:absolute;}}.object[data-object-type="text"]{{white-space:pre-wrap;overflow:visible;outline:none;}}.object[data-object-type="svg"]>svg{{width:100%;height:100%;}}@page{{size:{width}px {height}px;margin:0}}@media print{{body{{print-color-adjust:exact;-webkit-print-color-adjust:exact}}}}
</style></head><body><main id="poster" aria-label="{title}">{''.join(html)}</main><script type="application/json" id="posfoxgen-metadata">{metadata}</script></body></html>'''
    out.mkdir(parents=True,exist_ok=True);(out/'assets').mkdir(exist_ok=True)
    for dest,source in required_images.items():shutil.copy2(source,out/dest)
    (out/'fidelity_report.json').write_text(json.dumps({'format':'posfoxgen-fidelity-v1','fonts':font_reports,'images':image_reports,'warnings':warnings,'scientific_quality_pass':None,'semantic_cropping_automatically_verified':False},ensure_ascii=False,indent=2))
    (out/'poster.html').write_text(document);(out/'poster_spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2))
    return out/'poster.html'


def export_svg(spec, asset_table, out_dir):
    """Export the same native objects as SVG, with source images embedded.

    SVG text remains text/tspan; it is not an HTML foreignObject or screenshot.
    The HTML remains the primary deliverable and browser layout authority.
    """
    import base64
    import mimetypes
    if isinstance(spec,(str,Path)):spec=json.loads(Path(spec).read_text())
    if isinstance(asset_table,(str,Path)):
        path=Path(asset_table).resolve();asset_table=json.loads(path.read_text());asset_table.setdefault('root',str(path.parent))
    build_poster(spec,asset_table,out_dir)
    declarations,font_css=font_declarations(spec)
    ns='http://www.w3.org/2000/svg';ET.register_namespace('',ns)
    def el(tag,parent,attrs):return ET.SubElement(parent,'{'+ns+'}'+tag,{k:str(v) for k,v in attrs.items()})
    width=spec['width'];height=spec['height'];root=ET.Element('{'+ns+'}svg',{'width':str(width),'height':str(height),'viewBox':f'0 0 {width} {height}'})
    if font_css:el('style',root,{}).text=font_css
    el('rect',root,{'id':'poster-background','x':0,'y':0,'width':width,'height':height,'fill':spec.get('background','#ffffff')})
    assets={a['id']:a for a in asset_table.get('assets',[])};asset_root=Path(asset_table.get('root','.'))
    def native_text(parent,obj,common,x,y,w,h=None):
        fs=obj.get('font_size',24);align=obj.get('align','left');anchor='middle' if align=='center' else 'end' if align=='right' else 'start'
        tx=x+w/2 if align=='center' else x+w if align=='right' else x
        measured=obj
        if not resolve_font(obj.get('font_family','Arial, sans-serif'),obj.get('font_weight',400),obj.get('font_style','normal'),declarations)['available']:
            measured={**obj,'font_family':'Arial, sans-serif'}
        styled=bool(obj.get('emphasis'))
        lines=_emphasis_lines(measured,w,declarations) if styled else wrap_lines(obj.get('text',''),measured,w,declarations)
        # Use the actual selected font, not an unconditional Arial measurement.
        from .fonts import measurement_font
        font,scale=measurement_font(measured,declarations);ascent,descent=font.getmetrics();lh=fs*obj.get('line_height',1.25)
        baseline=(lh-(ascent+descent)/scale)/2+ascent/scale
        if h is not None:baseline+=(h-lh*len(lines))/2
        node=el('text',parent,{**common,'x':tx,'y':y+baseline,'font-family':obj.get('font_family','Arial, sans-serif'),'font-size':fs,'font-weight':obj.get('font_weight',400),'font-style':obj.get('font_style','normal'),'fill':obj.get('color','#17232b'),'text-anchor':anchor,'xml:space':'preserve'})
        for index,line in enumerate(lines):
            child=el('tspan',node,{'x':tx,'dy':0 if index==0 else lh})
            if not styled:child.text=line
            elif len(line)==1:
                value,weight,marked=line[0];child.text=value
                if marked:child.set('font-weight',str(weight))
            else:
                for value,weight,marked in line:
                    part=el('tspan',child,{'font-weight':weight});part.text=value
        return node
    for panel in spec.get('panels',[]):
        group=el('g',root,{'id':panel['id'],'transform':f'translate({panel.get("x",0)} {panel.get("y",0)})','data-panel-id':panel['id']})
        if panel.get('background'):el('rect',group,{'id':panel['id']+'-background','width':panel['width'],'height':panel['height'],'fill':panel['background']})
        for obj in panel.get('objects',[]):
            x=obj.get('x',0);y=obj.get('y',0);kind=obj['type'];common={'id':obj['id'],'data-object-type':kind,'data-source-ids':json.dumps(obj.get('source_ids',[]))}
            if kind=='text':
                if obj.get('background'):el('rect',group,{'x':x,'y':y,'width':obj['width'],'height':obj['height'],'fill':obj['background']})
                native_text(group,obj,common,x,y,obj['width'])
            elif kind=='image':
                asset=assets[obj['asset_id']];path=asset_root/asset['path'];mime=mimetypes.guess_type(path.name)[0] or 'image/png'
                position=obj.get('position','center');ax='Min' if 'left' in position else 'Max' if 'right' in position else 'Mid';ay='Min' if 'top' in position else 'Max' if 'bottom' in position else 'Mid'
                preserve='x'+ax+'Y'+ay+' meet'
                contract=_image_contract(obj,asset,path,panel,spec,asset_table)
                dw,dh=contract['display_pixels']
                dx=0 if ax=='Min' else obj['width']-dw if ax=='Max' else (obj['width']-dw)/2
                dy=0 if ay=='Min' else obj['height']-dh if ay=='Max' else (obj['height']-dh)/2
                if obj.get('background'):el('rect',group,{'x':x,'y':y,'width':obj['width'],'height':obj['height'],'fill':obj['background']})
                el('image',group,{**common,'x':x+dx,'y':y+dy,'width':dw,'height':dh,'preserveAspectRatio':preserve,'href':'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode(),'data-asset-id':obj['asset_id']})
            elif kind in {'rect','line'}:
                tag,attrs=_shape(obj)
                if tag=='rect':attrs.update(x=x,y=y)
                else:
                    for key in ['x1','x2']:attrs[key]+=x
                    for key in ['y1','y2']:attrs[key]+=y
                el(tag,group,{**common,**attrs})
            elif kind=='table':
                rows,columns,heights,padding,stroke,header,row_weights,column_aligns,row_fills=_table_layout(obj)
                table=el('g',group,{**common,'transform':f'translate({x} {y})'});cy=0
                for ri,row in enumerate(rows):
                    cx=0
                    for ci,value in enumerate(row):
                        cid=f'{obj["id"]}-cell-{ri}-{ci}';fill=row_fills[ri]
                        el('rect',table,{'id':cid,'x':cx,'y':cy,'width':columns[ci],'height':heights[ri],'fill':fill,'stroke':_paint(obj.get('stroke','#17232b')),'stroke-width':stroke})
                        cell={**obj,'text':str(value),'font_weight':row_weights[ri],'align':column_aligns[ci]}
                        native_text(table,cell,{'id':cid+'-text'},cx+padding,cy+padding,columns[ci]-padding*2-stroke,heights[ri]-padding*2)
                        cx+=columns[ci]
                    cy+=heights[ri]
            elif kind=='svg':
                node=ET.fromstring(_safe_svg(obj['svg']));node.set('id',obj['id']);node.set('x',str(x));node.set('y',str(y));node.set('width',str(obj['width']));node.set('height',str(obj['height']));group.append(node)
    output=Path(out_dir)/'poster.svg';output.write_text(ET.tostring(root,encoding='unicode'))
    repair=spec.get('typography_repair')
    if repair is not None:
        if not isinstance(repair,dict) or repair.get('format')!='posfoxgen-svg-text-repair-v1' or not isinstance(repair.get('issues'),dict):
            raise ValueError('invalid typography_repair replay contract')
        from .svg_text_repair import repair_svg
        import tempfile
        with tempfile.TemporaryDirectory(prefix='posfox-text-replay-') as temporary:
            report=repair_svg(output,spec,temporary,issues=repair['issues'])
            svg_payload=Path(report['svg']).read_text();output.write_text(svg_payload)
            shutil.copyfile(Path(temporary)/'poster.png',Path(out_dir)/'poster.png')
            report.update(svg=str(output.resolve()),source_svg='deterministic base export of this poster_spec')
            (Path(out_dir)/'text-repair-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        # HTML and SVG now use one actual native tree, including typeset formulae.
        metadata=json.dumps({'format':'posfoxgen-editable-v1','spec':spec},ensure_ascii=False).replace('<','\\u003c')
        document=f'''<!doctype html><html><head><meta charset="utf-8"><title>{escape(spec.get('title','Poster'))}</title><style>html,body{{margin:0;padding:0}}#poster{{width:{width}px;height:{height}px}}#poster>svg{{display:block}}</style></head><body><main id="poster">{svg_payload}</main><script id="posfoxgen-metadata" type="application/json">{metadata}</script></body></html>'''
        (Path(out_dir)/'poster.html').write_text(document)
    return output


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('spec');parser.add_argument('--assets',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args(argv);print(build_poster(args.spec,args.assets,args.out))


if __name__=='__main__':main()

"""Measured native SVG text repair. No model calls, raster replacement or font shrinking.

The sibling poster_spec.json supplies frame geometry absent from SVG text. Exact
reference line breaks/emphasis/TeX must be supplied by an evidence-backed issue map;
this tool never infers scientific subscripts from ambiguous baseline letters.
"""
from __future__ import annotations
import argparse
from html import escape
import io
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from .render import find_browser

NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)
SUB=dict(zip('₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ','0123456789+−=()aehijklmnoprstuvx'))
SUP=dict(zip('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵀ','0123456789+−=()niT'))

def _scripts(text):
    parts=[]
    for c in text:
        if c in SUB:parts.append('<sub>'+escape(SUB[c])+'</sub>')
        elif c in SUP:parts.append('<sup>'+escape(SUP[c])+'</sup>')
        else:parts.append(escape(c))
    return ''.join(parts)


def _formula(latex,size,color='#000000'):
    import matplotlib
    from matplotlib.mathtext import math_to_image
    from matplotlib.font_manager import FontProperties
    try:
        stream=io.BytesIO()
        with matplotlib.rc_context({'svg.fonttype':'path','mathtext.fontset':'stix','savefig.transparent':True,'svg.hashsalt':'posfox-native-math-v1'}):
            depth=math_to_image('$'+latex+'$',stream,prop=FontProperties(size=size),dpi=72,format='svg',color=color)
        root=ET.fromstring(stream.getvalue())
        for child in list(root):
            if child.tag.rsplit('}',1)[-1]=='metadata':root.remove(child)
        for node in root.iter():
            link=node.attrib.pop('{http://www.w3.org/1999/xlink}href',None)
            if link is not None:
                if not link.startswith('#'):raise ValueError('nonlocal mathematical reference')
                node.set('href',link)
        vb=[float(v) for v in root.get('viewBox').split()]
        return root,vb[2],vb[3],depth
    except Exception as exc:raise ValueError('formula compilation failed: '+latex) from exc


def _content(obj,issue,formulae):
    text=obj.get('text','')
    if issue.get('rewrap_soft_breaks'):
        text=re.sub(r'(?<!\n)\n(?!\n)',' ',text)
    if 'lines' in issue:
        if ' '.join(' '.join(issue['lines']).split())!=' '.join(text.split()):
            raise ValueError('reference line breaks must preserve complete source text: '+obj['id'])
        text='\n'.join(issue['lines'])
    spans=[]
    for e in issue.get('emphasis',obj.get('emphasis',[])):
        weight=e['font_weight']
        if type(weight) is not int or weight not in {400,500,600,700,800,900}:raise ValueError('invalid emphasis weight')
        for m in re.finditer(re.escape(e['text']),text):spans.append((m.start(),m.end(),'weight',weight))
        if e['text'] not in text:raise ValueError('emphasis text absent: '+e['text'])
    for e in issue.get('style_runs',[]):
        if not e.get('text') or e['text'] not in text:raise ValueError('style-run text absent')
        style=e.get('font_style')
        if style not in {'normal','italic'}:raise ValueError('invalid inline font style')
        for m in re.finditer(re.escape(e['text']),text):spans.append((m.start(),m.end(),'style',style))
    for e in issue.get('math_runs',[]):
        if not e.get('text') or e['text'] not in text:raise ValueError('formula source text absent')
        for m in re.finditer(re.escape(e['text']),text):
            key='math'+str(len(formulae));formulae[key]=_formula(e['latex'],obj.get('font_size',24),obj.get('color','#17232b'))+(e['latex'],)
            spans.append((m.start(),m.end(),'math',key))
    spans.sort();end=0;html=[]
    for a,b,kind,val in spans:
        if a<end:raise ValueError('overlapping emphasis/formula ranges; split into disjoint runs')
        html.append(_scripts(text[end:a]))
        if kind=='weight':html.append(f'<span style="font-weight:{val}" data-weight="{val}">'+_scripts(text[a:b])+'</span>')
        elif kind=='style':html.append(f'<span style="font-style:{val}">'+_scripts(text[a:b])+'</span>')
        else:
            root,w,h,depth,latex=formulae[val];markup=ET.tostring(root,encoding='unicode');markup=markup.replace('svg:','').replace('ns0:','')
            # Explicit CSS pixel dimensions make math and poster use one unit system.
            markup=markup.replace('<svg ',f'<svg style="position:absolute;left:0;top:-{h-depth}px;width:{w}px;height:{h}px" ',1)
            html.append(f'<span data-math="{val}" style="display:inline-block;position:relative;width:{w}px;height:0;vertical-align:baseline">'+markup+'</span>')
        end=b
    html.append(_scripts(text[end:]));return ''.join(html)


_MEASURE=r'''() => {
 const canvas=document.createElementNS('http://www.w3.org/1999/xhtml','canvas'),ctx=canvas.getContext('2d'),out=[];
 for(const el of document.querySelectorAll('.repair-text')){
  const runs=[];const frame=el.getBoundingClientRect();
  function walk(node){
   if(node.nodeType===1 && node.hasAttribute('data-strut'))return;
   if(node.nodeType===1 && node.hasAttribute('data-math')){
    const b=node.querySelector('svg').getBoundingClientRect();runs.push({math:node.getAttribute('data-math'),x:b.x,y:b.y,width:b.width,height:b.height});return;
   }
   if(node.nodeType===3){
    const css=getComputedStyle(node.parentElement);ctx.font=`${css.fontStyle} ${css.fontWeight} ${css.fontSize} ${css.fontFamily}`;
    const metrics=ctx.measureText('Mg'),ascent=metrics.fontBoundingBoxAscent;
    for(let i=0;i<node.length;){
     const step=node.data.codePointAt(i)>65535?2:1;
     const range=document.createRange();range.setStart(node,i);range.setEnd(node,i+step);
     const b=range.getBoundingClientRect(),value=node.data.slice(i,i+step);i+=step;
     if(value==='\n'||!b.width)continue;
     const y=b.y+ascent;const key=JSON.stringify([Math.round(y*100)/100,css.fontWeight,css.fontStyle,css.fontSize,css.fontFamily,css.color]);
     const last=runs[runs.length-1];
     if(last && !last.math && last.key===key && Math.abs(last.right-b.x)<0.5){last.text+=value;last.right=b.right;}
     else runs.push({text:value,x:b.x,y,right:b.right,key,weight:css.fontWeight,style:css.fontStyle,size:parseFloat(css.fontSize),family:css.fontFamily,color:css.color});
    }return;
   }
   for(const child of node.childNodes)walk(child);
  }walk(el);
  out.push({id:el.id,frame:{x:frame.x,y:frame.y,width:frame.width,height:frame.height},runs});
 }return out;
}'''


_SVG_GEOMETRY = r"""() => [...document.querySelectorAll('text[data-frame]')].map(n=>{
      const [x,y,w,h]=JSON.parse(n.getAttribute('data-frame')),parent=n.parentNode,inv=parent.getCTM().inverse();
      const elements=[...(n.textContent.trim()?[n]:[]),...[...parent.querySelectorAll('g[data-owner]')].filter(g=>g.getAttribute('data-owner')===n.id)];
      const ctx=document.createElementNS('http://www.w3.org/1999/xhtml','canvas').getContext('2d');
      const points=elements.flatMap(e=>{
        if(e.tagName.toLowerCase()==='text'){
          const leaves=[...e.querySelectorAll('tspan')].filter(t=>!t.children.length&&t.textContent.trim());const spans=leaves.length?leaves:(e.textContent.trim()?[e]:[]);
          return spans.flatMap(t=>{const css=getComputedStyle(t);ctx.font=`${css.fontStyle} ${css.fontWeight} ${css.fontSize} ${css.fontFamily}`;
            const a=ctx.measureText(t.textContent),p=t.getStartPositionOfChar(0),m=inv.multiply(t.getCTM());
            return [[p.x-a.actualBoundingBoxLeft,p.y-a.actualBoundingBoxAscent],[p.x+a.actualBoundingBoxRight,p.y+a.actualBoundingBoxDescent]].map(([x,y])=>new DOMPoint(x,y).matrixTransform(m));});
        }
        const b=e.getBBox(),m=inv.multiply(e.getCTM());return [[b.x,b.y],[b.x+b.width,b.y+b.height]].map(([x,y])=>new DOMPoint(x,y).matrixTransform(m));});
      if(!points.length)return {object_id:n.id,horizontal:false,vertical:false,empty:true,frame:[x,y,w,h]};
      const left=Math.min(...points.map(p=>p.x)),top=Math.min(...points.map(p=>p.y)),right=Math.max(...points.map(p=>p.x)),bottom=Math.max(...points.map(p=>p.y));
      return {object_id:n.id,x:left,y:top,width:right-left,height:bottom-top,frame:[x,y,w,h],horizontal:left<x-1||right>x+w+1,vertical:top<y-2||bottom>y+h+2};})"""


def repair_svg(svg_path,spec,out_dir,*,issues=None,page=None):
    """Patch only native text nodes; retain all other original SVG elements.

    A returned report may contain blockers: execution is not visual acceptance.
    Inputs are never overwritten. Font sizes and panel geometry are preserved.
    """
    if page is None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=find_browser(),headless=True)
            try:return repair_svg(svg_path,spec,out_dir,issues=issues,page=browser.new_page())
            finally:browser.close()
    if isinstance(spec,(str,Path)):spec=json.loads(Path(spec).read_text())
    issues=issues or {};source=Path(svg_path).resolve();out=Path(out_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'poster.svg')==source:raise ValueError('output must not overwrite input SVG')
    root=ET.parse(source).getroot();nodes={n.get('id'):n for n in root.iter() if n.get('id')};formulae={};html=[];positions={}
    for panel in spec['panels']:
        for obj in panel['objects']:
            if obj.get('type')!='text':continue
            oid=obj['id']
            if oid not in nodes:raise ValueError('SVG text object missing: '+oid)
            if not nodes[oid].tag.endswith('}text'):raise ValueError('target is not native text: '+oid)
            x=panel.get('x',0)+obj.get('x',0);y=panel.get('y',0)+obj.get('y',0);positions[oid]=(panel.get('x',0),panel.get('y',0),obj)
            obj={**obj,**{k:v for k,v in issues.get(oid,{}).get('style',{}).items() if k in {'font_family','font_weight','font_style'}}}
            positions[oid]=(panel.get('x',0),panel.get('y',0),obj)
            content=_content(obj,issues.get(oid,{}),formulae)
            family=escape(obj.get('font_family','Arial, sans-serif'),quote=True)
            style=f"position:absolute;left:{x}px;top:{y}px;width:{obj['width']}px;height:{obj['height']}px;font-family:{family};font-size:{obj.get('font_size',24)}px;font-weight:{obj.get('font_weight',400)};font-style:{obj.get('font_style','normal')};line-height:{obj.get('line_height',1.25)};text-align:{obj.get('align','left')};color:{obj.get('color','#17232b')};white-space:pre-wrap;overflow-wrap:normal"
            html.append(f'<div class="repair-text" id="{escape(oid)}" style="{style}"><span data-strut="true">&#8203;</span>{content}</div>')
    # Only trusted local poster-spec text is used; no original HTML scripts execute.
    page.set_viewport_size({'width':int(spec['width']),'height':int(spec['height'])})
    page.goto(source.as_uri());page.evaluate('document.fonts.ready')
    frames={oid:[o.get('x',0),o.get('y',0),o['width'],o['height']] for oid,(_,_,o) in positions.items()}
    page.evaluate("frames => Object.entries(frames).forEach(([id,frame])=>[...document.querySelectorAll('text')].find(n=>n.id===id).setAttribute('data-frame',JSON.stringify(frame)))",frames)
    before=page.evaluate(_SVG_GEOMETRY)
    triggered={c['object_id'] for c in before if c['horizontal'] or c['vertical']}|set(issues)
    triggered|={oid for oid,(_,_,obj) in positions.items() if any(c in SUB or c in SUP for c in obj.get('text',''))}
    page.goto('about:blank')
    page.set_content('<html><head><style>html,body{margin:0;padding:0}sub,sup{font-size:70%;line-height:0}svg{width:100%;height:100%}</style></head><body>'+''.join(html)+'</body></html>')
    page.evaluate('document.fonts.ready');measured=page.evaluate(_MEASURE);reports=[]
    for item in measured:
        oid=item['id'];px,py,obj=positions[oid]
        if oid not in triggered:continue
        node=nodes[oid]
        old_groups=[g for g in root.iter() if g.get('data-owner')==oid and g.get('data-latex')]
        if old_groups and not issues.get(oid,{}).get('math_runs'):
            raise ValueError('existing formula requires its original math_runs when repairing '+oid)
        for g in old_groups:
            parent=next(p for p in root.iter() if g in list(p));parent.remove(g)
        node.text=None
        for child in list(node):node.remove(child)
        node.set('text-anchor','start');node.set('font-size',str(obj.get('font_size',24)))
        node.set('data-source-text',obj.get('text',''));node.set('data-repair','browser-measured-lines');node.set('data-frame',json.dumps([obj.get('x',0),obj.get('y',0),obj['width'],obj['height']]))
        math_groups=[]
        for ri,run in enumerate(item['runs']):
            if 'text' in run and (ri+1==len(item['runs']) or ('text' in item['runs'][ri+1] and abs(item['runs'][ri+1]['y']-run['y'])>0.1)):
                run['text']=run['text'].rstrip()
            if 'math' in run:
                tree,w,h,depth,latex=formulae[run['math']];g=ET.Element('{'+NS+'}g',{'id':oid+'-'+run['math'],'data-owner':oid,'data-latex':latex,'transform':f"translate({run['x']-px} {run['y']-py})"})
                # MathText emits local IDs; namespace them before placing several formulae.
                payload=ET.tostring(tree,encoding='unicode');ids=re.findall(r'\bid="([^"]+)"',payload)
                for old in sorted(set(ids),key=len,reverse=True):
                    new=oid+'-'+run['math']+'-'+old;payload=payload.replace('id="'+old+'"','id="'+new+'"').replace('#'+old+'"','#'+new+'"').replace('#'+old+')','#'+new+')')
                mathroot=ET.fromstring(payload);mathroot.set('width',str(w));mathroot.set('height',str(h));g.append(mathroot);math_groups.append(g)
            else:
                attrs={'x':str(run['x']-px),'y':str(run['y']-py),'font-size':str(run['size']),'font-weight':run['weight'],'font-style':run['style'],'font-family':run['family'],'fill':run['color']}
                ET.SubElement(node,'{'+NS+'}tspan',attrs).text=run['text']
        if math_groups:
            parent=next(p for p in root.iter() if node in list(p));idx=list(parent).index(node)
            for g in math_groups:idx+=1;parent.insert(idx,g)
        frame=item['frame'];runs=item['runs'];text_runs=[v for v in runs if 'text' in v]
        # Final glyph bboxes below give the authoritative overflow check.
        reports.append({'object_id':oid,'line_count':len(set(round(v['y'],2) for v in text_runs)),'font_size':obj.get('font_size',24),'weights':sorted({v['weight'] for v in text_runs}),'emphasis_runs':[{'text':v['text'],'weight':int(v['weight'])} for v in text_runs if int(v['weight'])>400],'emphasized':any(int(v['weight'])>400 for v in text_runs),'math_count':len(math_groups),'frame':frame,'weight_levels':sorted({{400:'regular',500:'medium',600:'semibold',700:'bold',800:'heavy',900:'black'}.get(int(v['weight']),'other') for v in text_runs})})
    target=out/'poster.svg';target.write_text(ET.tostring(root,encoding='unicode'))
    page.goto(target.as_uri());page.evaluate('document.fonts.ready')
    geometry_js = _SVG_GEOMETRY
    page.evaluate("frames => Object.entries(frames).forEach(([id,frame])=>[...document.querySelectorAll('text')].find(n=>n.id===id).setAttribute('data-frame',JSON.stringify(frame)))",frames)
    check=page.evaluate(geometry_js)
    shifts=[]
    for c in check:
        x,y,w,h=c['frame'];delta=max(0,y-c.get('y',y))
        if delta and delta<=positions[c['object_id']][2].get('font_size',24)*.25 and c.get('y',y)+c.get('height',0)+delta<=y+h+1:
            node=nodes[c['object_id']]
            for t in node:
                if t.get('y') is not None:t.set('y',str(float(t.get('y'))+delta))
            for g in root.iter():
                if g.get('data-owner')==c['object_id']:
                    # Append in local coordinates; no scale or rotation is introduced.
                    g.set('transform',g.get('transform','')+f' translate(0 {delta})')
            shifts.append({'object_id':c['object_id'],'baseline_shift_px':delta})
    if shifts:
        target.write_text(ET.tostring(root,encoding='unicode'));page.reload();page.evaluate('document.fonts.ready');page.evaluate("frames => Object.entries(frames).forEach(([id,frame])=>[...document.querySelectorAll('text')].find(n=>n.id===id).setAttribute('data-frame',JSON.stringify(frame)))",frames);check=page.evaluate(geometry_js)
    subprocess.run(['rsvg-convert','--background-color','white','--output',str(out/'poster.png'),str(target)],check=True,capture_output=True)
    result={'svg':str(target),'source_svg':str(source),'before_geometry_checks':before,'baseline_adjustments':shifts,'triggered_object_ids':sorted(triggered),'total_text_objects':len(positions),'emphasized_objects':[v['object_id'] for v in reports if v['emphasized']],'text_objects':reports,'svg_width_blockers':[c for c in check if c['horizontal']],'svg_height_blockers':[c for c in check if c['vertical']],'geometry_checks':check,'formulas_compiled':len(formulae),'limitations':['Preserves spec font size and geometry; cannot infer exact reference line breaks or missing emphasis without an issue map.','SVG font portability still depends on target installed fonts; formula paths do not.','Text overflow is reported, never hidden by shrinking fonts or clipping.']}
    (out/'text-repair-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('svg');p.add_argument('--spec');p.add_argument('--issues');p.add_argument('--out',required=True);a=p.parse_args()
    result=repair_svg(a.svg,a.spec or Path(a.svg).with_name('poster_spec.json'),a.out,issues=json.loads(Path(a.issues).read_text()) if a.issues else None)
    print(json.dumps({'svg':result['svg'],'horizontal_blockers':len(result['svg_width_blockers']),'vertical_blockers':len(result['svg_height_blockers']),'formulas_compiled':result['formulas_compiled']}))

if __name__=='__main__':main()

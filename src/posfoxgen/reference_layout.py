"""Source-bound, scoped container checks after measured text repair."""
import hashlib
import re
from pathlib import Path


def validate_reference(issues):
    for oid, issue in issues.items():
        evidence=issue.get('reference',{})
        path=Path(evidence.get('path',''))
        if not issue.get('reason') or not isinstance(issue.get('lines'),list) or not issue['lines'] or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=evidence.get('sha256'):
            raise ValueError('reference evidence, reason and exact lines required: '+oid)
        joined=' '.join(issue['lines'])
        phrases=['et al.']+issue.get('protected_phrases',[])
        for phrase in phrases:
            if re.search(re.escape(phrase),joined,re.I) and not any(re.search(re.escape(phrase),line,re.I) for line in issue['lines']):
                raise ValueError('protected phrase split across reference lines: '+phrase)


def inspect_reference_lines(root, issues):
    nodes={n.get('id'):n for n in root.iter() if n.get('id')};result=[]
    for oid,issue in issues.items():
        node=nodes[oid];rows={}
        cursor=[float(node.get('y','0'))]
        def walk(span):
            if span is not node:
                if span.get('y') is not None:cursor[0]=float(span.get('y'))
                cursor[0]+=float(span.get('dy','0'))
            if span.text:rows.setdefault(round(cursor[0],4),[]).append(span.text)
            for child in span:
                walk(child)
                if child.tail:rows.setdefault(round(cursor[0],4),[]).append(child.tail)
        walk(node)
        actual=[''.join(row).strip() for row in rows.values()] or [(node.text or '').strip()]
        reference=issue['lines'];joined=' '.join(reference)
        split=[phrase for phrase in ['et al.']+issue.get('protected_phrases',[]) if re.search(re.escape(phrase),joined,re.I) and not any(re.search(re.escape(phrase),line,re.I) for line in actual)]
        result.append({'object_id':oid,'actual_lines':actual,'reference_lines':reference,'line_mismatch':actual!=reference,'split_protected_phrases':split,'severity':'severe' if split else ('layout' if actual!=reference else 'none')})
    return result


def _contains(frame, box):
    x,y,w,h=frame;a,b,c,d=box
    return a>=x-1 and b>=y-2 and a+c<=x+w+1 and b+d<=y+h+2


def _overlap(a,b):
    return min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0])>1 and min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1])>1


def check_containers(root, geometry, issues, positions):
    """Audit fixed containers after typography adaptation; never resize them.

    Frames and glyph geometry use the text's immediate parent coordinates. All
    neighbours are compared in poster coordinates using supplied panel origins.
    Unsupported transformed containers stay blocked instead of guessing.
    """
    nodes={n.get('id'):n for n in root.iter() if n.get('id')}
    parents={n:p for p in root.iter() for n in p};checks={g['object_id']:g for g in geometry};result=[]
    for oid,issue in issues.items():
        g=checks[oid];box=[g[k] for k in ('x','y','width','height')];px,py,obj=positions[oid]
        record={'object_id':oid,'text_frame_pass':not(g.get('horizontal') or g.get('vertical'))}
        c=issue.get('container');node=nodes.get(c.get('id')) if c else None
        if c:
            record['container_id']=c.get('id')
            if node is None or node.tag.rsplit('}',1)[-1]!='rect' or node.get('transform') or (oid in nodes and parents.get(nodes[oid]) is not parents.get(node)):
                record['status']='blocked_unsupported_container'
            else:
                old=[float(node.get(k,0)) for k in ('x','y','width','height')]
                record['status']='unchanged_container_fits' if _contains(old,box) else 'blocked_container_overflow'
        else:
            frame=issue.get('panel_frame')
            record['status']='unchanged_container_fits' if frame and _contains(frame,box) else 'blocked_container_not_verified'
        neighbours=[]
        for nid,ng in checks.items():
            if nid==oid:continue
            nx,ny,_=positions[nid];nb=[ng['x']+nx-px,ng['y']+ny-py,ng['width'],ng['height']]
            if _overlap(box,nb):neighbours.append(nid)
        record['text_collision_ids']=neighbours
        result.append(record)
    return result


# Adjust only tracking and leading on explicit targets. Range metrics are read
# again after each change; font size, frame dimensions and neighbouring nodes stay fixed.
COMPACT = r"""({targets,obstacles}) => {
 const records=[], canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
 const measure=__MEASURE__;
 function bounds(item){
  const boxes=item.runs.map(r=>{
   if(r.math)return [r.x,r.y,r.x+r.width,r.y+r.height];
   ctx.font=`${r.style} ${r.weight} ${r.size}px ${r.family}`;
   ctx.letterSpacing=r.spacing==='normal'?'0px':r.spacing;
   const m=ctx.measureText(r.text);
   return [r.x-m.actualBoundingBoxLeft,r.y-m.actualBoundingBoxAscent,r.right,r.y+m.actualBoundingBoxDescent];
  });
  return {left:Math.min(...boxes.map(b=>b[0])),top:Math.min(...boxes.map(b=>b[1])),right:Math.max(...boxes.map(b=>b[2])),bottom:Math.max(...boxes.map(b=>b[3]))};
 }
 for(const id of targets){
  const el=document.getElementById(id),f=el.getBoundingClientRect(),css=getComputedStyle(el),size=parseFloat(css.fontSize);
  const initial={letter_spacing_px:parseFloat(css.letterSpacing)||0,line_height_px:parseFloat(css.lineHeight)};
  let bottom=f.bottom;
  for(const ob of obstacles){
   if(ob.id===id)continue;
   if(ob.x<f.right && ob.x+ob.width>f.left && ob.y>f.top+size*.5)bottom=Math.min(bottom,ob.y-1);
  }
  let before=null,after=null;
  for(let pass=0;pass<6;pass++){
   const item=measure().find(x=>x.id===id),b=bounds(item);if(!before)before=b;after=b;
   const excess=b.right-f.right,vertical=b.bottom-bottom;
   let changed=false;
   if(excess>0.5){
    const rows=new Map();for(const run of item.runs)if(run.text){const k=Math.round(run.y);rows.set(k,(rows.get(k)||0)+run.text.length);}
    const chars=Math.max(2,...rows.values()),old=parseFloat(getComputedStyle(el).letterSpacing)||0;
    const next=Math.max(-size*.12,old-(excess+.15)/(chars-1));
    if(next<old-.001){el.style.letterSpacing=next+'px';changed=true;}
   }
   if(vertical>.5){
    const count=el.textContent.split('\n').length,old=parseFloat(getComputedStyle(el).lineHeight);
    const next=Math.max(size*.85,old-(vertical+.15)/Math.max(.5,count-.5));
    if(next<old-.001){el.style.lineHeight=next+'px';changed=true;}
   }
   if(!changed)break;
  }
  const final=getComputedStyle(el),end={letter_spacing_px:parseFloat(final.letterSpacing)||0,line_height_px:parseFloat(final.lineHeight)};
  if(initial.letter_spacing_px!==end.letter_spacing_px||initial.line_height_px!==end.line_height_px)records.push({object_id:id,before:initial,after:end,ink_before:before,ink_after:after,available_bottom:bottom});
 }
 return records;
}"""

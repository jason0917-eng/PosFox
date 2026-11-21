"""Local Chromium PNG/PDF rendering and read-only geometry diagnostics."""
from __future__ import annotations
import argparse
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


_AUDIT = r'''<script>
(async()=>{
 await document.fonts.ready;
 await Promise.all([...document.images].map(i=>i.complete?Promise.resolve():new Promise(r=>{i.onload=r;i.onerror=r;setTimeout(r,3000)})));
 const main=document.getElementById('poster');
 if(!main){document.body.setAttribute('data-render-error','missing-poster');return;}
 const rect=main.getBoundingClientRect(),blockers=[],objects=[],fonts=[],warnings=[];
 for(const el of main.querySelectorAll('[data-object-type]')){
  const b=el.getBoundingClientRect(),p=el.closest('[data-panel-id]'),pb=p?p.getBoundingClientRect():rect;
  const item={object_id:el.id,type:el.dataset.objectType,panel_id:p?.id||null,x:b.left-rect.left,y:b.top-rect.top,width:b.width,height:b.height,scroll_width:el.scrollWidth,scroll_height:el.scrollHeight};objects.push(item);
  const nativeText=el.namespaceURI==='http://www.w3.org/2000/svg'&&el.tagName.toLowerCase()==='text';
  if(!nativeText&&(b.left<pb.left-1||b.top<pb.top-1||b.right>pb.right+1||b.bottom>pb.bottom+1))blockers.push({code:'outside_panel',object_id:el.id});
  if(!nativeText&&(b.left<rect.left-1||b.top<rect.top-1||b.right>rect.right+1||b.bottom>rect.bottom+1))blockers.push({code:'outside_poster',object_id:el.id});
  if(el.dataset.objectType==='text'&&el.namespaceURI!=='http://www.w3.org/2000/svg'&&(el.scrollHeight>el.clientHeight+1||el.scrollWidth>el.clientWidth+1))blockers.push({code:'text_overflow',object_id:el.id,scroll_width:el.scrollWidth,scroll_height:el.scrollHeight,width:el.clientWidth,height:el.clientHeight});
  const css=getComputedStyle(el);
  if(el.dataset.fontFamily){
   const family=el.dataset.fontFamily,embedded=el.dataset.fontEmbedded==='true',declaredFace=el.dataset.fontDeclared==='true';
   const declared=[...document.fonts].filter(f=>f.family.replace(/["']/g,'')===family);
   const available=el.dataset.fontAvailable==='true'&&(!declaredFace||(declared.length>0&&declared.some(f=>f.status==='loaded')));
   const context=document.createElement('canvas').getContext('2d');context.font=`${css.fontStyle} ${css.fontWeight} ${css.fontSize} ${css.fontFamily}`;
   fonts.push({object_id:el.id,requested_family:family,computed_family:css.fontFamily,available,embedded,sample_text:'Experimental results',sample_advance_px:context.measureText('Experimental results').width,faces:declared.map(f=>({family:f.family,status:f.status,weight:f.weight,style:f.style}))});
   if(!available)(el.dataset.fontRequired==='true'?blockers:warnings).push({code:'font_unavailable',object_id:el.id,family});
  }
  if(el.tagName==='IMG'){
   item.natural_width=el.naturalWidth;item.natural_height=el.naturalHeight;item.object_fit=css.objectFit;item.object_position=css.objectPosition;item.background=css.backgroundColor;
   if(!el.complete||el.naturalWidth===0)blockers.push({code:'image_unavailable',object_id:el.id});
   if(css.objectFit==='cover')blockers.push({code:'image_semantic_crop',object_id:el.id});
   if(css.objectFit==='fill')blockers.push({code:'image_distortion_forbidden',object_id:el.id});
   if(el.dataset.imageFit&&el.dataset.imageFit!==css.objectFit)blockers.push({code:'image_fit_contract_changed',object_id:el.id});
  }
  if(el.dataset.objectType==='table'){
   item.cells=[];
   for(const cell of el.querySelectorAll('[data-table-cell]')){
    const cb=cell.getBoundingClientRect();item.cells.push({cell_id:cell.dataset.tableCell,text_align:getComputedStyle(cell).textAlign,x:cb.left-rect.left,y:cb.top-rect.top,width:cb.width,height:cb.height});
    if(cell.scrollHeight>cell.clientHeight+1||cell.scrollWidth>cell.clientWidth+1)blockers.push({code:'table_cell_overflow',object_id:el.id,cell_id:cell.dataset.tableCell,scroll_width:cell.scrollWidth,scroll_height:cell.scrollHeight,width:cell.clientWidth,height:cell.clientHeight});
   }
  }
 }
 const metadata=document.getElementById('posfoxgen-metadata');
 if(metadata){
  const spec=JSON.parse(metadata.textContent).spec;
  for(const panel of spec?.panels||[])for(const obj of panel.objects||[]){
   if(obj.type!=='text')continue;
   const node=[...main.querySelectorAll('text')].find(n=>n.id===obj.id);
   if(node)node.setAttribute('data-frame',JSON.stringify([obj.x||0,obj.y||0,obj.width,obj.height]));
  }
 }
 const svg_text_checks=(__POSFOX_SVG_GEOMETRY__)();
 for(const c of svg_text_checks)if(c.horizontal||c.vertical)blockers.push({code:'svg_text_overflow',object_id:c.object_id,geometry:c});
 const contract=metadata?JSON.parse(metadata.textContent).spec:null;
 if(contract?.typography_repair?.mode==='reference-guided'){
  const origins=new Map();for(const p of contract.panels)for(const o of p.objects||[])origins.set(o.id,[p.x||0,p.y||0]);
  const absolute=c=>{const [x,y]=origins.get(c.object_id)||[0,0];return {...c,x:c.x+x,y:c.y+y};};
  const all=svg_text_checks.map(absolute);
  for(const [id,issue] of Object.entries(contract.typography_repair.issues)){
   const c=all.find(x=>x.object_id===id);if(!c)continue;
   for(const n of all){
    if(n.object_id===id)continue;
    if(Math.min(c.x+c.width,n.x+n.width)-Math.max(c.x,n.x)>1 && Math.min(c.y+c.height,n.y+n.height)-Math.max(c.y,n.y)>1)
     blockers.push({code:'reference_text_collision',object_id:id,neighbour_id:n.object_id,overlap_y:Math.min(c.y+c.height,n.y+n.height)-Math.max(c.y,n.y)});
   }
   const local=svg_text_checks.find(x=>x.object_id===id);let frame=issue.panel_frame;
   if(issue.container){
    const box=[...main.querySelectorAll('rect')].find(x=>x.id===issue.container.id);
    if(box && !box.hasAttribute('transform'))frame=['x','y','width','height'].map(k=>parseFloat(box.getAttribute(k)||0));else frame=null;
   }
   if(!frame || local.x<frame[0]-1 || local.y<frame[1]-2 || local.x+local.width>frame[0]+frame[2]+1 || local.y+local.height>frame[1]+frame[3]+2)
    blockers.push({code:'reference_container_overflow',object_id:id});
  }
 }
 const formula_checks=[...main.querySelectorAll('g[data-latex]')].map(g=>{
  const uses=[...g.querySelectorAll('use')];const missing=uses.filter(n=>!n.href?.baseVal?.startsWith('#')||!document.getElementById(n.href.baseVal.slice(1)));
  const b=g.getBBox();return {object_id:g.id,latex:g.getAttribute('data-latex'),reference_count:uses.length,missing_references:missing.length,visible_width:b.width,visible_height:b.height};
 });
 for(const c of formula_checks)if(c.missing_references||!c.visible_width||!c.visible_height)blockers.push({code:'svg_formula_missing_reference',object_id:c.object_id,geometry:c});

 const out=document.createElement('script');out.id='posfoxgen-render-audit';out.type='application/json';out.textContent=JSON.stringify({width:rect.width,height:rect.height,objects,fonts,warnings,blockers,svg_text_checks,formula_checks});document.body.append(out);
})();
</script>'''


class _AuditParser(HTMLParser):
    def __init__(self):super().__init__();self.inside=False;self.data=''
    def handle_starttag(self,tag,attrs):
        if tag=='script' and dict(attrs).get('id')=='posfoxgen-render-audit':self.inside=True
    def handle_endtag(self,tag):
        if tag=='script':self.inside=False
    def handle_data(self,value):
        if self.inside:self.data+=value


def find_browser(explicit=None):
    candidates=[explicit,os.environ.get('POSFOXGEN_CHROMIUM'),'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',shutil.which('chromium'),shutil.which('chromium-browser'),shutil.which('google-chrome')]
    for path in candidates:
        if path and Path(path).is_file():return str(path)
    raise RuntimeError('No local Chromium found; render with the Harness browser or set POSFOXGEN_CHROMIUM to an installed browser. No browser is downloaded automatically.')


def render_poster(html_path,out_dir,browser=None):
    """Use a fresh isolated headless Chromium profile; no user browser state.

    The audit reports actual DOM geometry, not scientific quality. Review and
    scores remain separate Harness work and cannot be inferred from these checks.
    """
    source=Path(html_path).resolve();out=Path(out_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    executable=find_browser(browser)
    if not source.is_file():raise ValueError('poster HTML does not exist')
    # Relative source assets must keep resolving from the original document root.
    base='<base href="'+html.escape(source.parent.as_uri()+'/',quote=True)+'">'
    from .svg_text_repair import _SVG_GEOMETRY
    audit_script=_AUDIT.replace('__POSFOX_SVG_GEOMETRY__',_SVG_GEOMETRY)
    original=source.read_text();audit_source=original.replace('<head>','<head>'+base,1)
    if '<head>' not in original:audit_source=base+audit_source
    audit_source=audit_source.replace('</body>',audit_script+'</body>',1) if '</body>' in audit_source else audit_source+audit_script
    with tempfile.TemporaryDirectory(prefix='posfoxgen-render-') as tmp:
        tmp=Path(tmp);audit_file=tmp/'audit.html';audit_file.write_text(audit_source)
        common=[executable,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--hide-scrollbars','--no-pdf-header-footer','--disable-dev-shm-usage','--user-data-dir='+str(tmp/'profile')]
        def call(options,url):
            command=common+options+[url]
            result=subprocess.run(command,capture_output=True,text=True,timeout=75)
            if result.returncode:raise RuntimeError('Chromium renderer failed: '+result.stderr[-1800:])
            return result
        result=call(['--virtual-time-budget=4000','--dump-dom'],audit_file.as_uri())
        parser=_AuditParser();parser.feed(result.stdout)
        if not parser.data:raise RuntimeError('Chromium did not produce a DOM audit; no render was accepted')
        audit=json.loads(parser.data);width=round(audit['width']);height=round(audit['height'])
        if not 1<=width<=12000 or not 1<=height<=12000:raise ValueError('poster dimensions outside render limits')
        call(['--virtual-time-budget=1500',f'--window-size={width},{height}','--force-device-scale-factor=1','--screenshot='+str(out/'poster.png')],source.as_uri())
        call(['--virtual-time-budget=1500','--print-to-pdf='+str(out/'poster.pdf')],source.as_uri())
    from PIL import Image
    actual=Image.open(out/'poster.png').size
    if actual!=(width,height):raise RuntimeError(f'Chromium screenshot dimensions differ: {actual} versus {(width,height)}')
    report={'format':'posfoxgen-render-report-v1','engine':'chromium','browser_executable':executable,'rendered':True,'source_html':str(source),'png':str(out/'poster.png'),'pdf':str(out/'poster.pdf'),'width':width,'height':height,'objects':audit['objects'],'formula_checks':audit.get('formula_checks',[]),'svg_text_checks':audit.get('svg_text_checks',[]),'fonts':audit.get('fonts',[]),'warnings':audit.get('warnings',[]),'blockers':audit['blockers'],'layout_pass':not audit['blockers'],'scientific_quality_pass':None}
    (out/'render_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('html');p.add_argument('--out',required=True);p.add_argument('--browser')
    args=p.parse_args(argv);report=render_poster(args.html,args.out,args.browser);print(json.dumps({'rendered':report['rendered'],'layout_pass':report['layout_pass'],'blockers':report['blockers'],'png':report['png'],'pdf':report['pdf']}))


if __name__=='__main__':main()

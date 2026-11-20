"""Replay source-verified issue maps against existing PosFox SVG deliverables."""
from pathlib import Path
import argparse,hashlib,json,sys,collections
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from posfoxgen.svg_text_repair import repair_svg
from posfoxgen.render import find_browser
from playwright.sync_api import sync_playwright
import xml.etree.ElementTree as ET


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--out',required=True);p.add_argument('--issues-dir',required=True);p.add_argument('--cases',default='01,02,03,05,07,11,20,21,25,29');a=p.parse_args()
    root=Path(a.root);out=Path(a.out);out.mkdir(parents=True,exist_ok=True);summary=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=find_browser(),headless=True)
        try:
            page=browser.new_page()
            for n in a.cases.split(','):
                source=next(root/n/sub/'poster.svg' for sub in ['delivery-editable','editable-repaired','editable'] if (root/n/sub/'poster.svg').is_file());spec=source.with_name('poster_spec.json')
                issue_path=Path(a.issues_dir)/n/'issues.json';issues=json.loads(issue_path.read_text()) if issue_path.is_file() else {}
                result=repair_svg(source,spec,out/n,issues=issues,page=page)
                before=ET.parse(source);after=ET.parse(result['svg']);nodes={node.get('id'):node for node in after.iter() if node.get('id')}
                protected=[node for node in before.iter() if node.tag.rsplit('}',1)[-1] in {'image','rect','line','path'} and node.get('id')]
                key=lambda node:(node.tag,tuple(sorted(node.attrib.items())))
                protected_counts=collections.Counter(map(key,protected));after_counts=collections.Counter(key(node) for node in after.iter())
                unchanged=all(after_counts[k]>=v for k,v in protected_counts.items())
                sizes=all(node.get('font-size')==nodes[node.get('id')].get('font-size') for node in before.iter() if node.tag.rsplit('}',1)[-1]=='text' and node.get('id') in nodes)
                ids=[node.get('id') for node in after.iter() if node.get('id')];before_ids=collections.Counter(node.get('id') for node in before.iter() if node.get('id'));after_ids=collections.Counter(ids)
                old_duplicates=[k for k,v in before_ids.items() if v>1];new_duplicates=[k for k,v in after_ids.items() if v>max(1,before_ids[k])]
                row={'case':n,'total_text_objects':result['total_text_objects'],'repaired_text_objects':len(result['text_objects']),'before_horizontal':sum(c['horizontal'] for c in result['before_geometry_checks']),'after_horizontal':len(result['svg_width_blockers']),'after_vertical':len(result['svg_height_blockers']),'compiled_formula_runs':result['formulas_compiled'],'protected_objects_unchanged':unchanged,'font_sizes_unchanged':sizes,'preexisting_duplicate_ids':old_duplicates,'new_duplicate_ids':new_duplicates,'source_svg_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'spec_sha256':hashlib.sha256(spec.read_bytes()).hexdigest(),'issues_sha256':hashlib.sha256(json.dumps(issues,sort_keys=True).encode()).hexdigest()}
                row['mechanical_pass']=not row['after_horizontal'] and not row['after_vertical'] and unchanged and sizes and not new_duplicates;summary.append(row);print(json.dumps(row),flush=True)
        finally:browser.close()
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    if not all(row['mechanical_pass'] for row in summary):raise SystemExit(1)

if __name__=='__main__':main()

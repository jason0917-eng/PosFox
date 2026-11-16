"""Local font discovery and opt-in font embedding. No fonts are downloaded.

Embedding requires an explicit spec declaration and a content hash. Font discovery
never copies system fonts. An embedding declaration is the caller's assertion of
permission, not a license granted by this tool.
"""
from __future__ import annotations
import argparse
import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from PIL import ImageFont


@lru_cache(maxsize=16)
def _inventory(extra_roots=()):
    roots=[Path('/System/Library/Fonts'),Path('/Library/Fonts'),Path.home()/'Library/Fonts',Path('/usr/share/fonts'),Path('/usr/local/share/fonts'),Path.home()/'.local/share/fonts',Path('C:/Windows/Fonts')]
    roots.extend(Path(root).expanduser() for root in extra_roots)
    result=[];seen=set()
    for root in roots:
        if not root.is_dir():continue
        for path in sorted(root.rglob('*')):
            if path.suffix.lower() not in {'.ttf','.otf','.ttc','.otc'} or path in seen:continue
            seen.add(path)
            for index in range(64 if path.suffix.lower() in {'.ttc','.otc'} else 1):
                try:font=ImageFont.truetype(str(path),16,index=index);family,style=font.getname()
                except (OSError,ValueError):break
                result.append({'family':family,'style':style,'path':str(path),'index':index,'available':True})
    return tuple(result)


def font_inventory(extra_roots=None):
    return [dict(item) for item in _inventory(tuple(str(Path(root).expanduser()) for root in (extra_roots or [])))]


def family_list(value):
    if not isinstance(value,str) or not re.fullmatch(r'[\w ,"\'-]+',value):raise ValueError('invalid font family')
    names=[s.strip().strip('"\'') for s in value.split(',') if s.strip()]
    if not names:raise ValueError('font family must not be empty')
    return names


def font_declarations(spec):
    declarations={};css=[]
    for item in spec.get('fonts',[]):
        family=item['family'];names=family_list(family)
        if len(names)!=1:raise ValueError('declared font must have one family')
        weight=item.get('weight',400);style=item.get('style','normal')
        if weight not in {400,500,600,700,800,900} or style not in {'normal','italic'}:raise ValueError('invalid declared font weight/style')
        key=(names[0].casefold(),weight,style)
        if key in declarations:raise ValueError('duplicate declared font')
        path=Path(item['path']).expanduser().resolve()
        if not path.is_file():raise ValueError('declared font unavailable: '+family)
        payload=path.read_bytes();digest=hashlib.sha256(payload).hexdigest()
        if item.get('sha256') and item['sha256']!=digest:raise ValueError('font hash mismatch: '+family)
        try:font=ImageFont.truetype(str(path),16,index=item.get('index',0));real_family,_=font.getname()
        except (OSError,ValueError) as exc:raise ValueError('unreadable font: '+family) from exc
        resolved={'family':family,'real_family':real_family,'style':style,'weight':weight,'path':str(path),'index':item.get('index',0),'sha256':digest,'embedded':bool(item.get('embed',False)),'font_face_declared':True,'available':True}
        if item.get('embed'):
            if item.get('embedding_authorized') is not True:raise ValueError('font embedding must be explicitly authorized')
            if not item.get('sha256'):raise ValueError('embedded font requires a source hash')
            if path.suffix.lower() not in {'.ttf','.otf','.woff','.woff2'}:raise ValueError('embedding a font collection is unsupported; supply a licensed individual font')
            # The caller must also comply with the file's own embedding restrictions.
            try:
                from fontTools.ttLib import TTFont
                font_file=TTFont(str(path),lazy=True)
                flags=getattr(font_file.get('OS/2'),'fsType',0);font_file.close()
                if flags & 0x0002 or flags & 0x0200:raise ValueError('font embedding is restricted by the font file')
            except ImportError:
                raise ValueError('fontTools is required to verify embedding restrictions')
            mime={'.ttf':'font/ttf','.otf':'font/otf','.woff':'font/woff','.woff2':'font/woff2'}[path.suffix.lower()]
            src='url("data:'+mime+';base64,'+base64.b64encode(payload).decode()+'")'
        else:
            # A family-only local("Arial") can select Regular even in a bold
            # @font-face. Use exact face names, then the explicitly supplied file.
            face_names=[]
            try:
                from fontTools.ttLib import TTFont
                font_file=TTFont(str(path),fontNumber=item.get('index',0),lazy=True)
                for name_id in (6,4):
                    name=font_file['name'].getDebugName(name_id)
                    if name and name not in face_names:face_names.append(name)
                font_file.close()
            except (ImportError,OSError):pass
            sources=['local('+json.dumps(name)+')' for name in face_names]
            if path.suffix.lower() not in {'.ttc','.otc'}:sources.append('url('+json.dumps(path.as_uri())+')')
            if not sources:raise ValueError('font collection requires an exact local face name')
            src=','.join(sources)
        css.append('@font-face{font-family:'+json.dumps(family)+';font-style:'+style+';font-weight:'+str(weight)+';src:'+src+';}')
        declarations[key]=resolved
    return declarations,'\n'.join(css)


def resolve_font(family='Arial, sans-serif',weight=400,style='normal',declarations=None):
    names=family_list(family);declarations=declarations or {}
    generics={'sans-serif':'Arial','serif':'Times New Roman','monospace':'Courier New','cursive':'Apple Chancery','fantasy':'Chalkduster','system-ui':'Arial'}
    for order,name in enumerate(names):
        key=(name.casefold(),weight,style)
        if key in declarations:return {**declarations[key],'requested_family':names[0],'resolved_family':name,'fallback_used':order>0}
        # A declared face may be synthesized by browsers; record it rather than hiding it.
        faces=[v for k,v in declarations.items() if k[0]==name.casefold()]
        if faces:
            selected=min(faces,key=lambda f:abs(f['weight']-weight)+(1000 if f['style']!=style else 0))
            return {**selected,'requested_family':names[0],'resolved_family':name,'fallback_used':order>0,'synthesized_style':True}
        actual=generics.get(name.casefold(),name)
        matches=[item for item in _inventory() if item['family'].casefold()==actual.casefold()]
        if matches:
            def score(item):
                lower=item['style'].lower();bold=any(k in lower for k in ['bold','black','heavy','demi']);italic=any(k in lower for k in ['italic','oblique'])
                return (bold!=(weight>=600))*10+(italic!=(style=='italic'))*10+len(lower)*.001
            selected=min(matches,key=score)
            return {**selected,'requested_family':names[0],'resolved_family':selected['family'],'embedded':False,'fallback_used':order>0,'generic_requested':name.casefold() in generics}
    return {'requested_family':names[0],'resolved_family':None,'available':False,'embedded':False,'fallback_used':False}


def measurement_font(obj,declarations=None):
    resolved=resolve_font(obj.get('font_family','Arial, sans-serif'),obj.get('font_weight',400),obj.get('font_style','normal'),declarations)
    if not resolved['available']:raise ValueError('SVG measurement font unavailable: '+resolved['requested_family'])
    size=obj.get('font_size',24);scale=4
    return ImageFont.truetype(resolved['path'],round(size*scale),index=resolved.get('index',0)),scale


def wrap_lines(text,obj,width,declarations=None):
    font,scale=measurement_font(obj,declarations);lines=[]
    for paragraph in str(text).split('\n'):
        line=''
        for word in paragraph.split(' '):
            candidate=(line+' '+word).strip()
            if line and font.getlength(candidate)/scale>width:
                lines.append(line);line=word
            else:line=candidate
        lines.append(line)
    return lines


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out');parser.add_argument('--font-root',action='append',default=[]);args=parser.parse_args(argv)
    result={'fonts':font_inventory(args.font_root),'notice':'Local availability only. System fonts are not copied or licensed for redistribution by this inventory.'}
    payload=json.dumps(result,ensure_ascii=False,indent=2)
    if args.out:Path(args.out).write_text(payload)
    else:print(payload)


if __name__=='__main__':main()

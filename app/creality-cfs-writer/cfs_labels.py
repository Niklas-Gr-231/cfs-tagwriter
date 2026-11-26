# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Deterministic 40 x 30 mm PNG labels from confirmed profile values."""
from copy import deepcopy
from decimal import Decimal,InvalidOperation
from functools import lru_cache
from pathlib import Path
import hashlib
import io
import json
import os
import re
import tempfile

from cfs_nozzles import split_manufacturer,NOZZLES
DEFAULT_PLATE='Glatte / High-Temp-Platte'
PLATE_PREFERENCE_REVISION=2
PLATES={'Texturierte PEI-Platte':'textured_plate_temp','Glatte / High-Temp-Platte':'hot_plate_temp',
        'Engineering-Platte':'eng_plate_temp','Cool Plate':'cool_plate_temp'}
MODELS={'F012':'K2 Pro','F008':'K2 Plus','F018':'Creality Hi','F001':'K1'}
ASSETS=Path(__file__).with_name('label-assets')


def scalar(value):
    if isinstance(value,list):
        if len(value)!=1:return None
        return scalar(value[0])
    if value is None or isinstance(value,(dict,bool)):return None
    text=str(value).strip()
    return None if text.casefold() in ('','nil','none','null','nan','inf','infinity') else text


def decimal_text(value):
    text=scalar(value)
    if text is None:return None
    try:
        number=Decimal(text)
        if not number.is_finite() or number<0:return None
        result=format(number,'f')
        if '.' in result:result=result.rstrip('0').rstrip('.')
        return result.replace('.',',')
    except InvalidOperation:return None


def temperature(params,key):
    normal=decimal_text(params.get(key));first=decimal_text(params.get(key+'_initial_layer'))
    if normal is None:return ('1.L. '+first+' °C') if first is not None else 'n. a.'
    return (first+'→'+normal if first is not None and first!=normal else normal)+' °C'


def document(profile,printer=None,scope=''):
    printer=printer or {}
    record=profile.get('record') or {};base=record.get('base') or {}
    params=deepcopy(profile.get('resolved') or record.get('kvParam') or {})
    if not isinstance(params,dict):raise ValueError('Aufgelöste Profilwerte fehlen.')
    name=str(profile.get('name') or base.get('name') or params.get('name') or '').strip()
    if not name:raise ValueError('Profilname fehlt.')
    from cfs_nozzles import manufacturer_value
    raw_brand=manufacturer_value({'resolved':params,'raw_brand':profile.get('raw_brand'),'brand':profile.get('brand') or base.get('brand')})
    brand,nozzle=split_manufacturer(raw_brand)
    diameter=scalar(record.get('nozzleDiameter')) or scalar(printer.get('nozzle_diameter'))
    model=record.get('printerIntName') or printer.get('printer_int_name')
    identity=profile.get('identity') or profile.get('profile_setting_id') or profile.get('material_id')
    if not identity:raise ValueError('Dauerhafte Profilkennung fehlt.')
    canonical=json.dumps({'params':params,'name':name,'brand':raw_brand,'model':model,'diameter':diameter},sort_keys=True,ensure_ascii=False,allow_nan=False)
    fingerprint=hashlib.sha256(canonical.encode()).hexdigest()
    key=hashlib.sha256((str(scope)+'|'+str(identity)+'|'+str(model)+'|'+str(diameter)).encode()).hexdigest()
    from cfs_compatibility import model_info
    printer_info = model_info(model)
    return {'key':key,'profile_id':str(identity),'code':str(profile.get('material_id','')),
        'printer_manufacturer':printer_info['manufacturer'],'printer_model':printer_info['model'],
        'name':name,'brand':brand or 'Hersteller n. a.','raw_brand':raw_brand,'nozzle_code':nozzle,
        'nozzle_type':NOZZLES.get(nozzle,'nicht erfasst'),'model':MODELS.get(str(model),str(model or 'Drucker n. a.')),
        'diameter':decimal_text(diameter),'color':str(profile.get('color') or scalar(params.get('default_filament_colour')) or scalar(base.get('colors')) or ''),
        'type':str(profile.get('type') or scalar(params.get('filament_type')) or base.get('meterialType') or 'Filament'),
        'values_source':profile.get('values_source'),'origin':profile.get('origin','cloud'),'update_status':profile.get('update_status',''),
        'params':params,'fingerprint':fingerprint}


def load_documents(registry,codes=None):
    before=registry.printer
    if registry.sync_source=='printer_cloud':
        snapshot=registry.cloud_catalog(fresh=True);profiles=snapshot['profiles']
        printer=dict(before,printer_int_name=snapshot.get('printer_int_name'),nozzle_diameter=snapshot.get('nozzle_diameter'))
        chosen=list(profiles) if codes is None else list(codes)
        if not chosen or not set(chosen).issubset(profiles):raise ValueError('Gewählte Profile sind nicht vollständig verfügbar. Druckerprofile aktualisieren.')
        result=[document(profiles[code],printer,before.get('ip','')) for code in chosen]
    else:
        profiles=registry.resolve_all();chosen=set(codes) if codes is not None else {p['entry']['material_id'] for p in profiles}
        result=[]
        for row in profiles:
            if row['entry']['material_id'] not in chosen:continue
            m=row['material'];result.append(document(dict(m,material_id=m['id'],resolved=row['resolved']),before,before.get('ip','')))
        if not result or len(result)!=len(chosen):raise ValueError('Gewählte lokale Profile sind nicht vollständig verfügbar.')
    if registry.printer!=before:raise ValueError('Druckerauswahl während des Etikettenabrufs geändert.')
    return result


def documents_from_bundle(bundle,scope=''):
    from cfs_transfer_core import validate_bundle
    bundle=validate_bundle(bundle);result=[]
    for p in bundle['profiles']:
        result.append(document(dict(p,origin='local' if p.get('origin_kind')=='local' else 'imported',update_status='export_snapshot'),bundle['source'],scope))
    return result


def label_values(doc,options=None):
    options=options or {};params=doc['params'];plate=options.get('plate',DEFAULT_PLATE)
    if plate not in PLATES:raise ValueError('Unbekannte Druckplatte.')
    flow=decimal_text(params.get('filament_flow_ratio'));vol=decimal_text(params.get('filament_max_volumetric_speed'))
    pa=decimal_text(params.get('pressure_advance'));flag=params.get('enable_pressure_advance');enabled='1' if flag is True else '0' if flag is False else scalar(flag)
    if pa is not None and enabled=='0':pa+=' (aus)'
    cost=decimal_text(params.get('filament_cost'))
    currency=str(options.get('currency','€')).strip()
    if currency not in ('€','$','£','CHF','EUR','USD','GBP'):raise ValueError('Währung bitte aus der Liste auswählen.')
    display_type=doc['type']
    if doc['brand'].casefold()=='sunlu' and doc['type'].casefold()=='petg' and re.search(r'\bHISPD\b',doc['name'],re.IGNORECASE):
        display_type='PETG High Speed Matte'
    plate_key=PLATES[plate]
    unsupported=any(decimal_text(params.get(k))=='0' for k in (plate_key,plate_key+'_initial_layer'))
    return {'name':str(options.get('display_name') or doc['name']).strip(),
        'brand':doc['brand'],'nozzle_type':doc['nozzle_type'],'nozzle_code':doc['nozzle_code'],
        'model':doc['model'],'diameter':doc['diameter'],'type':doc['type'],'display_type':display_type,'color':doc['color'],'code':doc['code'],
        'nozzle_temperature':temperature(params,'nozzle_temperature'),
        'bed_temperature':'n. a.' if unsupported else temperature(params,plate_key),'plate':plate,
        'bed_temperature_key':plate_key,'plate_unsupported':unsupported,
        'flow':flow or 'n. a.','volumetric_speed':vol+' mm³/s' if vol is not None else 'n. a.',
        'pressure_advance':pa or 'n. a.','price':cost+' '+currency+'/kg' if cost is not None else 'n. a.',
        'show_pa':bool(options.get('show_pa',True)),'show_price':bool(options.get('show_price',True)),
        'profile_fingerprint':doc['fingerprint'],'source':doc['origin'],'update_status':doc['update_status']}


@lru_cache(maxsize=96)
def font(size,bold=False):
    try:
        from PIL import ImageFont
    except ImportError as error:raise ValueError('Für Etiketten fehlt Pillow. Die neue Einzeldatei starten und die Paket-Einrichtung verwenden; unter Mint alternativ python3-pil installieren.') from error
    return ImageFont.truetype(str(ASSETS/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')),max(1,int(size)))


def render_image(doc,options=None):
    try:
        from PIL import Image,ImageDraw
    except ImportError as error:raise ValueError('Pillow fehlt. Die neue Einzeldatei verwenden oder unter Mint python3-pil installieren.') from error
    options=options or {};dpi=int(options.get('dpi',300))
    if dpi not in (203,300,600):raise ValueError('Unterstützte Auflösungen: 203, 300 oder 600 dpi.')
    values=label_values(doc,options);scale=dpi/25.4
    width,height=round(40*scale),round(30*scale)
    image=Image.new('RGB',(width,height),'white');draw=ImageDraw.Draw(image);measurements=[]
    def text(text,x,y,w,size=2.1,bold=False,minimum=1.8,color='black'):
        selected=None
        for step in range(round(size*100),round(minimum*100)-1,-5):
            selected=font(round(step/100*scale),bold)
            if draw.textlength(text,font=selected)<=w*scale:break
        else:raise ValueError('Text passt bei lesbarer Schrift nicht auf 40 × 30 mm: '+text+'. Etikettenname kürzen oder optionale Angaben ausblenden.')
        bbox=draw.textbbox((round(x*scale),round(y*scale)),text,font=selected,anchor='lt')
        if bbox[0]<0 or bbox[1]<0 or bbox[2]>width or bbox[3]>height:raise ValueError('Etikettenlayout überschreitet die Druckfläche.')
        draw.text((round(x*scale),round(y*scale)),text,font=selected,fill=color,anchor='lt');measurements.append(bbox)
    text(values['brand'],1.3,1.05,26,3.1,True,1.9)
    text(values['color'] or 'RGB n. a.',28,1.7,10.7,1.8,False,1.65)
    draw.rectangle((round(1.3*scale),round(5*scale),round(38.7*scale),round(7.5*scale)),fill='white',outline='black',width=max(1,round(.15*scale)))
    text(values['display_type']+'  ·  '+(values['code'] or 'Profilwerte'),2,5.3,36,1.85,True,1.7)
    # Wrap descriptive text only. Numeric calibration values are never truncated.
    f=font(round(2.05*scale),True);words=values['name'].split();full=' '.join(words)
    if draw.textlength(full,font=f)<=37.4*scale:lines=[full]
    else:
        candidates=[]
        for split in range(1,len(words)):
            pair=[' '.join(words[:split]),' '.join(words[split:])]
            lengths=[draw.textlength(line,font=f) for line in pair]
            if max(lengths)<=37.4*scale:candidates.append((abs(lengths[0]-lengths[1]),pair))
        lines=min(candidates,key=lambda p:p[0])[1] if candidates else [full,'','']
    if len(lines)>2:raise ValueError('Etikettenname ist zu lang für zwei Zeilen. Einen kürzeren Etikettennamen eingeben; das Profil bleibt unverändert.')
    for n,line in enumerate(lines):text(line,1.3,8.3+n*2.5,37.4,2.05,True)
    text(values['model']+' · Ø '+(values['diameter'] or 'n. a.')+' mm',1.3,13.8,37.4,1.95,True)
    text('Düse: '+values['nozzle_type']+(' ('+values['nozzle_code']+')' if values['nozzle_code'] else ''),1.3,16.4,37.4,1.95)
    draw.line((round(1.3*scale),round(19.2*scale),round(38.7*scale),round(19.2*scale)),fill='black',width=max(1,round(.1*scale)))
    text('Temp. '+values['nozzle_temperature'],1.3,20.1,18,2.0,True,1.7)
    text('Bett '+values['bed_temperature'],21,20.1,17.7,2.0,True,1.7)
    text('Flow '+values['flow'],1.3,22.9,18,2.0,False,1.7)
    text('Vol. '+values['volumetric_speed'],21,22.9,17.7,2.0,False,1.7)
    if values['show_pa']:text('PA '+values['pressure_advance'],1.3,25.7,18,2.0,False,1.7)
    if values['show_price']:text(values['price'],21,25.7,17.7,2.0,False,1.7)
    return image,values,measurements


def render_png(doc,options=None):
    options=options or {};dpi=int(options.get('dpi',300))
    image,values,measurements=render_image(doc,options)
    from PIL import PngImagePlugin
    metadata=PngImagePlugin.PngInfo();metadata.add_text('CFS Label',json.dumps(values,ensure_ascii=False,sort_keys=True));metadata.add_text('Print size','40 x 30 mm; print at 100%, no fit-to-page')
    raw=io.BytesIO();image.save(raw,format='PNG',dpi=(dpi,dpi),pnginfo=metadata)
    return raw.getvalue(),values,measurements


def safe_filename(doc):
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',doc['name']).strip(' .')[:90] or 'Filament'
    return (doc['code']+'-' if doc['code'] else '')+name+'-'+(doc['nozzle_code'] or 'Duesentyp-offen')+'.png'


def write_png(path,raw,overwrite=False):
    path=Path(path)
    if path.suffix.casefold()!='.png':raise ValueError('Etiketten bitte als .png speichern.')
    if path.exists() and not overwrite:raise FileExistsError('Datei existiert bereits: '+str(path))
    descriptor,temp=tempfile.mkstemp(prefix='.cfs-label-',suffix='.png',dir=str(path.parent))
    try:
        with os.fdopen(descriptor,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        if path.exists() and not overwrite:raise FileExistsError('Datei wurde zwischenzeitlich angelegt: '+str(path))
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def documents_from_slicer(paths,dependencies=None):
    """Read current slicer files without requiring an NFC assignment or login."""
    from cfs_local_profiles import load_resolved
    from cfs_codec import _slicer_parent
    from cfs_registry import read_profile_info
    selected={Path(p).expanduser().resolve() for p in paths};all_paths=set(selected);pending=list(selected)
    while pending:
        path=pending.pop()
        raw=json.loads(path.read_text(encoding='utf-8-sig'));parent=scalar(raw.get('inherits'))
        if parent:
            found=_slicer_parent(parent,path)
            if found is not None and found.resolve() not in all_paths:
                if len(all_paths)>100:raise ValueError('Zu viele Profilabhängigkeiten.')
                all_paths.add(found.resolve());pending.append(found.resolve())
    resolved=load_resolved(sorted(all_paths),dependencies);result=[]
    aliases={'F012':('Creality K2 Pro',),'F008':('Creality K2 Plus',),'F018':('Creality Hi',),'F001':('Creality K1',)}
    from cfs_compatibility import CREALITY, ANYCUBIC
    known_names = {name for names in aliases.values() for name in names}
    for brand, models in (('Creality', CREALITY), ('Anycubic', ANYCUBIC)):
        for model in models:
            name = brand+' '+model
            if name not in known_names:
                aliases[name] = (name,)
    for path,raw,params in resolved:
        if path not in selected:continue
        if raw.get('from')!='User' and 'filament_settings_id' not in raw:raise ValueError('Bitte eigene Filamentprofile auswählen: '+path.name)
        candidates=set()
        for value in params.get('compatible_printers',[]):
            if not isinstance(value,str):continue
            for model,names in aliases.items():
                for name in names:
                    match=re.fullmatch(re.escape(name)+r'\s+(0\.[0-9]+)\s+nozzle',value,re.IGNORECASE)
                    if match:candidates.add((model,match.group(1)))
        if len(candidates)!=1:raise ValueError('Druckermodell und Düsendurchmesser sind im Profil nicht eindeutig: '+path.name+'. Ein passendes Druckerprofil bzw. einen vollständigen CFS-Export verwenden.')
        model,diameter=next(iter(candidates))
        info=path.with_suffix('.info');setting=read_profile_info(info).get('setting_id') if info.exists() else None
        identity=setting or hashlib.sha256(str(path).encode()).hexdigest()
        profile={'profile_setting_id':identity,'name':params.get('name',raw.get('name')),
            'resolved':params,'origin':'slicer','update_status':'local_file'}
        result.append(document(profile,{'printer_int_name':model,'nozzle_diameter':diameter},str(path.parent)))
    return result

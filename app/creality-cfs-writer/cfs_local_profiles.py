# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Strict Creality Print JSON inheritance and cloud-independent local import."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from cfs_transfer_core import FORMAT,validate_bundle,validate_record

MODELS={'F012':('Creality K2 Pro','K2 Pro'),'F008':('Creality K2 Plus','K2 Plus'),
        'F018':('Creality Hi',),'F001':('Creality K1',)}
META={'inherits','name','filament_settings_id','filament_id','from','version','type',
      'compatible_printers','compatible_printers_condition','compatible_prints','compatible_prints_condition',
      'instantiation','setting_id','cfs_local_id','filament_notes','description'}


def read_json(path):
    path=Path(path)
    with path.open('rb') as stream:raw=stream.read(4_000_001)
    if len(raw)>4_000_000:raise ValueError('Profildatei zu groß: '+path.name)
    data=json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data,dict):raise ValueError('Keine einzelne Creality-Print-Profil-JSON: '+path.name)
    return data


def scalar(value):
    if isinstance(value,list):
        if len(value)!=1:raise ValueError('Profilwert ist nicht für einen einzelnen Extruder aufgelöst.')
        return scalar(value[0])
    if isinstance(value,bool):return '1' if value else '0'
    if isinstance(value,(str,int,float)):return str(value)
    raise ValueError('Ungültiger Profilwert.')


def load_resolved(paths,dependencies=None):
    paths=[Path(p).expanduser().resolve() for p in paths]
    candidates=set(paths)
    for parent in {p.parent for p in paths}:candidates.update(parent.glob('*.json'))
    if dependencies:
        for count,p in enumerate(Path(dependencies).expanduser().resolve().rglob('*.json')):
            if count>=10000:raise ValueError('Abhängigkeitsordner zu groß; gezielt den Profilordner auswählen.')
            candidates.add(p.resolve())
    names={};cache={}
    for p in sorted(candidates):
        try:data=read_json(p)
        except (ValueError,OSError):
            if p in paths:raise
            continue
        cache[p]=data
        if isinstance(data.get('name'),str):names.setdefault(data['name'],[]).append(p)
    resolved_cache={};heights={}
    def resolve(p,stack=()):
        if p in stack or len(stack)>=32:raise ValueError('Zirkuläre oder zu tiefe Profilvererbung: '+p.name)
        if p in resolved_cache:
            if len(stack)+heights[p]>32:raise ValueError('Zirkuläre oder zu tiefe Profilvererbung: '+p.name)
            return resolved_cache[p]
        data=cache[p];parent=scalar(data.get('inherits','')).strip();result={};height=1
        if parent:
            found=names.get(parent,[])
            if len(found)!=1:
                raise ValueError('Abhängigkeit „'+parent+'“ '+('fehlt' if not found else 'ist mehrdeutig')+'. Abhängigkeitsordner mit den Systemprofilen auswählen.')
            result.update(resolve(found[0],stack+(p,)));height+=heights[found[0]]
        result.update(data);resolved_cache[p]=result;heights[p]=height
        return result
    return [(p,cache[p],dict(resolve(p))) for p in paths]



def identity_for(path,raw,known):
    explicit=raw.get('cfs_local_id')
    if explicit:
        try:return uuid.UUID(str(explicit)).hex
        except ValueError as error:raise ValueError('Ungültige cfs_local_id.') from error
    info=path.with_suffix('.info')
    if info.is_file():
        values=dict(line.split('=',1) for line in info.read_text(encoding='utf-8-sig').splitlines() if '=' in line)
        setting=values.get('setting_id','').strip()
        if re.fullmatch(r'(?:[0-9a-f]{24}|[0-9a-f]{32}|[0-9a-f-]{36})',setting):
            # This is a local namespace, never a fabricated cloud account or login.
            return uuid.uuid5(uuid.NAMESPACE_URL,'cfs-local-creality-print:'+setting).hex
    key=str(path)
    if key not in known:known[key]=uuid.uuid4().hex
    return known[key]


def compatible(profile,model,nozzle):
    printers=profile.get('compatible_printers')
    if not isinstance(printers,list) or not printers:
        raise ValueError('Explizite kompatible Drucker fehlen; eine Bedingungsformel allein reicht nicht als Modell-/Düsennachweis.')
    labels=MODELS.get(model,(model,))
    for printer in printers:
        if not isinstance(printer,str):continue
        lower=printer.casefold()
        if any(label.casefold()+' ' in lower+' ' for label in labels) and re.search(r'(?<![0-9.])'+re.escape(nozzle)+r'(?:\s*mm)?\s+nozzle\b',lower):
            return
    raise ValueError('Profil passt nicht zum Zielmodell '+model+' mit Düse '+nozzle+' mm.')


def resolved_profiles(paths,dependencies=None):
    from cfs_codec import _slicer_parent
    selected={Path(p).expanduser().resolve() for p in paths};all_paths=set(selected);pending=list(selected)
    while pending:
        path=pending.pop();raw=read_json(path);parent=scalar(raw.get('inherits','')).strip()
        if parent:
            found=_slicer_parent(parent,path)
            if found and found.resolve() not in all_paths:
                if len(all_paths)>10000:raise ValueError('Zu viele Profilabhängigkeiten.')
                all_paths.add(found.resolve());pending.append(found.resolve())
    return [(p,raw,params) for p,raw,params in load_resolved(sorted(all_paths),dependencies) if p in selected]


def record_for_slicer(resolved,database,model,nozzle,code):
    compatible(resolved,model,nozzle);kind=scalar(resolved.get('filament_type',''))
    templates=[r for r in database.get('result',{}).get('list',[]) if r.get('printerIntName')==model
        and r.get('nozzleDiameter')==[nozzle] and 'userMaterial' not in r
        and r.get('base',{}).get('name')=='Generic '+kind and r['base'].get('meterialType')==kind
        and not str(r['base'].get('id','')).startswith('99')]
    if len(templates)!=1:raise ValueError('Keine eindeutige native Vorlage für '+kind+'.')
    template=templates[0]
    required=(set(template['kvParam'])-META)|{'name','default_filament_colour','filament_vendor','filament_type',
        'filament_density','filament_diameter','filament_soluble','filament_is_support'}
    missing=required-set(resolved)
    native_empty={k:template['kvParam'][k] for k in missing if k=='material_flow_temp_graph' and template['kvParam'][k]==''}
    missing-=native_empty.keys()
    if missing:raise ValueError('Aufgelöste Druckwerte fehlen: '+', '.join(sorted(missing))+'. Keine Standardwerte eingesetzt.')
    from cfs_profile_sync import make_record
    record=make_record(template,resolved,code)
    record['kvParam']={k:scalar(v) for k,v in resolved.items() if k not in META}
    record['kvParam'].update(native_empty);record['kvParam']['filament_settings_id']=scalar(resolved['name'])
    validate_record(record,model,nozzle)
    return record


def local_bundle(paths,database,model,nozzle,identities,dependencies=None):
    profiles=[];ids=set()
    for number,(path,raw,resolved) in enumerate(resolved_profiles(paths,dependencies)):
        if not (raw.get('from')=='User' or 'inherits' in raw or 'filament_settings_id' in raw):raise ValueError('Kein eigenes Filamentprofil: '+path.name)
        code=str(99021+number);record=record_for_slicer(resolved,database,model,nozzle,code)
        local_id=identity_for(path,raw,identities)
        if local_id in ids:raise ValueError('Dieselbe lokale Profilidentität wurde mehrfach ausgewählt.')
        ids.add(local_id)
        profiles.append({'material_id':code,'origin_kind':'local','origin_account_id':None,
            'origin_setting_id':local_id,'identity':'local:'+local_id,'record':record,
            'source_profile':deepcopy(resolved)})
    return validate_bundle({'format':FORMAT,'schema_version':2,
        'source':{'printer_int_name':model,'nozzle_diameter':nozzle},'profiles':profiles})


def prepare_local_import(registry,paths,password,dependencies=None,*,ssh_factory=None):
    catalog=registry.cloud_catalog(fresh=True)
    if catalog.get('schema_version')!=2:
        if catalog.get('service_version')=='2.0.0' and catalog.get('updates_deferred'):
            raise ValueError('Dienst 2.0.0 ist installiert; die Umstellung wartet auf das Druckende. Lokalen Import anschließend erneut öffnen.')
        raise ValueError('Für lokale Profile zuerst den Druckerdienst 2.0.0 unter Einstellungen → Druckersoftware installieren bzw. reparieren.')
    if ssh_factory is None:
        from cfs_profile_sync import PrinterSSH
        ssh_factory=PrinterSSH
    before=registry.printer
    remote=ssh_factory(before['ip'],Path(registry.path).parent/'state/known_hosts',password or None)
    from cfs_profile_sync import connection_session,write_json
    with connection_session(remote):
        status=remote.read_status()
        actual=str(status.get('configfile',{}).get('settings',{}).get('extruder',{}).get('nozzle_diameter',''))
        if actual!=catalog['nozzle_diameter']:
            raise ValueError('Aktuelle Druckerdüse passt nicht zum eingerichteten Profilbestand. Einrichtung und passende Profile prüfen.')
        _,database=remote.read_database()
    if {r.get('printerIntName') for r in database.get('result',{}).get('list',[])}!={catalog['printer_int_name']}:
        raise ValueError('Druckermodell im aktuellen Katalog passt nicht zur Einrichtung.')
    identity_path=Path(registry.path).parent/'local-profile-identities.json'
    from cfs_locking import locked_file
    with identity_path.with_suffix('.lock').open('a+') as lock,locked_file(lock):
        known=json.loads(identity_path.read_text()) if identity_path.exists() else {}
        bundle=local_bundle(paths,database,catalog['printer_int_name'],catalog['nozzle_diameter'],known,dependencies)
        write_json(identity_path,known);identity_path.chmod(0o600)
    if registry.printer!=before:raise ValueError('Druckerauswahl während des lokalen Imports geändert.')
    # Raw slicer files have no source RFID code. Preserve known target codes,
    # including disabled identities, instead of deriving them from list order.
    target_codes={p['identity']:p['material_id'] for p in catalog['profiles'].values() if p.get('identity')}
    target_codes.update({p['source_identity']:p['material_id'] for p in registry.entries if p.get('source_identity')})
    used=set(catalog.get('used_material_ids',[]))|set(target_codes.values())
    for profile in bundle['profiles']:
        code=target_codes.get(profile['identity'])
        if code is None:
            code=next((str(n) for n in range(99021,100000) if str(n) not in used),None)
            if code is None:raise ValueError('Kein freier Materialcode.')
        used.add(code);profile['material_id']=code;profile['record']['base']['id']=code
    return validate_bundle(bundle)

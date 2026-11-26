# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Saved Slicer JSON -> checked printer preview, with permanent Slicer priority.

Never writes Slicer files or Cloud APIs. Only app-local source IDs/settings and
explicitly confirmed printer imports are written. No profile-name matching.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,json,re,uuid
from cfs_local_profiles import resolved_profiles,record_for_slicer
from cfs_profile_sync import PrinterSSH,connection_session,write_json
from cfs_profile_transfer import transfer
from cfs_transfer_core import FORMAT,validate_bundle


def file_hash(path):
    raw=Path(path).read_bytes()
    if len(raw)>4_000_000:raise ValueError('Quelldatei zu groß: '+Path(path).name)
    return hashlib.sha256(raw).hexdigest()


def checks_for(paths,dependencies=None):
    from cfs_codec import _slicer_parent
    checks={};pending=list({Path(p).resolve() for p in paths})
    if dependencies:pending.extend(Path(dependencies).resolve().rglob('*.json'))
    for parent in {p.parent for p in pending}:pending.extend(parent.glob('*.json'))
    seen=set()
    while pending:
        p=pending.pop().resolve()
        if p in seen:continue
        seen.add(p)
        if len(seen)>10000:raise ValueError('Zu viele Quelldateien; gezielt den Profilordner wählen.')
        checks[str(p)]=file_hash(p)
        if p.suffix=='.json':
            try:raw=json.loads(p.read_text(encoding='utf-8-sig'))
            except (ValueError,OSError):continue
            parent=raw.get('inherits') if isinstance(raw,dict) else None
            if isinstance(parent,str):
                found=_slicer_parent(parent,p)
                if found:pending.append(found)
            info=p.with_suffix('.info')
            checks[str(info)]=file_hash(info) if info.exists() else None
    return checks


def verify_sources(checks):
    for path,expected in checks.items():
        p=Path(path)
        if (file_hash(p) if p.exists() else None)!=expected:
            raise ValueError('Slicerdateien wurden seit der Vorschau geändert. Bitte erneut prüfen: '+p.name)


def info_for(path):
    from cfs_registry import read_profile_info
    info=Path(path).with_suffix('.info')
    return read_profile_info(info) if info.exists() else {}


def prepare(registry,paths,password=None,dependencies=None,*,ssh_factory=None):
    paths=sorted({Path(p).expanduser().resolve() for p in paths})
    if not paths:raise ValueError('Bitte gespeicherte JSON-Filamentprofile auswählen.')
    printer=deepcopy(registry.printer);catalog=registry.cloud_catalog(fresh=True)
    version=str(catalog.get('service_version',''))
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or tuple(map(int,version.split('.')))<(2,1,0):
        raise ValueError('Slicer-Vorrang benötigt Druckerdienst 2.1.0. Bitte über „Druckerdienst prüfen / aktualisieren“ manuell installieren.')
    factory=ssh_factory or PrinterSSH
    remote=factory(printer['ip'],Path(registry.path).parent/'state/known_hosts',password or None)
    with connection_session(remote):
        status=remote.read_status();_,database=remote.read_database()
        model,nozzle=catalog['printer_int_name'],catalog['nozzle_diameter']
        actual=str(status.get('configfile',{}).get('settings',{}).get('extruder',{}).get('nozzle_diameter',''))
        if actual!=nozzle:raise ValueError('Aktuelle Druckerdüse passt nicht zum Profilkatalog.')
        if {r.get('printerIntName') for r in database.get('result',{}).get('list',[])}!={model}:raise ValueError('Druckermodell passt nicht zum aktuellen Katalog.')
        checks=checks_for(paths,dependencies)
        resolved=resolved_profiles(paths,dependencies)
        from cfs_locking import locked_file
        identity_path=Path(registry.path).parent/'slicer-source-identities.json'
        with identity_path.with_suffix('.lock').open('a+') as lock,locked_file(lock):
            known=json.loads(identity_path.read_text()) if identity_path.exists() else {'schema_version':1,'files':{}}
            if known.get('schema_version')!=1 or not isinstance(known.get('files'),dict):raise ValueError('Gespeicherte Slicerkennungen sind beschädigt.')
            profiles=[];identities=set();used=set(catalog.get('used_material_ids',[]))
            active={p.get('identity'):p for p in catalog['profiles'].values()}
            references={}
            for profile in catalog['profiles'].values():
                ref=(str(profile.get('origin_account_id')),profile.get('origin_setting_id')) if profile.get('origin')=='cloud' else None
                source=profile.get('slicer_source') or {}
                if source.get('cloud_account_id') and source.get('cloud_setting_id'):ref=(source['cloud_account_id'],source['cloud_setting_id'])
                if ref:
                    if ref in references and references[ref]['identity']!=profile['identity']:raise ValueError('Mehrere Druckerprofile beanspruchen dieselbe Cloud-ID; Zuordnung zuerst klären.')
                    references[ref]=profile
            details={}
            for path,raw,params in resolved:
                if raw.get('from')!='User' and 'filament_settings_id' not in raw:raise ValueError('Kein eigenes Filamentprofil: '+path.name)
                info=info_for(path);account=str(info.get('user_id',''));cloud_id=str(info.get('setting_id',''))
                if not re.fullmatch(r'[0-9]+',account) or not re.fullmatch(r'[0-9a-f]{24}',cloud_id):account=cloud_id=None
                entry=deepcopy(known['files'].get(str(path),{}))
                if entry.get('cloud_id') and cloud_id and entry['cloud_id']!=cloud_id:entry={}
                if not entry and cloud_id:
                    found=[v for v in known['files'].values() if v.get('cloud_id')==cloud_id and v.get('account')==account]
                    if len(found)==1:entry=deepcopy(found[0])
                if not entry:entry={'file_id':uuid.uuid4().hex}
                target=active.get(entry.get('identity'))
                reference=references.get((account,cloud_id))
                if target and reference and target['identity']!=reference['identity']:
                    raise ValueError('Diese Cloud-ID besitzt bereits einen anderen Materialcode ('+reference['material_id']+'). Die doppelte Zuordnung zuerst in der Profilverwaltung klären; kein automatisches Zusammenlegen.')
                if target is None and entry.get('identity','').startswith('local:'):
                    identity=entry['identity'];origin_kind='local';origin_account=None;origin_sid=identity.split(':',1)[1]
                elif target is not None:
                    identity=target['identity'];origin_kind='local' if target['origin']=='local' else 'cloud';origin_account=target.get('origin_account_id');origin_sid=target.get('origin_setting_id')
                elif (account,cloud_id) in references:
                    target=references[(account,cloud_id)];identity=target['identity'];origin_kind='local' if target['origin']=='local' else 'cloud'
                    origin_account=target.get('origin_account_id');origin_sid=target.get('origin_setting_id')
                else:
                    origin_kind='local';origin_account=None;origin_sid=entry['file_id'];identity='local:'+origin_sid
                if identity in identities:raise ValueError('Mehrere Dateien beanspruchen dieselbe Profilidentität. Bitte gezielt eine Quelldatei auswählen: '+path.name)
                identities.add(identity)
                if target:
                    code=target['material_id']
                    if (target.get('slicer_source') or {}).get('file_id'):entry['file_id']=target['slicer_source']['file_id']
                else:
                    code=next((str(n) for n in range(99001,100000) if str(n) not in used),None)
                    if code is None:raise ValueError('Kein freier Materialcode.')
                used.add(code)
                record=record_for_slicer(params,database,model,nozzle,code)
                if origin_kind=='cloud' and target and target.get('record',{}).get('userMaterial'):
                    record['userMaterial']=target['record']['userMaterial']
                metadata={'schema_version':1,'authority':'slicer','file_id':entry['file_id'],
                    'fingerprint':hashlib.sha256(json.dumps({'raw':raw,'resolved':params},sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest(),
                    'filename':path.name,'cloud_account_id':account,'cloud_setting_id':cloud_id}
                if origin_kind=='cloud':metadata.update(cloud_account_id=origin_account,cloud_setting_id=origin_sid)
                profile={'material_id':code,'origin_kind':origin_kind,'origin_account_id':origin_account,'origin_setting_id':origin_sid,
                    'identity':identity,'record':record,'source_profile':deepcopy(params),'slicer_source':metadata}
                profiles.append(profile)
                previous=target.get('record',{}) if target else {};diff={}
                for section in ('base','kvParam'):
                    before=previous.get(section,{})
                    for key,value in record[section].items():
                        if before.get(key)!=value:diff[section+'.'+key]={'vorher':before.get(key),'Slicer':value}
                details[identity]={'filename':path.name,'changes':diff,'new':target is None}
                entry.update(identity=identity,cloud_id=cloud_id,account=account);known['files'][str(path)]=entry
            verify_sources(checks);write_json(identity_path,known);identity_path.chmod(0o600)
        bundle=validate_bundle({'format':FORMAT,'schema_version':2,'source':{'printer_int_name':model,'nozzle_diameter':nozzle},'profiles':profiles})
        if registry.printer!=printer:raise ValueError('Druckerauswahl während der Vorschau geändert.')
        def reuse_target(address,known_hosts,secret):
            if address!=printer['ip'] or secret!=(password or None):raise ValueError('Druckerauswahl während der Vorschau geändert.')
            return remote
        preview=transfer(registry,bundle,password,ssh_factory=reuse_target)
        verify_sources(checks)
        return {'bundle':bundle,'preview':preview,'source_checks':checks,'details':details,'printer':printer}


def apply(registry,prepared,password=None,*,ssh_factory=None):
    if registry.printer!=prepared['printer']:raise ValueError('Zieldrucker seit der Vorschau geändert.')
    verify_sources(prepared['source_checks'])
    result=transfer(registry,prepared['bundle'],password,preview=prepared['preview'],ssh_factory=ssh_factory)
    try:verify_sources(prepared['source_checks'])
    except (ValueError,OSError):result['source_warning']='Während der Übertragung wurde im Slicer weitergespeichert. Der bestätigte Vorschaustand wurde übertragen; bitte erneut abgleichen.'
    return result

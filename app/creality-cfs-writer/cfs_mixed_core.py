# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Independent local and account-scoped cloud identities. Python 3.9, pure data."""
from copy import deepcopy
import hashlib
import re


def migrate_manifest(manifest, receipt=None):
    result=deepcopy(manifest)
    if result.get('schema_version')==2:
        validate_manifest(result)
        return result
    if result.get('schema_version')!=1:
        raise ValueError('Unbekanntes Profilmanifest; keine Migration ausgeführt.')
    account=result.get('account_id')
    if result.get('profiles') and (not isinstance(account,str) or not re.fullmatch(r'[0-9]+',account)):
        raise ValueError('Die Herkunft bestehender Cloud-Zuordnungen ist nicht nachgewiesen.')
    if receipt and result.get('profiles') and receipt.get('account_id',account)!=account:
        raise ValueError('Besitznachweis und ursprüngliches Cloudkonto widersprechen sich.')
    for profile in result.get('profiles',[]):
        profile['account_id']=account
        profile['cloud_setting_id']=profile['profile_setting_id']
    result['schema_version']=2
    result.setdefault('imported_profiles',[])
    validate_manifest(result)
    return result


def cloud_identity(profile):
    return 'cloud:'+profile['account_id']+':'+profile.get('cloud_setting_id',profile['profile_setting_id'])


def validate_manifest(manifest):
    from cfs_transfer_core import CODE,SID,MODEL,imported_exports
    if manifest.get('schema_version')!=2 or not MODEL.fullmatch(str(manifest.get('printer_int_name',''))):
        raise ValueError('Unbekanntes lokales Profilmanifest oder Druckermodell.')
    if not re.fullmatch(r'0\.(4|6|8)',str(manifest.get('nozzle_diameter',''))):
        raise ValueError('Nicht unterstützter Düsendurchmesser.')
    profiles=manifest.get('profiles')
    if not isinstance(profiles,list):raise ValueError('Cloud-Zuordnungsliste fehlt.')
    codes,sids,identities=set(),set(),set()
    for p in profiles:
        if (not isinstance(p,dict) or not CODE.fullmatch(str(p.get('material_id','')))
            or not SID.fullmatch(str(p.get('profile_setting_id','')))
            or not SID.fullmatch(str(p.get('cloud_setting_id','')))
            or not re.fullmatch(r'[0-9]+',str(p.get('account_id','')))
            or not isinstance(p.get('enabled',True),bool)):
            raise ValueError('Ungültige kontogebundene Cloud-Zuordnung.')
        if 'slicer_override' in p:
            from cfs_slicer_policy import validate_source,cloud_reference
            from cfs_transfer_core import validate_record
            override=p['slicer_override'];validate_source(override.get('source'))
            record=validate_record(override.get('record'),manifest['printer_int_name'],manifest['nozzle_diameter'])
            if record['base']['id']!=p['material_id'] or cloud_reference(override['source'])!=cloud_identity(p):
                raise ValueError('Slicer-Priorität gehört zu einer anderen Cloudidentität.')
        identity=cloud_identity(p)
        if p['material_id'] in codes or p['profile_setting_id'] in sids or identity in identities:
            raise ValueError('Doppelte Profilidentität oder Materialkennung.')
        codes.add(p['material_id']);sids.add(p['profile_setting_id']);identities.add(identity)
    imported=imported_exports(manifest)
    if identities & {p['identity'] for p in imported}:
        raise ValueError('Eine Profilidentität ist zugleich live verknüpft und als Kopie registriert.')


def exported_record(profile,record,origin,status,reason='',source_file=None):
    from cfs_transfer_core import validate_record
    base,kv=record['base'],record['kvParam']
    code=profile['material_id']
    identity=cloud_identity(profile) if origin=='cloud' else profile['identity']
    account=profile.get('account_id') if origin=='cloud' else profile.get('origin_account_id')
    sid=profile.get('cloud_setting_id') if origin=='cloud' else profile.get('origin_setting_id')
    return {'material_id':code,'profile_setting_id':profile['profile_setting_id'],
        'identity':identity,'origin':origin,'origin_account_id':account,'origin_setting_id':sid,
        'name':base['name'],'brand':base['brand'],'type':kv['filament_type'],
        'color':base['colors'][0].upper(),'source_file':source_file or ('local://' if origin=='local' else 'imported://')+identity,
        'update_status':status,'update_reason':reason,'record':deepcopy(record),
        'resolved':dict(deepcopy(kv),name=base['name']),
        'profile_metadata':{'nozzle_temperature':str(kv['nozzle_temperature']),
            'flow_ratio':str(kv['filament_flow_ratio']),'pressure_advance':str(kv['pressure_advance'])}}


def build_mixed(database,index,cloud_files,manifest,receipt=None,cloud_issue=''):
    from cfs_transfer_core import digest,imported_exports,validate_record,CODE
    from cloud_alias_core import _index_records,_active_index,_native_record,DeferredSyncError
    validate_manifest(manifest)
    catalog=database.get('result',{})
    old=catalog.get('list')
    if not isinstance(old,list) or not isinstance(catalog.get('count'),int) or isinstance(catalog.get('count'),bool) or catalog.get('count')!=len(old) or 'version' not in catalog:
        raise ValueError('Native Materialdatenbank ist unvollständig.')
    if any(not isinstance(p,dict) or not re.fullmatch(r'[A-Za-z0-9]{5}',str(p.get('base',{}).get('id',''))) for p in old):
        raise ValueError('Ungültige native Materialeinträge.')
    if any(r.get('printerIntName')!=manifest['printer_int_name'] for r in old):
        raise ValueError('Druckermodell im aktuellen Materialkatalog passt nicht zur Einrichtung.')
    receipt=deepcopy(receipt or {'schema_version':1,'owned_entries':{}})
    if receipt.get('schema_version')!=1:raise ValueError('Unbekannter Besitznachweis.')
    owned=receipt.setdefault('owned_entries',{});bindings=receipt.setdefault('profile_bindings',{})
    if not isinstance(owned,dict) or not isinstance(bindings,dict):raise ValueError('Ungültiger Besitznachweis.')
    for code,record in owned.items():
        if not CODE.fullmatch(str(code)) or not isinstance(record,dict) or record.get('base',{}).get('id')!=code:
            raise ValueError('Ungültiger eigener Materialeintrag im Besitznachweis.')
    positions={}
    for n,row in enumerate(old):positions.setdefault(row['base']['id'],[]).append(n)
    merged=deepcopy(database);entries=merged['result']['list']
    exported,unavailable,changes=[],[],[]
    all_profiles=manifest['profiles']+manifest.get('imported_profiles',[])
    imported={p['material_id']:p for p in imported_exports(manifest)}
    for p in all_profiles:
        if not p.get('enabled',True):continue
        code=p['material_id'];is_cloud=p in manifest['profiles']
        identity=cloud_identity(p) if is_cloud else p['identity']
        previous=bindings.get(code,{})
        found=positions.get(code,[])
        try:
            if previous and (previous.get('profile_setting_id')!=p['profile_setting_id'] or previous.get('identity',identity)!=identity):
                raise ValueError('Dauerhafter Materialcode gehört zu einer anderen Profilidentität.')
            if len(found)>1 or (found and (code not in owned or digest(old[found[0]])!=digest(owned[code]))):
                raise ValueError('Materialcode ist fremd belegt oder extern verändert; kein Überschreiben.')
            source=deepcopy(previous)
            if is_cloud and 'slicer_override' in p:
                override=p['slicer_override'];record=deepcopy(override['record'])
                row=exported_record(p,record,'cloud','slicer_current','Gespeicherter Slicerstand hat Vorrang vor Cloud-/Druckerwerten.',
                    'slicer://'+override['source']['file_id'])
                row.update(values_source='slicer',slicer_source=deepcopy(override['source']))
                if 'source_profile' in override:row['source_profile']=deepcopy(override['source_profile'])
            elif is_cloud:
                sid=p['cloud_setting_id'];account=p['account_id']
                try:
                    if cloud_issue:raise DeferredSyncError(cloud_issue)
                    active=_active_index(_index_records(index,account),sid)
                    if int(active['version'])<int(previous.get('cloud_version','0')) or active['revision']<int(previous.get('cloud_revision',0)):
                        raise DeferredSyncError('Cloudindex ist älter als der bestätigte Stand.')
                    native,cloud,name,brand,color,count,richness=_native_record(old,active,cloud_files,
                        manifest['printer_int_name'],manifest['nozzle_diameter'],set(owned))
                    record=deepcopy(native);record['base'].update(id=code,brand=brand,colors=[color])
                    source.update(cloud_path=active['path'],cloud_version=active['version'],cloud_revision=active['revision'])
                    status,reason='cloud_cache_current','Nativer Cloudcache konsistent; Internetverbindung nicht gesondert geprüft.'
                except DeferredSyncError as error:
                    # A saved row is usable only with both exact ownership and identity proof.
                    trusted_identity=previous.get('identity')==identity or (
                        previous.get('profile_setting_id')==p['profile_setting_id'] and receipt.get('account_id')==account)
                    if code not in owned or not trusted_identity:
                        raise ValueError('Cloudquelle fehlt und kein bestätigter Profilstand vorhanden: '+str(error))
                    record=deepcopy(owned[code]);status,reason='cached_cloud',str(error)
                row=exported_record(p,record,'cloud',status,reason,source.get('cloud_path'))
            else:
                record=deepcopy(imported[code]['record'])
                row=deepcopy(imported[code]);row.update(update_status='local_current' if row['origin']=='local' else 'imported_snapshot',
                    update_reason='Lokal importierter, dauerhaft auf diesem Drucker gespeicherter Stand.')
                if 'slicer_source' in imported[code]:row.update(values_source='slicer',slicer_source=deepcopy(imported[code]['slicer_source']),update_status='slicer_current')
                source.update(origin=row['origin'],origin_account_id=row.get('origin_account_id'),origin_setting_id=row.get('origin_setting_id'))
            validate_record(record,manifest['printer_int_name'],manifest['nozzle_diameter'])
            source.update(profile_setting_id=p['profile_setting_id'],identity=identity)
            if found:
                if entries[found[0]]!=record:
                    entries[found[0]]=deepcopy(record);changes.append({'material_id':code,'name':row['name'],'action':'updated'})
            else:
                entries.append(deepcopy(record));changes.append({'material_id':code,'name':row['name'],'action':'restored' if code in owned else 'added'})
            owned[code]=deepcopy(record);bindings[code]=source;exported.append(row)
        except (ValueError,KeyError,TypeError) as error:
            unavailable.append({'material_id':code,'profile_setting_id':p['profile_setting_id'],'identity':identity,'reason':str(error)})
    merged['result']['count']=len(entries)
    before=[r for r in old if r['base']['id'] not in owned]
    after=[r for r in entries if r['base']['id'] not in owned]
    if before!=after or catalog['version']!=merged['result']['version']:
        raise AssertionError('Fremde Materialeinträge wurden verändert.')
    available=[]
    account_ids=set()
    if isinstance(index,list):
        for item in index:
            m=re.fullmatch(r'/mnt/UDISK/creality/userdata/box/usrMaterial/([0-9]+)/[0-9a-f]{24}-[0-9]+',str(item.get('path','')) if isinstance(item,dict) else '')
            if m:account_ids.add(m.group(1))
    active_account=next(iter(account_ids)) if len(account_ids)==1 and not cloud_issue else None
    if active_account:
        assigned={cloud_identity(p) for p in manifest['profiles']}|{p['identity'] for p in manifest.get('imported_profiles',[])}
        try:records=_index_records(index,active_account)
        except DeferredSyncError:records={}
        used_sids={p['profile_setting_id'] for p in all_profiles}|{p.get('profile_setting_id') for p in bindings.values() if isinstance(p,dict)}
        from cfs_slicer_policy import cloud_reference
        slicer_refs={cloud_reference(p['slicer_source']) for p in manifest.get('imported_profiles',[]) if 'slicer_source' in p and p.get('enabled',True)}
        for sid in sorted(records):
            identity='cloud:'+active_account+':'+sid
            if identity in assigned or identity in slicer_refs:continue
            alias=sid if sid not in used_sids else hashlib.sha256(identity.encode()).hexdigest()[:24]
            try:
                active=_active_index(records,sid)
                native,cloud,name,brand,color,_,_=_native_record(old,active,cloud_files,manifest['printer_int_name'],manifest['nozzle_diameter'],set(owned))
                available.append({'profile_setting_id':alias,'cloud_setting_id':sid,'account_id':active_account,
                    'identity':identity,'status':'unassigned','name':name,'brand':brand,'color':color,
                    'type':native['kvParam']['filament_type'],'source_file':active['path']})
            except DeferredSyncError as error:
                available.append({'profile_setting_id':alias,'status':'cloud_pending','reason':str(error)})
    kinds={p['origin'] for p in exported}
    source_mode='mixed' if 'local' in kinds and any(k!='local' for k in kinds) else ('local' if kinds=={'local'} else 'cloud' if kinds else 'empty')
    receipt.update(source='printer_profiles')
    report={'source':'printer_profiles','registered_profiles':len(exported),'changes':changes,'new_count':len(entries),
        'unrelated_records_unchanged':True,'version_preserved':True,'unavailable_profiles':unavailable}
    export={'schema_version':2,'source':'printer_profiles','printer_registration_status':'pending',
        'account_id':manifest.get('account_id'),'cloud_account_id':active_account,
        'cloud_status':'native_cache_available' if active_account else 'source_missing_or_incomplete',
        'cloud_warning':cloud_issue,'profile_source_mode':source_mode,
        'profiles':exported,'available_profiles':available,'unavailable_profiles':unavailable}
    return merged,receipt,report,export


def plan_mixed_import(bundle,database,manifest,receipt,export):
    from cfs_transfer_core import validate_bundle,imported_exports,digest
    bundle=validate_bundle(bundle);target=deepcopy(manifest);receipt=receipt or {}
    if any(bundle['source'][key]!=manifest[key] for key in ('printer_int_name','nozzle_diameter')):
        raise ValueError('Export passt nicht zu Modell bzw. Düse des Zieldruckers.')
    all_profiles=target['profiles']+target.setdefault('imported_profiles',[])
    used={p['base']['id'] for p in database['result']['list']}|set(receipt.get('owned_entries',{}))|set(receipt.get('profile_bindings',{}))|set(receipt.get('reserved_material_ids',[]))|{p['material_id'] for p in all_profiles}
    copies={p['identity']:p for p in target['imported_profiles']}
    clouds={cloud_identity(p):p for p in target['profiles']}
    names={p['name'].casefold() for p in export.get('profiles',[])}
    available={p.get('identity'):p for p in export.get('available_profiles',[]) if p.get('status')=='unassigned'}
    rows=[]
    for p in bundle['profiles']:
        identity=p['identity'];source_code=p['material_id'];cloud=clouds.get(identity);linked=False
        if cloud is None and identity not in copies and identity in available:
            native=available[identity]
            code=source_code if source_code not in used else next((str(n) for n in range(99021,100000) if str(n) not in used),None)
            if code is None:raise ValueError('Kein freier Materialcode.')
            cloud={'material_id':code,'profile_setting_id':native['profile_setting_id'],
                'cloud_setting_id':native['cloud_setting_id'],'account_id':native['account_id'],'enabled':True}
            target['profiles'].append(cloud);clouds[identity]=cloud;used.add(code);linked=True
        if cloud:
            action='cloud_linked' if linked else 'cloud_existing' if cloud.get('enabled',True) else 'cloud_restored';cloud['enabled']=True
            code,sid=cloud['material_id'],cloud['profile_setting_id']
            if 'slicer_source' in p:
                from cfs_slicer_policy import validate_source,cloud_reference
                source=validate_source(p['slicer_source'])
                if cloud_reference(source)!=identity:raise ValueError('Slicerdatei und bestehende Cloudzuordnung passen nicht zusammen.')
                record=deepcopy(p['record']);record['base']['id']=code
                record.pop('userMaterial',None)
                trusted_path=receipt.get('owned_entries',{}).get(code,{}).get('userMaterial') or available.get(identity,{}).get('source_file')
                if trusted_path:record['userMaterial']=trusted_path
                override={'record':record,'source':source}
                if 'source_profile' in p:override['source_profile']=deepcopy(p['source_profile'])
                action='slicer_cloud_unchanged' if cloud.get('slicer_override')==override else 'slicer_cloud_updated'
                cloud['slicer_override']=override
        else:
            existing=copies.get(identity)
            history=next(((code,b) for code,b in receipt.get('profile_bindings',{}).items() if b.get('identity')==identity),None)
            code=existing['material_id'] if existing else history[0] if history else source_code if source_code not in used else next((str(n) for n in range(99021,100000) if str(n) not in used),None)
            if code is None:raise ValueError('Kein freier Materialcode.')
            sid=existing['profile_setting_id'] if existing else history[1]['profile_setting_id'] if history else hashlib.sha256(('cfs-import:'+identity).encode()).hexdigest()[:24]
            record=deepcopy(p['record']);record.pop('userMaterial',None);record['base']['id']=code
            original_name=record['base']['name']
            if existing and not identity.startswith('local:') and existing.get('source_name')==original_name:
                record['base']['name']=existing['record']['base']['name']
            if not identity.startswith('local:') and record['base']['name'].casefold() in names and not existing:
                record['base']['name']=record['base']['name'][:210]+' [Import '+sid[-6:]+']'
            if 'filament_settings_id' in record['kvParam']:record['kvParam']['filament_settings_id']=record['base']['name']
            copy={key:deepcopy(p[key]) for key in ('identity','origin_account_id','origin_setting_id','origin_kind','source_profile','slicer_source') if key in p}
            copy.update(material_id=code,profile_setting_id=sid,record=record,source_name=original_name)
            if existing:
                action='copy_unchanged' if copy==existing else 'copy_updated'
                target['imported_profiles'][target['imported_profiles'].index(existing)]=copy
            else:
                action='copy_restored' if history else 'copy_created';target['imported_profiles'].append(copy)
            copies[identity]=copy;used.add(code);names.add(record['base']['name'].casefold())
        found=[r for r in database['result']['list'] if r['base']['id']==code]
        if found and (len(found)!=1 or code not in receipt.get('owned_entries',{}) or digest(found[0])!=digest(receipt['owned_entries'][code])):
            raise ValueError('Materialcode '+code+' ist extern verändert; Konflikt vor dem Import klären.')
        rows.append({'identity':identity,'name':p['record']['base']['name'],'source_code':source_code,
            'material_id':code,'profile_setting_id':sid,'action':action,'retag_required':source_code!=code})
    validate_manifest(target)
    return target,rows

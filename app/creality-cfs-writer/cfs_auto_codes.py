# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit refresh action: register ready new cloud profiles, never rebind IDs."""
from pathlib import Path
from cfs_cloud_admin import register_cloud_profile
from cfs_profile_sync import PrinterSSH,connection_session
from cfs_progress import report


def refresh_and_assign(registry,password=None,progress=None,ssh_factory=None,initial_catalog=None):
    before=registry.printer;catalog=initial_catalog if initial_catalog is not None else registry.cloud_catalog(fresh=True)
    ready=[p for p in catalog.get('available_profiles',[]) if p.get('status','unassigned')=='unassigned']
    assigned=[];errors=[]
    if ready:
        factory=ssh_factory or PrinterSSH
        remote=factory(before['ip'],Path(registry.path).parent/'state/known_hosts',password or None)
        with connection_session(remote):
            try:
                remote.check_idle()
                for index,profile in enumerate(ready):
                    if registry.printer!=before:raise ValueError('Druckerauswahl geändert; automatische Vergabe angehalten.')
                    current=registry.cloud_catalog(fresh=True)
                    available={p['profile_setting_id']:p for p in current.get('available_profiles',[]) if p.get('status','unassigned')=='unassigned'}
                    sid=profile['profile_setting_id']
                    if sid not in available:continue
                    code=current.get('next_material_id')
                    if code is None:raise ValueError('Kein freier Materialcode verfügbar.')
                    report(progress,'Neue NFC-Materialcodes zuweisen',index,len(ready),'Profile',profile.get('name',''))
                    result=register_cloud_profile(registry,sid,None,password,ssh_factory=lambda *args:remote)
                    assigned.append({'material_id':result['material_id'],'profile_setting_id':result['profile_setting_id'],'name':result['name']})
                report(progress,'Neue Cloud-Profile geprüft',len(ready),len(ready),'Profile',str(len(assigned))+' Materialcodes angelegt')
            except Exception as error:errors.append(str(error))
    current=registry.cloud_catalog(fresh=True) if ready else catalog
    if registry.printer!=before:raise ValueError('Druckerauswahl geändert. Ergebnis am ursprünglich gewählten Drucker prüfen.')
    materials=[registry._resolve_cloud(entry,current)['material'] for entry in registry.entries if entry.get('enabled',True) and entry['material_id'] in current['profiles']]
    return {'materials':materials,'assigned':assigned,'errors':errors,
        'pending':sum(p.get('status')=='cloud_pending' for p in current.get('available_profiles',[])),
        'unassigned':sum(p.get('status','unassigned')=='unassigned' for p in current.get('available_profiles',[]))}

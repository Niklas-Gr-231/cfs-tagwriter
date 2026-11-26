#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Install/restore this one printer service without restarting the printer."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
WRITER = HERE.parent / 'creality-cfs-writer'
sys.path.insert(0, str(WRITER))
from cfs_profile_sync import PrinterSSH, SyncError
from cfs_registry import ProfileRegistry
from cfs_progress import report

CONFIG = '/mnt/UDISK/printer_data/config/cfs_cloud_profiles'
INIT = '/etc/init.d/cfs-cloud-profiles'


def install(remote,seed=None,state_dir=None,progress=None):
    report(progress,'Druckerstatus und bestehende Installation prüfen')
    try:
        remote.check_idle()
    except SyncError:
        status=remote.read_status()
        owned=remote.run('if [ -f '+INIT+' ]; then cat '+INIT+'; fi')
        if (status.get('webhooks',{}).get('state') != 'ready' or
            status.get('print_stats',{}).get('state') not in ('printing','paused') or
            b'cfs_cloud_profiles/cloud_service.py' not in owned):
            raise
    remote.run('mkdir -p '+shlex.quote(CONFIG)+'; chmod 755 '+shlex.quote(CONFIG))
    state_root = Path(state_dir) if state_dir else WRITER/'state'
    local_backup = state_root / ('cloud-registry-backup-'+remote.ip+'.json')
    legacy_backup = state_root / 'cloud-registry-backup.json'
    if not local_backup.exists() and legacy_backup.exists():
        if json.loads(legacy_backup.read_text()).get('printer_ip') == remote.ip:
            local_backup = legacy_backup
    saved = json.loads(local_backup.read_text()) if local_backup.exists() else {}
    if seed is not None and saved and any(saved.get('manifest', {}).get(key) != seed['manifest'][key] for key in ('printer_int_name','nozzle_diameter')):
        raise ValueError('Die vorhandene Sicherung gehört zu einem anderen Modell oder Düsendurchmesser; keine Zuordnungen überschrieben.')
    report(progress,'Profilzuordnungen erhalten oder wiederherstellen')
    for filename in ('manifest.json','receipt.json'):
        present=remote.run('if [ -f '+shlex.quote(CONFIG+'/'+filename)+' ]; then printf present; fi')
        if not present:
            key = filename.split('.')[0]
            if saved.get('schema_version') == 1 and isinstance(saved.get(key), dict):
                seed_raw=(json.dumps(saved[key],ensure_ascii=False,indent=2)+'\n').encode()
            elif seed is not None:
                seed_raw=(json.dumps(seed[key],ensure_ascii=False,indent=2)+'\n').encode()
            else:
                seed_raw=(HERE/'install-data'/filename).read_bytes()
            remote.run('umask 077; cat > '+shlex.quote(CONFIG+'/'+filename),seed_raw)
    files=('cfs_versions.py','cfs_transfer_core.py','cfs_mixed_core.py','cfs_slicer_policy.py','cloud_alias_core.py','cloud_service.py')
    for index,filename in enumerate(files):
        report(progress,'Dienstdateien übertragen und prüfen',index,len(files),'Dateien',filename)
        raw=(HERE/filename).read_bytes();stage=CONFIG+'/'+filename+'.installing'
        remote.run('umask 077; cat > '+shlex.quote(stage),raw)
        checked=remote.run('sha256sum '+shlex.quote(stage)).decode().split()[0]
        if checked!=hashlib.sha256(raw).hexdigest():raise ValueError('Uploadprüfung fehlgeschlagen: '+filename)
        remote.run('mv -f '+shlex.quote(stage)+' '+shlex.quote(CONFIG+'/'+filename))
    report(progress,'Dienstdateien übertragen und prüfen',len(files),len(files),'Dateien')
    report(progress,'Eigenen Dienststarter einrichten')
    init_type = seed.get('init_type') if seed else remote.run('if [ -f /etc/rc.common ]; then printf procd; else printf sysv; fi').decode().strip()
    init=(HERE/('cfs-cloud-profiles.init' if init_type=='procd' else 'cfs-cloud-profiles.sysv')).read_bytes()
    existing=remote.run('if [ -f '+INIT+' ]; then cat '+INIT+'; fi')
    if existing and b'cfs_cloud_profiles/cloud_service.py' not in existing:
        raise ValueError('Ein fremder Dienst verwendet bereits denselben Namen; Installation angehalten.')
    remote.run('umask 022; cat > '+INIT+'.installing',init)
    remote.run('chmod 755 '+INIT+'.installing; mv -f '+INIT+'.installing '+INIT)
    report(progress,'Materialzuordnungen prüfen und abgleichen')
    command='python3 '+CONFIG+'/cloud_service.py --config '+CONFIG+' --once'
    for attempt in range(5):
        try:
            result=json.loads(remote.run(command,timeout=45))
            break
        except SyncError as error:
            if 'arbeitet gerade' not in str(error) or attempt == 4:
                raise
            time.sleep(0.6)
    if result.get('success') is not True:raise ValueError('Abgleich nicht bestätigt')
    report(progress,'Zusatzdienst starten')
    remote.run(INIT+' enable; '+INIT+' restart')
    report(progress,'Zusatzdienst gestartet')
    return {k:result.get(k) for k in ('success','status','registered_profiles','new_count','unrelated_records_unchanged')}


def main():
    p=argparse.ArgumentParser(description='CFS-Cloud-Zuordnung installieren oder nach Firmwareupdate wiederherstellen')
    p.add_argument('--ip', help='Drucker-IP; Standard: die im Tagwriter ausgewählte Verbindung')
    args=p.parse_args()
    registry=ProfileRegistry()
    address=args.ip or registry.printer['ip']
    secret=getpass.getpass('SSH-Passwort des K2 Pro: ')
    remote=PrinterSSH(address,registry.path.parent/'state/known_hosts',secret)
    result=install(remote,state_dir=registry.path.parent/'state')
    url='http://'+address+':4408/server/files/config/cfs_cloud_profiles/tag-materials.json'
    with urllib.request.urlopen(url,timeout=10) as response:snapshot=json.load(response)
    if snapshot.get('printer_registration_status')!='installed':raise ValueError('Druckerexport noch nicht bestätigt')
    print(json.dumps({'installation':result,'profiles':len(snapshot['profiles']),'printer_restarted':False},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

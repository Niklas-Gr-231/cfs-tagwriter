# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Manage only the optional CFS profile service, never printer firmware."""
import json
from pathlib import Path
import shlex
import uuid

from cfs_cloud_admin import REMOTE_CONFIG, REMOTE_SERVICE
from cfs_profile_sync import PrinterSSH, SyncError, write_json,connection_session
from cfs_profile_transfer import save_backup
from cfs_transfer_core import bundle_from_snapshot

INIT = '/etc/init.d/cfs-cloud-profiles'


def install_button_text(report,target):
    if not report or not report.get('installed'):return 'Installieren'
    import re
    current=str(report.get('version',''))
    if re.fullmatch(r'\d+\.\d+\.\d+',current) and tuple(map(int,current.split('.')))<tuple(map(int,target.split('.'))):
        return 'Auf '+target+' aktualisieren'
    return 'Neu installieren / reparieren ('+target+')'


def remote_for(registry, password, address=None):
    return PrinterSSH(address or registry.printer['ip'], Path(registry.path).parent/'state/known_hosts', password or None)


def service_status(registry,password,address=None,_remote=None):
    remote=_remote or remote_for(registry,password,address)
    with connection_session(remote):
        # OpenWrt init status can succeed even when the service files vanished.
        script = '\n'.join([
            'import json, os',
            'init = '+repr(INIT),
            'service = '+repr(REMOTE_SERVICE),
            'config = '+repr(REMOTE_CONFIG),
            'owned = not os.path.exists(init) or service in open(init).read()',
            'files = '+repr(['cloud_service.py','cfs_versions.py','cfs_transfer_core.py','cfs_mixed_core.py','cfs_slicer_policy.py','cloud_alias_core.py','manifest.json','receipt.json']),
            'complete = os.access(init, os.X_OK) and all(os.path.isfile(config+"/"+name) for name in files)',
            'installed = os.path.exists(init) or os.path.exists(service)',
            'running = False',
            'for pid in os.listdir("/proc"):',
            '    if not pid.isdigit(): continue',
            '    try:',
            '        args = open("/proc/"+pid+"/cmdline", "rb").read().split(b"\\0")',
            '        if service.encode() in args and b"--run" in args: running = True',
            '    except OSError: pass',
            'state = "missing" if not installed else "broken" if not complete else "running" if running else "stopped"',
            'model = ""',
            'try:',
            '    model = json.load(open(config+"/manifest.json")).get("printer_int_name", "")',
            'except (OSError, ValueError, AttributeError): pass',
            'print(json.dumps({"state":state,"owned":owned,"model":model}))',
        ])
        report = json.loads(remote.run("python3 - <<'CFS_STATUS'\n"+script+"\nCFS_STATUS"))
        if not report['owned']:
            raise ValueError('Ein fremder Dienst verwendet denselben Namen; keine Dienstaktion ausgeführt')
        state = report['state']
        version = None
        if state not in ('missing', 'broken'):
            try: version = remote.run('python3 '+REMOTE_SERVICE+' --version').decode().strip()
            except SyncError: state = 'broken'
        from cfs_compatibility import model_info
        model = report.get('model', '')
        return {'installed': state != 'missing', 'running': state == 'running', 'state': state, 'version': version,
                'model': model, 'compatibility': model_info(model)}


def control_service(registry, action, password, address=None):
    if action not in ('start', 'stop', 'restart'):
        raise ValueError('Unbekannte Dienstaktion')
    remote = remote_for(registry, password, address)
    with connection_session(remote):
        remote.run(INIT+' '+action)
        return service_status(registry,password,address,_remote=remote)


def uninstall_service(registry, password):
    remote = remote_for(registry, password)
    remote.check_idle()
    before = service_status(registry, password)
    if not before['installed']:
        return before
    state = Path(registry.path).parent/'state'
    archive_id = uuid.uuid4().hex[:12]
    backup = {'schema_version': 1,
        'manifest': json.loads(remote.run('cat '+REMOTE_CONFIG+'/manifest.json')),
        'receipt': json.loads(remote.run('cat '+REMOTE_CONFIG+'/receipt.json'))}
    save_backup(registry, backup)
    # Preserve a reimportable material snapshot before removing own aliases.
    raw_export = json.loads(remote.run('cat '+REMOTE_CONFIG+'/tag-materials.json'))
    if raw_export.get('profiles'):
        write_json(state/('uninstalled-profiles-'+archive_id+'.json'), bundle_from_snapshot(raw_export))
    remote.run(INIT+' stop')
    try:
        reply = json.loads(remote.run('python3 '+REMOTE_SERVICE+' --config '+REMOTE_CONFIG+' --uninstall', timeout=60))
        if reply.get('success') is not True:
            raise ValueError('Dienstentfernung nicht bestätigt')
    except Exception:
        if before['running']:
            remote.run(INIT+' start')
        raise
    remote.run(INIT+' disable; rm -f '+INIT+'; mv '+shlex.quote(REMOTE_CONFIG)+' '+shlex.quote(REMOTE_CONFIG+'.removed-'+archive_id))
    return {'installed': False, 'running': False, 'state': 'missing', 'version': None,
            'backup': str(state), 'remaining_records': reply['remaining_records']}

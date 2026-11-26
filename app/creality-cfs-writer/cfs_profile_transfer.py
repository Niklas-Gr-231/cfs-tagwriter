# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Material transfer client: fresh HTTP export, checked SSH preview and commit."""
from copy import deepcopy
import json
from pathlib import Path
import re
import shlex
from datetime import datetime, timezone
import uuid

from cfs_transfer_core import bundle_from_snapshot, validate_bundle, digest
from cfs_cloud_admin import REMOTE_CONFIG, REMOTE_SERVICE


def export_profiles(registry, destination, material_ids=None):
    before = registry.printer
    snapshot = registry.cloud_catalog(fresh=True)
    if material_ids is not None:
        if not material_ids or not set(material_ids).issubset(snapshot['profiles']):
            raise ValueError('Die gewählten Profile sind nicht mehr vollständig verfügbar')
        snapshot['profiles'] = {code: snapshot['profiles'][code] for code in material_ids}
    bundle = bundle_from_snapshot(snapshot, before)
    if registry.printer != before:
        raise ValueError("Druckerauswahl während des Exports geändert. Bitte erneut exportieren.")
    from cfs_profile_sync import write_json
    write_json(Path(destination), bundle)
    return {"count": len(bundle["profiles"]), "path": str(destination)}


def read_bundle(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError("Die Transferdatei ist zu groß")
    return validate_bundle(json.loads(raw.decode('utf-8-sig')))


def transfer(registry, bundle, password, preview=None, *, ssh_factory=None):
    bundle = validate_bundle(bundle)
    if password is not None and (len(password) > 1024 or '\n' in password or '\r' in password):
        raise ValueError("Ungültiges SSH-Passwort")
    before = registry.printer
    catalog = registry.cloud_catalog(fresh=True)
    if any('slicer_source' in p for p in bundle['profiles']):
        version=str(catalog.get('service_version',''))
        if not re.fullmatch(r'\d+\.\d+\.\d+',version) or tuple(map(int,version.split('.')))<(2,1,0):
            raise ValueError('Slicer-Vorrang benötigt Druckerdienst 2.1.0. Bitte manuell über die App aktualisieren.')
    if catalog['printer_registration_status'] != 'installed':
        raise ValueError("Der Profildienst auf dem Zieldrucker ist nicht bereit")
    if ssh_factory is None:
        from cfs_profile_sync import PrinterSSH
        ssh_factory = PrinterSSH
    parts = ['python3', REMOTE_SERVICE, '--config', REMOTE_CONFIG, '--import-profiles']
    if preview is None:
        parts.append('--preview')
    else:
        if preview.get('printer') != before or preview.get('bundle_sha256') != digest(bundle) or not re.fullmatch(r'[0-9a-f]{64}', str(preview.get('plan_token', ''))):
            raise ValueError("Datei oder Zieldrucker wurde nach der Vorschau geändert. Bitte Vorschau erneut laden.")
        parts += ['--expected-plan', preview['plan_token']]
    remote = ssh_factory(before['ip'], Path(registry.path).parent/'state/known_hosts', password or None)
    from cfs_profile_sync import run_json_command
    reply = run_json_command(remote,' '.join(shlex.quote(part) for part in parts),
        (json.dumps(bundle, ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8'), timeout=60)
    if reply.get('success') is not True or reply.get('status') != ('preview' if preview is None else 'imported'):
        raise ValueError(str(reply.get('message') or 'Der Drucker hat den Import nicht bestätigt'))
    rows = reply.get('plan')
    identities = {p['identity']: p for p in bundle['profiles']}
    if not isinstance(rows, list) or len(rows) != len(identities) or len({p.get('identity') for p in rows}) != len(identities):
        raise ValueError("Unvollständiger Importplan vom Drucker")
    codes = set()
    for row in rows:
        original = identities.get(row.get('identity'))
        code = row.get('material_id')
        if original is None or row.get('source_code') != original['material_id'] or not isinstance(code, str) or not re.fullmatch(r'99[0-9]{3}', code) or code in codes or not re.fullmatch(r'[0-9a-f]{24}', str(row.get('profile_setting_id', ''))):
            raise ValueError("Widersprüchliche Profil- oder Codezuordnung in der Importantwort")
        if row.get('retag_required') != (original['material_id'] != code):
            raise ValueError("Ungültige Angabe zur notwendigen Tagänderung")
        codes.add(code)
    if registry.printer != before:
        raise ValueError("Die Druckerauswahl wurde während des Imports geändert. Zielstatus vor einem erneuten Import prüfen.")
    if preview is None:
        if not re.fullmatch(r'[0-9a-f]{64}', str(reply.get('plan_token', ''))):
            raise ValueError("Gültigkeitsnachweis für die Vorschau fehlt")
        return dict(reply, printer=before, bundle_sha256=digest(bundle))
    if reply.get('plan') != preview.get('plan'):
        raise ValueError("Der Drucker bestätigt eine andere Zuordnung als in der Vorschau. Zielstatus prüfen.")
    registry.set_profile_activity(rows, True)
    current = registry.cloud_catalog(fresh=True)
    for row in rows:
        profile = current['profiles'].get(row['material_id'])
        if profile is None or profile['profile_setting_id'] != row['profile_setting_id']:
            raise ValueError("Import noch nicht vollständig im Druckerexport bestätigt. Profile neu laden.")
    warning = None
    try:
        save_backup(registry, reply.get('configuration_backup'))
        from cfs_profile_sync import write_json
        write_json(Path(registry.path).parent/'state'/('import-report-'+before['ip']+'.json'),
            {'printer': before, 'plan': rows, 'bundle_sha256': digest(bundle), 'status': 'imported'})
    except OSError:
        warning = 'Import bestätigt; lokale Sicherung oder Zuordnungsliste konnte nicht geschrieben werden.'
    return dict(reply, materials=registry.materials(), backup_warning=warning)


def save_backup(registry, backup):
    if not isinstance(backup, dict) or backup.get('schema_version') != 1:
        raise ValueError('Die Druckerantwort enthält keine vollständige Zuordnungssicherung')
    from cfs_profile_sync import write_json
    backup = deepcopy(backup)
    address = registry.printer['ip']
    backup['printer_ip'] = address
    state = Path(registry.path).parent/'state'
    for name in ('cloud-registry-backup-'+address+'.json', 'cloud-registry-backup.json'):
        path = state/name
        write_json(path, backup)
        path.chmod(0o600)


def delete_profiles(registry, codes, password, preview=None, *, ssh_factory=None):
    if not isinstance(codes, list) or not codes or len(set(codes)) != len(codes) or any(not isinstance(code, str) or not re.fullmatch(r'99[0-9]{3}', code) for code in codes):
        raise ValueError('Bitte eigene Profile zum Entfernen auswählen')
    if password is not None and (len(password) > 1024 or '\n' in password or '\r' in password):
        raise ValueError('Ungültiges SSH-Passwort')
    before = registry.printer
    catalog = registry.cloud_catalog(fresh=True)
    if not set(codes).issubset(catalog['profiles']):
        raise ValueError('Die gewählten Profile sind nicht mehr vollständig auf dem Zieldrucker verfügbar')
    parts = ['python3', REMOTE_SERVICE, '--config', REMOTE_CONFIG, '--delete-profiles']
    backup_path = None
    if preview is None:
        parts.append('--preview')
    else:
        if preview.get('printer') != before or preview.get('codes') != codes or not re.fullmatch(r'[0-9a-f]{64}', str(preview.get('plan_token', ''))):
            raise ValueError('Ziel oder Auswahl nach der Vorschau geändert')
        parts += ['--expected-plan', preview['plan_token']]
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
        backup_path = Path(registry.path).parent/'state'/('deleted-profiles-'+before['ip']+'-'+stamp+'.json')
        export_profiles(registry, backup_path, codes)
    if ssh_factory is None:
        from cfs_profile_sync import PrinterSSH
        ssh_factory = PrinterSSH
    remote = ssh_factory(before['ip'], Path(registry.path).parent/'state/known_hosts', password or None)
    from cfs_profile_sync import run_json_command
    reply = run_json_command(remote,' '.join(shlex.quote(part) for part in parts),
        json.dumps({'material_ids': codes}).encode(), timeout=60)
    if reply.get('success') is not True or reply.get('status') != ('preview' if preview is None else 'deleted'):
        raise ValueError(str(reply.get('message') or 'Entfernung nicht bestätigt'))
    rows = reply.get('plan')
    if not isinstance(rows, list) or {row.get('material_id') for row in rows} != set(codes) or len(rows) != len(codes):
        raise ValueError('Unvollständige Bestätigung der zu entfernenden Profile')
    for row in rows:
        if row.get('profile_setting_id') != catalog['profiles'][row['material_id']]['profile_setting_id']:
            raise ValueError('Profil-ID passt nicht zur bestätigten Entfernung')
    if registry.printer != before:
        raise ValueError('Druckerauswahl während der Entfernung geändert; Zielstatus prüfen')
    if preview is None:
        if not re.fullmatch(r'[0-9a-f]{64}', str(reply.get('plan_token', ''))):
            raise ValueError('Gültigkeitsnachweis für die Vorschau fehlt')
        return dict(reply, printer=before, codes=codes)
    if rows != preview['plan']:
        raise ValueError('Entfernung bestätigt eine andere Auswahl als die Vorschau; Zielstatus prüfen')
    registry.set_profile_activity(rows, False)
    current = registry.cloud_catalog(fresh=True)
    if set(codes) & set(current['profiles']):
        raise ValueError('Entfernung im Druckerexport noch nicht bestätigt')
    warning = None
    try:
        save_backup(registry, reply.get('configuration_backup'))
    except OSError:
        warning = 'Profile entfernt; lokale Zuordnungssicherung konnte nicht geschrieben werden.'
    return dict(reply, materials=registry.materials(), backup_path=str(backup_path), backup_warning=warning)

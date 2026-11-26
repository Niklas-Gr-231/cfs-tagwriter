# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit SSH enrollment and supported-model setup; never flashes firmware."""
import base64
from cfs_locking import locked_file
import hashlib
import ipaddress
import json
from pathlib import Path
import subprocess
import sys


def scan_identity(address, known_hosts):
    address = str(ipaddress.IPv4Address(str(address).strip()))
    try:
        import paramiko
    except ImportError:
        run = subprocess.run(['ssh-keyscan', '-T', '5', '-t', 'ed25519', address],
                         capture_output=True, timeout=10)
        keys = [line.split() for line in run.stdout.decode().splitlines() if not line.startswith('#')]
        keys = [parts for parts in keys if len(parts) == 3 and parts[0] == address and parts[1] == 'ssh-ed25519']
    else:
        import socket
        transport = paramiko.Transport(socket.create_connection((address, 22), timeout=8))
        try:
            transport.start_client(timeout=8)
            server_key = transport.get_remote_server_key()
            keys = [[address, server_key.get_name(), server_key.get_base64()]]
        finally:
            transport.close()
    if len(keys) != 1:
        raise ValueError('Kein eindeutiger SSH-Hostschlüssel erreichbar. Root/SSH am Drucker und IP-Adresse prüfen.')
    key = keys[0]
    raw = base64.b64decode(key[2], validate=True)
    fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
    known_hosts = Path(known_hosts)
    trusted = False
    if known_hosts.exists():
        try:
            import paramiko
        except ImportError:
            found = subprocess.run(['ssh-keygen', '-F', address, '-f', str(known_hosts)], capture_output=True, timeout=5)
            previous = [line.split() for line in found.stdout.decode().splitlines() if not line.startswith('#')]
        else:
            hosts = paramiko.HostKeys(str(known_hosts))
            previous = [[address, kind, value.get_base64()] for kind, value in (hosts.lookup(address) or {}).items()]
        if previous:
            if not any(len(parts) >= 3 and parts[1:] == key[1:] for parts in previous):
                raise ValueError('Der SSH-Hostschlüssel dieser Adresse wurde geändert. Vor einer erneuten Einrichtung muss die Geräteidentität außerhalb des Tools geprüft werden.')
            trusted = True
    return {'address': address, 'key_line': ' '.join(key), 'fingerprint': fingerprint, 'trusted': trusted}


def trust_identity(identity, known_hosts):
    current = scan_identity(identity['address'], known_hosts)
    if current['key_line'] != identity['key_line']:
        raise ValueError('SSH-Identität seit der Prüfung verändert; keine Verbindung übernommen')
    if current['trusted']:
        return
    path = Path(known_hosts)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name+'.lock').open('a+', encoding='utf-8') as lock, locked_file(lock):
        with path.open('a+', encoding='utf-8') as stream:
            stream.seek(0)
            old = stream.read()
            stream.seek(0, 2)
            stream.write(('\n' if old and not old.endswith('\n') else '') + current['key_line'] + '\n')
            stream.flush()
            import os
            os.fsync(stream.fileno())
    path.chmod(0o600)


def preflight(remote):
    status = remote.read_status()
    if status.get('webhooks',{}).get('state') != 'ready' or status.get('print_stats',{}).get('state') not in ('standby','complete','cancelled','printing','paused'):
        raise ValueError('Drucker ist nicht betriebsbereit')
    _, database = remote.read_database()
    result = database.get('result', {})
    records = result.get('list')
    if not isinstance(records, list) or result.get('count') != len(records):
        raise ValueError('Nicht unterstützte Materialdatenbank')
    models = {record.get('printerIntName') for record in records}
    from cfs_transfer_core import MODEL
    if len(models) != 1 or not all(isinstance(model, str) and MODEL.fullmatch(model) for model in models):
        raise ValueError('Druckermodell im nativen Katalog ist nicht eindeutig; keine Installation ausgeführt.')
    model = next(iter(models))
    from cfs_compatibility import model_info
    compatibility = model_info(model)
    if not compatibility['service_available']:
        raise ValueError('Das native Modell ist kein unterstützter Creality-Dienstzugang. Für Anycubic ist kein CFS-Dienst installierbar.')
    nozzle = str(status.get('configfile', {}).get('settings', {}).get('extruder', {}).get('nozzle_diameter', ''))
    if nozzle not in ('0.4', '0.6', '0.8') or not any(record.get('nozzleDiameter') == [nozzle] for record in records):
        raise ValueError('Aktuelle Düse oder passende native Materialprofile konnten nicht sicher bestimmt werden')
    # Cloud files and credentials are optional; their presence is not enrollment.
    account=None
    init_type=remote.run('test -x /usr/bin/python3 && { if [ -f /etc/rc.common ]; then printf procd; elif [ -d /etc/init.d ] && command -v nohup >/dev/null; then printf sysv; else exit 1; fi; }').decode().strip()
    if init_type not in ('procd','sysv'):
        raise ValueError('Kein unterstützter Dienststarter gefunden')
    return {'manifest': {'schema_version': 2, 'account_id': account,
        'printer_int_name': model, 'nozzle_diameter': nozzle, 'profiles': [], 'imported_profiles': []},
        'receipt': {'schema_version': 1, 'owned_entries': {}}, 'init_type':init_type,
        'compatibility': compatibility}


def setup_printer(registry, name, address, password, identity, *, trust=False, allow_untested=False, progress=None):
    name = str(name).strip()
    if not name or len(name) > 80 or any(ord(char) < 32 for char in name):
        raise ValueError('Bitte eine gültige Druckerbezeichnung eingeben')
    if password is not None and (len(password) > 1024 or '\n' in password or '\r' in password):
        raise ValueError('Ungültiges SSH-Passwort')
    if str(ipaddress.IPv4Address(address.strip())) != identity['address']:
        raise ValueError('IP-Adresse wurde seit der Identitätsprüfung geändert')
    if not identity['trusted'] and not trust:
        raise ValueError('Der neue SSH-Hostschlüssel wurde noch nicht bestätigt')
    directory = Path(__file__).resolve().parent.parent/'creality-cfs-cloud'
    if not (directory/'install_printer_service.py').is_file():
        raise ValueError('Für die Einrichtung das Gesamtpaket mit dem Ordner creality-cfs-cloud verwenden')
    hostfile = Path(registry.path).parent/'state/known_hosts'
    from cfs_progress import report
    report(progress,'SSH-Identität bestätigen')
    trust_identity(identity,hostfile)
    from cfs_profile_sync import PrinterSSH
    remote = PrinterSSH(identity['address'], hostfile, password or None)
    from cfs_profile_sync import connection_session
    with connection_session(remote):
        report(progress,'Druckermodell, Düse und Profilpfade prüfen')
        seed = preflight(remote)
        if seed['compatibility']['experimental'] and not allow_untested:
            raise ValueError('Dieses Modell ist noch nicht praktisch geprüft. Die optionale Freigabe für ungeprüfte Modelle wurde nicht erteilt.')
        from cfs_versions import SERVICE_VERSION
        try:
            current_version = remote.run('python3 /mnt/UDISK/printer_data/config/cfs_cloud_profiles/cloud_service.py --version').decode().strip()
        except Exception:
            current_version = ''
        if __import__('re').fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', current_version) and tuple(map(int, current_version.split('.'))) > tuple(map(int, SERVICE_VERSION.split('.'))):
            raise ValueError('Der installierte Druckerdienst ist neuer als das Anwendungspaket. Bitte die Anwendung aktualisieren.')
        sys.path.insert(0, str(directory))
        from install_printer_service import install
        install(remote,seed=seed,state_dir=Path(registry.path).parent/'state',progress=progress)
        report(progress,'Profilkatalog vom Drucker zurücklesen')
        result = registry.select_printer(name, identity['address'], save=True)
        result['model'] = seed['manifest']['printer_int_name']
        result['compatibility'] = seed['compatibility']
        from cfs_profile_transfer import save_backup
        root = '/mnt/UDISK/printer_data/config/cfs_cloud_profiles/'
        backup = {'schema_version': 1, 'manifest': json.loads(remote.run('cat '+root+'manifest.json')),
                  'receipt': json.loads(remote.run('cat '+root+'receipt.json'))}
        report(progress,'Lokale Sicherung speichern')
        save_backup(registry,backup)
        report(progress,'Druckerdienst eingerichtet')
        return result

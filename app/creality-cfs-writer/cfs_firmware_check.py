# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Remember the actual printer firmware and a pending manual service repair."""
import json
from pathlib import Path
import re

from cfs_locking import locked_file
from cfs_profile_sync import write_json


def read_firmware(remote):
    raw = remote.run(
        'if [ -f /mnt/UDISK/creality/userdata/config/system_version.json ]; then '
        'cat /mnt/UDISK/creality/userdata/config/system_version.json; '
        'else fw_printenv version; fi', timeout=10).decode().strip()
    try:
        version = json.loads(raw).get('sys_version', '')
    except (ValueError, AttributeError):
        version = raw.removeprefix('version=').strip()
    if not isinstance(version, str) or not re.fullmatch(r'[0-9][A-Za-z0-9._+-]{0,79}', version):
        raise ValueError('Die vollständige Drucker-Firmwareversion konnte nicht gelesen werden.')
    return version


class FirmwareHistory:
    def __init__(self, directory):
        self.path = Path(directory) / 'state' / 'printer-firmware.json'

    def pending(self, address):
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text())
        for item in data.get('printers', {}).values():
            if item.get('ip') == address and item.get('needs_repair'):
                return item
        return None

    def observe(self, address, hostname, version, service, *, repaired=False):
        key = hostname or address
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a+') as lock, locked_file(lock):
            data = json.loads(self.path.read_text()) if self.path.exists() else {'schema_version': 1, 'printers': {}}
            if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('printers'), dict):
                raise ValueError('Die gespeicherte Firmwareprüfung ist beschädigt.')
            old = data['printers'].get(key, {})
            changed = bool(old.get('version') and old['version'] != version)
            needs_repair = bool(old.get('needs_repair') or changed or service.get('state') in ('missing', 'broken'))
            previous = old.get('previous_version', '')
            if changed:
                previous = old['version']
            if repaired:
                if not service.get('installed') or not service.get('running') or service.get('state') != 'running':
                    raise ValueError('Die Neuinstallation ist noch nicht als laufend bestätigt.')
                needs_repair = False
                previous = ''
            result = {'ip': address, 'hostname': hostname, 'version': version,
                      'previous_version': previous, 'needs_repair': needs_repair}
            if old != result:
                data['printers'][key] = result
                write_json(self.path, data)
        return result


def repair_message(report):
    previous = report.get('previous_version')
    if previous:
        return (f'Drucker-Firmware geändert: {previous} → {report["version"]}. '
                'Nach einem Druckerupdate ist eine Neuinstallation des Zusatzdienstes erforderlich. '
                'Zuerst „SSH-Identität / Installation prüfen“, dann „Neu installieren / reparieren“ wählen.')
    return (f'Drucker-Firmware {report["version"]}: Der Zusatzdienst fehlt oder ist unvollständig. '
            'Das kann nach einem Druckerupdate auftreten. '
            'Zuerst „SSH-Identität / Installation prüfen“, dann den Zusatzdienst installieren oder reparieren.')


def check_printer(registry, directory, password, *, address=None, repaired=False):
    from cfs_printer_identity import probe_printer
    from cfs_service_manager import remote_for, service_status
    address = address or registry.printer.get('ip')
    info = probe_printer(address)
    remote = remote_for(registry, password, address)
    with remote.session():
        version = read_firmware(remote)
        service = service_status(registry, password, address, _remote=remote)
    history = FirmwareHistory(directory).observe(address, info['hostname'], version, service, repaired=repaired)
    return dict(history, service=service)

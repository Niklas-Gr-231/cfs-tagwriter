# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Opt-in spool sharing and explicit, source-to-target profile transfer.

Never edits a slicer, switches the active printer, or merges calibration values
between models. Tag amounts always win over this local spool inventory.
"""
from copy import deepcopy
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import re

from cfs_locking import locked_file
from cfs_profile_sync import write_json
from cfs_compatibility import model_info

MODES = {'off': 'Getrennt halten', 'rolls': 'Nur Rollennummern teilen',
         'profiles': 'Rollennummern + Profile gleicher Druckertypen'}


def address(value):
    ip = ipaddress.IPv4Address(str(value).strip())
    if ip.is_unspecified or ip.is_loopback or ip.is_multicast or int(ip) == 0xffffffff:
        raise ValueError('Ungültige Druckeradresse')
    return str(ip)


def tag_key(protocol, uid):
    if protocol not in ('cfs', 'ace') or not re.fullmatch('[0-9A-Fa-f]{'+('8' if protocol == 'cfs' else '14')+'}', str(uid)):
        raise ValueError('Ungültige Tagkennung')
    return protocol+':'+uid.upper()


def validate(data):
    if not isinstance(data, dict) or data.get('format') != 'cfs-tagwriter-fleet' or data.get('schema_version') != 1:
        raise ValueError('Unbekanntes Format der Drucker-/Rollenzuordnungen')
    if not isinstance(data.get('policies'), dict) or not isinstance(data.get('rolls'), dict) or len(data['rolls']) > 20000:
        raise ValueError('Ungültige Drucker-/Rollenliste')
    for ip, mode in data['policies'].items():
        if address(ip) != ip or mode not in MODES:
            raise ValueError('Ungültige Synchronisierungseinstellung')
    seen = set()
    for serial, roll in data['rolls'].items():
        if not re.fullmatch(r'[0-9]{6}', serial) or not isinstance(roll, dict) or not isinstance(roll.get('tags'), list) or not isinstance(roll.get('printers'), dict):
            raise ValueError('Ungültige Rollennummer oder Zuordnung')
        for key in roll['tags']:
            protocol, _, uid = str(key).partition(':')
            if tag_key(protocol, uid) != key or key in seen:
                raise ValueError('Eine Tagkennung ist mehrfach oder widersprüchlich zugeordnet')
            seen.add(key)
        for ip, item in roll['printers'].items():
            address(ip)
            if not isinstance(item, dict) or not isinstance(item.get('material_id', ''), str):
                raise ValueError('Ungültige Druckerzuordnung der Rolle')
    return deepcopy(data)


class FleetStore:
    def __init__(self, directory):
        self.path = Path(directory)/'fleet.json'

    def load(self):
        if not self.path.exists():
            return {'format': 'cfs-tagwriter-fleet', 'schema_version': 1, 'policies': {}, 'rolls': {}}
        with self.path.open('rb') as stream:
            raw = stream.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError('Die Rollenzuordnung ist zu groß')
        return validate(json.loads(raw.decode('utf-8-sig')))

    def update(self, function):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a+') as lock, locked_file(lock):
            data = self.load()
            result = function(data)
            write_json(self.path, validate(data))
            self.path.chmod(0o600)
        return result

    def policy(self, ip):
        return self.load()['policies'].get(address(ip), 'off')

    def set_policy(self, ip, mode):
        ip = address(ip)
        if mode not in MODES:
            raise ValueError('Unbekannte Synchronisierungsoption')
        return self.update(lambda data: data['policies'].__setitem__(ip, mode))

    def sharing(self, ip):
        ip = address(ip)
        policies = self.load()['policies']
        return policies.get(ip, 'off') != 'off'

    def lookup(self, protocol, uid):
        key = tag_key(protocol, uid)
        return next((serial for serial, roll in self.load()['rolls'].items() if key in roll['tags']), None)

    def material_for_roll(self, ip, serial):
        if not self.sharing(ip):
            return None
        roll = self.load()['rolls'].get(str(serial), {})
        return roll.get('printers', {}).get(address(ip), {}).get('material_id') or None

    def remember(self, ip, protocol, uid, serial, material_id='', weight_g=None, *, allow_reassign=False):
        ip = address(ip)
        if not self.sharing(ip):
            return False
        key = tag_key(protocol, uid)
        if not re.fullmatch(r'[0-9]{6}', str(serial)):
            raise ValueError('Die Rollennummer muss sechs Ziffern enthalten')
        def save(data):
            for old_serial, old in data['rolls'].items():
                if old_serial != serial and key in old['tags']:
                    if allow_reassign:
                        old['tags'].remove(key)
                    else:
                        raise ValueError('Dieser Tag gehört bereits zu Rolle '+old_serial+'. Zuordnung zuerst bewusst entfernen oder eine neue Karte verwenden.')
            roll = data['rolls'].setdefault(serial, {'tags': [], 'printers': {}})
            if key not in roll['tags']:
                roll['tags'].append(key)
            # Observed tag amount is informational, never applied to a form.
            roll['printers'][ip] = {'material_id': str(material_id), 'observed_weight_g': weight_g,
                                     'observed_at': datetime.now(timezone.utc).isoformat()}
            return True
        return self.update(save)

    def import_inventory(self, incoming):
        incoming = validate(incoming)
        def merge(data):
            for serial, roll in incoming['rolls'].items():
                current = data['rolls'].setdefault(serial, {'tags': [], 'printers': {}})
                current['tags'] = sorted(set(current['tags']) | set(roll['tags']))
                # Existing observations and all opt-in policies stay local.
                for ip, item in roll['printers'].items():
                    current['printers'].setdefault(ip, deepcopy(item))
            validate(data)
            return len(incoming['rolls'])
        return self.update(merge)

    def link_profile_codes(self, source_ip, target_ip, rows):
        """A confirmed profile import can resolve a roll on a new target.

        Preserve any deliberately chosen per-printer profile (e.g. Hi vs Ob).
        Do not create a consumption observation or claim the tag was rewritten.
        """
        source_ip, target_ip = address(source_ip), address(target_ip)
        mapping = {row['source_code']: row['material_id'] for row in rows}
        def link(data):
            if data['policies'].get(source_ip, 'off') == 'off' or data['policies'].get(target_ip) != 'profiles':
                return 0
            count = 0
            for roll in data['rolls'].values():
                source = roll['printers'].get(source_ip, {})
                code = mapping.get(source.get('material_id'))
                if code and target_ip not in roll['printers']:
                    roll['printers'][target_ip] = {'material_id': code, 'binding_origin': 'profile_transfer',
                                                   'observed_weight_g': None, 'observed_at': None}
                    count += 1
            return count
        return self.update(link)


class TargetRegistry:
    """Isolated target view using the original validation and host-key store."""
    def __init__(self, registry, target):
        self.registry = registry
        self.path = registry.path
        self._printer = deepcopy(target)
        self._printer['ip'] = address(target['ip'])
        self.data = registry._load()
        scope = target.get('profile_scope') or {}
        self.data.update(profiles=deepcopy(scope.get('profiles', [])), cloud_account_id=scope.get('cloud_account_id'))
        self.data['printer'] = deepcopy(self._printer)
        self.data['cloud_materials_url'] = 'http://'+self._printer['ip']+':4408/server/files/config/cfs_cloud_profiles/tag-materials.json'

    @property
    def printer(self):
        return deepcopy(self._printer)

    def cloud_catalog(self, *, fresh=True):
        return self.registry._cloud_snapshot(self.data, fresh=fresh, adopt=False, remember=False)

    def set_profile_activity(self, rows, enabled):
        # Only this isolated view changes. Active local printer bindings stay
        # untouched; selecting the target later adopts its validated snapshot.
        for row in rows:
            current = next((p for p in self.data['profiles'] if p['material_id'] == row['material_id']), None)
            if current:
                current['enabled'] = enabled

    def materials(self):
        snapshot = self.cloud_catalog(fresh=True)
        return [deepcopy(p) for p in snapshot['profiles'].values()]


def require_matching_models(source, target):
    a, b = model_info(source.get('printer_int_name')), model_info(target.get('printer_int_name'))
    if a['manufacturer'] != 'Creality' or b['manufacturer'] != 'Creality' or a['model'] != b['model'] or a['model'] == 'Nicht erkannt':
        raise ValueError('Kalibrierungsprofile dürfen nur zwischen demselben bestätigten Druckertyp synchronisiert werden.')
    if not source.get('nozzle_diameter') or source.get('nozzle_diameter') != target.get('nozzle_diameter'):
        raise ValueError('Der Düsendurchmesser von Quelle und Ziel muss übereinstimmen.')


def sync_profiles(registry, store, target, codes, password, preview=None, *, transfer_function=None):
    """Fresh source wins; existing preview token protects the target commit."""
    if address(target['ip']) == registry.printer.get('ip'):
        raise ValueError('Quelle und Ziel müssen unterschiedliche Drucker sein.')
    if store.policy(target['ip']) != 'profiles':
        raise ValueError('Profil-Synchronisierung ist für dieses Ziel nicht freigegeben.')
    if model_info(target.get('printer_int_name') or target.get('model', ''))['manufacturer'] == 'Anycubic':
        raise ValueError('Für Anycubic ist nur die lokale Rollenzuordnung und der experimentelle ACE-Tagmodus verfügbar. Es gibt keinen Anycubic-Druckerdienst für Profilübertragung.')
    if not codes or len(set(codes)) != len(codes):
        raise ValueError('Mindestens ein eindeutiges Profil auswählen.')
    before = registry.printer
    source = registry.cloud_catalog(fresh=True)
    isolated = TargetRegistry(registry, target)
    destination = isolated.cloud_catalog(fresh=True)
    require_matching_models(source, destination)
    if not set(codes).issubset(source['profiles']):
        raise ValueError('Die gewählten Quellprofile sind nicht mehr verfügbar.')
    source['profiles'] = {code: source['profiles'][code] for code in codes}
    from cfs_transfer_core import bundle_from_snapshot
    bundle = bundle_from_snapshot(source, before)
    if registry.printer != before:
        raise ValueError('Der Quelldrucker wurde während der Prüfung geändert.')
    if transfer_function is None:
        from cfs_profile_transfer import transfer
        transfer_function = transfer
    result = transfer_function(isolated, bundle, password, preview)
    result['code_changes'] = [row for row in result['plan'] if row['retag_required']]
    if preview is not None:
        try:
            result['linked_rolls'] = store.link_profile_codes(before['ip'], target['ip'], result['plan'])
        except (OSError, ValueError) as error:
            result['roll_binding_warning'] = 'Profile übertragen, lokale Rollenzuordnungen nicht ergänzt: '+str(error)
    return result

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Independent experimental ACE (Pro / 2 Pro) NTAG213 codec and RC522 transport.

Field positions were checked against public protocol documentation, no upstream
implementation or dumps are distributed. This does not install a printer agent
or map arbitrary slicer calibrations into Anycubic firmware/cloud profiles.
"""
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import struct

from cfs_device import BridgeError


@dataclass(frozen=True)
class AceSpec:
    sku: str
    type: str
    color: str
    weight_g: int
    length_m: int
    nozzle_low: int
    nozzle_high: int
    bed_low: int
    bed_high: int
    serial: str = ''  # Local inventory only; not a documented native ACE field.

    @property
    def material_id(self):
        return self.sku


def encode(spec):
    if not isinstance(spec.sku, str) or not re.fullmatch(r'[A-Z0-9-]{1,20}', spec.sku):
        raise ValueError('Eine gültige Anycubic-SKU mit höchstens 20 Zeichen eingeben, z. B. von einem Original-Tag.')
    if not isinstance(spec.type, str) or not re.fullmatch(r'[A-Za-z0-9 +?._-]{1,20}', spec.type):
        raise ValueError('Der ACE-Materialtyp muss aus 1–20 ASCII-Zeichen bestehen.')
    if not re.fullmatch(r'#[0-9A-Fa-f]{6}', str(spec.color)):
        raise ValueError('Die Farbe muss ein RGB-Hexcode sein, z. B. #3366FF.')
    for value, low, high in ((spec.weight_g, 0, 5000), (spec.length_m, 0, 65535),
                             (spec.nozzle_low, 1, 350), (spec.nozzle_high, 1, 350),
                             (spec.bed_low, 0, 150), (spec.bed_high, 0, 150)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Ungültige Restmenge, Länge oder Temperatur für den ACE-Tag.')
    if spec.nozzle_low > spec.nozzle_high or spec.bed_low > spec.bed_high:
        raise ValueError('Die untere Temperatur darf nicht höher als die obere sein.')
    data = bytearray(144)  # Only user pages 4–39, no locks/config/passwords.
    data[:4] = bytes((0x7b, 0, 0x65, 0))
    data[4:4+len(spec.sku)] = spec.sku.encode('ascii')
    data[24:26] = b'AC'
    data[44:44+len(spec.type)] = spec.type.encode('ascii')
    rgb = bytes.fromhex(spec.color[1:])
    data[64:68] = b'\xff'+rgb[::-1]
    struct.pack_into('<HH', data, 80, spec.nozzle_low, spec.nozzle_high)
    struct.pack_into('<HH', data, 100, spec.bed_low, spec.bed_high)
    struct.pack_into('<HH', data, 104, 175, spec.length_m)
    struct.pack_into('<I', data, 108, spec.weight_g)
    return bytes(data)


def decode(raw):
    raw = bytes(raw)
    if len(raw) != 144 or raw[:2] != bytes((0x7b, 0)) or raw[2:4] not in (b'\x64\x00', b'\x65\x00'):
        raise ValueError('Kein bekanntes ACE-Pro-Tagformat (Version 1 oder 2).')
    def string(start, length):
        return raw[start:start+length].split(b'\0', 1)[0].decode('ascii')
    diameter, length = struct.unpack_from('<HH', raw, 104)
    if diameter != 175:
        raise ValueError('Dieses experimentelle Format unterstützt nur 1,75-mm-Filament.')
    nozzle = struct.unpack_from('<HH', raw, 80)
    bed = struct.unpack_from('<HH', raw, 100)
    spec = AceSpec(string(4, 20), string(44, 20), '#'+raw[65:68][::-1].hex().upper(),
                   struct.unpack_from('<I', raw, 108)[0], length, *nozzle, *bed)
    encode(spec)  # Apply the same range checks to read data.
    return spec


class AceDevice:
    def __init__(self, bridge, progress=None, *, target=None):
        self.bridge = bridge
        self.progress = progress or (lambda update: None)
        self.target = dict(target) if target is not None else None

    def _command(self, command, *args):
        try:
            return self.bridge._command(command, *args)
        except BridgeError as error:
            if error.code == 'UNSUPPORTED_TAG':
                raise BridgeError(error.code, 'Im ACE-Modus wird ein NTAG213 mit 7-Byte-UID benötigt. MIFARE Classic, NTAG215/216 und unbekannte Chips sind dafür nicht freigegeben.') from error
            if error.code == 'ACCESS_BITS':
                raise BridgeError(error.code, 'NTAG213 ist gesperrt, passwortgeschützt oder nicht im unterstützten Auslieferungszustand. Sperren und Passwörter werden nicht verändert.') from error
            raise

    def _scan(self, expected_uid=None):
        hello = self.bridge.hello()
        if 'ntag213' not in hello.get('capabilities', []):
            raise BridgeError('FIRMWARE_UPDATE', 'Für Anycubic-NTAG213 die Bridge 1.1.0 manuell unter Einstellungen → Arduino aufspielen. Creality funktioniert auch mit der bisherigen Bridge.')
        result = self._command('NTSCAN')
        uid = str(result.get('uid', '')).upper()
        if not re.fullmatch(r'[0-9A-F]{14}', uid) or result.get('type') != 'NTAG213':
            raise BridgeError('UNSUPPORTED_TAG', 'Der ACE-Modus benötigt einen NTAG213 mit 7-Byte-UID. Deine CFS-MIFARE-Tags sind ein anderer Typ.')
        if expected_uid is not None and uid != expected_uid:
            raise BridgeError('UID_MISMATCH', 'Ein anderer Tag liegt auf. Diesen zuerst erneut lesen.')
        return uid

    def _read(self, uid, page):
        result = self._command('NTREAD', uid, page)
        raw = result.get('data', '')
        if result.get('uid') != uid or result.get('page') != page or not re.fullmatch(r'[0-9A-Fa-f]{32}', str(raw)):
            raise BridgeError('PROTOCOL', 'Unvollständige NTAG213-Leseantwort.')
        return bytes.fromhex(raw)

    def _inspect(self, expected_uid=None):
        uid = self._scan(expected_uid)
        system = self._read(uid, 0)
        config = self._read(uid, 40)
        payload = b''.join(self._read(uid, page) for page in range(4, 40, 4))
        writable = system[10:12] == b'\0\0' and system[12:16] == bytes.fromhex('E1101200') and config[:3] == b'\0\0\0' and config[7] == 0xff
        try:
            spec = decode(payload)
        except (ValueError, UnicodeDecodeError):
            spec = None
        return {'uid': uid, 'type': 'NTAG213', 'formatted': spec is not None, 'spec': spec,
                'writable': writable, 'payload': payload, 'system': system, 'config': config}

    def read_tag(self):
        with self.bridge._lock:
            return self._inspect()

    def write_tag(self, expected_uid, spec, backup_dir):
        if self.target is not None:
            from cfs_anycubic_feeders import require_write_target
            require_write_target(**self.target)
        payload = encode(spec)
        if not re.fullmatch(r'[0-9A-F]{14}', str(expected_uid)):
            raise BridgeError('UID_MISMATCH', 'Zuerst den zu beschreibenden NTAG213 lesen.')
        with self.bridge._lock:
            before = self._inspect(expected_uid)
            if not before['writable']:
                raise BridgeError('ACCESS_BITS', 'NTAG213 ist gesperrt, passwortgeschützt oder nicht im unterstützten Auslieferungszustand. Sperren und Passwörter werden nicht verändert.')
            directory = Path(backup_dir)
            directory.mkdir(parents=True, exist_ok=True)
            backup = directory/f'{datetime.now():%Y%m%d-%H%M%S-%f}_{expected_uid}_ACE.json'
            # Backup must succeed before the very first write command.
            with backup.open('x', encoding='utf-8') as stream:
                json.dump({'format': 'ace-ntag213-user-pages-backup-v1', 'uid': expected_uid,
                           'user_pages_4_39': before['payload'].hex().upper(),
                           'system_read_only': before['system'].hex().upper(),
                           'config_read_only': before['config'].hex().upper()}, stream, indent=2)
                stream.write('\n')
            for index, page in enumerate(range(4, 40)):
                current = payload[index*4:index*4+4]
                if current != before['payload'][index*4:index*4+4]:
                    result = self._command('NTWRITE', expected_uid, page, current.hex().upper())
                    if result.get('uid') != expected_uid or result.get('page') != page or result.get('verified') is not True:
                        raise BridgeError('VERIFY_FAILED', 'Eine NTAG213-Seite wurde nicht bestätigt. Tag erneut lesen.', backup=str(backup))
                self.progress({'phase': 'ACE-Tag schreiben und prüfen', 'current': index+1, 'total': 36, 'unit': 'Seiten'})
            actual = self._inspect(expected_uid)
            if actual['payload'] != payload or actual['system'] != before['system'] or actual['config'] != before['config']:
                raise BridgeError('VERIFY_FAILED', 'Rücklesen des vollständigen ACE-Tags fehlgeschlagen.', backup=str(backup))
            return {'uid': expected_uid, 'verified': True, 'backup': str(backup)}

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Capability labels, not a claim that untested hardware passed a device test."""
import re

CREALITY = ('K2 Pro', 'K2 Plus', 'K2', 'Hi', 'K1 Max 2025', 'K1C 2025', 'K1 Max', 'K1C', 'K1 SE', 'K1')
from cfs_anycubic_feeders import PRINTERS as ANYCUBIC
INTERNAL = {'F012': 'K2 Pro', 'F008': 'K2 Plus', 'F018': 'Hi', 'F001': 'K1'}
SOURCES = {
    'Creality CFS': 'https://www.creality.com/eu/products/k2-series-3d-printer',
    'Creality CFS-C': 'https://www.creality.com/products/cfs-c-smart-filament-system',
    'Anycubic ACE Pro': 'https://eu.anycubic.com/products/ace-pro',
    'Anycubic ACE 2 Pro': 'https://store.anycubic.com/products/ace-2-pro',
    'Kobra X integriert': 'https://eu.anycubic.com/products/kobra-x-combo-3d-printer',
    'ACE-Tagformat': 'https://github.com/Molodos/anycubic-nfc-filament/blob/main/format.md',
}


def compact(value):
    return re.sub(r'[^a-z0-9]', '', str(value).casefold())


def model_info(model='', manufacturer=''):
    value = str(model or '').strip()
    value = INTERNAL.get(value, value)
    brand = str(manufacturer or '').strip()
    if 'anycubic' in value.casefold() or compact(value).startswith('kobra'):
        brand = 'Anycubic'
    elif value in CREALITY or re.fullmatch(r'F[0-9]{3}', value) or value.upper().startswith(('K1', 'K2', 'CR-K')) or 'creality' in value.casefold():
        brand = 'Creality'
    for prefix in ('Creality ', 'Anycubic '):
        if value.startswith(prefix):
            value = value[len(prefix):]
    known = ANYCUBIC if brand == 'Anycubic' else CREALITY if brand == 'Creality' else ()
    # Exact model names only; a hostname is not proof of installed hardware.
    value = next((name for name in known if compact(name) == compact(value)), value)
    tested = brand == 'Creality' and value == 'K2 Pro'
    return {'manufacturer': brand or 'Unbekannt', 'model': value or 'Nicht erkannt',
            'tested': tested, 'experimental': not tested,
            'status': 'Am K2 Pro getestet' if tested else 'Experimentell · nicht am Gerät geprüft',
            'tag_format': 'Wechslerabhängig · Auswahl erforderlich' if brand == 'Anycubic' else 'MIFARE Classic 1K / CFS',
            'service_available': brand == 'Creality'}


def material_printer(material, fallback=None):
    fallback = fallback or {}
    record = material.get('record') or {}
    printer = material.get('printer') or {}
    model = (material.get('printer_int_name') or record.get('printerIntName') or
             printer.get('printer_int_name') or printer.get('model') or
             material.get('printer_model') or fallback.get('printer_int_name') or fallback.get('model'))
    return model_info(model, material.get('printer_manufacturer') or printer.get('manufacturer') or fallback.get('manufacturer', ''))


def rows():
    return [model_info(model, brand) for brand, models in (('Creality', CREALITY), ('Anycubic', ANYCUBIC)) for model in models]

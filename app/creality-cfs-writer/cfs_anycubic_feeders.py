# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Researched Anycubic feeder families, variants and explicit test boundaries.

Product compatibility is separate from acceptance of our independently written
tags. No network requests, firmware patches, or inferred hardware detection.
"""
from copy import deepcopy

RESEARCH_DATE = '2026-11-26'
PRINTERS = ('Kobra 3', 'Kobra 3 V2', 'Kobra 3 Max', 'Kobra 3 Max V2',
            'Kobra 4', 'Kobra S1', 'Kobra S1 Max', 'Kobra X')
PRO_MODELS = ('Kobra 3', 'Kobra 3 V2', 'Kobra 3 Max', 'Kobra S1')
ACE2_3_MODELS = ('Kobra 3', 'Kobra 3 V2', 'Kobra 3 Max', 'Kobra 3 Max V2', 'Kobra 4')
ACE2_S_MODELS = ('Kobra S1', 'Kobra S1 Max', 'Kobra X')

FEEDERS = {
    'ace_pro': {
        'name': 'ACE Pro', 'kind': 'Externe Filamentbox', 'format_state': 'documented',
        'models': PRO_MODELS, 'codec': 'ACE Version 2 / NTAG213',
        'variants': {
            'kobra3': ('ACE Pro für Kobra 3 / Kobra 3 V2', ('Kobra 3', 'Kobra 3 V2')),
            's1': ('ACE Pro für Kobra S1', ('Kobra S1',)),
            'k3_max': ('ACE Pro für Kobra 3 Max', ('Kobra 3 Max',)),
            'k3_max_upgrade': ('Kobra-3-Ausführung mit Kobra-3-Max-Upgrade-Kit', ('Kobra 3 Max',)),
        },
        'source': 'https://eu.anycubic.com/products/ace-pro',
        'note': 'Die Kobra-3-, Kobra-S1- und Kobra-3-Max-Anschlussausführungen sowie das offizielle Upgrade-Kit gehören zur ACE-Pro-Familie. Passende Kabel und Firmware am Gerät prüfen.',
    },
    'ace2_pro': {
        'name': 'ACE 2 Pro', 'kind': 'Externe Filamentbox', 'format_state': 'documented',
        'models': ACE2_3_MODELS+ACE2_S_MODELS, 'codec': 'ACE Version 2 / NTAG213',
        'variants': {
            'k3_k4': ('Für Kobra 3 / 3 V2 / 3 Max / 3 Max V2 / 4', ACE2_3_MODELS),
            's1_x': ('Für Kobra S1 / S1 Max / X', ACE2_S_MODELS),
        },
        'source': 'https://store.anycubic.com/products/ace-2-pro',
        'note': 'Die beiden offiziellen Zubehör-/Anschlussgruppen werden getrennt erfasst. Das gemeinsame ACE-Taglayout ist durch unabhängige Analyse der ACE-2-Pro-Firmware V1.1.31 dokumentiert; unsere Tags sind hier nicht am Gerät geprüft.',
    },
    'kobra_x_integrated': {
        'name': 'Kobra X – integrierter Wechsler / RFID', 'kind': 'Im Drucker integriert',
        'format_state': 'unconfirmed', 'models': ('Kobra X',),
        'codec': 'ACE-Version-2-Testformat / NTAG213 · Erkennung offen',
        'variants': {'integrated': ('Integriert (ACE Gen 2), keine externe ACE-Box', ('Kobra X',))},
        'source': 'https://wiki.anycubic.com/kobra-x/M02010203-Kobra%20X%E7%94%A8%E6%88%B7%E6%89%8B%E5%86%8C-EN.pdf',
        'note': 'Mehrfarbwechsel und RFID sind offiziell beschrieben. Das ist ein anderer Eintrag als eine externe ACE 2 Pro am Kobra X. Das Ziel-Tagformat ist für diesen integrierten Leser noch nicht bestätigt.',
    },
    'other': {
        'name': 'Anderer / unbekannter Anycubic-NFC-Wechsler', 'kind': 'Nicht zugeordnet',
        'format_state': 'unconfirmed', 'models': PRINTERS,
        'codec': 'ACE-Version-2-Testformat / NTAG213 · Erkennung offen',
        'variants': {'unknown': ('Ausführung unbekannt', PRINTERS)}, 'source': '',
        'note': 'Ein Auffangeintrag für weitere Hardware, keine Kompatibilitätszusage. Ein NFC-Leser allein bestätigt weder das Tagformat noch den Zugriff auf eigene Kalibrierungsprofile.',
    },
}


def get_feeder(feeder_id):
    if feeder_id not in FEEDERS:
        raise ValueError('Zuerst den tatsächlich verwendeten Anycubic-Wechsler auswählen.')
    return deepcopy(FEEDERS[feeder_id])


def validate_selection(feeder_id, variant, model):
    feeder = get_feeder(feeder_id)
    if variant not in feeder['variants']:
        raise ValueError('Die Anschluss-/Zubehörvariante des Wechslers auswählen.')
    model = str(model).removeprefix('Anycubic ')
    if model not in feeder['variants'][variant][1]:
        raise ValueError(feeder['name']+' in dieser Ausführung ist nicht für '+model+' hinterlegt. Druckertyp und Wechsler getrennt prüfen.')
    return feeder


def require_write_target(feeder_id, variant, model, *, test_unknown_format=False):
    feeder = validate_selection(feeder_id, variant, model)
    if feeder['format_state'] != 'documented' and test_unknown_format is not True:
        raise ValueError('Das Tagformat dieses Wechslers ist noch nicht bestätigt. Das ACE-Testformat nur über die ausdrückliche Testfreigabe schreiben.')
    return feeder


def target_status(feeder_id, variant, model):
    try:
        feeder = validate_selection(feeder_id, variant, model)
    except ValueError as error:
        return str(error)
    return ('Experimentell · '+feeder['name']+' · '+feeder['codec']+
            ' · kein eigener Gerätetest. '+feeder['note'])


def feeder_rows():
    return [dict(id=key, **get_feeder(key)) for key in FEEDERS]

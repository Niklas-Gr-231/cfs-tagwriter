# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Validated saved-slicer authority metadata; no filesystem/network operations."""
from copy import deepcopy
import re


def validate_source(source):
    if not isinstance(source,dict) or source.get('schema_version')!=1 or source.get('authority')!='slicer':
        raise ValueError('Ungültige Slicer-Priorität.')
    if not re.fullmatch(r'[0-9a-f]{32}',str(source.get('file_id',''))) or not re.fullmatch(r'[0-9a-f]{64}',str(source.get('fingerprint',''))):
        raise ValueError('Stabile Slicerkennung oder Quellstand fehlt.')
    filename=source.get('filename')
    if not isinstance(filename,str) or not filename or len(filename)>255 or any(c in filename for c in '/\\\x00\r\n') or not filename.lower().endswith('.json'):
        raise ValueError('Ungültiger Slicer-Dateiname.')
    account,sid=source.get('cloud_account_id'),source.get('cloud_setting_id')
    if (account is None)!=(sid is None) or (account is not None and (not isinstance(account,str) or not isinstance(sid,str) or not re.fullmatch(r'[0-9]+',str(account)) or not re.fullmatch(r'[0-9a-f]{24}',str(sid)))):
        raise ValueError('Unvollständiger Cloud-Verweis der Slicerdatei.')
    return deepcopy(source)


def cloud_reference(source):
    source=validate_source(source)
    return 'cloud:'+source['cloud_account_id']+':'+source['cloud_setting_id'] if source.get('cloud_account_id') else None

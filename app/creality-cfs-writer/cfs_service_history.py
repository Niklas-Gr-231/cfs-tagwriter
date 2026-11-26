# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Last confirmed service report per address; never a live status substitute."""
from datetime import datetime, timezone
import json
from pathlib import Path
from cfs_locking import locked_file
from cfs_profile_sync import write_json


class ServiceHistory:
    def __init__(self, directory):
        self.path = Path(directory)/'state'/'printer-services.json'

    def _read(self):
        if not self.path.exists():return {'schema_version':1, 'printers':{}}
        data = json.loads(self.path.read_text())
        if not isinstance(data,dict) or data.get('schema_version') != 1 or not isinstance(data.get('printers'),dict):
            raise ValueError('Gespeicherte Dienstversionsübersicht ist beschädigt.')
        return data

    def get(self, address):
        return self._read()['printers'].get(address)

    def observe(self, address, report):
        if not address:raise ValueError('Druckeradresse fehlt.')
        item = {key:report.get(key) for key in ('installed','running','version','state','model')}
        item['checked_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a+') as lock, locked_file(lock):
            data = self._read()
            data['printers'][address] = item
            write_json(self.path, data)
        return item

    def label(self, address):
        item = self.get(address)
        if not item:return 'Dieser Drucker: Dienstversion noch nicht geprüft.'
        return ('Dieser Drucker: zuletzt bestätigte Dienstversion '+str(item['version'] or 'nicht installiert/unbekannt')+
                ' · '+str(item.get('model') or 'Modell nicht bestätigt')+' · '+item['checked_at']+
                '. Status vor einer Aktion erneut prüfen.')

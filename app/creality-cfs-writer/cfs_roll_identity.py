# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Stable local roll identity; no printer/profile synchronization or tag writes."""
import json
from contextlib import nullcontext
from pathlib import Path
import re
from cfs_codec import new_serial
from cfs_fleet import tag_key,FleetStore
from cfs_locking import locked_file
from cfs_profile_sync import write_json


def valid_serial(value):
    value=str(value or '').strip()
    return value if re.fullmatch('[0-9]{6}',value) and value!='000000' else None


class RollIdentities:
    def __init__(self,directory,factory=None,*,memory=False):
        self.path=Path(directory)/'state/roll-identities.json'
        self.factory=factory or new_serial
        self.memory=memory
        self._memory_data={'schema_version':1,'tags':{}}

    def _load(self):
        if self.memory:return self._memory_data
        if not self.path.exists():return {'schema_version':1,'tags':{}}
        with self.path.open('rb') as stream:raw=stream.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Die lokale Rollenzuordnung ist zu groß.')
        try:data=json.loads(raw.decode('utf-8'))
        except (ValueError,UnicodeError):raise ValueError('Die lokale Rollenzuordnung ist beschädigt. Die Datei wurde nicht verändert.') from None
        if not isinstance(data,dict) or data.get('schema_version')!=1 or not isinstance(data.get('tags'),dict) or len(data['tags'])>20000:
            raise ValueError('Die lokale Rollenzuordnung ist beschädigt.')
        for key,serial in data['tags'].items():
            protocol,_,uid=key.partition(':')
            if tag_key(protocol,uid)!=key or not valid_serial(serial):raise ValueError('Ungültige lokale Rollenzuordnung.')
        return data

    def resolve(self,protocol,uid,incoming=None,legacy=None):
        key=tag_key(protocol,uid)
        if not self.memory:self.path.parent.mkdir(parents=True,exist_ok=True)
        with (nullcontext() if self.memory else self.path.with_suffix('.lock').open('a+')) as lock, (nullcontext() if self.memory else locked_file(lock)):
            data=self._load();previous=data['tags'].get(key)
            serial=valid_serial(incoming) or previous or valid_serial(legacy)
            created=False
            if serial is None:
                used=set(data['tags'].values())
                if not self.memory:used.update(FleetStore(self.path.parent.parent).load()['rolls'])
                for _ in range(100):
                    candidate=valid_serial(self.factory())
                    if candidate and candidate not in used:
                        serial=candidate;created=True;break
                if serial is None:raise ValueError('Keine freie Rollennummer gefunden. Erneut lesen.')
            if previous!=serial:
                if previous is None and len(data['tags'])>=20000:raise ValueError('Die lokale Rollenzuordnung ist voll.')
                data['tags'][key]=serial
                if not self.memory:write_json(self.path,data);self.path.chmod(0o600)
            return serial,created

    def remember(self,protocol,uid,serial):
        if not valid_serial(serial):raise ValueError('Die Rollennummer muss sechs Ziffern enthalten und darf nicht 000000 sein.')
        return self.resolve(protocol,uid,incoming=serial)[0]

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Optional two-tag workflow; each tag keeps its own UID and derived key."""
from copy import deepcopy
from datetime import datetime


def payload_identity(spec):
    return spec.material_id,spec.color.lstrip('#').upper(),spec.weight_g,spec.serial


class TwoTagSession:
    def __init__(self,clock=None):
        self.clock=clock or (lambda:datetime.now().astimezone().strftime('%H:%M:%S'))
        self.enabled=False
        self.reset()

    def reset(self,seen=False):
        self.seen=bool(seen)
        self.written=[]
        self.spec=None
        self.last_read_uid=None
        self.written_at={}
        self.last_event=''

    def enable(self,enabled,seen=False):
        self.enabled=bool(enabled)
        self.reset(seen)

    @property
    def preserve_values(self):
        return self.enabled and self.seen

    @property
    def locked(self):
        return self.enabled and self.spec is not None

    def number_for(self,uid):
        uid=uid.upper()
        if uid in self.written:return self.written.index(uid)+1
        return len(self.written)+1 if len(self.written)<2 else None

    def read(self,uid=None):
        if not self.enabled:return
        self.seen=True
        if uid is None:return
        uid=uid.upper();self.last_read_uid=uid
        number=self.number_for(uid);at=self.clock()
        if uid in self.written:
            self.last_event=f'Tag {number} erneut gelesen um {at}. Bereits geschrieben und geprüft um {self.written_at[uid]}.'
        elif number is None:
            self.last_event=f'Weiterer Tag gelesen um {at}. Beide Tags dieser Gruppe sind bereits fertig.'
        else:self.last_event=f'Tag {number} gelesen um {at}.'

    def check_write(self,uid,spec):
        if not self.enabled:return
        if len(self.written)>=2:
            raise ValueError('Beide Tags sind fertig. Für die nächste Rolle „Neue Rolle“ wählen oder den Zweiermodus zurücksetzen.')
        if uid.upper() in self.written:
            raise ValueError('Dieser Tag wurde in der Zweiergruppe bereits beschrieben. Bitte den anderen Tag einlesen.')
        if self.spec is not None and payload_identity(spec)!=payload_identity(self.spec):
            raise ValueError('Die Materialdaten haben sich seit Tag 1 geändert. Zweiermodus zurücksetzen und beide Tags mit den gewünschten Werten neu schreiben.')

    def confirmed(self,uid,spec):
        if not self.enabled:return
        self.check_write(uid,spec)
        if self.spec is None:self.spec=deepcopy(spec)
        self.written.append(uid.upper())
        self.written_at[uid.upper()]=self.clock()
        self.last_event=f'Tag {len(self.written)} geschrieben und zurückgelesen um {self.written_at[uid.upper()]}.'
        self.seen=True

    def hint(self):
        if not self.enabled:return ''
        if len(self.written)==2:
            phase='2/2 Tags geschrieben. Für die nächste Rolle „Neue Rolle“ wählen oder Zweiermodus zurücksetzen.'
        elif len(self.written)==1:
            if self.last_read_uid and self.last_read_uid not in self.written:
                phase='1/2 Tags geschrieben. Tag 2 ist bereit: „Tag schreiben“ wählen. Wunschwerte bleiben gleich.'
            else:phase='1/2 Tags geschrieben. Zweiten Tag einlesen – Material, Farbe, Restmenge und Rollennummer bleiben gleich.'
        elif self.seen:phase='Wunschwerte einstellen und schreiben. Beim nächsten Einlesen bleiben diese Werte erhalten.'
        else:phase='Tag 1 lesen: vorhandene Daten samt Rollennummer übernehmen. Bei Bedarf ändern, schreiben, dann Tag 2 lesen und schreiben.'
        return (self.last_event+' '+phase).strip()

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Keep tag feedback separate from unrelated network and progress messages."""
class TagFeedback:
    def __init__(self):
        self.reset()

    def reset(self):
        self.operation = None
        self.phase = 'idle'
        self.uid = None
        self.message = 'Noch kein Tag gelesen.'

    def begin(self, operation):
        if operation not in ('read', 'write'):
            raise ValueError('Unbekannte Tag-Aktion')
        self.operation = operation
        self.phase = 'busy'
        self.message = 'Tag wird gelesen…' if operation == 'read' else 'Tag wird geschrieben und zurückgelesen…'

    def success(self, uid, *, verified=False, details=''):
        if self.operation == 'write' and verified is not True:
            raise ValueError('Schreiben ohne Rücklesebestätigung ist kein Erfolg.')
        self.uid = uid
        self.phase = 'success'
        self.message = ('✓ Tag geschrieben und durch Rücklesen geprüft' if self.operation == 'write' else '✓ Tag erfolgreich gelesen')+' · '+uid
        if details:self.message+='\n'+str(details)

    def fail(self, message):
        self.phase = 'error'
        self.message = ('✕ Schreiben fehlgeschlagen. Erneut schreiben.' if self.operation == 'write' else
                        '✕ Lesen fehlgeschlagen. Erneut lesen.')+' '+str(message)

    def edited(self):
        if self.operation == 'write' and self.phase == 'success':
            self.phase = 'idle'
            self.message = 'Angaben geändert. Diese Änderungen sind noch nicht auf den Tag geschrieben.'

    def caption(self, operation):
        if self.operation == operation and self.phase == 'busy':
            return 'Wird gelesen…' if operation == 'read' else 'Wird geschrieben…'
        if self.operation == operation and self.phase == 'error':
            return 'Erneut lesen' if operation == 'read' else 'Erneut schreiben'
        return 'Tag lesen' if operation == 'read' else 'Tag schreiben'


def filament_details(spec,material=None):
    """Snapshot the actual verified payload, not later edits to the form."""
    import re
    material=material or {}
    name=str(getattr(spec,'name','') or material.get('name') or '').strip()
    kind=getattr(spec,'type',None) or material.get('type')
    if isinstance(kind,list):kind=kind[0] if kind else ''
    if not kind:
        match=re.search(r'\b(PETG|PLA|TPU|ABS|ASA|PVA|PA|PC|PET|HIPS)(?:[-+][A-Z0-9]+)?\b',name,re.IGNORECASE)
        kind=match[0].upper() if match else 'Filament'
    parts=[str(kind)]
    if name and name.casefold()!=str(kind).casefold():parts.append(name)
    parts.extend((str(spec.color).upper(),str(spec.weight_g)+' g','Rolle '+spec.serial))
    return ' · '.join(parts)

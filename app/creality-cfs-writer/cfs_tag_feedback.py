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

    def success(self, uid, *, verified=False):
        if self.operation == 'write' and verified is not True:
            raise ValueError('Schreiben ohne Rücklesebestätigung ist kein Erfolg.')
        self.uid = uid
        self.phase = 'success'
        self.message = ('✓ Tag geschrieben und durch Rücklesen geprüft' if self.operation == 'write' else '✓ Tag erfolgreich gelesen')+' · '+uid

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

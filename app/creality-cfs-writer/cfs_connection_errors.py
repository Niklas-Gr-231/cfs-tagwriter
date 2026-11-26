# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Actionable connection failures; no passwords or raw server errors in UI."""
import errno
import socket
import subprocess
import urllib.error

class ConnectionIssue(ValueError):
    def __init__(self,code,message):
        self.code=code
        super().__init__(message)

def auth_issue(password_supplied=True):
    if password_supplied:
        return ConnectionIssue('SSH_AUTH_FAILED','Passwort nicht akzeptiert. Das SSH-Passwort für Benutzer root prüfen; maßgeblich ist das am Drucker angezeigte bzw. selbst geänderte Passwort.')
    return ConnectionIssue('SSH_AUTH_FAILED','SSH-Anmeldung fehlgeschlagen. Bitte das Root-/SSH-Passwort eingeben oder eine gültige SSH-Schlüsselanmeldung verwenden.')

def network_issue(error,address='',*,ssh=False):
    if isinstance(error,ConnectionIssue):return error
    names={kind.__name__ for kind in type(error).__mro__}
    if 'BadHostKeyException' in names:
        return ConnectionIssue('HOST_KEY_CHANGED','Der SSH-Hostschlüssel hat sich geändert. Geräteidentität prüfen; die Verbindung wurde nicht übernommen.')
    reason=getattr(error,'reason',error)
    if isinstance(reason,(TimeoutError,socket.timeout,subprocess.TimeoutExpired)):
        return ConnectionIssue('NETWORK_TIMEOUT',f'Keine Antwort von {address or "dieser IP-Adresse"}. Drucker einschalten und IP-Adresse sowie Heimnetz prüfen.')
    if isinstance(error,urllib.error.HTTPError):
        if error.code in (401,403):
            return ConnectionIssue('PRINTER_API_AUTH','Der Druckerzugang ist geschützt. Die lokale Moonraker-Zugriffsfreigabe prüfen; dies ist keine Bestätigung eines falschen SSH-Passworts.')
        return ConnectionIssue('NOT_PRINTER','Unter dieser IP wurde kein unterstützter Druckerzugang gefunden. IP-Adresse und den lokalen Druckerzugang auf Port 4408 prüfen.')
    errors=getattr(error,'errors',{})
    errnos={getattr(e,'errno',None) for e in errors.values()} if isinstance(errors,dict) else set()
    errnos.add(getattr(reason,'errno',None))
    if errno.ECONNREFUSED in errnos:
        if ssh:return ConnectionIssue('SSH_DISABLED','SSH-Verbindung abgelehnt. Root-/SSH-Zugang am Drucker aktivieren und Port 22 prüfen.')
        return ConnectionIssue('PRINTER_API_UNAVAILABLE','Unter dieser IP ist kein Druckerzugang auf Port 4408 erreichbar. IP prüfen; gegebenenfalls Drucker einschalten oder den lokalen Zugriff freigeben.')
    if isinstance(reason,OSError) or errno.ENETUNREACH in errnos or errno.EHOSTUNREACH in errnos:
        return ConnectionIssue('NETWORK_UNREACHABLE',f'{address or "Die Adresse"} ist nicht erreichbar. IP-Adresse, Heimnetz und eingeschalteten Drucker prüfen.')
    if ssh:
        return ConnectionIssue('SSH_CONNECTION','SSH-Verbindung fehlgeschlagen. IP-Adresse, Root-/SSH-Freigabe und Port 22 prüfen.')
    return ConnectionIssue('NOT_PRINTER','Die IP antwortet nicht wie ein unterstützter Drucker. IP-Adresse und den lokalen Druckerzugang prüfen.')

def ssh_issue(error,address='',password_supplied=True):
    names={kind.__name__ for kind in type(error).__mro__}
    if names.intersection({'AuthenticationException','UnableToAuthenticate','PasswordRequiredException'}):
        return auth_issue(password_supplied)
    return network_issue(error,address,ssh=True)

def ssh_cli_issue(returncode,error,password_supplied=True):
    message=error.lower()
    if returncode==5 or any(term in message for term in ('permission denied','authentication failed','access denied')):
        return auth_issue(password_supplied)
    if 'host key verification failed' in message or 'remote host identification has changed' in message:
        return ConnectionIssue('HOST_KEY_CHANGED','Der SSH-Hostschlüssel ist unbekannt oder verändert. Die Geräteidentität zuerst prüfen.')
    if 'connection refused' in message:
        return network_issue(ConnectionRefusedError(errno.ECONNREFUSED,''),ssh=True)
    if 'timed out' in message:return network_issue(TimeoutError(),ssh=True)
    return network_issue(RuntimeError(),ssh=True)

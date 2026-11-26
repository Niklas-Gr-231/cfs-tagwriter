# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Local printer bookmarks; optional passwords live only in the OS keyring."""
import importlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from cfs_locking import locked_file

SERVICE = 'CFS-Tagwriter-SSH'

class ConnectionStore:
    def __init__(self, directory, backend=None):
        self.directory=Path(directory)
        self.path=self.directory/'printer-connections.json'
        self.backend=backend

    def _address(self,address):
        ip=ipaddress.IPv4Address(str(address).strip())
        if ip.is_unspecified or ip.is_loopback or ip.is_multicast or int(ip)==0xffffffff:
            raise ValueError('Bitte die lokale IPv4-Adresse des Druckers eingeben.')
        return str(ip)

    def choices(self):
        if not self.path.exists():return []
        data=json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or data.get('schema_version')!=1 or not isinstance(data.get('printers'),list):
            raise ValueError('Gespeicherte Druckerverbindungen sind beschädigt.')
        seen=set()
        for item in data['printers']:
            if not isinstance(item,dict) or not isinstance(item.get('name'),str) or not isinstance(item.get('password_saved'),bool):
                raise ValueError('Gespeicherte Druckerverbindungen sind beschädigt.')
            address=self._address(item.get('ip',''))
            if address in seen:raise ValueError('Druckerverbindung ist doppelt gespeichert.')
            seen.add(address)
        return data['printers']

    def _keyring(self,install=False):
        if self.backend is not None:return self.backend
        libraries=self.directory/'python-libs'
        if str(libraries) not in sys.path:sys.path.insert(0,str(libraries))
        try:import keyring
        except ImportError:
            if not install:raise ValueError('Schlüsselbund-Paket fehlt. Mit „Passwort merken“ einmal erfolgreich verbinden, um es einzurichten.')
            try:result=subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--target',str(libraries),'keyring==25.6.0'],capture_output=True,timeout=300)
            except (OSError,subprocess.TimeoutExpired):raise ValueError('Schlüsselbund-Paket konnte nicht eingerichtet werden; Passwort wurde nicht gespeichert.') from None
            if result.returncode:raise ValueError('Schlüsselbund-Paket konnte nicht eingerichtet werden. Python-pip und Internet prüfen; Passwort wurde nicht gespeichert.')
            importlib.invalidate_caches()
        try:
            if sys.platform=='win32':
                from keyring.backends.Windows import WinVaultKeyring
                backend=WinVaultKeyring()
            elif sys.platform=='darwin':
                from keyring.backends.macOS import Keyring
                backend=Keyring()
            else:
                from keyring.backends.SecretService import Keyring
                backend=Keyring()
            if backend.priority<=0:raise ValueError()
        except Exception:
            raise ValueError('Kein verfügbarer System-Schlüsselbund. Unter Mint den Anmeldeschlüsselbund entsperren bzw. python3-pip und gnome-keyring prüfen. Passwort wird nicht als Datei gespeichert.') from None
        self.backend=backend
        return backend

    def password(self,address):
        address=self._address(address)
        if not any(p['ip']==address and p.get('password_saved') for p in self.choices()):return ''
        try:return self._keyring().get_password(SERVICE,'root@'+address) or ''
        except ValueError:raise
        except Exception:raise ValueError('Gespeichertes Passwort konnte nicht aus dem System-Schlüsselbund gelesen werden.') from None

    def remember(self,name,address,password='',remember_password=False,*,model='',feeder_id=None,feeder_variant=None):
        address=self._address(address);name=str(name).strip()
        if not name or len(name)>80 or any(ord(c)<32 for c in name):raise ValueError('Bitte eine gültige Druckerbezeichnung eingeben.')
        if len(password)>1024 or '\n' in password or '\r' in password:raise ValueError('Ungültiges Passwort.')
        self.directory.mkdir(parents=True,exist_ok=True)
        with self.path.with_suffix('.lock').open('a+') as lock,locked_file(lock):
            choices=self.choices();old=next((p for p in choices if p['ip']==address),{})
            selected_model=str(model or old.get('model',''))[:80]
            extra={}
            if selected_model.startswith('Anycubic '):
                if feeder_id is not None:
                    from cfs_anycubic_feeders import validate_selection
                    validate_selection(feeder_id,feeder_variant,selected_model)
                    extra={'feeder_id':feeder_id,'feeder_variant':feeder_variant}
                else:
                    extra={key:old[key] for key in ('feeder_id','feeder_variant') if key in old}
            if remember_password:
                if not password:raise ValueError('Zum Merken ein Passwort eingeben oder „Passwort merken“ abwählen.')
                try:self._keyring(install=True).set_password(SERVICE,'root@'+address,password)
                except ValueError:raise
                except Exception:raise ValueError('Passwort konnte nicht im System-Schlüsselbund gespeichert werden.') from None
            elif old.get('password_saved'):
                try:
                    backend=self._keyring()
                    if backend.get_password(SERVICE,'root@'+address) is not None:backend.delete_password(SERVICE,'root@'+address)
                except ValueError:raise
                except Exception:raise ValueError('Gespeichertes Passwort konnte nicht gelöscht werden.') from None
            rows=[p for p in choices if p['ip']!=address]
            rows.append({'name':name,'ip':address,'password_saved':bool(remember_password),'model':selected_model,**extra})
            temporary=None
            try:
                with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=self.directory,delete=False) as stream:
                    temporary=Path(stream.name)
                    json.dump({'schema_version':1,'printers':rows},stream,ensure_ascii=False,indent=2)
                    stream.flush();os.fsync(stream.fileno())
                temporary.chmod(0o600);temporary.replace(self.path)
            finally:
                if temporary is not None:temporary.unlink(missing_ok=True)
        return {'saved':True,'password_saved':bool(remember_password)}

#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Check the staged/tracked publication set without reading user data folders."""
import hashlib
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRECTORIES = {'state', 'backups', 'userdata', 'data', 'python-libs', 'label-python-libs', 'arduino-tools', '.venv', '__pycache__'}
FORBIDDEN_NAMES = {'printer-connections.json', 'profil-zuordnung.json', 'known_hosts', 'ui-settings.json', 'label-printer.json', 'fleet.json', 'slicer-sync-settings.json', 'slicer-source-identities.json', 'printer-firmware.json', 'printer-services.json', 'fleet.json', 'label-preferences.json'}
REQUIRED = ('LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md', 'README.md', 'requirements.txt', 'start.py',
            'docs/GITHUB-BESCHREIBUNG.md', 'docs/INSTALLATION.md', 'docs/RECHTLICHES.md', '.gitignore')


def publication_files():
    if (ROOT/'.git').is_dir():
        raw = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
        return [Path(os_path) for os_path in raw.decode().split('\0') if os_path]
    # Source ZIPs have no Git metadata. Ignore only known local runtime caches.
    return [p.relative_to(ROOT) for p in ROOT.rglob('*') if p.is_file()
            and not set(p.relative_to(ROOT).parts).intersection({'.git', '.venv', '__pycache__'})]


def check():
    if (ROOT/'.git').is_dir():
        result = subprocess.run(['git', 'diff', '--quiet', '--'], cwd=ROOT)
        if result.returncode:
            raise SystemExit('Ungestagte Änderungen zuerst prüfen und mit git add übernehmen, damit Arbeitsstand und Veröffentlichungsindex übereinstimmen.')
    files = publication_files()
    failures = []
    for required in REQUIRED:
        if Path(required) not in files:
            failures.append('Pflichtdatei fehlt im Veröffentlichungssatz: '+required)
    for relative in files:
        path = ROOT/relative
        if path.is_symlink():
            failures.append('Symlink im Veröffentlichungssatz: '+str(relative))
            continue
        if set(relative.parts).intersection(FORBIDDEN_DIRECTORIES) or relative.name in FORBIDDEN_NAMES or relative.suffix in ('.hex', '.elf', '.pem', '.key', '.pyc'):
            failures.append('Laufzeit-/Gerätedatei enthalten: '+str(relative))
        if path.suffix == '.3mf':
            with zipfile.ZipFile(path) as archive:
                expected={'[Content_Types].xml','_rels/.rels','3D/3dmodel.model','Metadata/ATTRIBUTION.txt'}
                if set(archive.namelist()) != expected or sum(item.file_size for item in archive.infolist())>2_000_000:
                    failures.append('Nicht geprüfte 3MF-Inhalte: '+str(relative));continue
                text='\n'.join(archive.read(name).decode('utf-8') for name in sorted(expected))
        elif path.suffix in ('.py', '.ino', '.md', '.json', '.sh', '.command', '.bat', '.yml', '.txt', '.svg', '.cpp', '.h'):
            text = path.read_text(encoding='utf-8')
        else:
            continue
        checks = (
            r'-----BEGIN (?:OPENSSH|RSA|EC|DSA|PRIVATE) PRIVATE KEY-----',
            r'-----BEGIN ' + r'PRIVATE KEY-----',
            r'/home/[A-Za-z0-9_.-]+/',
            r'/Users/[A-Za-z0-9_.-]+/',
            r'(?i)\b(?:Authorization:\s*Bearer|access_token|refresh_token)\s*[=:]\s*[A-Za-z0-9._-]{20,}',
            r'(?i)[A-Z]:\\Users\\[^\\\s]+\\',
            r'\b192\.168\.\d{1,3}\.\d{1,3}\b',
            r'https?://[^/\s]+:[^/@\s]+@',
        )
        if any(re.search(pattern, text) for pattern in checks):
            failures.append('Mögliche persönliche Daten prüfen: '+str(relative))
    official = ROOT/'LICENSES/PolyForm-Noncommercial-1.0.0.txt'
    if (ROOT/'LICENSE').read_bytes() != official.read_bytes():
        failures.append('Projektlizenz weicht vom unveränderten Lizenztext ab.')
    expected = 'ffcca38841adb694b6f380647e15f17c446a4d1656fed51a1e2041d064c94cc8'
    if hashlib.sha256(official.read_bytes()).hexdigest() != expected:
        failures.append('Der geprüfte offizielle Lizenztext wurde verändert.')
    if failures:
        raise SystemExit('\n'.join(failures))
    print(f'{len(files)} Dateien geprüft. Lizenztexte und Veröffentlichungssatz vollständig, keine Treffer der Datenschutzprüfung.')
    return files


if __name__ == '__main__':
    check()

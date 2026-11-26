#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Start the source checkout with a separate per-user data directory."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
WRITER = ROOT/'app/creality-cfs-writer'
SERVICE = ROOT/'app/creality-cfs-cloud'


def user_data_directory():
    if os.environ.get('CFS_APP_DATA'):
        return Path(os.environ['CFS_APP_DATA']).expanduser().resolve()
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))
        return base/'CFS-Tagwriter/data'
    if sys.platform == 'darwin':
        return Path.home()/'Library/Application Support/CFS-Tagwriter/data'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'cfs-tagwriter/data'


def main(argv=None):
    if sys.version_info < (3, 10):
        raise SystemExit('Python 3.10 oder neuer wird benötigt.')
    parser = argparse.ArgumentParser(description='CFS Tagwriter aus dem Git-Projekt starten')
    parser.add_argument('--demo', action='store_true', help='Oberfläche ohne Gerätezugriffe öffnen')
    parser.add_argument('--check', action='store_true', help='Abhängigkeiten ohne Gerätezugriff prüfen')
    parser.add_argument('--data-dir', type=Path, help='Eigene Benutzerablage wählen')
    args = parser.parse_args(argv)
    required = ('tkinter', 'serial', 'cryptography', 'paramiko', 'keyring', 'PIL')
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        print('Fehlende Komponenten: '+', '.join(missing), file=sys.stderr)
        print('Siehe docs/INSTALLATION.md. Python-Pakete mit python -m pip install -r requirements.txt installieren.', file=sys.stderr)
        return 1
    sys.path[:0] = [str(WRITER), str(SERVICE)]
    from cfs_versions import APP_VERSION, SERVICE_VERSION, BRIDGE_VERSION
    if args.check:
        from cfs_label_protocol import compression_library
        try:
            compression_library()
            compression = 'bereit'
        except ValueError as error:
            compression = str(error)
        print(json.dumps({'app': APP_VERSION, 'printer_service': SERVICE_VERSION,
                          'bridge': BRIDGE_VERSION, 'platform': sys.platform,
                          'dependencies': 'ready', 'optional_direct_print_compression': compression}, ensure_ascii=False))
        return 0
    directory = args.data_dir.expanduser().resolve() if args.data_dir else user_data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    registry = directory/'profil-zuordnung.json'
    if not registry.exists():
        initial = {'schema_version': 1, 'sync_source': 'printer_cloud', 'profiles': [],
                   'printer': {'ip': '', 'name': 'Mein Drucker'}, 'cloud_materials_url': ''}
        try:
            with registry.open('x', encoding='utf-8') as stream:
                json.dump(initial, stream, ensure_ascii=False, indent=2)
        except FileExistsError:
            pass
    os.environ['CFS_APP_DATA'] = str(directory)
    os.environ['CFS_PROFILE_REGISTRY'] = str(registry)
    from cfs_writer import main as run_writer
    arguments = ['--registry', str(registry)]
    if args.demo:
        arguments.append('--demo')
    return run_writer(arguments)


if __name__ == '__main__':
    raise SystemExit(main())

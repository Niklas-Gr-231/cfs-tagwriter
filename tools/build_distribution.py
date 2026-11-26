#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Prepare versioned public release assets; never publish or replace a release."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
import zipfile
from check_publication import ROOT, check


def release_versions(tag=None):
    values=runpy.run_path(str(ROOT/'app/creality-cfs-writer/cfs_versions.py'))
    version=values['APP_VERSION']
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)',version):
        raise ValueError('Die App-Version muss eine stabile dreiteilige Versionsnummer sein.')
    if tag is not None and tag!='v'+version:
        raise ValueError('Git-Tag und App-Version stimmen nicht überein: erwartet v'+version)
    return values


def release_notes(version):
    text=(ROOT/'CHANGELOG.md').read_text(encoding='utf-8')
    marker='**'+version+' ·'
    if marker not in text:raise ValueError('Änderungsbeschreibung für diese Version fehlt.')
    section=text[text.index(marker):]
    following=re.search(r'\n\*\*[0-9]+\.[0-9]+\.[0-9]+ ·',section)
    if following:section=section[:following.start()]
    return '# CFS Tagwriter '+version+'\n\n'+section.strip()+'\n\nÄltere Versionen bleiben unter Releases und Tags verfügbar. Persönliche Profile und Zugangsdaten sind nicht enthalten.\n'


def build(destination,tag=None):
    versions=release_versions(tag)
    destination=Path(destination).expanduser().resolve()
    if destination==ROOT or ROOT in destination.parents:raise ValueError('Ausgabe außerhalb des Repositorys wählen.')
    if destination.exists() and any(destination.iterdir()):raise ValueError('Ausgabeordner ist nicht leer; vorhandene Releases werden nicht überschrieben.')
    check()
    notes=release_notes(versions['APP_VERSION'])
    destination.mkdir(parents=True,exist_ok=True)
    version=versions['APP_VERSION']
    subprocess.run([sys.executable,str(ROOT/'tools/build_portable.py'),str(destination)],check=True)
    app=destination/('CFS_Tagwriter_'+version+'.py')
    subprocess.run([sys.executable,str(app),'--self-check'],check=True)
    subprocess.run([sys.executable,str(ROOT/'tools/build_release.py'),str(destination/('CFS_Tagwriter_'+version+'_Git_Projekt.zip'))],check=True)
    with zipfile.ZipFile(destination/('CFS_Tagwriter_'+version+'_Weitergabe.zip'),'x',zipfile.ZIP_DEFLATED) as archive:
        archive.write(app,app.name)
        for name in ('README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md'):
            archive.write(ROOT/name,name)
        for directory in ('docs','LICENSES'):
            for file in sorted((ROOT/directory).rglob('*')):
                if file.is_file():archive.write(file,file.relative_to(ROOT))
        for file in sorted((ROOT/'app/creality-cfs-writer/sample-assets').iterdir()):
            if file.is_file():archive.write(file,'Beispielplatte/'+file.name)
        shell='#!/bin/sh\nset -eu\nTASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec python3 "$TASK_DIR/'+app.name+'" "$@"\n'
        for name in ('Start-Tagwriter.sh','Start-Tagwriter.command'):
            info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=0o100755<<16;info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,shell)
        archive.writestr('Start-Tagwriter.bat','@echo off\r\npy -3 "%~dp0'+app.name+'" %*\r\n')
    (destination/'RELEASE-NOTES.md').write_text(notes,encoding='utf-8')
    for archive in destination.glob('*.zip'):
        with zipfile.ZipFile(archive) as opened:
            if opened.testzip() is not None:raise ValueError('Archivprüfung fehlgeschlagen.')
    manifest={'app_version':version,'printer_service_version':versions['SERVICE_VERSION'],'arduino_bridge_version':versions['BRIDGE_VERSION'],
              'private_data_included':False,'sha256':{file.name:hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted(destination.iterdir()) if file.is_file()}}
    (destination/('CFS_Tagwriter_'+version+'_Pruefsummen.json')).write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (destination/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.name+'\n' for file in sorted(destination.iterdir()) if file.is_file()))
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--tag')
    args=parser.parse_args()
    try:print('Release-Dateien erstellt:',build(args.destination,args.tag))
    except (ValueError,OSError) as error:raise SystemExit(str(error))

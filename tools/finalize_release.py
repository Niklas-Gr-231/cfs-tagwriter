#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Add all tested platform packages, then regenerate the complete checksums."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
from check_publication import ROOT


def finalize(destination,native):
    values=runpy.run_path(str(ROOT/'app/creality-cfs-writer/cfs_versions.py'));version=values['APP_VERSION']
    required=['CFS_Tagwriter_'+version+'_'+key+extension for key,extension in (
        ('linux-x86_64','.AppImage'),('windows-x86_64','.exe'),('macos-arm64','.zip'),('macos-x86_64','.zip'),('macos-arm64','.dmg'),('macos-x86_64','.dmg'))]
    required.append('CFS_Tagwriter_'+version+'_AppImage_Runtime_Quellen.zip')
    for name in required:
        source=native/name
        if not source.is_file() or not source.with_name(name+'.sha256').is_file():raise ValueError('Geprüftes Plattformpaket fehlt: '+name)
        expected=source.with_name(name+'.sha256').read_text(encoding='utf-8').split()[0]
        if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:raise ValueError('Prüfsumme falsch: '+name)
        if (destination/name).exists():raise ValueError('Plattformpaket existiert bereits: '+name)
    for name in required:
        shutil.copy2(native/name,destination/name);shutil.copy2(native/(name+'.sha256'),destination/(name+'.sha256'))
    shutil.copy2(ROOT/'install-macos.sh',destination/'install-macos.sh')
    manifest=destination/('CFS_Tagwriter_'+version+'_Pruefsummen.json')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    data['sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.iterdir()) if p.is_file() and p.name not in (manifest.name,'SHA256SUMS.txt')}
    manifest.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    (destination/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(destination.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('destination',type=Path);parser.add_argument('native',type=Path)
    args=parser.parse_args();finalize(args.destination.resolve(),args.native.resolve())

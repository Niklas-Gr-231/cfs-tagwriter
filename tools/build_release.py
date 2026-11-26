#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Build a reviewed source ZIP, excluding Git metadata and local runtime files."""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile
from check_publication import ROOT, check

sys.path.insert(0, str(ROOT/'app/creality-cfs-writer'))
from cfs_versions import APP_VERSION

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path, help='ZIP-Speicherort außerhalb des Repositorys')
    args = parser.parse_args()
    destination = args.destination.expanduser().resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise SystemExit('Das Release außerhalb des Quellcodeordners speichern.')
    if destination.exists():
        raise SystemExit('Die Zieldatei existiert bereits. Einen neuen Speicherort wählen.')
    files = check()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(files):
            archive.write(ROOT/relative, f'cfs-tagwriter-{APP_VERSION}/'+relative.as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise SystemExit('ZIP-Prüfung fehlgeschlagen.')
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix+'.sha256').write_text(digest+'  '+destination.name+'\n')
    print(f'Quellcodepaket {APP_VERSION} erstellt. SHA-256 {digest}')

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Refresh only this application's existing Mint menu entry on normal launch."""
from pathlib import Path
import os
import sys
import tempfile
from cfs_versions import APP_VERSION

def refresh_menu_icon(assets,desktop=None):
    if not sys.platform.startswith('linux'):return False
    assets=Path(assets).resolve()
    desktop=Path(desktop) if desktop is not None else Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'applications/cfs-tagwriter.desktop'
    source_icon=assets/'cfs-tagwriter.png'
    if not desktop.is_file() or not source_icon.is_file():return False
    icon=assets/('cfs-tagwriter-'+APP_VERSION+'.png')
    text=desktop.read_text(encoding='utf-8')
    lines=text.splitlines()
    executable=next((line[5:] for line in lines if line.startswith('Exec=')),'')
    if 'Name=CFS Tagwriter' not in lines or str(assets) not in executable:return False
    if not icon.is_file() or icon.read_bytes()!=source_icon.read_bytes():icon.write_bytes(source_icon.read_bytes())
    wanted='Icon='+str(icon)
    if wanted in lines:return False
    if any(line.startswith('Icon=') for line in lines):
        lines=[wanted if line.startswith('Icon=') else line for line in lines]
    else:lines.append(wanted)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=desktop.parent,prefix='.cfs-icon-',delete=False) as stream:
            temporary=Path(stream.name)
            stream.write('\n'.join(lines)+'\n');stream.flush();os.fsync(stream.fileno())
        temporary.chmod(desktop.stat().st_mode&0o777)
        temporary.replace(desktop)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return True

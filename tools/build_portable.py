#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Build the portable app from reviewed public source only."""
import base64
import hashlib
import io
from pathlib import Path
import zipfile
import runpy
import argparse

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('destination', type=Path)
args = parser.parse_args()
OUT = args.destination.expanduser().resolve()
if OUT == ROOT or ROOT in OUT.parents:raise SystemExit('Ausgabe außerhalb des Quellcodeordners wählen.')
OUT.mkdir(parents=True,exist_ok=True)
SOURCE = ROOT
APP_SOURCE = SOURCE/'app'
from check_publication import check
check()
app_version = runpy.run_path(str(APP_SOURCE/'creality-cfs-writer/cfs_versions.py'))['APP_VERSION']
payload = io.BytesIO()
with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED) as archive:
    for directory in ('creality-cfs-writer', 'creality-cfs-cloud'):
        folder = APP_SOURCE/directory
        for path in sorted(folder.glob('*.py')):
            archive.write(path, directory+'/'+path.name)
    writer = APP_SOURCE/'creality-cfs-writer'
    for sketch in ('CFS_Mega_Bridge', 'CFS_Nano_Bridge'):
        for path in sorted((writer/sketch).rglob('*')):
            if path.is_file(): archive.write(path, 'creality-cfs-writer/'+str(path.relative_to(writer)))
    for name in ('cfs-tagwriter.svg','cfs-tagwriter.png','cfs-tagwriter-small.png','cfs-tagwriter.ico','printer-closed.png','printer-hi.png','printer-generic.png','tag-position.png','tag-position.svg','QUELLEN.md','app-release-notes.md','app-release-history.md'):
        archive.write(writer/name, 'creality-cfs-writer/'+name)
    for path in sorted((writer/'label-assets').iterdir()):
        if path.is_file():archive.write(path,'creality-cfs-writer/label-assets/'+path.name)
    for path in sorted((writer/'sample-assets').iterdir()):
        if path.is_file():archive.write(path,'creality-cfs-writer/sample-assets/'+path.name)
    for path in sorted((writer/'hardware-assets').iterdir()):
        if path.is_file():archive.write(path,'creality-cfs-writer/hardware-assets/'+path.name)
    for path in sorted((writer/'theme-assets').rglob('*.png')):
        archive.write(path,'creality-cfs-writer/'+str(path.relative_to(writer)))
    archive.write(APP_SOURCE/'creality-cfs-cloud/cfs-cloud-profiles.init', 'creality-cfs-cloud/cfs-cloud-profiles.init')
    archive.write(APP_SOURCE/'creality-cfs-cloud/cfs-cloud-profiles.sysv', 'creality-cfs-cloud/cfs-cloud-profiles.sysv')
    for name in ('LICENSE','NOTICE','THIRD_PARTY_NOTICES.md'):
        archive.write(SOURCE/name,name)
    for path in sorted((SOURCE/'LICENSES').glob('*')):
        if path.is_file():archive.write(path,'LICENSES/'+path.name)
raw = payload.getvalue()
template = r'''#!/usr/bin/env python3
"""CFS Tagwriter __APP_VERSION__ – redistributable single-file launcher (Python 3.10+)."""
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import runpy
import argparse
import subprocess
import sys
import threading
import zipfile

VERSION = '__APP_VERSION__'
ARCHIVE_SHA256 = '__HASH__'
ENCODED_SHA256 = '__ENCODED_HASH__'
FILES = __FILES__
PAYLOAD = '__PAYLOAD__'

def main():
    if sys.version_info < (3, 10):
        raise SystemExit('Bitte Python 3.10 oder neuer installieren.')
    if hashlib.sha256(PAYLOAD.encode('ascii')).hexdigest() != ENCODED_SHA256:
        raise SystemExit('Anwendungspaket beschädigt.')
    def archive_bytes():
        raw=base64.b85decode(PAYLOAD)
        if hashlib.sha256(raw).hexdigest()!=ARCHIVE_SHA256:raise SystemExit('Anwendungspaket beschädigt.')
        return raw
    if '--self-check' in sys.argv:
        with zipfile.ZipFile(io.BytesIO(archive_bytes())) as archive:
            assert archive.testzip() is None
            assert not any(name.endswith('profil-zuordnung.json') or '/state/' in name or '/install-data/' in name for name in archive.namelist())
            assert {item.filename:hashlib.sha256(archive.read(item)).hexdigest() for item in archive.infolist()}==dict(FILES)
            print(json.dumps({'app_version': VERSION, 'embedded_files':len(archive.namelist()), 'private_settings_included':False}))
        return
    if os.environ.get('CFS_APP_HOME'):
        home = Path(os.environ['CFS_APP_HOME']).expanduser()
    elif sys.platform == 'win32':
        home = Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))/'CFS-Tagwriter'
    elif sys.platform == 'darwin':
        home = Path.home()/'Library/Application Support/CFS-Tagwriter'
    else:
        home = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'cfs-tagwriter'
    data, application, libraries = home/'data', home/'app'/VERSION, home/'python-libs'
    data.mkdir(parents=True, exist_ok=True)
    libraries.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(libraries))
    needed = [name for name in ('serial','cryptography','paramiko','keyring','PIL') if importlib.util.find_spec(name) is None]
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        raise SystemExit('Tkinter fehlt. Unter Mint: sudo apt install python3-tk python3-pip\nUnter Windows/macOS Python mit Tkinter von python.org installieren.')
    if needed:
        root = tk.Tk(); root.title('CFS Tagwriter '+VERSION+' – erste Einrichtung')
        root.geometry('640x360')
        frame = ttk.Frame(root, padding=20); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Benötigte Python-Pakete einrichten', font=('TkDefaultFont',14,'bold')).pack(anchor='w')
        ttk.Label(frame, text='Einmaliger Download von Paramiko, pyserial, cryptography, keyring und Pillow.\nDie Pakete werden nur im eigenen Anwendungsordner abgelegt.').pack(anchor='w', pady=14)
        status = tk.StringVar(value='Danach öffnet sich die Anwendung automatisch.')
        ttk.Label(frame, textvariable=status, wraplength=590).pack(anchor='w', pady=10)
        messages = queue.Queue(); ready = [False]
        def install():
            button.configure(state='disabled'); status.set('Python-Pakete werden heruntergeladen und eingerichtet…')
            def work():
                try:
                    result = subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--target',str(libraries),
                        'paramiko==4.0.0','pyserial==3.5','cryptography==47.0.0','keyring==25.7.0','Pillow==12.3.0'], capture_output=True, timeout=300)
                    messages.put((result.returncode==0, (result.stdout+result.stderr).decode(errors='replace')[-1800:]))
                except Exception as error: messages.put((False,str(error)))
            threading.Thread(target=work,daemon=True).start()
        def poll():
            try:
                success, detail = messages.get_nowait()
                if success: ready[0]=True; root.destroy(); return
                status.set('Einrichtung fehlgeschlagen: '+detail+'\nUnter Mint gegebenenfalls python3-pip installieren.'); button.configure(state='normal')
            except queue.Empty: pass
            root.after(100,poll)
        button = ttk.Button(frame,text='Python-Pakete einrichten und starten',command=install); button.pack(anchor='w',pady=12)
        root.after(100,poll); root.mainloop()
        if not ready[0]: return
        importlib.invalidate_caches()
    application.mkdir(parents=True,exist_ok=True)
    base=application.resolve()
    def destination_for(name):
        destination=(application/name).resolve()
        if not destination.is_relative_to(base):raise SystemExit('Ungültiger Paketpfad')
        return destination
    # Verify every installed byte, but avoid decoding and decompressing the
    # bundled archive on each warm start. Changed/missing files are repaired.
    complete=True
    for name,expected in FILES:
        destination=destination_for(name)
        try:correct=hashlib.sha256(destination.read_bytes()).hexdigest()==expected
        except OSError:correct=False
        if not correct:complete=False;break
    if not complete:
        with zipfile.ZipFile(io.BytesIO(archive_bytes())) as archive:
            for entry in archive.infolist():
                destination=destination_for(entry.filename)
                destination.parent.mkdir(parents=True,exist_ok=True)
                contents=archive.read(entry)
                if not destination.exists() or destination.read_bytes()!=contents:
                    destination.write_bytes(contents)
    registry = data/'profil-zuordnung.json'
    if not registry.exists():
        registry.write_text(json.dumps({'schema_version':1,'sync_source':'printer_cloud',
            'profiles':[],'printer':{'ip':'','name':'Mein Drucker'},'cloud_materials_url':''},indent=2)+'\n')
    os.environ['CFS_PROFILE_REGISTRY']=str(registry)
    os.environ['CFS_APP_DATA']=str(data)
    sys.path.insert(0,str(application/'creality-cfs-writer'))
    sys.argv=[str(application/'creality-cfs-writer/cfs_writer.py')]+[arg for arg in sys.argv[1:] if arg!='--self-check']
    runpy.run_path(sys.argv[0],run_name='__main__')

if __name__=='__main__': main()
'''
encoded=base64.b85encode(raw).decode()
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    files=[(entry.filename,hashlib.sha256(archive.read(entry)).hexdigest()) for entry in archive.infolist()]
source = template.replace('__APP_VERSION__', app_version).replace('__HASH__', hashlib.sha256(raw).hexdigest()).replace('__ENCODED_HASH__',hashlib.sha256(encoded.encode('ascii')).hexdigest()).replace('__FILES__',repr(files)).replace('__PAYLOAD__',encoded)
target = OUT/('CFS_Tagwriter_'+app_version+'.py')
if target.exists():raise SystemExit('Portable Zieldatei existiert bereits; Versionen werden nicht überschrieben.')
target.write_text(source,encoding="utf-8")
target.chmod(0o755)
print(str(target), target.stat().st_size, 'bytes; keine privaten Einstellungen enthalten')

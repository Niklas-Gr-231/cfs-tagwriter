# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Versioned Mega2560 uploader; tool downloads have pinned upstream hashes."""
import hashlib
import io
import os
import signal
import json
from pathlib import Path
import platform
import queue
import threading
import time
import re
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

from cfs_versions import BRIDGE_VERSION
from cfs_progress import report,cli_progress

CLI_VERSION = '1.5.1'
BOARDS = {
    'mega2560': {'name': 'Mega2560 R3', 'family': 'mega2560', 'sketch': 'CFS_Mega_Bridge', 'fqbn': 'arduino:avr:mega:cpu=atmega2560'},
    'nano328p': {'name': 'Nano Classic ATmega328P', 'family': 'nano328p', 'sketch': 'CFS_Nano_Bridge', 'fqbn': 'arduino:avr:nano:cpu=atmega328'},
    'nano328p_old': {'name': 'Nano Classic ATmega328P – alter Bootloader', 'family': 'nano328p', 'sketch': 'CFS_Nano_Bridge', 'fqbn': 'arduino:avr:nano:cpu=atmega328old'},
}
ASSETS = {
    ('Linux', 'x86_64'): ('Linux_64bit.tar.gz', '28a8e119c498a25607821c36cb2dc49e8463941b261a0d99091baa7bc692dd2b'),
    ('Linux', 'aarch64'): ('Linux_ARM64.tar.gz', '1e69e077479f300614d4551334e0a33f08ee40b04315d83b8e7e0e94f0d0ee62'),
    ('Darwin', 'x86_64'): ('macOS_64bit.tar.gz', 'c982e940027996bea9901050e95fae99c59c1dcfee54beedecaf28141e7bf2e7'),
    ('Darwin', 'arm64'): ('macOS_ARM64.tar.gz', 'cb952e8c1621c95ef5f1d17831c945e3d0ec5973f89c557a7ec8feb9c4f7d4c9'),
    ('Windows', 'AMD64'): ('Windows_64bit.zip', 'fabe42e0eb04d00e776a66178299ff95a46c623dbc260f997e58fd514853dd40'),
}


def prepare_tools(data_root, notify=lambda message: None, *, progress=None):
    folder = Path(data_root).expanduser().resolve()/'arduino-tools'
    folder.mkdir(parents=True, exist_ok=True)
    binary_name = 'arduino-cli.exe' if platform.system() == 'Windows' else 'arduino-cli'
    binary = folder/binary_name
    if not binary.exists():
        suffix, expected = ASSETS.get((platform.system(), platform.machine()), (None, None))
        if suffix is None:
            raise ValueError('Für diese Plattform ist kein geprüfter Arduino-CLI-Download hinterlegt')
        notify('Arduino CLI '+CLI_VERSION+' wird heruntergeladen…')
        url = 'https://downloads.arduino.cc/arduino-cli/arduino-cli_'+CLI_VERSION+'_'+suffix
        report(progress,'Arduino CLI herunterladen',0,None,'bytes')
        with urllib.request.urlopen(url, timeout=30) as response:
            header=response.headers.get('Content-Length','')
            total=int(header) if header.isdigit() else None
            chunks=[];received=0;last=0
            while True:
                chunk=response.read(65536)
                if not chunk:break
                chunks.append(chunk);received+=len(chunk)
                if received>40_000_000:raise ValueError('Arduino-CLI-Download ist unerwartet groß')
                now=time.monotonic()
                if now-last>=.08 or received==total:
                    report(progress,'Arduino CLI herunterladen',received,total,'bytes');last=now
            raw=b''.join(chunks)
        report(progress,'Arduino CLI: Prüfsumme kontrollieren')
        if len(raw) > 40_000_000 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Arduino-CLI-Prüfsumme stimmt nicht; Download wird nicht ausgeführt')
        report(progress,'Arduino CLI entpacken')
        if suffix.endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = [name for name in archive.namelist() if Path(name).name == binary_name]
                if len(entries) != 1: raise ValueError('Kein eindeutiges CLI-Programm im Archiv')
                content = archive.read(entries[0])
        else:
            with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
                entries = [item for item in archive.getmembers() if item.isfile() and Path(item.name).name == binary_name]
                if len(entries) != 1: raise ValueError('Kein eindeutiges CLI-Programm im Archiv')
                content = archive.extractfile(entries[0]).read()
        binary.write_bytes(content)
        binary.chmod(0o755)
    config = folder/'arduino-cli.json'
    config.write_text(json.dumps({'directories': {'data': str(folder/'data'),
        'downloads': str(folder/'downloads'), 'user': str(folder/'user')}}))
    command = [str(binary), '--config-file', str(config)]
    marker = folder/'avr-1.8.8.ready'
    if not marker.exists():
        for parts in (['core', 'update-index'], ['core', 'install', 'arduino:avr@1.8.8']):
            notify('Arduino-Werkzeuge einrichten: '+' '.join(parts))
            report(progress,'Paketindex aktualisieren' if parts[1]=='update-index' else 'Arduino AVR-Werkzeuge installieren')
            run(command+parts,notify,progress=progress)
        marker.write_text('1.8.8\n')
    report(progress,'Arduino-Werkzeuge bereit')
    return command


def run(command,notify=lambda message:None,*,progress=None,timeout=300):
    # A reader thread prevents a silent subprocess from freezing timeout checks.
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,bufsize=0,start_new_session=os.name=='posix')
    def stop():
        try:
            if os.name=='posix':os.killpg(process.pid,signal.SIGKILL)
            elif os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=5)
            else:process.kill()
        except (ProcessLookupError,OSError,subprocess.SubprocessError):pass
        if process.poll() is None:process.kill()
        process.wait(timeout=5)
    chunks=queue.Queue()
    def read():
        try:
            while True:
                chunk=process.stdout.read(4096)
                if not chunk:break
                chunks.put(chunk)
        finally:chunks.put(None)
    reader=threading.Thread(target=read,daemon=True,name='cfs-arduino-output');reader.start()
    import codecs
    decoder=codecs.getincrementaldecoder('utf-8')(errors='replace')
    deadline=time.monotonic()+timeout;tail='';pending='';eof=False
    def line(value):
        value=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',value).strip()
        if value and not cli_progress(value,progress):notify(value[-800:])
    try:
        while not eof:
            if time.monotonic()>deadline:
                stop()
                hint='USB-Verbindung und Bootloader-Auswahl prüfen.' if 'upload' in command else 'Internetverbindung prüfen und die Werkzeug-Einrichtung erneut versuchen.'
                raise ValueError('Zeitüberschreitung beim Arduino-Werkzeug. '+hint)
            try:chunk=chunks.get(timeout=.05)
            except queue.Empty:continue
            if chunk is None:eof=True;continue
            text=decoder.decode(chunk);tail=(tail+text)[-64000:];pending+=text
            pieces=re.split(r'[\r\n]',pending);pending=pieces.pop()
            for value in pieces:line(value)
        pending+=decoder.decode(b'',final=True)
        if pending:line(pending)
        result=process.wait(timeout=max(.1,deadline-time.monotonic()))
    finally:
        if process.poll() is None:stop()
        reader.join(timeout=.5);process.stdout.close()
    if result:raise ValueError('Arduino-Werkzeug fehlgeschlagen: '+tail[-3000:])
    return tail


def upload_bridge(port,data_root,notify=lambda message:None,*,board='mega2560',progress=None):
    if board not in BOARDS:
        raise ValueError('Bitte Mega2560 oder Nano Classic ATmega328P auswählen')
    report(progress,'USB-Port und Bridge-Prüfsumme prüfen')
    target = BOARDS[board]
    from serial.tools.list_ports import comports
    if port not in {item.device for item in comports()}:
        raise ValueError('Der ausgewählte USB-Port ist nicht mehr vorhanden')
    sketch = Path(__file__).resolve().parent/target['sketch']
    manifest = sketch/'precompiled/manifest.json'
    image = sketch/('precompiled/'+target['sketch']+'.ino.hex')
    if manifest.exists():
        metadata = json.loads(manifest.read_text())
        if metadata.get('version') != BRIDGE_VERSION or metadata.get('board_family') != target['family'] or metadata.get('sha256') != hashlib.sha256(image.read_bytes()).hexdigest():
            raise ValueError('Arduino-Firmwareversion oder Prüfsumme passt nicht zum Paket')
    command=prepare_tools(data_root,notify,progress=progress)
    notify(target['name']+' wird mit Bridge '+BRIDGE_VERSION+' programmiert. USB-Verbindung nicht trennen.')
    with tempfile.TemporaryDirectory(prefix='bridge-',dir=Path(data_root)/'arduino-tools') as temporary:
        image_directory = image.parent
        if not manifest.exists():
            report(progress,'MFRC522-Bibliothek einrichten')
            run(command+['lib','install','MFRC522@1.4.12'],notify,progress=progress)
            report(progress,'Arduino-Bridge aus Quellcode kompilieren')
            run(command+['compile','--fqbn',target['fqbn'],'--output-dir',temporary,str(sketch)],notify,progress=progress)
            image_directory = Path(temporary)
        if port not in {item.device for item in comports()}:
            raise ValueError('USB-Port nach der Vorbereitung nicht mehr vorhanden. Arduino erneut verbinden.')
        report(progress,'Arduino verbinden und Bootloader starten')
        run(command+['upload','--verbose','--verify','--port',port,'--fqbn',target['fqbn'],
            '--input-dir',str(image_directory),str(sketch)],notify,progress=progress)
    report(progress,'Arduino-Upload abgeschlossen')
    return {'version': BRIDGE_VERSION, 'port': port, 'board': board}


def export_ide_sketch(destination, board='mega2560'):
    if board not in BOARDS:
        raise ValueError('Nicht unterstütztes Arduino-Board')
    target = BOARDS[board]
    name = target['sketch']
    folder = Path(destination)/name
    source = Path(__file__).resolve().parent/name/(name+'.ino')
    contents = source.read_text(encoding='utf-8')
    folder.mkdir(parents=True, exist_ok=True)
    sketch = folder/(name+'.ino')
    sketch.write_text(contents, encoding='utf-8')
    (folder/'LIES-MICH.txt').write_text(
        'CFS Arduino-Bridge '+BRIDGE_VERSION+' – Arduino-IDE-Backup\n\n'
        'Board: '+target['name']+'\n'
        'Boardkennung: '+target['fqbn']+'\n\n'
        '1. '+name+'.ino in der Arduino IDE öffnen.\n'
        '2. Arduino AVR Boards installieren; passendes Mega2560- oder Nano-Board wählen.\n'
        '3. Beim Nano ATmega328P oder ATmega328P (Old Bootloader) passend auswählen.\n'
        '4. Bibliothek MFRC522 von GithubCommunity installieren (getestet: 1.4.12).\n'
        '5. USB-Port wählen; Tagwriter-Verbindung/seriellen Monitor vorher schließen.\n'
        '6. Hochladen. Danach seriellen Monitor schließen und im Tagwriter verbinden.\n\n'
        'Der Export selbst flasht kein Gerät und benötigt keinen Druckerzugriff.\n', encoding='utf-8')
    return {'path':str(sketch), 'board':board, 'version':BRIDGE_VERSION}

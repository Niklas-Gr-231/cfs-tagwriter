# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit release updates. Standard library only; no printer or profile writes."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4
import zipfile

REPOSITORY = 'Niklas-Gr-231/cfs-tagwriter'
API = 'https://api.github.com/repos/'+REPOSITORY+'/releases/latest'
MAX_PACKAGE = 800 * 1024 * 1024


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('Ungültige stabile App-Version.')
    return tuple(map(int, value.split('.')))


def platform_key(system=None, machine=None):
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    arch = {'amd64':'x86_64', 'x86_64':'x86_64', 'arm64':'arm64', 'aarch64':'arm64'}.get(machine)
    result = {'win32':'windows', 'darwin':'macos', 'linux':'linux'}.get(system)
    key = str(result)+'-'+str(arch)
    if key not in ('windows-x86_64', 'macos-x86_64', 'macos-arm64', 'linux-x86_64'):
        raise ValueError('Für dieses Betriebssystem bzw. diese Architektur gibt es noch kein geprüftes Installationspaket.')
    return key


def asset_name(version, key):
    version_tuple(version)
    suffix = {'windows-x86_64':'.exe', 'macos-x86_64':'.zip', 'macos-arm64':'.zip', 'linux-x86_64':'.AppImage'}[key]
    return 'CFS_Tagwriter_'+version+'_'+key+suffix


def _safe_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.hostname not in (
            'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
        raise ValueError('Update-Adresse gehört nicht zum freigegebenen GitHub-Download.')
    return url


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        _safe_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def _open(url):
    request = Request(_safe_url(url), headers={'User-Agent':'CFS-Tagwriter-Updater', 'Accept':'application/vnd.github+json' if url == API else 'application/octet-stream'})
    try:
        return build_opener(_Redirects()).open(request, timeout=30)
    except HTTPError as error:
        if error.code == 404:raise ValueError('Es ist noch keine veröffentlichte Update-Version verfügbar.') from None
        if error.code in (403, 429):raise ValueError('GitHub begrenzt die Abfragen gerade. Bitte später erneut versuchen.') from None
        raise ValueError('GitHub konnte die Update-Anfrage nicht beantworten (HTTP '+str(error.code)+').') from None
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError('Update-Server nicht erreichbar. Internetverbindung prüfen: '+str(error)) from None


def check_release(current, key=None):
    key = key or platform_key()
    with _open(API) as response:
        raw = response.read(2*1024*1024+1)
    if len(raw) > 2*1024*1024:raise ValueError('Update-Antwort ist zu groß.')
    try:release = json.loads(raw)
    except (ValueError, UnicodeError):raise ValueError('Update-Antwort ist beschädigt.') from None
    if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
        raise ValueError('Die angebotene Version ist keine freigegebene stabile Version.')
    tag = release.get('tag_name', '')
    version = tag[1:] if isinstance(tag, str) and tag.startswith('v') else ''
    if version_tuple(version) <= version_tuple(current):
        return {'available':False, 'version':version}
    name = asset_name(version, key)
    assets = [item for item in release.get('assets', []) if isinstance(item,dict) and item.get('name') == name]
    if len(assets) != 1:raise ValueError('Für Version '+version+' ist das passende Installationspaket noch nicht verfügbar. Bitte später erneut prüfen.')
    asset = assets[0]
    expected_url = 'https://github.com/'+REPOSITORY+'/releases/download/v'+version+'/'+name
    if asset.get('browser_download_url') != expected_url:raise ValueError('Die Download-Adresse passt nicht zum Release.')
    digest = asset.get('digest', '')
    size = asset.get('size')
    if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('GitHub stellt keine gültige SHA-256-Prüfsumme für dieses Paket bereit.')
    if type(size) is not int or not 0 < size <= MAX_PACKAGE:raise ValueError('Unzulässige Paketgröße.')
    notes = release.get('body') or 'Für diese Version wurden keine Änderungen beschrieben.'
    if not isinstance(notes,str):raise ValueError('Ungültige Änderungsbeschreibung.')
    return {'available':True, 'version':version, 'key':key, 'name':name, 'url':expected_url,
            'sha256':digest[7:], 'size':size, 'notes':notes[:100000]}


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):digest.update(chunk)
    return digest.hexdigest()


def _extract_mac(package, destination):
    """Preserve macOS bundle links, verifying every resolved path stays in the app."""
    total = 0
    with zipfile.ZipFile(package) as archive:
        entries = archive.infolist()
        if len(entries) > 25000:raise ValueError('Zu viele Dateien im Update.')
        names = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            total += entry.file_size
            if (not path.parts or path.parts[0] != 'CFS Tagwriter.app' or path.is_absolute()
                    or '..' in path.parts or '\\' in entry.filename or ':' in entry.filename
                    or entry.filename in names
                    or stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR,stat.S_IFLNK)
                    or total > MAX_PACKAGE*3):
                raise ValueError('Unsicherer oder zu großer Inhalt im Mac-Update.')
            names.add(entry.filename)
        links=[]
        for entry in entries:
            target = destination.joinpath(*PurePosixPath(entry.filename).parts)
            if stat.S_ISLNK(entry.external_attr >> 16):
                link=archive.read(entry).decode('utf-8')
                normalized=PurePosixPath(posixpath.normpath(str(PurePosixPath(entry.filename).parent/link)))
                if not link or link.startswith('/') or '\\' in link or ':' in link or normalized.parts[0]!='CFS Tagwriter.app':
                    raise ValueError('Unsicheres Verknüpfungsziel im Mac-Update.')
                links.append((target,link));continue
            if entry.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(entry) as source, target.open('xb') as out:shutil.copyfileobj(source,out)
            target.chmod(0o755 if (entry.external_attr >> 16)&0o111 else 0o644)
        for target,link in links:
            target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(link)
        app=(destination/'CFS Tagwriter.app').resolve()
        for entry in entries:
            if not destination.joinpath(*PurePosixPath(entry.filename).parts).resolve().is_relative_to(app):
                raise ValueError('Mac-Verknüpfung verlässt das App-Paket.')
    return destination/'CFS Tagwriter.app/Contents/MacOS/CFS Tagwriter'


def launch_environment(data):
    env = os.environ.copy()
    for name in ('APPIMAGE','APPDIR','OWD','ARGV0','LD_LIBRARY_PATH','LD_LIBRARY_PATH_ORIG','DYLD_LIBRARY_PATH','PYTHONHOME','PYTHONPATH'):
        env.pop(name,None)
    # Bundled libraries live in a temporary directory that disappears when the
    # old app closes. An explicit library outside the bundle remains supported.
    bundle=getattr(sys,'_MEIPASS',None)
    configured=env.get('CFS_LIBLZMA')
    if bundle and configured and Path(configured).resolve().is_relative_to(Path(bundle).resolve()):
        env.pop('CFS_LIBLZMA',None)
    # Tell the PyInstaller bootloader this is a fresh independent process.
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    env['APPIMAGE_EXTRACT_AND_RUN'] = '1'
    env['CFS_APP_DATA'] = str(Path(data).resolve())
    env['CFS_PROFILE_REGISTRY'] = str(Path(data).resolve()/'profil-zuordnung.json')
    return env


def stage_release(release, data, progress=None):
    """Download, verify, and probe in isolation. Never activate on partial failure."""
    version = release['version'];version_tuple(version)
    if release['key'] != platform_key() or release['name'] != asset_name(version,release['key']):
        raise ValueError('Das Paket passt nicht zu diesem Rechner.')
    expected = 'https://github.com/'+REPOSITORY+'/releases/download/v'+version+'/'+release['name']
    if release['url'] != expected or not re.fullmatch('[0-9a-f]{64}',release['sha256']):raise ValueError('Ungültiger Update-Auftrag.')
    size = release['size']
    if type(size) is not int or not 0 < size <= MAX_PACKAGE:raise ValueError('Unzulässige Paketgröße.')
    base = Path(data).resolve()/'updates'
    base.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(base).free < size*4+50*1024*1024:raise ValueError('Für Download und Installation ist nicht genug freier Speicher vorhanden.')
    temporary = Path(tempfile.mkdtemp(prefix='download-',dir=base))
    final = base/(version+'-'+uuid4().hex)
    try:
        package = temporary/release['name']
        received = 0;digest = hashlib.sha256()
        with _open(release['url']) as response, package.open('xb') as stream:
            while True:
                chunk = response.read(256*1024)
                if not chunk:break
                received += len(chunk)
                if received > size:raise ValueError('Download ist größer als angekündigt.')
                stream.write(chunk);digest.update(chunk)
                if progress:progress({'phase':'App-Update herunterladen', 'current':received,'total':size,'detail':str(received//1048576)+' / '+str((size+1048575)//1048576)+' MB'})
        if received != size or digest.hexdigest() != release['sha256']:
            raise ValueError('Download unvollständig oder Prüfsumme falsch. Die bisherige App bleibt erhalten.')
        if progress:progress({'phase':'Update prüfen und vorbereiten','detail':'Die aktuelle Installation bleibt erhalten.'})
        if release['key'].startswith('macos-'):
            executable = _extract_mac(package,temporary)
            package.unlink()
        else:
            executable = temporary/('CFS Tagwriter.exe' if release['key'].startswith('windows-') else 'CFS_Tagwriter.AppImage')
            package.rename(executable);executable.chmod(0o755)
        relative = executable.relative_to(temporary)
        probe_data = temporary/'probe-data'
        report_file=probe_data/'check.json'
        result = subprocess.run([str(executable),'--check','--report-file',str(report_file)],env=launch_environment(probe_data),
                                capture_output=True,text=True,timeout=90, **({'creationflags':0x08000000} if os.name=='nt' else {}))
        try:report=json.loads(report_file.read_text(encoding='utf-8') if report_file.is_file() else result.stdout.strip())
        except ValueError:raise ValueError('Die neue App konnte ihren Starttest nicht abschließen. Die bisherige App bleibt erhalten.') from None
        if result.returncode or report.get('app') != version or report.get('dependencies') != 'ready':
            raise ValueError('Der Starttest der neuen App ist fehlgeschlagen. Die bisherige App bleibt erhalten.')
        shutil.rmtree(probe_data,ignore_errors=True)
        receipt = {'version':version,'executable':str(final/relative),'sha256':_hash(executable),'notes':release['notes']}
        _atomic_json(temporary/'receipt.json',receipt)
        temporary.rename(final)
        return receipt
    except BaseException:
        shutil.rmtree(temporary,ignore_errors=True)
        raise


def _checked_receipt(receipt, data):
    if not isinstance(receipt,dict):raise ValueError('Update-Vermerk ist beschädigt.')
    version_tuple(receipt.get('version'))
    path = Path(receipt.get('executable','')).resolve()
    base = (Path(data).resolve()/'updates').resolve()
    if not path.is_relative_to(base) or not path.is_file() or _hash(path) != receipt.get('sha256'):
        raise ValueError('Die vorbereitete App fehlt oder wurde verändert. Bitte das Update erneut herunterladen.')
    return path


def launch_updated(receipt, data, demo=False):
    executable = _checked_receipt(receipt,data)
    path = Path(data)/'app-update.json'
    previous = path.read_bytes() if path.exists() else None
    _atomic_json(path,receipt)
    try:
        return subprocess.Popen([str(executable)]+(['--demo'] if demo else []),env=launch_environment(data),
                                cwd=str(executable.parent),start_new_session=os.name=='posix')
    except OSError:
        if previous is None:path.unlink(missing_ok=True)
        else:
            temporary = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
            temporary.write_bytes(previous);os.replace(temporary,path)
        raise


def redirect_to_update(current, data, demo=False):
    path = Path(data)/'app-update.json'
    if not path.exists():return False
    try:
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if version_tuple(receipt.get('version')) <= version_tuple(current):return False
        launch_updated(receipt,data,demo)
        return True
    except (OSError,ValueError,TypeError):
        # A damaged update must not prevent the original app from opening.
        return False

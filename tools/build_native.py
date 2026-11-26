#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Build on the target OS. No credentials or user runtime files are collected."""
import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import runpy
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from check_publication import ROOT,check

XZ_VERSION='5.8.4'
XZ_HASH='0014c7886930454fe8bd4228665b51af55eeae560ea135c9c4cd33f55b2591d9'
RUNTIME_COMMIT='caf24f9f712084686bfc24a70b75e50df0aefb9c'
RUNTIME_SOURCE_HASH='944e9bb5c587818c54fec3231067ec03d67b8062c68278f4ca99d504216117be'
APPIMAGETOOL_HASH='ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0'


def download(url,path,digest):
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest:return
    with urllib.request.urlopen(url,timeout=60) as response,path.open('wb') as stream:shutil.copyfileobj(response,stream)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Bauwerkzeug hat eine falsche Prüfsumme: '+path.name)


def build_lzma(work):
    source=work/('xz-'+XZ_VERSION)
    package=work/('xz-'+XZ_VERSION+'.tar.gz')
    download('https://github.com/tukaani-project/xz/releases/download/v'+XZ_VERSION+'/'+package.name,package,XZ_HASH)
    if not source.exists():
        with tarfile.open(package) as archive:archive.extractall(work,filter='data')
    cmake=shutil.which('cmake') or str(Path(sys.executable).with_name('cmake'))
    build=work/'xz-build';prefix=work/'xz-install'
    subprocess.run([cmake,'-S',str(source),'-B',str(build),'-DBUILD_SHARED_LIBS=ON','-DBUILD_TESTING=OFF','-DXZ_TOOL_XZ=OFF','-DXZ_TOOL_XZDEC=OFF','-DXZ_TOOL_LZMADEC=OFF','-DXZ_TOOL_LZMAINFO=OFF','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_INSTALL_PREFIX='+str(prefix)],check=True)
    subprocess.run([cmake,'--build',str(build),'--config','Release','--parallel','2'],check=True)
    subprocess.run([cmake,'--install',str(build),'--config','Release'],check=True)
    libraries=[p for p in prefix.rglob('*') if p.is_file() and not p.is_symlink() and (p.suffix in ('.dll','.dylib') or '.so.' in p.name)]
    if len(libraries)!=1:raise ValueError('Die gebaute liblzma-Bibliothek fehlt oder ist nicht eindeutig: '+str(libraries))
    return source,libraries[0]


def runtime_notices(destination,xz_source):
    destination.mkdir(parents=True,exist_ok=True)
    versions={}
    for distribution in importlib.metadata.distributions():
        name=distribution.metadata.get('Name','unknown');versions[name]=distribution.version
        for relative in distribution.files or []:
            if 'license' in relative.name.lower() or relative.name.lower() in ('copying','notice','authors'):
                source=Path(distribution.locate_file(relative))
                if source.is_file():
                    target=destination/name/relative.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    import sysconfig
    for source in (Path(sysconfig.get_path('stdlib'))/'LICENSE.txt', Path(sys.base_prefix)/'LICENSE.txt', Path(sys.base_prefix)/'LICENSE'):
        if source.is_file():shutil.copy2(source,destination/'Python-LICENSE.txt');break
    else:
        # Debian's Python installation stores the complete copyright/license here.
        source=Path('/usr/share/doc/python'+str(sys.version_info.major)+'.'+str(sys.version_info.minor)+'/copyright')
        if not source.is_file():raise ValueError('Python-Lizenztext für das native Paket fehlt.')
        shutil.copy2(source,destination/'Python-LICENSE.txt')
    shutil.copytree(xz_source/'COPYING',destination/'XZ',dirs_exist_ok=True) if (xz_source/'COPYING').is_dir() else shutil.copy2(xz_source/'COPYING',destination/'XZ-COPYING.txt')
    if (xz_source/'COPYING.0BSD').is_file():shutil.copy2(xz_source/'COPYING.0BSD',destination/'XZ-0BSD.txt')
    (destination/'versions.json').write_text(json.dumps(versions,indent=2)+'\n',encoding='utf-8')


def zip_app(app,output):
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(app.rglob('*')):
            name=str(Path(app.name)/path.relative_to(app)).replace('\\','/')
            if path.is_symlink():
                entry=zipfile.ZipInfo(name);entry.create_system=3;entry.external_attr=(stat.S_IFLNK|0o777)<<16
                archive.writestr(entry,os.readlink(path))
            elif path.is_file():archive.write(path,name)


def build(work,output):
    files=check()
    version=runpy.run_path(str(ROOT/'app/creality-cfs-writer/cfs_versions.py'))['APP_VERSION']
    sys.path.insert(0,str(ROOT/'app/creality-cfs-writer'))
    from cfs_updates import platform_key,asset_name
    key=platform_key()
    for directory in (work,output):
        directory.mkdir(parents=True,exist_ok=True)
        if ROOT==directory or ROOT in directory.parents:raise ValueError('Bauordner und Pakete außerhalb des Repositorys wählen.')
    target=output/asset_name(version,key)
    if target.exists():raise ValueError('Vorhandenes Paket wird nicht überschrieben.')
    xz_source,lib=build_lzma(work)
    notices=work/'runtime-licenses';runtime_notices(notices,xz_source)
    datas=[(str(ROOT/p),str(p.parent)) for p in files if p.parts[0]=='app']
    datas += [(str(ROOT/'start.py'),'.'),(str(notices),'runtime-licenses'),(str(ROOT/'LICENSES'),'LICENSES')]
    datas += [(str(ROOT/name),'.') for name in ('LICENSE','NOTICE','THIRD_PARTY_NOTICES.md')]
    # Mac bundle symlinks, frameworks and code signatures are preserved in zip_app.
    spec=work/'native.spec'
    hidden=set()
    own={p.stem for folder in ('creality-cfs-writer','creality-cfs-cloud') for p in (ROOT/'app'/folder).glob('*.py')}
    for file in files:
        if file.parts[0]=='app' and file.suffix=='.py':
            for node in ast.walk(ast.parse((ROOT/file).read_text(encoding='utf-8'))):
                if isinstance(node,ast.Import):hidden.update(item.name for item in node.names)
                elif isinstance(node,ast.ImportFrom) and node.module and not node.level:hidden.add(node.module)
    hidden=sorted(name for name in hidden if name.split('.')[0] not in own and name.split('.')[0] not in ('pytest','unittest','pip','setuptools','test','tests'))
    common=f"a=Analysis([{str(ROOT/'packaging/native_entry.py')!r}],pathex=[],binaries=[({str(lib)!r},'native-libs')],datas={datas!r},hiddenimports={hidden!r}+collect_submodules('keyring.backends')+collect_submodules('bleak.backends')+collect_submodules('PIL')+collect_submodules('serial.tools')+collect_submodules('tkinter')+['xml.etree.ElementTree','concurrent.futures.thread'],hookspath=[],runtime_hooks=[],excludes=['pytest','unittest','pip','setuptools','wheel','cmake'],noarchive=False)\npyz=PYZ(a.pure)\n"
    if sys.platform=='win32':
        end=f"exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='CFS Tagwriter',console=False,icon={str(ROOT/'app/creality-cfs-writer/cfs-tagwriter.ico')!r})\n"
    else:
        end="exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='CFS Tagwriter',console=False)\ncoll=COLLECT(exe,a.binaries,a.datas,name='CFS Tagwriter')\n"
        if sys.platform=='darwin':
            from PIL import Image
            icon=work/'cfs.icns';Image.open(ROOT/'app/creality-cfs-writer/cfs-tagwriter.png').save(icon)
            info={'CFBundleShortVersionString':version,'CFBundleVersion':version,'NSBluetoothAlwaysUsageDescription':'CFS Tagwriter verbindet deinen Etikettendrucker für den gewünschten Direktdruck.','NSBluetoothPeripheralUsageDescription':'Bluetooth-Verbindung zum Etikettendrucker.','NSHighResolutionCapable':True}
            end+=f"app=BUNDLE(coll,name='CFS Tagwriter.app',icon={str(icon)!r},bundle_identifier='io.github.cfs-tagwriter',info_plist={info!r})\n"
    spec.write_text('from PyInstaller.utils.hooks import collect_submodules\n'+common+end,encoding='utf-8')
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(work/'dist'),'--workpath',str(work/'pyinstaller'),str(spec)],check=True)
    if sys.platform=='win32':shutil.copy2(work/'dist/CFS Tagwriter.exe',target)
    elif sys.platform=='darwin':
        app=work/'dist/CFS Tagwriter.app'
        subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
        zip_app(app,target)
        stage=work/'dmg'
        if stage.exists():shutil.rmtree(stage)
        stage.mkdir();shutil.copytree(app,stage/app.name,symlinks=True)
        (stage/'Applications').symlink_to('/Applications')
        subprocess.run(['hdiutil','create','-volname','CFS Tagwriter '+version,'-srcfolder',str(stage),'-ov','-format','UDZO',str(target.with_suffix('.dmg'))],check=True)
    else:
        appdir=work/'CFS_Tagwriter.AppDir'
        if appdir.exists():shutil.rmtree(appdir)
        appdir.mkdir()
        shutil.copytree(work/'dist/CFS Tagwriter',appdir/'usr',dirs_exist_ok=True,symlinks=True)
        (appdir/'AppRun').write_text('#!/bin/sh\nTASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$TASK_DIR/usr/CFS Tagwriter" "$@"\n')
        (appdir/'AppRun').chmod(0o755)
        (appdir/'cfs-tagwriter.desktop').write_text('[Desktop Entry]\nType=Application\nName=CFS Tagwriter\nExec=AppRun\nIcon=cfs-tagwriter\nCategories=Utility;\n')
        shutil.copy2(ROOT/'app/creality-cfs-writer/cfs-tagwriter.png',appdir/'cfs-tagwriter.png')
        tool=work/'appimagetool.AppImage'
        download('https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage',tool,APPIMAGETOOL_HASH)
        tool.chmod(0o755)
        offset=int(subprocess.check_output([str(tool),'--appimage-offset'],text=True).strip())
        runtime=work/'appimage-runtime';runtime.write_bytes(tool.read_bytes()[:offset])
        # Keep the exact runtime source, LGPL libfuse source, patches/build recipes
        # and replacement instructions alongside the distributed runtime.
        runtime_source=work/'AppImage-runtime-source.tar.gz'
        download('https://codeload.github.com/AppImage/type2-runtime/tar.gz/'+RUNTIME_COMMIT,runtime_source,RUNTIME_SOURCE_HASH)
        fuse=work/'fuse-3.15.0.tar.xz'
        download('https://github.com/libfuse/libfuse/releases/download/fuse-3.15.0/'+fuse.name,fuse,'70589cfd5e1cff7ccd6ac91c86c01be340b227285c5e200baa284e401eea2ca0')
        source_bundle=output/('CFS_Tagwriter_'+version+'_AppImage_Runtime_Quellen.zip')
        with zipfile.ZipFile(source_bundle,'x',zipfile.ZIP_DEFLATED) as archive:
            archive.write(runtime_source,runtime_source.name);archive.write(fuse,fuse.name)
            archive.writestr('RUNTIME-AUSTAUSCH.txt','Unveränderter AppImage-Runtime-Stand '+RUNTIME_COMMIT+' (MIT), mit libfuse 3.15.0 (LGPL).\nPatches und Bauanweisungen im Runtime-Quellarchiv.\nEine eigene Runtime lässt sich ohne Änderung des App-Codes verwenden: vorhandenes AppImage --appimage-extract; anschließend mit appimagetool --runtime-file <eigene-runtime> squashfs-root <neues.AppImage> neu packen.\nDie App-Sektion bleibt unabhängig und unverändert.\n')
        source_bundle.with_name(source_bundle.name+'.sha256').write_text(hashlib.sha256(source_bundle.read_bytes()).hexdigest()+'  '+source_bundle.name+'\n',encoding='utf-8')
        with tarfile.open(fuse) as archive:
            for member in archive.getmembers():
                if member.isfile() and member.name.endswith(('LGPL2.txt','GPL2.txt','LICENSE')):
                    content=archive.extractfile(member).read()
                    (appdir/('libfuse-'+Path(member.name).name)).write_bytes(content)
        env=dict(os.environ,APPIMAGE_EXTRACT_AND_RUN='1',ARCH='x86_64',VERSION=version)
        subprocess.run([str(tool),'--runtime-file',str(runtime),'--mksquashfs-opt','-processors','--mksquashfs-opt','2',str(appdir),str(target)],check=True,env=env)
        target.chmod(0o755)
    (target.with_name(target.name+'.sha256')).write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name+'\n',encoding='utf-8')
    if sys.platform=='darwin':
        dmg=target.with_suffix('.dmg');dmg.with_name(dmg.name+'.sha256').write_text(hashlib.sha256(dmg.read_bytes()).hexdigest()+'  '+dmg.name+'\n',encoding='utf-8')
    print('Natives Paket:',target)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.work.resolve(),args.output.resolve())

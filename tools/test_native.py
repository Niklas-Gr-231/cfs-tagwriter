#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Probe actual packaged dependencies, offline exports, and the real demo window."""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app/creality-cfs-writer'))
from cfs_updates import _extract_mac,launch_environment


def check(package,gui=True):
    version=runpy.run_path(str(ROOT/'app/creality-cfs-writer/cfs_versions.py'))['APP_VERSION']
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);data=root/'data'
        executable=_extract_mac(package,root) if package.suffix=='.zip' else package
        report=root/'report.json';env=launch_environment(data)
        subprocess.run([str(executable),'--check','--report-file',str(report)],check=True,timeout=90,env=env)
        result=json.loads(report.read_text(encoding='utf-8'))
        assert result['app']==version and result['dependencies']=='ready',result
        assert result['optional_direct_print_compression']=='bereit',result
        if gui:subprocess.run([str(executable),'--smoke-test'],check=True,timeout=45,env=env)
        print('Natives Paket erfolgreich geprüft:',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('package',type=Path);parser.add_argument('--no-gui',action='store_true')
    args=parser.parse_args();check(args.package.resolve(),not args.no_gui)

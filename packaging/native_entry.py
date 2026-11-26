# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Native bootloader; app sources/resources retain their original directory layout."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile

# Static imports let PyInstaller collect the external runtime, including hooks.
import tkinter
import tkinter.ttk
import tkinter.colorchooser
import tkinter.filedialog
import tkinter.messagebox
import serial.tools.list_ports
import cryptography
import paramiko
import keyring
import PIL.Image
import PIL.ImageFont
import PIL.ImageTk
import bleak
import lzma
import certifi


def main():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    os.environ.setdefault('SSL_CERT_FILE',certifi.where())
    for path in sorted((root/'native-libs').glob('*lzma*')):
        os.environ.setdefault('CFS_LIBLZMA',str(path));break
    source=runpy.run_path(str(root/'start.py'))
    arguments=sys.argv[1:]
    if '--check' in arguments:
        buffer=io.StringIO()
        with contextlib.redirect_stdout(buffer):result=source['main'](['--check'])
        if '--report-file' in arguments:
            path=Path(arguments[arguments.index('--report-file')+1]);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(buffer.getvalue(),encoding='utf-8')
        elif sys.stdout is not None:sys.stdout.write(buffer.getvalue())
        return result
    if '--smoke-test' in arguments:
        with tempfile.TemporaryDirectory() as directory:
            os.environ['CFS_APP_DATA']=directory
            (Path(directory)/'ui-settings.json').write_text(json.dumps({'first_start_notice_acknowledged':True}))
            original=tkinter.Tk
            class ClosingWindow(original):
                def __init__(self,*args,**kwargs):
                    super().__init__(*args,**kwargs);self.after(2500,self.destroy)
            tkinter.Tk=ClosingWindow
            return source['main'](['--demo'])
    return source['main'](arguments)


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        if sys.stderr is not None:raise
        tkinter.messagebox.showerror('CFS Tagwriter konnte nicht starten',str(error))
        raise SystemExit(1)

#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Open the real demo UI with temporary settings, then close automatically."""
import json
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import start


class ClosingWindow(tk.Tk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.after(1500, self.destroy)


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        os.environ['CFS_APP_DATA'] = directory
        (Path(directory)/'ui-settings.json').write_text(json.dumps({'first_start_notice_acknowledged': True}))
        tk.Tk = ClosingWindow
        raise SystemExit(start.main(['--demo']))

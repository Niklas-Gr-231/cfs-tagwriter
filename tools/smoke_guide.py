#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Exercise wiring sheets without Pillow's separately packaged ImageTk."""
import builtins
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/creality-cfs-writer'))
from cfs_hardware_guide import show_guide
from cfs_theme import apply
original_import=builtins.__import__
def without_imagetk(name, globals=None, locals=None, fromlist=(), level=0):
    if name=='PIL.ImageTk' or name=='PIL' and 'ImageTk' in (fromlist or ()):
        raise ImportError('ImageTk deliberately unavailable in this check')
    return original_import(name,globals,locals,fromlist,level)
root=tk.Tk();root.geometry('1000x700');errors=[]
root.report_callback_exception=lambda *args:errors.append(args)
def settle():
    deadline=time.monotonic()+.25
    while time.monotonic()<deadline:root.update();time.sleep(.005)
with patch('builtins.__import__',side_effect=without_imagetk):
    for dark in (False,True):
        for board in ('mega2560','nano328p'):
            guide=show_guide(root,tk,ttk,board=board,dark=dark)
            apply(root,tk,ttk,dark);settle()
            main=guide['viewers'][0]
            assert main['state']['photo'].width()>400
            main['zoom'](1.25);settle()
            main['zoom']();settle()
            guide['notebook'].select(2);settle()
            assert guide['viewers'][1]['state']['photo'].width()>400
            guide['window'].destroy();settle()
root.destroy()
assert not errors,errors
print('Wiring guide passed for Mega/Nano and both themes without ImageTk.')

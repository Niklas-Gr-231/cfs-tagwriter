# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Phase-based progress: measured counts when available, otherwise activity."""
import re


def report(callback,phase,current=None,total=None,unit='',detail=''):
    if callback is None:return
    callback({'phase':str(phase),'current':current,'total':total,'unit':unit,'detail':str(detail)})


def describe(update):
    phase=update.get('phase','Bitte warten…');current=update.get('current');total=update.get('total');unit=update.get('unit','')
    if isinstance(current,(int,float)) and isinstance(total,(int,float)) and total>0:
        current=max(0,min(current,total))
        if unit=='bytes':return f'{phase} · {current/1048576:.1f} / {total/1048576:.1f} MB'
        if unit=='%':return f'{phase} · {current/total*100:.0f} %'
        return f'{phase} · {int(current)}/{int(total)} {unit}'.strip()
    if isinstance(current,(int,float)) and unit=='bytes':return f'{phase} · {current/1048576:.1f} MB'
    return phase


def cli_progress(line,callback):
    # AVRDUDE reports its write and readback progress on carriage-return lines.
    match=re.search(r'\b(Writing|Reading)\s*\|.*?\|\s*(\d{1,3})%',line,re.I)
    if match:
        report(callback,'Flash schreiben' if match[1].lower()=='writing' else 'Flash zurücklesen und prüfen',min(int(match[2]),100),100,'%')
        return True
    match=re.search(r'(?<!\d)(\d{1,3})(?:\.\d+)?%',line)
    if match and int(match[1])<=100:
        report(callback,'Arduino-Werkzeuge herunterladen',int(match[1]),100,'%',line[:180])
        return True
    return False

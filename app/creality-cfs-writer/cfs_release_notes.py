# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Offline patch history and a small, dependency-free release notes renderer."""
from functools import lru_cache
from pathlib import Path
import re
from cfs_versions import APP_VERSION
from cfs_updates import version_tuple


def release_notes():
    try:return Path(__file__).with_name('app-release-notes.md').read_text(encoding='utf-8')
    except OSError:return 'CFS Tagwriter '+APP_VERSION+'\nFür diese Version ist keine Änderungsbeschreibung enthalten.'


def parse_history(value):
    headings=list(re.finditer(r'^\*\*(\d+\.\d+\.\d+)\s*·[^\n]*\*\*\s*$',value,re.MULTILINE))
    entries={}
    for index,heading in enumerate(headings):
        version=heading.group(1)
        end=headings[index+1].start() if index+1<len(headings) else len(value)
        entries.setdefault(version,{'version':version,'notes':value[heading.start():end].strip()})
    return sorted(entries.values(),key=lambda item:version_tuple(item['version']),reverse=True)


@lru_cache(maxsize=1)
def release_history():
    try:value=Path(__file__).with_name('app-release-history.md').read_text(encoding='utf-8')
    except OSError:value=''
    entries={item['version']:item for item in parse_history(value)}
    entries[APP_VERSION]={'version':APP_VERSION,'notes':release_notes()}
    return sorted(entries.values(),key=lambda item:version_tuple(item['version']),reverse=True)


def _plain(value):
    # Preserve labels and destinations without exposing Markdown punctuation.
    value=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',lambda match:match[1]+' ('+match[2]+')',value)
    return value.replace('**','').replace('`','')


def note_blocks(value):
    """Join source-wrapped lines into paragraphs; preserve headings and bullets."""
    result=[];pending=[];kind='body'
    def flush():
        if pending:result.append((kind,_plain(' '.join(pending))));pending.clear()
    for line in value.splitlines():
        stripped=line.strip()
        if not stripped:flush();kind='body';continue
        heading=re.match(r'^#{1,6}\s+(.+)$',stripped)
        bold_heading=stripped.startswith('**') and stripped.endswith('**')
        bullet=re.match(r'^(?:[-*]|\d+[.)])\s+(.+)$',stripped)
        if heading or bold_heading:
            flush();result.append(('heading',_plain(heading[1] if heading else stripped)));kind='body'
        elif bullet:
            flush();kind='bullet';pending.append(bullet[1])
        else:pending.append(stripped)
    flush()
    return result


def render_notes(widget,value):
    from tkinter import font as tkfont
    if not hasattr(widget,'_cfs_notes_fonts'):
        base=tkfont.nametofont('TkDefaultFont',root=widget).copy()
        heading=base.copy();heading.configure(weight='bold',size=int(base.cget('size'))+2)
        widget._cfs_notes_fonts=(base,heading)
        widget.configure(font=base,spacing1=3,spacing3=7)
        widget.tag_configure('notes_heading',font=heading,spacing1=8,spacing3=12)
        widget.tag_configure('notes_bullet',lmargin1=0,lmargin2=20,spacing3=9)
    widget.configure(state='normal');widget.delete('1.0','end')
    for kind,text in note_blocks(value):
        widget.insert('end',('•  ' if kind=='bullet' else '')+text+'\n',('notes_'+kind,))
    widget.configure(state='disabled');widget.yview_moveto(0)


def notes_panel(parent,tk,ttk,*,history=True):
    """A reusable view; selection never changes the downloadable update."""
    panel=ttk.Frame(parent);panel.columnconfigure(0,weight=1);panel.rowconfigure(1,weight=1)
    selected=tk.StringVar();records={}
    selector=None
    if history:
        row=ttk.Frame(panel);row.grid(row=0,column=0,sticky='ew',pady=(0,12));row.columnconfigure(1,weight=1)
        ttk.Label(row,text='Patch-Historie').grid(row=0,column=0,sticky='w',padx=(0,12))
        selector=ttk.Combobox(row,textvariable=selected,state='readonly',width=35)
        selector.grid(row=0,column=1,sticky='ew')
    frame=ttk.Frame(panel);frame.grid(row=1,column=0,sticky='nsew')
    text=tk.Text(frame,height=12,width=1,wrap='word',padx=16,pady=12,relief='flat',borderwidth=0)
    scrollbar=ttk.Scrollbar(frame,orient='vertical',command=text.yview)
    text.configure(yscrollcommand=scrollbar.set);scrollbar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
    def show(_event=None):
        if selected.get() in records:render_notes(text,records[selected.get()]['notes'])
    def set_offer(release=None):
        previous=selected.get();records.clear()
        if release:records[release['version']+' · Update verfügbar']=release
        for entry in release_history():
            records[entry['version']+(' · Installiert' if entry['version']==APP_VERSION else '')]=entry
        if selector:selector.configure(values=list(records))
        selected.set(next(iter(records)) if release or previous not in records else previous);show()
    if selector:selector.bind('<<ComboboxSelected>>',show)
    set_offer()
    return {'panel':panel,'text':text,'selector':selector,'selection':selected,'set_offer':set_offer}

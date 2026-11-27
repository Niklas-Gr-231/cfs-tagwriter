# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Update and release notes pages, using the existing themed controls."""
import json
from pathlib import Path
from cfs_versions import APP_VERSION
from cfs_updates import check_release, stage_release, _atomic_json


def release_notes():
    path=Path(__file__).with_name('app-release-notes.md')
    try:return path.read_text(encoding='utf-8')
    except OSError:return 'CFS Tagwriter '+APP_VERSION+'\nFür diesen Entwicklungsstand ist noch keine Änderungsbeschreibung eingebaut.'


def show_notes(app,tk,ttk,*,automatic=False):
    window=tk.Toplevel(app.root);window.title('Was ist neu? · CFS Tagwriter '+APP_VERSION)
    window.geometry('800x570');window.minsize(560,350)
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='CFS Tagwriter '+APP_VERSION,font=('TkDefaultFont',17,'bold')).pack(anchor='w',pady=(0,14))
    text_frame=ttk.Frame(frame);text_frame.pack(fill='both',expand=True)
    text=tk.Text(text_frame,wrap='word',padx=12,pady=12,relief='flat',borderwidth=0)
    scrollbar=ttk.Scrollbar(text_frame,orient='vertical',command=text.yview)
    text.configure(yscrollcommand=scrollbar.set);scrollbar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
    text.insert('1.0',release_notes());text.configure(state='disabled')
    def close():
        if automatic:_atomic_json(app.data_dir/'app-update-seen.json',{'version':APP_VERSION})
        window.destroy()
    ttk.Button(frame,text='Verstanden' if automatic else 'Schließen',command=close,style='Primary.TButton').pack(anchor='e',pady=(15,0))
    window.protocol('WM_DELETE_WINDOW',close)
    app.apply_theme(persist=False)
    if automatic:window.transient(app.root);window.lift()
    return window


def notify_after_update(app,tk,ttk):
    """Show once after a changed installation, and again until acknowledged."""
    def read(name):
        try:return json.loads((app.data_dir/name).read_text(encoding='utf-8'))
        except (OSError,ValueError):return {}
    seen=read('app-update-seen.json').get('version')
    updated=read('app-update.json').get('version')==APP_VERSION
    if seen==APP_VERSION:return
    if not seen and not updated:
        _atomic_json(app.data_dir/'app-update-seen.json',{'version':APP_VERSION});return
    def ready():
        if app.close_pending:return
        if app.busy or app.root.grab_current():app.root.after(700,ready);return
        show_notes(app,tk,ttk,automatic=True)
    app.root.after(900,ready)


def show_updates(app,tk,ttk,dialogs):
    if app.busy or app.close_pending:return
    from cfs_pages import open_page
    body,_=open_page(app,tk,ttk,'App aktualisieren')
    card=ttk.Frame(body,padding=24);card.pack(fill='both',expand=True)
    ttk.Label(card,text='Installiert: CFS Tagwriter '+APP_VERSION,font=('TkDefaultFont',18,'bold')).pack(anchor='w')
    ttk.Label(card,text='Freigegebene GitHub-Versionen · Einstellungen und Profile bleiben erhalten.\nDruckerdienst und Arduino werden separat und nur auf deinen Wunsch aktualisiert.',wraplength=850).pack(anchor='w',pady=(10,20))
    status=tk.StringVar(value='Zum Prüfen auf „Nach Updates suchen“ klicken.')
    ttk.Label(card,textvariable=status,wraplength=850).pack(anchor='w',pady=10)
    progress_text=tk.StringVar(value='')
    ttk.Label(card,textvariable=progress_text,wraplength=850).pack(anchor='w')
    progress=ttk.Progressbar(card,mode='determinate');progress.pack(fill='x',pady=(6,10))
    controls=ttk.Frame(card);controls.pack(fill='x',pady=10)
    state={'release':None,'receipt':None}
    note_frame=ttk.Frame(card);note_frame.pack(fill='both',expand=True,pady=12)
    notes=tk.Text(note_frame,height=14,wrap='word',relief='flat',borderwidth=0,padx=12,pady=12)
    scroll=ttk.Scrollbar(note_frame,orient='vertical',command=notes.yview);scroll.pack(side='right',fill='y')
    notes.configure(yscrollcommand=scroll.set)
    notes.pack(fill='both',expand=True);notes.insert('1.0',release_notes());notes.configure(state='disabled')
    def set_notes(value):
        notes.configure(state='normal');notes.delete('1.0','end');notes.insert('1.0',value);notes.configure(state='disabled');app.apply_theme(persist=False)
    def ready(receipt):
        state['receipt']=receipt
        status.set('Version '+receipt['version']+' ist geprüft und bereit. Zum Anwenden die App neu starten.')
        install.configure(text='Update anwenden und neu starten',state='normal')
        search.configure(state='normal')
    def download():
        if app.busy:return
        if state['receipt']:
            if dialogs['messagebox'].askyesno('Update anwenden','Die App wird geschlossen und mit der geprüften neuen Version neu gestartet. Jetzt fortfahren?',parent=app.root):
                app.pending_app_update=state['receipt'];app.on_close()
            return
        release=state['release']
        if not release:return
        search.configure(state='disabled');install.configure(state='disabled')
        status.set('Update wird im Hintergrund heruntergeladen und geprüft…')
        def work():
            try:return {'receipt':stage_release(release,app.data_dir,app.report_progress)}
            except Exception as error:return {'error':str(error)}
        def done(result):
            if not card.winfo_exists():return
            search.configure(state='normal')
            if 'error' in result:
                status.set('Update fehlgeschlagen: '+result['error']);install.configure(text='Download erneut versuchen',state='normal')
                app.log('App-Update fehlgeschlagen: '+result['error'])
            else:ready(result['receipt'])
        app.run_operation('App-Update herunterladen und prüfen…',work,done)
    def search_updates():
        if app.busy:return
        state.update(release=None,receipt=None);install.configure(text='Update herunterladen',state='disabled');search.configure(state='disabled')
        status.set('GitHub wird nach einer freigegebenen Version gefragt…')
        def work():
            try:return check_release(APP_VERSION)
            except Exception as error:return {'error':str(error)}
        def done(result):
            if not card.winfo_exists():return
            search.configure(state='normal')
            if 'error' in result:status.set('Suche fehlgeschlagen: '+result['error']);return
            if not result['available']:status.set('Die App ist aktuell. Neueste freigegebene Version: '+result['version']);return
            state['release']=result;status.set('Version '+result['version']+' verfügbar · '+str(round(result['size']/1048576,1))+' MB')
            set_notes(result['notes']);install.configure(state='normal')
        app.run_operation('Nach App-Updates suchen…',work,done)
    search=ttk.Button(controls,text='Nach Updates suchen',command=search_updates,style='Primary.TButton');search.pack(side='left')
    install=ttk.Button(controls,text='Update herunterladen',command=download,state='disabled');install.pack(side='left',padx=12)
    ttk.Button(controls,text='Was ist neu?',command=lambda:show_notes(app,tk,ttk)).pack(side='left')
    app.update_page_fields={'search':search,'install':install,'status':status,'state':state,'notes':notes,'window':card,'progress':progress,'progress_text':progress_text}
    app.apply_theme(persist=False)

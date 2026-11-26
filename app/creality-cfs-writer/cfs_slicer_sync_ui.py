# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Automatic main-window Slicer comparison; printer writes remain explicit."""
import json
from pathlib import Path


GROUPS=('new','updated','unchanged')
ACTION_LABELS={'slicer_cloud_updated':'Vorrang aktualisieren','slicer_cloud_unchanged':'Unverändert',
    'copy_created':'Neu anlegen','copy_updated':'Slicerstand aktualisieren','copy_unchanged':'Unverändert',
    'copy_restored':'Wiederherstellen'}


def group_rows(plan):
    """Classify the authoritative transfer plan, including metadata-only changes."""
    grouped={key:[] for key in GROUPS}
    for row in plan:
        action=row['action']
        group='unchanged' if action in ('slicer_cloud_unchanged','copy_unchanged') else 'new' if action in ('copy_created','copy_restored') else 'updated'
        grouped[group].append(row)
    for rows in grouped.values():rows.sort(key=lambda row:(row['name'].casefold(),row['material_id'],row['identity']))
    return grouped


def show(app,tk,ttk,dialogs,codec):
    if app.busy or app.registry is None:return
    from cfs_pages import open_page
    from cfs_profile_sync import write_json
    body,page_close=open_page(app,tk,ttk,'Slicerprofile synchronisieren')
    outer=ttk.Frame(body,padding=18);outer.pack(fill='both',expand=True)
    outer.columnconfigure(1,weight=1);outer.rowconfigure(4,weight=1)
    ttk.Label(outer,text='Slicer → Drucker · gespeicherte Slicerwerte haben Vorrang',font=('TkDefaultFont',14,'bold')).grid(row=0,column=0,columnspan=2,sticky='w')
    intro=ttk.Label(outer,text='Ziel ist ausschließlich der ausgewählte Drucker, kein Cloud-Upload. Der Abgleich startet beim Öffnen automatisch. Neue Profile stehen oben, Änderungen in der Mitte, unveränderte unten. Erst „Slicer → Drucker übernehmen“ schreibt zum Drucker; Slicerdateien und Cloudprofile bleiben erhalten.',style='Hint.TLabel',wraplength=940)
    intro.grid(row=1,column=0,columnspan=3,sticky='w',pady=(7,10))
    settings=app.data_dir/'slicer-sync-settings.json'
    try:saved=json.loads(settings.read_text()) if settings.exists() else {}
    except (ValueError,OSError):saved={}
    if not isinstance(saved,dict):saved={}
    folder=tk.StringVar(value=str(saved.get('folder',app.import_directory)))
    folder_label=ttk.Label(outer,text='Profilordner');folder_label.grid(row=2,column=0,sticky='w',padx=(0,10))
    entry=ttk.Entry(outer,textvariable=folder);entry.grid(row=2,column=1,sticky='ew')
    state={'prepared':None,'paths':saved.get('files') if isinstance(saved.get('files'),list) and all(isinstance(p,str) for p in saved['files']) else None,
        'dependencies':saved.get('dependencies') if isinstance(saved.get('dependencies'),str) else None,
        'running':False,'pending':0,'generation':0,'auto_after':None,'closed':False,'counts':dict.fromkeys(GROUPS,0)}
    result=tk.StringVar(value='Gespeicherte Quelle wird abgeglichen… Dienst 2.1.0 und SSH erforderlich. Neue Profile und Änderungen werden vor der Übernahme angezeigt.')
    source_hint=tk.StringVar();controls=[];tables={};headings={}
    def source_text():
        source_hint.set('Quelle: '+(str(len(state['paths']))+' ausdrücklich ausgewählte JSON-Dateien' if state['paths'] else 'alle JSON-Filamentprofile im Ordner')+'. Änderungen zuerst im Slicer speichern.')
    def clear_preview(*args):
        state['generation']+=1;state['prepared']=None;state['pending']=0;state['counts']=dict.fromkeys(GROUPS,0)
        apply_button.configure(state='disabled',text='Slicer → Drucker übernehmen')
        for key,table in tables.items():
            children=table.get_children()
            if children:table.delete(*children)
            headings[key].set(titles[key]+' · noch nicht geprüft')
        details.configure(state='normal');details.delete('1.0','end');details.configure(state='disabled')
        source_text()
    def choose_folder():
        path=dialogs['filedialog'].askdirectory(parent=app.root,title='Ordner mit gespeicherten Slicer-Filamentprofilen wählen',initialdir=folder.get())
        if path:folder.set(path);state['paths']=None;state['dependencies']=None;clear_preview();check()
    choose=ttk.Button(outer,text='Ordner wählen…',command=choose_folder);choose.grid(row=2,column=2,padx=(10,0));controls.extend((entry,choose))
    access=ttk.Frame(outer);access.grid(row=3,column=0,columnspan=3,sticky='ew',pady=(7,9));access.columnconfigure(1,weight=1)
    password=tk.StringVar(value=app.remembered_ssh_password())
    ttk.Label(access,text='SSH-Passwort').grid(row=0,column=0,sticky='w',padx=(0,10))
    pw=ttk.Entry(access,textvariable=password,show='•',width=22);pw.grid(row=0,column=1,sticky='w');controls.append(pw)
    def files():
        chosen=dialogs['filedialog'].askopenfilenames(parent=app.root,title='Slicer-JSON-Filamentprofile wählen',initialdir=folder.get(),filetypes=[('Filamentprofile','*.json')])
        if chosen:folder.set(str(Path(chosen[0]).parent));state['paths']=list(chosen);clear_preview();check()
    pick=ttk.Button(access,text='Dateien auswählen…',command=files);pick.grid(row=0,column=2,padx=(8,8));controls.append(pick)
    setup=ttk.Button(access,text='Druckerdienst…',command=app.show_setup);setup.grid(row=0,column=3,sticky='e');controls.append(setup)
    ttk.Label(access,textvariable=source_hint,style='Hint.TLabel',wraplength=940).grid(row=1,column=0,columnspan=4,sticky='w',pady=(5,0))
    # Three distinct result areas stay visible; details occupy their own column.
    config_visible=[False]
    def configure_source(visible):
        config_visible[0]=visible
        for widget in (folder_label,entry,choose,access):
            if visible:widget.grid()
            else:widget.grid_remove()
        config_toggle.configure(text='Quelle / SSH ausblenden' if visible else 'Quelle / SSH anzeigen')
    config_toggle=ttk.Button(outer,text='Quelle / SSH anzeigen',command=lambda:configure_source(not config_visible[0]));config_toggle.grid(row=0,column=2,sticky='e',padx=(10,0));controls.append(config_toggle)
    configure_source(False)
    panes=ttk.Panedwindow(outer,orient='horizontal');panes.grid(row=4,column=0,columnspan=3,sticky='nsew')
    lists=ttk.Panedwindow(panes,orient='vertical');panes.add(lists,weight=3)
    titles={'new':'Neu anzulegen','updated':'Zu aktualisieren','unchanged':'Unverändert'}
    for key in GROUPS:
        frame=ttk.Frame(lists);frame.columnconfigure(0,weight=1);frame.rowconfigure(1,weight=1);lists.add(frame,weight=1)
        headings[key]=tk.StringVar(value=titles[key]+' · noch nicht geprüft')
        ttk.Label(frame,textvariable=headings[key],font=('TkDefaultFont',10,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(3,3))
        table=ttk.Treeview(frame,columns=('name','code','action'),show='headings',selectmode='browse',height=2)
        for column,title,width,minimum in (('name','Slicerprofil',285,160),('code','Code',75,65),('action','Status',190,105)):
            table.heading(column,text=title);table.column(column,width=width,minwidth=minimum,stretch=column=='name')
        table.grid(row=1,column=0,sticky='nsew');scroll=ttk.Scrollbar(frame,orient='vertical',command=table.yview);scroll.grid(row=1,column=1,sticky='ns');table.configure(yscrollcommand=scroll.set)
        horizontal=ttk.Scrollbar(frame,orient='horizontal',command=table.xview)
        def horizontal_view(first,last,bar=horizontal):
            bar.set(first,last)
            if float(first)<=0 and float(last)>=1:bar.grid_remove()
            else:bar.grid(row=2,column=0,sticky='ew')
        table.configure(xscrollcommand=horizontal_view)
        tables[key]=table
    right=ttk.Frame(panes,padding=(10,0,0,0));right.columnconfigure(0,weight=1);right.rowconfigure(1,weight=1);panes.add(right,weight=2)
    ttk.Label(right,text='Änderungsdetails',font=('TkDefaultFont',10,'bold')).grid(row=0,column=0,sticky='w',pady=(3,3))
    details=tk.Text(right,wrap='word',width=30,height=7,state='disabled',relief='flat',padx=8,pady=8);details.grid(row=1,column=0,sticky='nsew')
    ds=ttk.Scrollbar(right,command=details.yview);ds.grid(row=1,column=1,sticky='ns');details.configure(yscrollcommand=ds.set)
    summary=ttk.Label(outer,textvariable=result,style='Hint.TLabel',wraplength=940);summary.grid(row=5,column=0,columnspan=3,sticky='w',pady=(8,8))
    buttons=ttk.Frame(outer);buttons.grid(row=6,column=0,columnspan=3,sticky='e')
    def running(value):
        state['running']=value
        for widget in controls+[check_button,back]:widget.configure(state='disabled' if value else 'normal')
        app.main_page_fields['back'].configure(state='disabled' if value else 'normal')
        apply_button.configure(state='normal' if not value and state['prepared'] and state['pending'] else 'disabled')
    def selected(key):
        table=tables[key];rows=table.selection()
        if not rows or not state['prepared']:return
        for other in tables.values():
            if other is not table and other.selection():other.selection_remove(*other.selection())
        identity=rows[0];info=state['prepared']['details'][identity]
        text='Datei: '+info['filename']+'\nQuelle: gespeicherter Slicerstand (Vorrang)\n'
        text+=json.dumps(info['changes'],ensure_ascii=False,indent=2) if info['changes'] else ('Profil und Slicer-Zuordnung sind bereits aktuell.' if key=='unchanged' else 'Keine geänderten Druckwerte. Slicer-Vorrang bzw. Zuordnung wird eingerichtet oder aktualisiert.')
        details.configure(state='normal');details.delete('1.0','end');details.insert('1.0',text);details.configure(state='disabled')
    for key,table in tables.items():table.bind('<<TreeviewSelect>>',lambda event,key=key:selected(key))
    def check(completed=''):
        if state['running'] or state['closed'] or app.busy:return
        clear_preview();generation=state['generation'];source_folder=folder.get();source_files=list(state['paths']) if state['paths'] else None
        from cfs_slicer_sync import prepare
        secret=password.get();dependencies=state['dependencies']
        running(True);result.set((completed+'\n' if completed else '')+'Gespeicherte Quelldateien und Drucker abgleichen…')
        def work():
            try:
                paths=source_files or sorted(Path(source_folder).expanduser().glob('*.json'))
                if not paths:raise ValueError('Keine JSON-Filamentprofile im gewählten Ordner. Bitte den Profilordner wählen.')
                return {'prepared':prepare(app.registry,paths,secret,dependencies)}
            except Exception as error:return {'error':str(error)}
        def done(reply):
            if state['closed']:return
            running(False)
            if generation!=state['generation']:
                result.set('Quelle wurde während des Abgleichs geändert. Bitte erneut synchronisieren.');return
            if 'error' in reply:
                configure_source(True)
                result.set((completed+'\nFolgeprüfung: ' if completed else '')+reply['error'])
                if 'Abhängigkeit' in reply['error']:
                    dep=dialogs['filedialog'].askdirectory(parent=app.root,title='Ordner mit fehlenden System-/Elternprofilen wählen')
                    if dep:state['dependencies']=dep;check(completed)
                return
            state['prepared']=reply['prepared'];grouped=group_rows(state['prepared']['preview']['plan'])
            for key,rows in grouped.items():
                state['counts'][key]=len(rows);headings[key].set(titles[key]+' · '+str(len(rows)))
                for row in rows:tables[key].insert('', 'end',iid=row['identity'],values=(row['name'],row['material_id'],ACTION_LABELS.get(row['action'],row['action'])))
            state['pending']=state['counts']['new']+state['counts']['updated'];running(False)
            apply_button.configure(text='Slicer → Drucker übernehmen ('+str(state['pending'])+')' if state['pending'] else 'Alles aktuell')
            for key in ('new','updated','unchanged'):
                children=tables[key].get_children()
                if children:tables[key].selection_set(children[0]);tables[key].focus(children[0]);selected(key);break
            counts=state['counts'];message=f"{counts['new']} neu · {counts['updated']} zu aktualisieren · {counts['unchanged']} unverändert."
            message+=' „Slicer → Drucker übernehmen“ überträgt die geprüften Werte zum Drucker.' if state['pending'] else ' Alle ausgewählten Profile sind aktuell.'
            result.set((completed+'\n' if completed else '')+message)
            try:write_json(settings,{'folder':source_folder,'files':source_files,'dependencies':dependencies})
            except OSError:pass
        app.run_operation('Slicerprofile automatisch abgleichen…',work,done)
    def commit():
        if state['running'] or app.busy or not state['prepared'] or not state['pending']:return
        from cfs_slicer_sync import apply
        prepared=state['prepared'];secret=password.get();running(True);result.set('Slicerstand auf den Drucker übernehmen…')
        def work():
            try:return {'result':apply(app.registry,prepared,secret)}
            except Exception as error:return {'error':str(error)}
        def done(reply):
            state['prepared']=None;state['pending']=0;running(False)
            if 'error' in reply:result.set(reply['error']+' Bitte erneut synchronisieren.');return
            result_data=reply['result'];app.set_materials([*codec.DEFAULT_MATERIALS,*result_data['materials']])
            current=app.material_by_label.get(app.material_var.get())
            if current:app.show_material(current)
            message='Slicerprofile übernommen. Materialcodes bleiben erhalten; neue Profile sind für NFC verfügbar.'
            if result_data.get('source_warning'):message+=' '+result_data['source_warning']
            if result_data.get('backup_warning'):message+=' '+result_data['backup_warning']
            app.status_var.set(message);app.log(message);check(message)
        app.run_operation('Slicerwerte und neue Materialcodes auf dem Drucker speichern…',work,done)
    def close():
        if state['running'] or app.busy:return
        state['closed']=True
        if state['auto_after'] is not None:app.root.after_cancel(state['auto_after']);state['auto_after']=None
        password.set('');page_close()
    check_button=ttk.Button(buttons,text='Erneut synchronisieren',command=check);check_button.pack(side='left',padx=(0,8))
    apply_button=ttk.Button(buttons,text='Slicer → Drucker übernehmen',style='Write.TButton',state='disabled',command=commit);apply_button.pack(side='left',padx=(0,8))
    back=ttk.Button(buttons,text='← Tagwriter',command=close);back.pack(side='left')
    def folder_changed(*args):
        state['paths']=None;state['dependencies']=None;clear_preview();result.set('Quelle geändert. „Erneut synchronisieren“ liest den gewählten Ordner neu ein.')
    folder.trace_add('write',folder_changed)
    def fit(event):
        width=max(400,event.width-36)
        for label in (intro,summary):label.configure(wraplength=width)
    body.bind('<Configure>',fit,add='+')
    app.main_page_fields['back'].configure(command=close);app.close_main_page=close
    app.slicer_sync_fields={'folder':folder,'password':password,'tables':tables,'table':tables['updated'],'check':check_button,'apply':apply_button,
        'result':result,'back':back,'state':state,'details':details,'files':files,'headings':headings,'source':source_hint,'panes':panes,'lists':lists,'configuration':config_toggle}
    source_text();app.apply_theme(persist=False)
    def automatic():
        state['auto_after']=None
        if not state['closed']:check()
    state['auto_after']=app.root.after_idle(automatic)
    return body

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Label selection and preview. Only local label preferences/images are written."""
import base64
from collections import OrderedDict
from copy import deepcopy
import io
import json
from pathlib import Path

from cfs_labels import PLATES,DEFAULT_PLATE,PLATE_PREFERENCE_REVISION,label_values,render_image,render_png,safe_filename,write_png


def show(app,tk,ttk,dialogs,documents,provider=None,embedded=True):
    if not documents:raise ValueError('Keine vollständigen Benutzerprofile für Etiketten verfügbar.')
    previous_grab=app.root.grab_current()
    if embedded:
        if previous_grab is not None:
            previous_grab.grab_release();previous_grab.withdraw()
        from cfs_pages import open_page
        parent,page_close=open_page(app,tk,ttk,'Filament-Etiketten · 40 × 30 mm')
        window=app.root
    else:
        window=tk.Toplevel(app.root);window.title('Filament-Etiketten · 40 × 30 mm');window.transient(app.root)
        window.geometry('1100x760');window.minsize(1000,700);parent=window
    content=ttk.Frame(parent,padding=18);content.pack(fill='both',expand=True)
    content.columnconfigure(0,weight=1);content.columnconfigure(1,weight=1);content.rowconfigure(2,weight=1)
    ttk.Label(content,text='Swatch-Etiketten aus gespeicherten Profilwerten',font=('TkDefaultFont',14,'bold')).grid(row=0,column=0,columnspan=2,sticky='w')
    ttk.Label(content,text='40 × 30 mm · Schwarz auf Weiß · Hi = High Unicorn / Ob = Obsidian. Der Zusatz kommt ausschließlich aus dem Herstellerfeld.',style='Hint.TLabel',wraplength=1020).grid(row=1,column=0,columnspan=2,sticky='w',pady=(6,12))
    left=ttk.Frame(content);left.grid(row=2,column=0,sticky='nsew',padx=(0,18));left.columnconfigure(0,weight=1);left.rowconfigure(1,weight=1)
    from cfs_nozzles import NOZZLES
    nozzle=tk.StringVar(value='Alle');search=tk.StringVar();manufacturer=tk.StringVar(value='Alle');material_type=tk.StringVar(value='Alle')
    def source_kind(doc):
        if doc.get('values_source')=='slicer':return 'Slicer (Vorrang)'
        if doc['update_status']=='export_snapshot':return 'CFS-Export'
        return {'cloud':'Cloud (Druckerstand)','local':'Lokal','slicer':'Slicer-Datei','imported':'Importstand'}.get(doc['origin'],'Importstand')
    sources=sorted({source_kind(d) for d in documents})
    source=tk.StringVar(value='Slicer (Vorrang)' if 'Slicer (Vorrang)' in sources else 'Cloud (Druckerstand)' if 'Cloud (Druckerstand)' in sources else 'Alle')
    filters=ttk.Frame(left);filters.grid(row=0,column=0,sticky='ew',pady=(0,8));filters.columnconfigure(1,weight=1);filters.columnconfigure(3,weight=1)
    ttk.Label(filters,text='Suche').grid(row=0,column=0,sticky='w',padx=(0,7))
    entry=ttk.Entry(filters,textvariable=search);entry.grid(row=0,column=1,columnspan=3,sticky='ew',pady=(0,6))
    printer_brand=tk.StringVar(value='Alle');printer_model=tk.StringVar(value='Alle')
    filter_widgets=[]
    for row,col,label,var,values in ((1,0,'Düse',nozzle,('Alle','Hi','Ob','Nicht erfasst')),
        (1,2,'Hersteller',manufacturer,['Alle']+sorted({d['brand'] for d in documents})),
        (2,0,'Filamentart',material_type,['Alle']+sorted({d['type'] for d in documents})),
        (2,2,'Quelle',source,['Alle']+sources),
        (3,0,'Druckerhersteller',printer_brand,['Alle']+sorted({d.get('printer_manufacturer','Unbekannt') for d in documents})),
        (3,2,'Druckertyp',printer_model,['Alle']+sorted({d.get('printer_model',d['model']) for d in documents}))):
        ttk.Label(filters,text=label).grid(row=row,column=col,sticky='w',padx=(0,7),pady=3)
        combo=ttk.Combobox(filters,textvariable=var,values=values,state='readonly',width=15)
        combo.grid(row=row,column=col+1,sticky='ew',padx=(0,7),pady=3);filter_widgets.append(combo)
    table=ttk.Treeview(left,columns=('name','brand','nozzle','printer'),show='headings',selectmode='extended',height=10)
    for key,title,width in (('name','Profil',265),('brand','Hersteller',90),('nozzle','Düse',55),('printer','Druckertyp',130)):
        table.heading(key,text=title);table.column(key,width=width,minwidth=45,stretch=key=='name')
    table.grid(row=1,column=0,sticky='nsew');scroll=ttk.Scrollbar(left,orient='vertical',command=table.yview);scroll.grid(row=1,column=1,sticky='ns');table.configure(yscrollcommand=scroll.set)
    ttk.Label(left,text='Mehrere mit Strg/Umschalt wählen. Suchfeld durchsucht Profil und Hersteller.',style='Hint.TLabel',wraplength=440).grid(row=2,column=0,sticky='w',pady=8)
    right_panel=ttk.Frame(content);right_panel.grid(row=2,column=1,sticky='nsew')
    right_panel.columnconfigure(0,weight=1);right_panel.rowconfigure(0,weight=1)
    option_canvas=tk.Canvas(right_panel,highlightthickness=0,yscrollincrement=4)
    option_canvas.grid(row=0,column=0,sticky='nsew')
    option_scroll=ttk.Scrollbar(right_panel,orient='vertical',command=option_canvas.yview)
    option_scroll.grid(row=0,column=1,sticky='ns');option_canvas.configure(yscrollcommand=option_scroll.set)
    right=ttk.Frame(option_canvas);right.columnconfigure(1,weight=1)
    option_item=option_canvas.create_window((0,0),window=right,anchor='nw')
    def fit_options(_event=None):
        width=max(1,option_canvas.winfo_width());height=max(option_canvas.winfo_height(),right.winfo_reqheight())
        option_canvas.itemconfigure(option_item,width=width,height=height)
        option_canvas.configure(scrollregion=(0,0,width,height))
        for widget in right.winfo_children():
            if isinstance(widget,ttk.Label) and str(widget.cget('wraplength')) not in ('','0'):
                desired=max(180,width-20)
                if str(widget.cget('wraplength'))!=str(desired):widget.configure(wraplength=desired)
    right.bind('<Configure>',fit_options);option_canvas.bind('<Configure>',fit_options)
    from cfs_scroll import SmoothWheel
    option_wheel=SmoothWheel(window,option_canvas)
    def scroll_options(event):
        widget=event.widget
        if isinstance(widget,(ttk.Combobox,ttk.Scrollbar)):return
        while widget is not None and widget is not right_panel:widget=getattr(widget,'master',None)
        if widget is right_panel:return option_wheel.feed(event)
    wheel_bindings=[(event,window.bind(event,scroll_options,add='+')) for event in ('<MouseWheel>','<Button-4>','<Button-5>')]
    preview=ttk.Label(right);preview.grid(row=0,column=0,columnspan=2,sticky='n')
    details=tk.StringVar();ttk.Label(right,textvariable=details,style='Hint.TLabel',wraplength=460).grid(row=1,column=0,columnspan=2,sticky='w',pady=8)
    preference_path=app.data_dir/'label-preferences.json'
    try:prefs=json.loads(preference_path.read_text()) if preference_path.exists() else {}
    except (ValueError,OSError):prefs={}
    if not isinstance(prefs,dict):prefs={}
    defaults=prefs.get('defaults',{}) if isinstance(prefs.get('defaults'),dict) else {}
    # One-time migration to the user's corrected smooth-PEI source. Later explicit
    # plate selections are preserved after an export or confirmed print.
    selected_plate=defaults.get('plate',DEFAULT_PLATE) if prefs.get('plate_preference_revision')==PLATE_PREFERENCE_REVISION else DEFAULT_PLATE
    title_var=tk.StringVar();plate=tk.StringVar(value=selected_plate if selected_plate in PLATES else DEFAULT_PLATE)
    currency=tk.StringVar(value=defaults.get('currency','€'));dpi=tk.StringVar(value=str(defaults.get('dpi',300)))
    show_pa=tk.BooleanVar(value=defaults.get('show_pa',True));show_price=tk.BooleanVar(value=defaults.get('show_price',True))
    controls=[]
    for row,label,var,values in ((2,'Etikettenname',title_var,None),(3,'Druckplatte',plate,tuple(PLATES)),(4,'Währung für Profilpreis',currency,('€','$','£','CHF','EUR','USD','GBP')),(5,'Auflösung (dpi)',dpi,('203','300','600'))):
        ttk.Label(right,text=label).grid(row=row,column=0,sticky='w',padx=(0,10),pady=5)
        widget=ttk.Entry(right,textvariable=var) if values is None else ttk.Combobox(right,textvariable=var,values=values,state='readonly')
        widget.grid(row=row,column=1,sticky='ew',pady=5);controls.append(widget)
    flags=ttk.Frame(right);flags.grid(row=6,column=0,columnspan=2,sticky='w',pady=7)
    for label,var in (('Pressure Advance',show_pa),('Preis/kg',show_price)):
        checkbox=ttk.Checkbutton(flags,text=label,variable=var);checkbox.pack(side='left',padx=(0,14));controls.append(checkbox)
    ttk.Label(right,text='Temperaturen: 1. Schicht → Folgeschichten, falls verschieden. Fehlende Werte: n. a. Währung separat wählen; sie steht nicht im Profil. Hi/Ob kennzeichnet deine Zuordnung und bestätigt keine automatische Kalibrierung.',style='Hint.TLabel',wraplength=460).grid(row=7,column=0,columnspan=2,sticky='w',pady=7)
    message=tk.StringVar(value='Etikett prüfen. Beim Drucken 40 × 30 mm Papier und 100 % / Originalgröße wählen; nicht an Seite anpassen.')
    ttk.Label(content,textvariable=message,style='Hint.TLabel',wraplength=1020).grid(row=3,column=0,columnspan=2,sticky='w',pady=12)
    actions=ttk.Frame(content);actions.grid(row=4,column=0,columnspan=2,sticky='e')
    state={'docs':{d['key']:d for d in documents},'current':None,'drafts':{},'loading':False,'running':False,'pending':None,'photo':None,'notice':'','preview_key':None,'preview_cache':OrderedDict(),'row_values':{},'index_docs':None,'search_index':[]}
    saved=prefs.get('profiles',{}) if isinstance(prefs.get('profiles'),dict) else {}
    def capture():
        if state['current'] and not state['loading']:state['drafts'][state['current']]=title_var.get()
    def options(doc):
        remembered=saved.get(doc['key'],{})
        default_name=remembered.get('display_name',doc['name']) if remembered.get('fingerprint')==doc['fingerprint'] else doc['name']
        return dict(display_name=state['drafts'].get(doc['key'],default_name),plate=plate.get(),currency=currency.get(),dpi=int(dpi.get()),show_pa=show_pa.get(),show_price=show_price.get())
    def update_preview():
        if state['pending']:
            window.after_cancel(state['pending']);state['pending']=None
        if state['loading'] or state['running']:return
        selected=table.selection()
        if not selected:export_button.configure(state='disabled');return
        key=table.focus() if table.focus() in selected else selected[0]
        if state['current']!=key:
            capture();state['loading']=True;state['current']=key
            doc=state['docs'][key];remembered=saved.get(key,{})
            title_var.set(state['drafts'].get(key,remembered.get('display_name',doc['name']) if remembered.get('fingerprint')==doc['fingerprint'] else doc['name']))
            state['drafts'][key]=title_var.get();state['loading']=False
        doc=state['docs'][key]
        try:
            opts=options(doc);values=label_values(doc,opts)
            cache_key=(json.dumps(values,sort_keys=True,ensure_ascii=False),opts['dpi'])
            if cache_key!=state['preview_key']:
                cache=state['preview_cache'];thumbnail=cache.get(cache_key)
                if thumbnail is None:
                    image,values,_=render_image(doc,opts);image.thumbnail((400,300));stream=io.BytesIO()
                    image.save(stream,format='PNG',compress_level=1);thumbnail=stream.getvalue();cache[cache_key]=thumbnail
                    if len(cache)>8:cache.popitem(last=False)
                cache.move_to_end(cache_key)
                state['photo']=tk.PhotoImage(data=base64.b64encode(thumbnail),format='png');preview.configure(image=state['photo']);state['preview_key']=cache_key
            missing=doc['nozzle_type']=='nicht erfasst'
            details.set(f"Quelle: {source_kind(doc)}\n{doc['model']} · Düse {doc['nozzle_type']} · Code {doc['code']} · {len(selected)} ausgewählt"+
                ('\nHersteller endet nicht auf Hi/Ob; Düsentyp wird nicht aus aktueller Hardware geraten.' if missing else '')+
                ('\nCloudquelle fehlt; letzter bestätigter Druckerstand.' if doc['update_status']=='cached_cloud' else '')+
                '\nBett: '+values['bed_temperature']+' aus '+values['plate']+
                (' · Profilwert 0: Platte nicht unterstützt.' if values['plate_unsupported'] else ''))
            export_button.configure(state='normal');message.set(state['notice'] or 'Vorschau: '+str(len(selected))+' Etikett(en). Kurznamen ändern nur das Etikett, keine Profilwerte. PNG bei 100 % drucken.')
        except (ValueError,ImportError,OSError) as error:message.set(str(error));export_button.configure(state='disabled')
    def schedule(*args):
        if state['loading']:return
        capture();state['notice']=''
        if state['pending']:window.after_cancel(state['pending'])
        state['pending']=window.after(130,update_preview)
    def fill(*args):
        capture();selected=set(table.selection())
        if state['index_docs'] is not state['docs']:
            state['index_docs']=state['docs']
            state['search_index']=[(d,(d['name']+' '+d['brand']+' '+d['nozzle_type']+' '+d['nozzle_code']+' '+d['model']+' '+d.get('printer_manufacturer','')).casefold(),source_kind(d)) for d in state['docs'].values()]
            removed=set(state['row_values'])-state['docs'].keys()
            if removed:
                table.delete(*removed)
                for key in removed:state['row_values'].pop(key,None)
        words=search.get().casefold().split();choice=nozzle.get();brand=manufacturer.get();kind=material_type.get();origin=source.get()
        visible=[]
        for d,text,doc_source in state['search_index']:
            code=d['nozzle_code']
            if choice!='Alle' and code!=('' if choice=='Nicht erfasst' else choice):continue
            if brand!='Alle' and d['brand']!=brand:continue
            if kind!='Alle' and d['type']!=kind:continue
            if origin!='Alle' and doc_source!=origin:continue
            if printer_brand.get()!='Alle' and d.get('printer_manufacturer','Unbekannt')!=printer_brand.get():continue
            if printer_model.get()!='Alle' and d.get('printer_model',d['model'])!=printer_model.get():continue
            if any(part not in text for part in words):continue
            visible.append(d)
        visible.sort(key=lambda d:(d.get('printer_manufacturer','').casefold(),d['model'].casefold(),d['brand'].casefold(),d['name'].casefold()))
        old=table.get_children();keys=tuple(d['key'] for d in visible)
        if old!=keys:
            if old:table.detach(*old)
            for index,d in enumerate(visible):
                key=d['key'];values=(d['name'],d['brand'],d['nozzle_code'] or '—',d['model'])
                if key not in state['row_values']:table.insert('',index,iid=key,values=values)
                else:table.move(key,'',index)
                if state['row_values'].get(key)!=values:table.item(key,values=values)
                state['row_values'][key]=values
        else:
            for d in visible:
                values=(d['name'],d['brand'],d['nozzle_code'] or '—',d['model']);key=d['key']
                if state['row_values'].get(key)!=values:table.item(key,values=values);state['row_values'][key]=values
        keep=[key for key in keys if key in selected]
        wanted=keep or keys[:1]
        if tuple(table.selection())!=tuple(wanted):table.selection_set(wanted)
        if keys:table.focus(wanted[0])
        update_preview()
    def set_running(value):
        state['running']=value
        for widget in controls+[entry,*filter_widgets,all_button,export_button,close_button]:widget.configure(state='disabled' if value else 'normal')
        if not value:
            for widget in controls[1:4]+filter_widgets:widget.configure(state='readonly')
    def save_images():
        if state['running']:return
        capture();keys=list(table.selection())
        if not keys:return
        state['notice']=''
        original={key:deepcopy(state['docs'][key]) for key in keys};set_running(True)
        def fetched(fresh):
            set_running(False);current={d['key']:d for d in fresh}
            if not set(keys).issubset(current):message.set('Profil oder Drucker gewechselt. Etikettenfenster erneut öffnen.');return
            if any(current[key]['fingerprint']!=original[key]['fingerprint'] for key in keys):
                state['docs']=current;state['current']=None
                for key in keys:state['drafts'].pop(key,None)
                state['notice']='Profilwerte wurden geändert. Vorschau ist aktualisiert; bitte prüfen und Export erneut starten.'
                fill();message.set(state['notice']);return
            opts={key:options(current[key]) for key in keys}
            if len(keys)==1:
                destination=dialogs['filedialog'].asksaveasfilename(parent=window,title='40 × 30 mm Etikett speichern',defaultextension='.png',initialfile=safe_filename(current[keys[0]]),filetypes=[('PNG-Bild','*.png')],confirmoverwrite=True)
            else:destination=dialogs['filedialog'].askdirectory(parent=window,title='Ordner für die ausgewählten PNG-Etiketten wählen')
            if not destination:return
            set_running(True)
            def write():
                prepared=[(current[key],render_png(current[key],opts[key])[0]) for key in keys]
                paths=[]
                for doc,raw in prepared:
                    path=Path(destination) if len(keys)==1 else Path(destination)/safe_filename(doc)
                    if len(keys)>1:
                        counter=2;initial=path
                        while path.exists() or path in paths:path=initial.with_name(initial.stem+'-'+str(counter)+'.png');counter+=1
                    write_png(path,raw,overwrite=len(keys)==1);paths.append(path)
                from cfs_profile_sync import write_json
                prefs['plate_preference_revision']=PLATE_PREFERENCE_REVISION
                prefs['defaults']={k:v for k,v in opts[keys[0]].items() if k!='display_name'}
                prefs.setdefault('profiles',{})
                for key in keys:prefs['profiles'][key]={'display_name':opts[key]['display_name'],'fingerprint':current[key]['fingerprint']}
                warning=''
                try:write_json(preference_path,prefs)
                except OSError:warning=' Etiketten gespeichert; lokale Anzeige-Einstellungen konnten nicht gemerkt werden.'
                return paths,warning
            def written(result):
                set_running(False);paths,warning=result
                state['notice']=str(len(paths))+' PNG-Etikett(en) gespeichert: '+str(paths[0].parent)+warning
                message.set(state['notice'])
                app.status_var.set(str(len(paths))+' Etikett(en) exportiert. Keine Drucker- oder Profilwerte geändert.')
            def work():
                try:return {'result':write()}
                except Exception as error:return {'error':str(error)}
            def done(reply):
                if 'error' in reply:set_running(False);message.set(reply['error']);return
                written(reply['result'])
            app.run_operation('Etikettenbilder werden gerendert und gespeichert…',work,done)
        def work():
            try:return {'docs':provider() if provider else list(state['docs'].values())}
            except Exception as error:return {'error':str(error)}
        def done(reply):
            if 'error' in reply:set_running(False);message.set(reply['error']);return
            fetched(reply['docs'])
        app.run_operation('Gespeicherte Profilwerte für Etiketten erneut prüfen…',work,done)
    def close():
        if not state['running']:
            if state['pending']:window.after_cancel(state['pending']);state['pending']=None
            state['preview_cache'].clear();state['photo']=None;state['search_index']=[];state['index_docs']=None;state['row_values'].clear()
            for event,binding in wheel_bindings:window.unbind(event,binding)
            if embedded:page_close()
            else:window.destroy()
            if previous_grab is not None and previous_grab.winfo_exists():
                if embedded:previous_grab.deiconify()
                previous_grab.grab_set()
    all_button=ttk.Button(actions,text='Alle sichtbaren auswählen',command=lambda:(table.selection_set(table.get_children()),update_preview()));all_button.pack(side='left',padx=(0,8))
    export_button=ttk.Button(actions,text='PNG exportieren…',command=save_images);export_button.pack(side='left',padx=(0,8))
    close_button=ttk.Button(actions,text='← Tagwriter' if embedded else 'Schließen',command=close);close_button.pack(side='left')
    def prepare_print():
        capture();keys=list(table.selection())
        if not keys:raise ValueError('Keine Profile ausgewählt.')
        original={key:deepcopy(state['docs'][key]) for key in keys}
        remembered_options={key:options(original[key]) for key in keys}
        opts={key:dict(remembered_options[key],dpi=203) for key in keys}
        def prepare():
            fresh=provider() if provider else list(original.values());current={d['key']:d for d in fresh}
            if not set(keys).issubset(current):raise ValueError('Profil oder Drucker gewechselt. Etikettenfenster erneut öffnen.')
            if any(current[key]['fingerprint']!=original[key]['fingerprint'] for key in keys):return {'changed':fresh}
            return {'images':[render_png(current[key],opts[key])[0] for key in keys]}
        def remember():
            from cfs_profile_sync import write_json
            prefs['plate_preference_revision']=PLATE_PREFERENCE_REVISION
            prefs['defaults']={k:v for k,v in remembered_options[keys[0]].items() if k!='display_name'}
            prefs.setdefault('profiles',{})
            for key in keys:prefs['profiles'][key]={'display_name':remembered_options[key]['display_name'],'fingerprint':original[key]['fingerprint']}
            write_json(preference_path,prefs)
        return {'count':len(keys),'prepare':prepare,'remember':remember}
    def print_finished(result):
        state['docs']={d['key']:d for d in result['changed']};state['current']=None;state['drafts'].clear()
        state['notice']='Profilwerte geändert. Vorschau wurde aktualisiert; vor dem Drucken erneut prüfen.';fill()
    from cfs_label_printer_ui import add_controls
    printer_fields=add_controls(app,tk,ttk,dialogs,right,actions,prepare_print,print_finished,set_running,lambda:bool(table.selection()) and not state['running'])
    for var in (title_var,plate,currency,dpi,show_pa,show_price):var.trace_add('write',schedule)
    
    for var in (search,nozzle,manufacturer,material_type,source,printer_brand,printer_model):var.trace_add('write',fill)
    table.bind('<<TreeviewSelect>>',lambda event:update_preview())
    app.label_dialog_fields={'window':window,'table':table,'preview':preview,'option_canvas':option_canvas,'options':right,'flags':flags,'export':export_button,'all':all_button,'result':message,'close':close_button,'title':title_var,'plate':plate,'nozzle':nozzle,'manufacturer':manufacturer,'material_type':material_type,'source':source,'search':search,'state':state,'printer':printer_fields}
    if embedded:
        app.close_main_page=close;app.main_page_fields['back'].configure(command=close)
    else:window.protocol('WM_DELETE_WINDOW',close);window.grab_set()
    fill();app.apply_theme(persist=False)
    return window

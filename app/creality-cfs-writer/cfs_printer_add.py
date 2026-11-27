# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Common printer setup. Saving a bookmark never installs software or copies profiles."""
from cfs_compatibility import CREALITY, ANYCUBIC, model_info
from cfs_connections import ConnectionStore


def configured_printers(app):
    choices={}
    registry=getattr(app,'registry',None)
    if registry is not None:
        for item in registry.printer_choices():choices[item['ip']]=dict(item)
        active=registry.printer
        if active.get('ip'):choices[active['ip']]={**choices.get(active['ip'],{}),**active}
    for item in ConnectionStore(app.data_dir).choices():
        previous=choices.get(item['ip'],{})
        choices[item['ip']]={**previous,**item}
        if previous.get('printer_int_name'):choices[item['ip']]['printer_int_name']=previous['printer_int_name']
    return list(choices.values())


def save_printer(app,name,ip,manufacturer,model,*,feeder_id=None,feeder_variant=None):
    if manufacturer not in ('Creality','Anycubic') or model not in (CREALITY if manufacturer=='Creality' else ANYCUBIC):
        raise ValueError('Bitte Hersteller und unterstützten Druckertyp auswählen.')
    store=ConnectionStore(app.data_dir);ip=store._address(ip)
    if any(item['ip']==ip for item in configured_printers(app)):
        raise ValueError('Diese IP-Adresse ist bereits eingerichtet. Den Drucker über „Drucker auswählen“ wählen; vorhandene Anmeldedaten bleiben erhalten.')
    store.remember(name,ip,model=manufacturer+' '+model,feeder_id=feeder_id,feeder_variant=feeder_variant)
    return next(item for item in store.choices() if item['ip']==ip)


def show_add_printer(app,tk,ttk):
    existing=getattr(app,'add_printer_fields',{}).get('window')
    if existing is not None and existing.winfo_exists():existing.lift();return
    from cfs_anycubic_feeders import FEEDERS, target_status
    window=tk.Toplevel(app.root);window.title('Drucker hinzufügen');window.transient(app.root)
    body=ttk.Frame(window,padding=22);body.pack(fill='both',expand=True);body.columnconfigure(1,weight=1)
    ttk.Label(body,text='Drucker hinzufügen',font=('TkDefaultFont',17,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,14))
    values={'manufacturer':tk.StringVar(value='Creality'),'model':tk.StringVar(value='K2 Pro'),
            'name':tk.StringVar(value='Creality K2 Pro'),'ip':tk.StringVar(),'feeder':tk.StringVar(),'variant':tk.StringVar()}
    widgets={};rows={}
    for row,(key,title,options) in enumerate((('manufacturer','Marke',('Creality','Anycubic')),('model','Druckertyp',CREALITY),
            ('name','Eigener Druckername',None),('ip','IP-Adresse',None),('feeder','Filamentwechsler',()),('variant','Ausführung',())),1):
        caption=ttk.Label(body,text=title);caption.grid(row=row,column=0,sticky='w',padx=(0,12),pady=6)
        field=ttk.Entry(body,textvariable=values[key],width=42) if options is None else ttk.Combobox(body,textvariable=values[key],values=options,state='readonly',width=40)
        field.grid(row=row,column=1,sticky='ew',pady=6);widgets[key]=field;rows[key]=(caption,field)
    message=tk.StringVar()
    ttk.Label(body,textvariable=message,style='Hint.TLabel',wraplength=650).grid(row=7,column=0,columnspan=2,sticky='w',pady=(14,8))
    default_name=['Creality K2 Pro']
    feeder_choices={};variants={}
    def refresh(_event=None):
        anycubic=values['manufacturer'].get()=='Anycubic'
        models=ANYCUBIC if anycubic else CREALITY;widgets['model'].configure(values=models)
        if values['model'].get() not in models:values['model'].set(models[0])
        model=values['model'].get();name=values['manufacturer'].get()+' '+model
        if values['name'].get()==default_name[0]:values['name'].set(name)
        default_name[0]=name
        for key in ('feeder','variant'):
            for widget in rows[key]:widget.grid() if anycubic else widget.grid_remove()
        info=model_info(model,values['manufacturer'].get())
        if not anycubic:
            message.set(info['status']+'. Speichert zunächst die Druckerauswahl. Zum Laden der Profile anschließend verknüpfen; der Druckerdienst wird separat eingerichtet und prüft das tatsächliche Modell.')
            return
        feeder_choices.clear();feeder_choices.update({item['name']:key for key,item in FEEDERS.items() if model in item['models']})
        widgets['feeder'].configure(values=list(feeder_choices))
        if values['feeder'].get() not in feeder_choices:values['feeder'].set(next(iter(feeder_choices),'') )
        feeder=feeder_choices.get(values['feeder'].get(),'')
        variants.clear();variants.update({item[0]:key for key,item in FEEDERS.get(feeder,{}).get('variants',{}).items() if model in item[1]})
        widgets['variant'].configure(values=list(variants))
        if values['variant'].get() not in variants:values['variant'].set(next(iter(variants),'') )
        message.set(target_status(feeder,variants.get(values['variant'].get(),''),model)+' Kein Anycubic-Cloud-/Profildienst. Gespeicherte Slicerprofile können für diesen Drucker geladen werden.')
    for key in ('manufacturer','model','feeder','variant'):widgets[key].bind('<<ComboboxSelected>>',refresh)
    def save():
        try:
            printer=save_printer(app,values['name'].get(),values['ip'].get(),values['manufacturer'].get(),values['model'].get(),
                feeder_id=feeder_choices.get(values['feeder'].get()) if values['manufacturer'].get()=='Anycubic' else None,
                feeder_variant=variants.get(values['variant'].get()) if values['manufacturer'].get()=='Anycubic' else None)
        except (OSError,ValueError) as error:message.set(str(error));return
        window.destroy();app.refresh_printer_filters()
        if values['manufacturer'].get()=='Anycubic':app.target_form.select(printer)
        else:app.status_var.set('Drucker gespeichert: '+printer['name']+'. Über „Drucker auswählen“ verknüpfen; Dienst bei Bedarf separat einrichten.')
    actions=ttk.Frame(body);actions.grid(row=8,column=0,columnspan=2,sticky='e',pady=(12,0))
    ttk.Button(actions,text='Abbrechen',command=window.destroy).pack(side='left',padx=(0,10))
    button=ttk.Button(actions,text='Drucker speichern',command=save,style='Write.TButton');button.pack(side='left')
    app.add_printer_fields={'window':window,'values':values,'fields':widgets,'save':button,'message':message}
    refresh();window.grab_set();app.apply_theme(False)

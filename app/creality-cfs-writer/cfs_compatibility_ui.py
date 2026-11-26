# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Read-only compatibility inventory, with explicit testing boundaries."""
def show(app, tk, ttk):
    from cfs_compatibility import rows, SOURCES
    from cfs_pages import open_page
    parent, close = open_page(app, tk, ttk, 'Drucker & Filamentwechsler')
    frame = ttk.Frame(parent, padding=18)
    frame.pack(fill='both', expand=True)
    frame.columnconfigure(0,weight=1)
    frame.rowconfigure(1,weight=1)
    ttk.Label(frame, text='Gerätetest: Creality K2 Pro mit CFS. Alle anderen Modelle sind experimentell.',
              style='Notice.TLabel', wraplength=1000).grid(row=0,column=0,sticky='ew',pady=(0,12))
    notebook=ttk.Notebook(frame);notebook.grid(row=1,column=0,columnspan=2,sticky='nsew')
    printers=ttk.Frame(notebook);printers.columnconfigure(0,weight=1);printers.rowconfigure(0,weight=1)
    feeders=ttk.Frame(notebook);feeders.columnconfigure(0,weight=1);feeders.rowconfigure(0,weight=1)
    notebook.add(printers,text='Druckertypen');notebook.add(feeders,text='Anycubic-Filamentwechsler')
    table = ttk.Treeview(printers, columns=('brand', 'model', 'state', 'service'), show='headings', height=15)
    for key, title, width in (('brand', 'Hersteller', 110), ('model', 'Druckertyp', 160), ('state', 'Prüfstand', 310), ('service', 'Integration', 350)):
        table.heading(key, text=title)
        table.column(key, width=width, minwidth=70)
    table.grid(row=0,column=0,sticky='nsew')
    scrollbar=ttk.Scrollbar(printers,orient='vertical',command=table.yview);scrollbar.grid(row=0,column=1,sticky='ns');table.configure(yscrollcommand=scrollbar.set)
    for row in rows():
        table.insert('', 'end', values=(row['manufacturer'], row['model'], row['status'],
            'CFS-Dienst nach automatischer Datenprüfung' if row['service_available'] else 'Wechsler getrennt wählen · kein Druckerdienst'))
    from cfs_anycubic_feeders import feeder_rows
    feeder_table=ttk.Treeview(feeders,columns=('name','variant','format'),show='headings',height=12)
    for key,title,width in (('name','Wechsler / RFID-System',270),('variant','Ausführung / passender Drucker',390),('format','Tagformat / Prüfstand',330)):
        feeder_table.heading(key,text=title);feeder_table.column(key,width=width,minwidth=80)
    feeder_table.grid(row=0,column=0,sticky='nsew')
    feeder_scroll=ttk.Scrollbar(feeders,orient='vertical',command=feeder_table.yview);feeder_scroll.grid(row=0,column=1,sticky='ns');feeder_table.configure(yscrollcommand=feeder_scroll.set)
    details={}
    for feeder in feeder_rows():
        for variant,(label,models) in feeder['variants'].items():
            key=feeder['id']+':'+variant
            feeder_table.insert('','end',iid=key,values=(feeder['name'],label,'Experimentell · '+('ACE V2 / NTAG213' if feeder['format_state']=='documented' else 'Ziel-Tagformat unbestätigt')))
            details[key]=feeder['note']+' Drucker: '+', '.join(models)+'. Kein eigener Gerätetest.'
    feeder_detail=tk.StringVar(value='Wechsler auswählen. Anschlusskompatibilität, bekanntes Datenformat und tatsächlicher Gerätetest werden getrennt angegeben.')
    ttk.Label(feeders,textvariable=feeder_detail,style='Hint.TLabel',wraplength=950).grid(row=1,column=0,sticky='ew',pady=10)
    feeder_table.bind('<<TreeviewSelect>>',lambda event:feeder_detail.set(details[feeder_table.selection()[0]]) if feeder_table.selection() else None)
    ttk.Label(frame, text='Creality: passende CFS-/CFS-C-Hardware bzw. Nachrüst-Kit nötig. Der Dienst prüft das native Modell, '
              'den Materialkatalog, Python und den Dienststarter vor der Installation. Anycubic: Hersteller-Hardwarekompatibilität '
              'bedeutet keinen eigenen Gerätetest. ACE Pro und ACE 2 Pro teilen hier das dokumentierte ACE-Format. Integrierte/unbekannte Leser benötigen eine eigene Formatprüfung. '
              'Eine automatische Zuordnung eigener Kalibrierungsprofile in Anycubic-Firmware oder Cloud ist nicht implementiert.',
              style='Hint.TLabel', wraplength=1000).grid(row=2,column=0,sticky='ew',pady=12)
    import webbrowser
    links = ttk.Frame(frame)
    links.grid(row=3,column=0,sticky='ew')
    for name, url in SOURCES.items():
        ttk.Button(links, text=name+' ↗', command=lambda url=url: webbrowser.open(url)).pack(side='left', padx=(0, 7))
    app.apply_theme(persist=False)
    app.compatibility_fields = {'table': table,'feeder_table':feeder_table,'notebook':notebook}
    return app.compatibility_fields

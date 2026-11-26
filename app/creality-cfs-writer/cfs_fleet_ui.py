# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Explicit multi-printer sync page; no automatic network polling or pushes."""
from copy import deepcopy
import json
from pathlib import Path
from cfs_fleet import FleetStore, MODES, TargetRegistry, sync_profiles
from cfs_compatibility import model_info


def show(app, tk, ttk, dialogs):
    from cfs_pages import open_page
    parent, close = open_page(app, tk, ttk, 'Drucker & Synchronisierung')
    content = ttk.Frame(parent, padding=18)
    content.pack(fill='both', expand=True)
    content.columnconfigure(0, weight=1)
    content.rowconfigure(4, weight=1)
    store = FleetStore(app.data_dir)
    source = deepcopy(app.target_form.current()) if getattr(app,'target_form',None) else (deepcopy(app.registry.printer) if app.registry is not None else {})
    source_is_anycubic = model_info(source.get('model') or source.get('printer_int_name',''))['manufacturer'] == 'Anycubic'
    choices = app.registry.printer_choices() if app.registry is not None else []
    from cfs_connections import ConnectionStore
    for bookmark in ConnectionStore(app.data_dir).choices():
        existing = next((item for item in choices if item['ip'] == bookmark['ip']), None)
        if existing is None:
            choices.append(dict(bookmark, printer_int_name=bookmark.get('model', '')))
        elif not existing.get('printer_int_name'):
            existing['printer_int_name'] = bookmark.get('model', '')
    for item in choices:
        if item['ip'] == source.get('ip'):
            item.update({key: source[key] for key in ('printer_int_name', 'nozzle_diameter') if key in source})
    state = {'targets': {}, 'preview': None, 'target': None, 'snapshot': None, 'codes': []}
    ttk.Label(content, text='Quelle: '+source.get('name', 'Noch kein Drucker')+' · '+source.get('ip', ''),
              font=('TkDefaultFont', 14, 'bold')).grid(row=0, column=0, sticky='w')
    ttk.Label(content, text='Rollennummern werden lokal anhand der Tagkennung zugeordnet. Auf jedem beteiligten Drucker einschalten. '
              'Restmengen werden beim Lesen immer vom Tag übernommen. Profilübertragung geht bewusst von der Quelle zum Ziel, '
              'nur bei gleichem Modell und Düsendurchmesser. Es wird kein Slicer verändert.',
              style='Hint.TLabel', wraplength=1000).grid(row=1, column=0, sticky='ew', pady=(8, 12))
    target_var = tk.StringVar()
    mode = tk.StringVar(value=MODES['off'])
    row = ttk.Frame(content)
    row.grid(row=2, column=0, sticky='ew')
    row.columnconfigure(1, weight=1)
    ttk.Label(row, text='Drucker').grid(row=0, column=0, padx=(0, 8))
    selector = ttk.Combobox(row, textvariable=target_var, state='readonly', width=60)
    selector.grid(row=0, column=1, sticky='ew')
    for item in choices:
        info = model_info(item.get('printer_int_name') or item.get('model', ''))
        label = f"{info['manufacturer']} / {info['model']} / {item['name']} · {item['ip']}"
        state['targets'][label] = deepcopy(item)
    selector.configure(values=sorted(state['targets'], key=str.casefold))
    ttk.Label(row, text='Teilen').grid(row=1, column=0, sticky='w', pady=8)
    policy = ttk.Combobox(row, textvariable=mode, values=list(MODES.values()), state='readonly', width=60)
    policy.grid(row=1, column=1, sticky='ew', pady=8)
    message = tk.StringVar(value='Einen Drucker auswählen. Einstellungen gelten erst nach „Auswahl speichern“.')
    notice = ttk.Label(content, textvariable=message, style='Notice.TLabel', wraplength=1000)
    notice.grid(row=3, column=0, sticky='ew', pady=10)
    notebook = ttk.Notebook(content)
    notebook.grid(row=4, column=0, columnspan=2, sticky='nsew')
    profile_tab = ttk.Frame(notebook)
    profile_tab.columnconfigure(0, weight=1)
    profile_tab.rowconfigure(0, weight=1)
    notebook.add(profile_tab, text='Profile übertragen')
    roll_tab = ttk.Frame(notebook)
    roll_tab.columnconfigure(0, weight=1)
    roll_tab.rowconfigure(0, weight=1)
    notebook.add(roll_tab, text='Gemeinsame Rollennummern')
    rolls = ttk.Treeview(roll_tab, columns=('serial', 'tags', 'printers'), show='headings')
    for key, title, width in (('serial', 'Rollennummer', 120), ('tags', 'Tagkennungen', 330), ('printers', 'Drucker / Materialcode', 450)):
        rolls.heading(key, text=title)
        rolls.column(key, width=width, minwidth=80)
    rolls.grid(row=0, column=0, sticky='nsew')
    roll_scroll = ttk.Scrollbar(roll_tab, orient='vertical', command=rolls.yview)
    roll_scroll.grid(row=0, column=1, sticky='ns')
    rolls.configure(yscrollcommand=roll_scroll.set)

    def fill_rolls():
        rolls.delete(*rolls.get_children())
        for serial, roll in sorted(store.load()['rolls'].items()):
            printers = ', '.join(ip+' / '+str(row['material_id']) for ip, row in roll['printers'].items())
            rolls.insert('', 'end', values=(serial, ', '.join(roll['tags']), printers))
    fill_rolls()
    table = ttk.Treeview(profile_tab, columns=('code', 'profile', 'action'), show='headings', selectmode='extended')
    for key, title, width in (('code', 'Materialcode', 110), ('profile', 'Quellprofil / Hersteller', 480), ('action', 'Ziel / Änderung', 270)):
        table.heading(key, text=title)
        table.column(key, width=width, minwidth=70)
    table.grid(row=0, column=0, sticky='nsew')
    scroll = ttk.Scrollbar(profile_tab, orient='vertical', command=table.yview)
    scroll.grid(row=0, column=1, sticky='ns')
    table.configure(yscrollcommand=scroll.set)
    credentials = ttk.Frame(content)
    credentials.grid(row=5, column=0, sticky='ew', pady=10)
    password = tk.StringVar()
    ttk.Label(credentials, text='SSH-Passwort des Zieldruckers').pack(side='left')
    password_entry = ttk.Entry(credentials, textvariable=password, show='•', width=24)
    password_entry.pack(side='left', padx=8)
    actions = ttk.Frame(content)
    actions.grid(row=6, column=0, sticky='ew', pady=8)
    lower = ttk.Frame(content)
    lower.grid(row=7, column=0, sticky='ew', pady=5)
    managed = []

    def invalidate(*_):
        state['preview'] = None
        apply.configure(state='disabled')

    def selected(_event=None):
        invalidate()
        item = state['targets'].get(target_var.get())
        if item is None:
            return
        state['target'] = deepcopy(item)
        info = model_info(item.get('printer_int_name') or item.get('model', ''))
        policy.configure(values=[MODES[key] for key in (('off', 'rolls') if info['manufacturer'] == 'Anycubic' else MODES)])
        mode.set(MODES[store.policy(item['ip'])])
        password.set('')
        try:
            password.set(ConnectionStore(app.data_dir).password(item['ip']))
        except ValueError:
            pass
        table.delete(*table.get_children())
        state['snapshot'] = None
        message.set('Gewählt: '+item['name']+' · '+MODES[store.policy(item['ip'])]+'. Ein Richtungswechsel überschreibt die Quelle nicht.')

    def save():
        try:
            item = state['target']
            if not item:
                raise ValueError('Zuerst einen Drucker wählen.')
            store.set_policy(item['ip'], next(key for key, value in MODES.items() if value == mode.get()))
            message.set('Gespeichert: '+item['name']+' · '+mode.get()+'. Es wurden keine Druckerdaten verändert.')
            invalidate()
        except (ValueError, OSError) as error:
            message.set(str(error))

    def operation(label, work, done):
        for button in managed:
            button.configure(state='disabled')
        selector.configure(state='disabled')
        policy.configure(state='disabled')
        password_entry.configure(state='disabled')
        table.configure(selectmode='none')
        def run():
            try:
                return {'value': work()}
            except Exception as error:
                return {'error': str(error)}
        def complete(reply):
            for button in managed:
                button.configure(state='normal')
            selector.configure(state='readonly')
            policy.configure(state='readonly')
            password_entry.configure(state='normal')
            table.configure(selectmode='extended')
            apply.configure(state='disabled')
            if 'error' in reply:
                invalidate()
                notice.configure(style='ErrorNotice.TLabel')
                message.set(reply['error'])
            else:
                notice.configure(style='Notice.TLabel')
                done(reply['value'])
        app.run_operation(label, run, complete)

    def load():
        if source_is_anycubic:
            message.set('Anycubic: nur lokale Rollenzuordnungen. Kein Drucker-Profildienst und kein Profiltransfer implementiert.');return
        invalidate()
        if app.registry is None:
            message.set('Zuerst einen Creality-Drucker einrichten.')
            return
        def done(snapshot):
            state['snapshot'] = snapshot
            table.delete(*table.get_children())
            for code, profile in sorted(snapshot['profiles'].items(), key=lambda pair: (pair[1]['brand'].casefold(), pair[1]['name'].casefold())):
                table.insert('', 'end', iid=code, values=(code, profile['brand']+' · '+profile['name'], 'Profil zum Übertragen auswählen'))
            message.set(str(len(snapshot['profiles']))+' Quellprofile geladen. Eines oder mehrere auswählen und Vorschau öffnen.')
        operation('Quellprofile frisch vom Drucker lesen…', lambda: app.registry.cloud_catalog(fresh=True), done)

    def preview():
        if source_is_anycubic:
            message.set('Anycubic: nur lokale Rollenzuordnungen. Kein Drucker-Profildienst und kein Profiltransfer implementiert.');return
        item = deepcopy(state['target'])
        codes = list(table.selection())
        if not item or not codes:
            message.set('Zieldrucker und mindestens ein Quellprofil auswählen.')
            return
        secret = password.get()
        def done(result):
            state['preview'] = result
            state['codes'] = codes
            for row in result['plan']:
                table.set(row['source_code'], 'action', row['action']+' → '+row['material_id']+(' · Tag neu schreiben' if row['retag_required'] else ' · Code bleibt'))
            message.set('Vorschau geprüft. '+str(len(result['plan']))+' Profile. '+str(len(result['code_changes']))+' abweichende Materialcodes. Nur das Ziel wird aktualisiert.')
            apply.configure(state='normal')
        operation('Modelle, Zielstatus und Materialcodes prüfen…', lambda: sync_profiles(app.registry, store, item, codes, secret), done)

    def commit():
        if source_is_anycubic:
            message.set('Anycubic: nur lokale Rollenzuordnungen. Kein Drucker-Profildienst und kein Profiltransfer implementiert.');return
        preview = state['preview']
        if preview is None:
            return
        item, codes, secret = deepcopy(state['target']), list(state['codes']), password.get()
        def done(result):
            invalidate()
            message.set('✓ '+str(len(result['plan']))+' Profile auf '+item['name']+' übernommen und zurückgelesen. '+str(len(result['code_changes']))+' Tags benötigen einen anderen Materialcode.')
            if result.get('linked_rolls'):
                message.set(message.get()+' '+str(result['linked_rolls'])+' neue Rollenzuordnungen ergänzt; Tags dadurch noch nicht umgeschrieben.')
            if result.get('roll_binding_warning'):
                message.set(message.get()+' '+result['roll_binding_warning'])
            fill_rolls()
        operation('Ausgewählte Profile auf den Zieldrucker übertragen…', lambda: sync_profiles(app.registry, store, item, codes, secret, preview), done)

    def export_rolls():
        path = dialogs['filedialog'].asksaveasfilename(parent=app.root, title='Rollenzuordnungen exportieren', defaultextension='.json', filetypes=[('Rollenzuordnungen', '*.json')])
        if path:
            try:
                from cfs_profile_sync import write_json
                write_json(Path(path), store.load())
                message.set('Rollenzuordnungen exportiert. Enthält IP-Zuordnungen, keine Passwörter.')
            except (ValueError, OSError) as error:
                message.set('Export fehlgeschlagen: '+str(error))

    def import_rolls():
        path = dialogs['filedialog'].askopenfilename(parent=app.root, title='Rollenzuordnungen importieren', filetypes=[('Rollenzuordnungen', '*.json')])
        if path:
            try:
                with Path(path).open('rb') as stream:
                    raw = stream.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise ValueError('Die Datei ist zu groß.')
                count = store.import_inventory(json.loads(raw.decode('utf-8-sig')))
                fill_rolls()
                message.set(str(count)+' Rollenzuordnungen importiert. Die örtlichen Freigaben bleiben unverändert.')
            except (ValueError, OSError) as error:
                message.set(str(error))

    for label, command in (('Auswahl speichern', save), ('Quellprofile laden', load), ('Synchronisierung prüfen', preview)):
        button = ttk.Button(actions, text=label, command=command,state='disabled' if source_is_anycubic and command in (load,preview) else 'normal')
        button.pack(side='left', padx=(0, 8))
        managed.append(button)
    apply = ttk.Button(actions, text='Profile jetzt übertragen', command=commit, style='Write.TButton', state='disabled')
    apply.pack(side='right')
    managed.append(apply)
    for label, command in (('Rollenzuordnungen exportieren…', export_rolls), ('Rollenzuordnungen importieren…', import_rolls)):
        button = ttk.Button(lower, text=label, command=command)
        button.pack(side='left', padx=(0, 8))
        managed.append(button)
    policy.bind('<<ComboboxSelected>>', invalidate)
    password.trace_add('write', invalidate)
    table.bind('<<TreeviewSelect>>', invalidate)
    selector.bind('<<ComboboxSelected>>', selected)
    if state['targets']:
        target_var.set(next(iter(state['targets'])))
        selected()
    app.apply_theme(persist=False)
    app.fleet_fields = {'selector': selector, 'mode': mode, 'table': table, 'message': message,
                        'state': state, 'save': save, 'load': load, 'preview': preview, 'apply': commit, 'store': store}
    return app.fleet_fields

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""One tag form, explicitly selected printer, separate protocol adapters.

Selecting a target never installs a service, changes a registry or writes a tag.
"""
import re
from cfs_compatibility import model_info


class TargetForm:
    def __init__(self, app, tk, ttk, dialogs, profile, write):
        self.app, self.tk, self.ttk, self.dialogs = app, tk, ttk, dialogs
        self.printer = None
        self.cfs_materials = None
        self.documents = []
        self.writable = False
        self.loading = False
        self.variables = {key: tk.StringVar(value=value) for key, value in
                          (('type', 'PLA'), ('nozzle_low', '200'), ('nozzle_high', '220'), ('bed_low', '50'), ('bed_high', '60'))}
        self.frame = ttk.Frame(profile)
        self.frame.grid(row=14, column=0, columnspan=6, sticky='ew', pady=8)
        self.widgets = []
        for col, (key, title) in enumerate((('type', 'ACE-Materialtyp'), ('nozzle_low', 'Düse min. °C'),
                                           ('nozzle_high', 'Düse max. °C'), ('bed_low', 'Bett min. °C'), ('bed_high', 'Bett max. °C'))):
            ttk.Label(self.frame, text=title).grid(row=0, column=col, sticky='w', padx=(0, 10))
            entry = ttk.Entry(self.frame, textvariable=self.variables[key], width=15 if col == 0 else 11)
            entry.grid(row=1, column=col, sticky='ew', padx=(0, 10))
            self.widgets.append(entry)
            self.variables[key].trace_add('write', self.edited)
        self.frame.grid_remove()
        self.notice = tk.StringVar()
        ttk.Label(write, textvariable=self.notice, style='Hint.TLabel', wraplength=810).grid(
            row=2, column=0, columnspan=2, sticky='w', pady=(9, 0))

    @property
    def ace(self):
        return self.printer is not None and model_info(self.printer.get('model'))['manufacturer'] == 'Anycubic'

    def current(self):
        return self.printer if self.ace else (self.app.registry.printer if self.app.registry else {})

    def edited(self, *_):
        if not self.loading and not self.app.busy:
            self.app.tag_feedback.edited()
            self.app.update_controls()

    def select(self, printer=None):
        app = self.app
        if app.busy:
            return
        if printer is not None:
            from cfs_anycubic_feeders import validate_selection
            validate_selection(printer.get('feeder_id', ''), printer.get('feeder_variant', ''), model_info(printer.get('model'))['model'])
            if not self.ace:
                self.cfs_materials = list(getattr(app, '_all_material_by_label', app.material_by_label).values())
        self.printer = dict(printer) if printer is not None else None
        app.pair_session.reset()
        app.clear_tag()
        app.tag_feedback.reset()
        self.writable = False
        self.loading = True
        app._suspend_updates = True
        try:
            app.clear_material_filters()
            if self.ace:
                self.frame.grid()
                app.set_materials([{'id': '', 'name': 'Eigene ACE-Tagdaten', 'source': 'slicer', 'brand': '',
                                    'printer_manufacturer': 'Anycubic', 'printer_model': model_info(printer['model'])['model']}])
                app.id_var.set('')
                app.name_var.set('')
                app.profile_source_var.set('Quelle: gespeicherter Slicer → Tag. Anycubic: kein Cloud-Upload und kein Drucker-Profildienst.')
                app.printer_hint_var.set('USB: Mega2560 / Nano + RC522 · Drucker: '+printer['name']+' · '+printer['model'])
                app.import_button.configure(text='Slicerprofile laden…')
                app.sync_direction_var.set('Slicer → Tag · kein Drucker-/Cloud-Upload')
            else:
                self.frame.grid_remove()
                app.sync_direction_var.set('Slicer → Drucker · kein Cloud-Upload')
                app.import_button.configure(text='Profile aktualisieren + neue Codes' if app.registry else 'Profile / Datenbank laden…')
                if self.cfs_materials:
                    app.set_materials(self.cfs_materials)
                    self.cfs_materials = None
            app.id_caption.configure(text='Anycubic-SKU' if self.ace else 'Materialcode')
        finally:
            self.loading = False
            app._suspend_updates = False
        app.status_var.set('Drucker ausgewählt. Tag vor dem Schreiben erneut lesen.')
        app.update_controls()
        app.apply_theme(False)

    def target_config(self):
        from cfs_anycubic_feeders import require_write_target
        printer = self.printer or {}
        config = dict(feeder_id=printer.get('feeder_id', ''), variant=printer.get('feeder_variant', ''),
                      model=model_info(printer.get('model'))['model'], test_unknown_format=printer.get('test_unknown_format') is True)
        require_write_target(**config)
        return config

    def spec(self):
        from cfs_anycubic import AceSpec, encode
        app = self.app
        def number(value):
            if not re.fullmatch(r'[0-9]+', str(value)):
                raise ValueError('Mengen und Temperaturen als ganze Zahlen eingeben.')
            return int(value)
        spec = AceSpec(app.id_var.get().strip(), self.variables['type'].get().strip(), app.color_var.get().strip().upper(),
                       number(app.weight_var.get()), number(app.length_var.get()),
                       *[number(self.variables[key].get()) for key in ('nozzle_low', 'nozzle_high', 'bed_low', 'bed_high')],
                       app.serial_var.get().strip())
        encode(spec)
        if not re.fullmatch(r'[0-9]{6}', spec.serial):
            raise ValueError('Die lokale Rollennummer muss sechs Ziffern enthalten.')
        self.target_config()
        return spec

    def update(self):
        app = self.app
        info = model_info(self.current().get('model') or self.current().get('printer_int_name'))
        self.notice.set(('Experimentell · '+info['manufacturer']+' '+info['model']+
                         ' ist nicht mit dieser App am Gerät geprüft. Erkennung im Drucker nach dem Schreiben testen.') if info['experimental'] else '')
        if not self.ace:
            return False
        app.mapping_hint_var.set('ACE-SKU und Materialtyp bestimmen die native Zuordnung. Flow/PA bleiben im Slicer; die Rollennummer wird lokal verwaltet.')
        app.profile_info_var.set('Gespeicherter Slicer → Tag. Kein Upload zu Anycubic oder zur Cloud. CFS-Tags sind nicht kompatibel; NTAG213 erforderlich.')
        app.weight_hint_var.set('ACE speichert Gramm und Meter getrennt. Beim Lesen werden beide vorhandenen Werte übernommen.')
        app.nozzle_info_var.set('Druckertyp: '+info['model'])
        locked = app.busy or app.close_pending
        for entry in self.widgets:
            entry.configure(state='disabled' if locked or app.pair_session.locked else 'normal')
        for name in ('new_profile_button', 'local_profile_button'):
            widget = getattr(app, name, None)
            if widget is not None: widget.configure(state='disabled')
        valid = False
        try:
            spec = self.spec()
            valid = True
            app.summary_var.set(f'{app.name_var.get() or spec.type} · SKU {spec.sku} · {spec.color} · {spec.weight_g} g / {spec.length_m} m\nRollennummer {spec.serial} (lokal) · Ziel: {app.uid or "noch kein Tag gelesen"}')
            app.write_hint_var.set('Tag schreiben und zurücklesen.' if app.uid and self.writable else 'Zum Schreiben zuerst einen ungesperrten NTAG213 lesen.')
        except (ValueError, TypeError, OverflowError) as error:
            app.summary_var.set('Filamentangaben ergänzen oder korrigieren.')
            app.write_hint_var.set(str(error))
        pair = app.pair_session
        app.pair_hint_var.set(pair.hint())
        if pair.enabled:app.pair_hint_label.grid()
        else:app.pair_hint_label.grid_remove()
        app.pair_reset_button.configure(state='normal' if pair.enabled and not locked else 'disabled')
        if pair.locked:
            for widget, _ in app.controls:
                if widget in (app.material_combo, app.id_entry, app.name_entry, app.color_entry, app.color_button, app.weight_combo,
                              app.length_entry, app.serial_entry, app.import_button, app.slicer_sync_button):widget.configure(state='disabled')
        writable = valid and self.writable and app.uid and app.bridge is not None and not locked
        if pair.enabled and (app.uid in pair.written or len(pair.written) >= 2):writable = False
        app.write_button.configure(state='normal' if writable else 'disabled', text=app.tag_feedback.caption('write'))
        app.read_button.configure(text=app.tag_feedback.caption('read'))
        app.tag_result_var.set(app.tag_feedback.message)
        app.tag_result_label.configure(style='ErrorNotice.TLabel' if app.tag_feedback.phase == 'error' else 'SuccessNotice.TLabel' if app.tag_feedback.phase == 'success' else 'Notice.TLabel')
        if hasattr(app, 'label_button'):
            selected=app.material_by_label.get(app.material_var.get())
            app.label_button.configure(state='normal' if selected and selected.get('ace_document') and not locked else 'disabled')
        app._schedule_content_fit()
        return True

    def read(self):
        from cfs_anycubic import AceDevice
        from cfs_fleet import FleetStore
        app = self.app
        preserve = app.pair_session.preserve_values
        app.clear_tag()
        self.writable = False
        app.tag_feedback.begin('read')
        def done(result):
            uid = result['uid']
            app.uid = uid
            self.writable = result['writable']
            app.pair_session.read(uid)
            self.loading = True
            app._suspend_updates = True
            try:
                old = result['spec']
                if old is not None and not preserve:
                    app.id_var.set(old.sku)
                    app.color_var.set(old.color)
                    app.weight_var.set(str(old.weight_g))
                    app.length_var.set(str(old.length_m))
                    for key in self.variables:self.variables[key].set(str(getattr(old, key)))
                    saved = FleetStore(app.data_dir).lookup('ace', uid)
                    if saved:app.serial_var.set(saved)
            finally:
                self.loading = False
                app._suspend_updates = False
            app.tag_feedback.success(uid)
            app.tag_var.set('UID '+uid+' · NTAG213')
            app.tag_hint_var.set(('Wunschwerte für Tag 2 beibehalten.' if preserve else 'Vorhandene Tagwerte übernommen.' if old else 'Leerer/unbekannter Datensatz; Angaben unten prüfen.')+
                                 ('' if self.writable else ' Tag ist gesperrt oder passwortgeschützt.'))
            app.status_var.set(app.tag_feedback.message)
        app.run_operation('Tag wird gelesen…', AceDevice(app.bridge).read_tag, done)

    def write(self):
        from cfs_anycubic import AceDevice, encode
        from cfs_fleet import FleetStore
        app = self.app
        if not app.uid or not self.writable or app.busy:return
        try:
            spec = self.spec()
            app.pair_session.check_write(app.uid, spec)
            if app.pair_session.spec is not None and encode(spec) != encode(app.pair_session.spec):
                raise ValueError('Die ACE-Tagwerte haben sich seit Tag 1 geändert. Zweiermodus zurücksetzen.')
            device = AceDevice(app.bridge, app.report_progress, target=self.target_config())
        except (ValueError, TypeError, OverflowError) as error:
            app.show_error(error)
            return
        uid, printer = app.uid, dict(self.printer)
        def done(result):
            if result.get('verified') is not True:raise ValueError('Schreiben nicht durch Zurücklesen bestätigt.')
            app.pair_session.confirmed(uid, spec)
            app.tag_feedback.success(uid, verified=True)
            app.status_var.set(app.tag_feedback.message+' · Druckererkennung noch testen.')
            app.tag_hint_var.set(app.pair_session.hint() if app.pair_session.enabled else 'Geschrieben und zurückgelesen. Experimenteller Gerätetest steht aus.')
            app.log('ACE-Tag geschrieben und geprüft. Sicherung: '+str(result.get('backup', '')))
            try:FleetStore(app.data_dir).remember(printer['ip'], 'ace', uid, spec.serial, spec.sku, spec.weight_g, allow_reassign=True)
            except (ValueError, OSError) as error:app.log('Tag geprüft; lokale Rollenzuordnung nicht gespeichert: '+str(error))
        app.tag_feedback.begin('write')
        app.run_operation('Tag wird geschrieben und zurückgelesen…', lambda:device.write_tag(uid, spec, app.backup_dir), done)

    def load_profiles(self):
        app = self.app
        if app.busy or app.pair_session.locked:
            app.status_var.set('Zuerst den laufenden Vorgang bzw. die Zweiergruppe abschließen oder zurücksetzen.');return
        paths = self.dialogs['filedialog'].askopenfilenames(parent=app.root, title='Gespeicherte Slicerprofile auswählen', filetypes=[('Filamentprofile', '*.json')])
        if not paths:return
        dependencies=[None]
        def work():
            from cfs_labels import documents_from_slicer
            try:return {'documents':documents_from_slicer(paths,dependencies[0])}
            except (ValueError,OSError) as error:return {'error':str(error)}
        def done(reply):
            if 'error' in reply:
                if 'Abhäng' in reply['error'] and dependencies[0] is None:
                    folder=self.dialogs['filedialog'].askdirectory(parent=app.root,title='Ordner mit geerbten Slicer-Systemprofilen wählen')
                    if folder:
                        dependencies[0]=folder
                        app.run_operation('Slicerprofil-Abhängigkeiten laden…',work,done)
                        return
                raise ValueError(reply['error'])
            documents=reply['documents']
            model = model_info(self.printer['model'])['model']
            documents = [d for d in documents if d.get('printer_manufacturer') == 'Anycubic' and d.get('printer_model') == model]
            if not documents:raise ValueError('Kein gespeichertes Profil für den ausgewählten Anycubic-Druckertyp gefunden.')
            self.documents = documents
            from cfs_labels import scalar
            app.set_materials([dict(id='', name=d['name'], source='slicer', source_file=str(d.get('source_file', '')),
                                    color=d['color'], brand=str(d.get('raw_brand') or d.get('brand','')), type=scalar(d['params'].get('filament_type')) or '',
                                    printer_manufacturer='Anycubic', printer_model=model, ace_document=d) for d in documents])
            app.status_var.set('Slicer → Tag: Profile geladen. SKU vom Originaltag übernehmen; keine Übertragung zum Drucker oder zur Cloud.')
        app.run_operation('Gespeicherte Slicerprofile laden…', work, done)

    def material(self, item):
        from cfs_labels import scalar
        app = self.app
        document = item.get('ace_document')
        if not document:return
        params = document['params']
        self.loading = True
        app._suspend_updates = True
        try:
            app.name_var.set(item['name'])
            app.color_var.set(document['color'])
            for key, source, default in (('type', 'filament_type', 'PLA'), ('nozzle_low', 'nozzle_temperature_range_low', '200'),
                                         ('nozzle_high', 'nozzle_temperature_range_high', '220'), ('bed_low', 'hot_plate_temp', '60'), ('bed_high', 'hot_plate_temp', '60')):
                self.variables[key].set(scalar(params.get(source)) or default)
        finally:
            self.loading = False
            app._suspend_updates = False
        app.update_controls()


def configure_anycubic(app, tk, ttk, *, printer=None):
    """One-time bookmark configuration; routine use only selects the printer."""
    from cfs_anycubic_feeders import FEEDERS, PRINTERS, validate_selection, target_status
    from cfs_connections import ConnectionStore
    from cfs_fleet import address
    window = tk.Toplevel(app.root)
    window.title('Anycubic-Drucker einrichten · experimentell')
    window.transient(app.root)
    body = ttk.Frame(window, padding=20)
    body.pack(fill='both', expand=True)
    printer = printer or (app.target_form.printer if app.target_form.ace else {})
    variables = {key:tk.StringVar(value=value) for key, value in (
        ('name', printer.get('name', 'Anycubic')), ('ip', printer.get('ip', '')),
        ('model', model_info(printer.get('model', 'Anycubic Kobra S1'))['model']), ('feeder', ''), ('variant', ''))}
    fields = {}
    for row, (key, title, values) in enumerate((('name', 'Bezeichnung', None), ('ip', 'IP-Adresse', None), ('model', 'Druckertyp', PRINTERS),
                                               ('feeder', 'Verbauter Filamentwechsler', [item['name'] for item in FEEDERS.values()]), ('variant', 'Ausführung', []))):
        ttk.Label(body, text=title).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=6)
        widget = ttk.Entry(body, textvariable=variables[key], width=44) if values is None else ttk.Combobox(body, textvariable=variables[key], values=list(values), state='readonly', width=42)
        widget.grid(row=row, column=1, sticky='ew', pady=6)
        fields[key] = widget
    message = tk.StringVar(value='Einmal Modell und verbauten Wechsler hinterlegen. Danach im gemeinsamen Tagwriter nur den Drucker wählen. Kein Anycubic-SSH-/Profildienst verfügbar.')
    ttk.Label(body, textvariable=message, style='Hint.TLabel', wraplength=620).grid(row=5, column=0, columnspan=2, sticky='w', pady=12)
    def chosen():
        feeder = next((key for key,item in FEEDERS.items() if item['name'] == variables['feeder'].get()), '')
        variants = FEEDERS.get(feeder, {}).get('variants', {})
        variant = next((key for key,item in variants.items() if item[0] == variables['variant'].get()), '')
        return feeder, variant
    def refresh(_event=None):
        feeder, variant = chosen()
        variants = FEEDERS.get(feeder, {}).get('variants', {})
        fields['variant'].configure(values=[item[0] for item in variants.values()])
        if variant not in variants:
            preferred = next((key for key,item in variants.items() if variables['model'].get() in item[1]), next(iter(variants), ''))
            variables['variant'].set(variants[preferred][0] if preferred else '')
        feeder, variant = chosen()
        if feeder:message.set(target_status(feeder, variant, variables['model'].get()))
    for key in ('model', 'feeder', 'variant'):fields[key].bind('<<ComboboxSelected>>', refresh)
    def save():
        try:
            ip = address(variables['ip'].get())
            feeder, variant = chosen()
            validate_selection(feeder, variant, variables['model'].get())
            store = ConnectionStore(app.data_dir)
            existing = next((item for item in store.choices() if item['ip'] == ip), None)
            if existing and not str(existing.get('model', '')).startswith('Anycubic '):raise ValueError('Diese Adresse gehört bereits zu einem Creality-Drucker.')
            store.remember(variables['name'].get(), ip, model='Anycubic '+variables['model'].get(), feeder_id=feeder, feeder_variant=variant)
            saved = next(item for item in store.choices() if item['ip'] == ip)
            app.target_form.select(dict(saved,test_unknown_format=bool(test_format.get())))
            window.destroy()
        except (ValueError, OSError) as error:message.set(str(error))
    test_format = tk.BooleanVar(value=False)
    ttk.Checkbutton(body,text='Unbestätigtes Ziel bewusst mit ACE-Testformat ausprobieren (nur diese Sitzung)',variable=test_format).grid(row=6,column=0,columnspan=2,sticky='w',pady=8)
    actions = ttk.Frame(body)
    actions.grid(row=7, column=0, columnspan=2, sticky='e')
    ttk.Button(actions, text='Abbrechen', command=window.destroy).pack(side='right')
    ttk.Button(actions, text='Drucker übernehmen', style='Write.TButton', command=save).pack(side='right', padx=8)
    if printer.get('feeder_id') in FEEDERS:
        variables['feeder'].set(FEEDERS[printer['feeder_id']]['name'])
        variant = FEEDERS[printer['feeder_id']]['variants'].get(printer.get('feeder_variant'))
        if variant:variables['variant'].set(variant[0])
        refresh()
    app.anycubic_setup_fields = dict(window=window, variables=variables, fields=fields, test_format=test_format, save=save, message=message)
    window.grab_set()
    app.apply_theme(False)

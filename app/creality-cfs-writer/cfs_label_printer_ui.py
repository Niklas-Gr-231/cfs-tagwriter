# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Inline label-printer controls; all device and rendering work stays off Tk."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
from cfs_label_printer import LabelPrinter,scan


def engine(app):
    extra=app.data_dir/'label-python-libs'
    if extra.is_dir() and str(extra) not in sys.path:sys.path.insert(0,str(extra))
    if not hasattr(app,'label_printer'):app.label_printer=LabelPrinter()
    return app.label_printer


def add_controls(app,tk,ttk,dialogs,parent,actions,prepare,finish,set_running,can_print):
    device=engine(app);prefs=app.data_dir/'label-printer.json'
    try:saved=json.loads(prefs.read_text())
    except (OSError,ValueError):saved={}
    if not isinstance(saved,dict):saved={}
    panel=ttk.LabelFrame(parent,text='Direktdruck · Katasymbol T50M Pro',padding=10)
    panel.grid(row=8,column=0,columnspan=2,sticky='ew',pady=(12,0));panel.columnconfigure(1,weight=1)
    address=tk.StringVar(value=saved.get('address',''));mode=tk.StringVar(value=saved.get('mode','Automatisch'))
    info=tk.StringVar(value='Nicht verbunden. Handy-App schließen; Drucker einschalten und Rolle einlegen.')
    ttk.Label(panel,text='Gerät / Adresse').grid(row=0,column=0,sticky='w',padx=(0,7))
    chooser=ttk.Combobox(panel,textvariable=address);chooser.grid(row=0,column=1,sticky='ew')
    devices={}
    controls=[chooser];connection_buttons={}
    buttons=ttk.Frame(panel);buttons.grid(row=1,column=0,columnspan=2,sticky='w',pady=5)
    def run(label,work,callback):
        if app.busy:return
        set_running(True);local_busy(True)
        def wrapped():
            try:return {'result':work()}
            except Exception as error:return {'error':str(error)}
        def done(reply):
            set_running(False);local_busy(False)
            if 'error' in reply:info.set(reply['error'] or 'Bluetooth-Vorgang fehlgeschlagen. Verbindung, Abstand und Geräteberechtigungen prüfen.');return
            callback(reply['result']);local_busy(False)
        app.run_operation(label,wrapped,done)
    def show_info(result):
        s=result['status'];m=result['media']
        text=f"{result.get('name','T50M Pro')} · {m['length_mm']} × {m['width_mm']} mm · "+(' / '.join(s['errors']) if s['errors'] else 'Beschäftigt' if s['busy'] or s['printing'] else 'Bereit')
        if s['warnings']:text+=' · '+' / '.join(s['warnings'])
        info.set(text)
    if device.info:show_info(device.info)
    def searched(found):
        devices.clear();devices.update({d['name']+' · '+d['address']:d['address'] for d in found});chooser.configure(values=list(devices))
        if found:address.set(next(iter(devices)));info.set(str(len(found))+' T50M Pro gefunden. Gerät wählen und verbinden.')
        else:info.set('Kein T50M Pro gefunden. Bluetooth, Abstand und geschlossene Handy-App prüfen; unter Linux kann die MAC-Adresse direkt eingegeben werden.')
    def connect():
        chosen=devices.get(address.get(),address.get()).strip();selected_mode=mode.get()
        def connected(result):
            show_info(result)
            from cfs_profile_sync import write_json
            try:write_json(prefs,{'address':chosen,'mode':selected_mode})
            except OSError:info.set(info.get()+' · Geräteauswahl konnte nicht gespeichert werden.')
        run('Etikettendrucker verbinden…',lambda:device.connect(chosen,selected_mode),connected)
    def disconnect():run('Etikettendrucker trennen…',device.disconnect,lambda _:info.set('Etikettendrucker getrennt.'))
    def refresh():
        def read():
            with device.lock:return device.refresh()
        run('Etikettendrucker prüfen…',read,show_info)
    for text,command in (('Suchen',lambda:run('Bluetooth-Drucker suchen…',scan,searched)),('Verbinden',connect),('Trennen',disconnect),('Status',refresh)):
        button=ttk.Button(buttons,text=text,command=command);index=len(connection_buttons);button.grid(row=index//2,column=index%2,sticky='ew',padx=(0,5),pady=3);controls.append(button);connection_buttons[text]=button
    buttons.columnconfigure(0,weight=1);buttons.columnconfigure(1,weight=1)
    ttk.Label(panel,text='Verbindung').grid(row=2,column=0,sticky='w')
    transport=ttk.Combobox(panel,textvariable=mode,values=('Automatisch','Bluetooth LE'),state='readonly',width=15);transport.grid(row=2,column=1,sticky='ew',pady=4);controls.append(transport)
    ttk.Label(panel,text='Automatisch: Linux über Classic; macOS/Windows über BLE. Nur Linux/Classic wurde am echten Gerät getestet. USB-Direktdruck ist noch nicht integriert.',style='Hint.TLabel',wraplength=430).grid(row=3,column=0,columnspan=2,sticky='w',pady=4)
    def setup():
        target=app.data_dir/'label-python-libs'
        def install():
            target.mkdir(parents=True,exist_ok=True)
            result=subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--target',str(target),'--upgrade','bleak==3.0.2'],capture_output=True,timeout=180)
            if result.returncode:raise ValueError('Bluetooth-Einrichtung fehlgeschlagen: '+(result.stderr or result.stdout).decode(errors='replace')[-1200:])
        def installed(_):
            if str(target) not in sys.path:sys.path.insert(0,str(target))
            importlib.invalidate_caches();info.set('Bluetooth-Suche eingerichtet. Jetzt „Suchen“ wählen.')
        run('Optionale Bluetooth-Suche einrichten…',install,installed)
    setup_button=ttk.Button(panel,text='Bluetooth einrichten…',command=setup);setup_button.grid(row=4,column=0,columnspan=2,sticky='w',pady=5);controls.append(setup_button)
    ttk.Label(panel,textvariable=info,style='Hint.TLabel',wraplength=430).grid(row=5,column=0,columnspan=2,sticky='w',pady=5)
    printopts=ttk.Frame(panel);printopts.grid(row=6,column=0,columnspan=2,sticky='w',pady=5)
    copies=tk.StringVar(value='1');density=tk.StringVar(value='4')
    ttk.Label(printopts,text='Kopien je Profil').pack(side='left')
    copybox=ttk.Entry(printopts,textvariable=copies,width=4);copybox.pack(side='left',padx=(6,14));controls.append(copybox)
    ttk.Label(printopts,text='Druckstärke').pack(side='left')
    densitybox=ttk.Combobox(printopts,textvariable=density,values=tuple(str(i) for i in range(1,10)),state='readonly',width=3);densitybox.pack(side='left',padx=6);controls.append(densitybox)
    def print_now():
        if app.busy or not can_print():return
        try:
            n=int(copies.get());d=int(density.get())
            if not 1<=n<=20 or not 1<=d<=9:raise ValueError()
            work=prepare()
            if work['count']*n>100:raise ValueError()
        except (ValueError,TypeError):info.set('Kopien: 1–20; Druckstärke: 1–9. Bitte mindestens ein Profil wählen.');return
        if not device.transport:info.set('Bitte zuerst den Etikettendrucker verbinden.');return
        if getattr(app,'demo',False):info.set('Demomodus: Kein physischer Etikettendruck.');return
        if not dialogs['messagebox'].askyesno('Etiketten direkt drucken',f'{work["count"]*n} Etikett(en) auf 40 × 30 mm drucken?\n\nDie Werte werden vorher nochmals aus der Profilquelle gelesen.',parent=app.root):return
        device.cancel.clear();cancel_button.configure(state='normal')
        def print_work():
            prepared=work['prepare']()
            if 'changed' in prepared:return prepared
            device.check_cancel()
            result=device.print_images(prepared['images'],copies=n,density=d,progress=app.report_progress)
            warning=''
            try:
                if work.get('remember'):work['remember']()
            except OSError:warning=' Anzeige-Einstellungen konnten nicht gemerkt werden.'
            return {'printed':result,'warning':warning}
        def printed(result):
            cancel_button.configure(state='disabled')
            if 'changed' in result:finish(result);return
            info.set(str(result['printed']['count'])+' Etikett(en): Auftrag vom Drucker beendet.'+result.get('warning',''));app.status_var.set(info.get())
        run('Profilwerte für Direktdruck prüfen…',print_work,printed)
    back_button=actions.winfo_children()[-1]
    print_button=ttk.Button(actions,text='Direkt drucken…',command=print_now);print_button.pack(side='left',padx=(0,8),before=back_button)
    cancel_button=ttk.Button(panel,text='Druck abbrechen',command=lambda:(device.cancel.set(),info.set('Abbruch angefordert; bereits gedruckte Etiketten bleiben bestehen.')),state='disabled');cancel_button.grid(row=7,column=0,columnspan=2,sticky='w',pady=4)
    def local_busy(value):
        for widget in controls+[print_button]:widget.configure(state='disabled' if value else 'normal')
        if not value:
            transport.configure(state='readonly');densitybox.configure(state='readonly');cancel_button.configure(state='disabled')
            connected=device.transport is not None and device.transport is not False
            connection_buttons['Trennen'].configure(state='normal' if connected else 'disabled');connection_buttons['Status'].configure(state='normal' if connected else 'disabled')
            print_button.configure(state='normal' if connected else 'disabled')
            if getattr(app,'demo',False):
                for widget in controls+[print_button]:widget.configure(state='disabled')
    def fit_labels(event):
        for widget in panel.winfo_children():
            if isinstance(widget,ttk.Label) and widget.cget('wraplength'):widget.configure(wraplength=max(180,event.width-28))
    panel.bind('<Configure>',fit_labels)
    local_busy(False)
    return {'panel':panel,'address':address,'mode':mode,'status':info,'copies':copies,'density':density,'print':print_button,'cancel':cancel_button,'controls':controls,'busy':local_busy}

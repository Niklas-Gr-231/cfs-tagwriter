#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Deutsche Oberfläche für den lokalen Mega/RC522-CFS-Tagwriter.

Die Gerätezugriffe laufen ausschließlich in einem Hintergrundthread. Der
Demo-Modus verwendet keine serielle Schnittstelle und schreibt keine Tags.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import queue
import re
import secrets
import sys
import threading
import time
from pathlib import Path
from cfs_versions import APP_VERSION, SERVICE_VERSION, BRIDGE_VERSION
from cfs_arduino import BOARDS


INSTALL_COMMAND = "sudo apt install python3-tk python3-serial python3-cryptography python3-pil"


def parse_weight(value):
    from cfs_codec import validate_weight
    text=str(value).strip()
    if not re.fullmatch(r'[0-9]{1,5}',text):raise ValueError('Restmenge bitte als ganze Grammzahl eingeben, zum Beispiel 825.')
    grams=int(text);validate_weight(grams)
    return grams


def parse_metres(value):
    text=str(value).strip()
    if not re.fullmatch(r'[0-9]{1,4}',text):
        raise ValueError('Restlänge bitte als ganze Meterzahl von 0 bis 9999 eingeben, zum Beispiel 280.')
    return int(text)


def weight_hint(value):
    from cfs_codec import weight_to_length,length_to_weight
    try:
        grams=parse_weight(value);code=weight_to_length(grams);stored=length_to_weight(code)
        return f'Ohne Leergewicht der Spule. Im Tag: {int(code)} m ≈ {stored} g; wenige Gramm Rundung sind möglich.'
    except ValueError as error:return str(error)


def new_serial() -> str:
    return f"{secrets.randbelow(900000):06d}"


def normal_color(value: str) -> str:
    return "#" + str(value).strip().lstrip("#").upper()


def material_title(entry: dict) -> str:
    name = str(entry.get("name", entry.get("id", ""))).strip()
    from cfs_nozzles import manufacturer_name
    brand = manufacturer_name(entry)
    return name if not brand or name.casefold().startswith(brand.casefold()) else f"{brand} · {name}"


def material_identity(entry: dict) -> tuple:
    """Slicer profiles are distinct even when they lack a registered code."""
    if entry.get("registry_managed"):
        return ("registered_profile", str(entry.get("profile_setting_id", "")))
    if entry.get("source") == "slicer":
        return ("slicer", str(entry.get("name", "")), str(entry.get("source_file", "")))
    return ("material", str(entry.get("id", "")))


def prepare_materials(materials) -> list[dict]:
    """Preserve slicer metadata and replace repeated imports of the same file."""
    unique = {}
    for entry in materials:
        if not isinstance(entry, dict):
            continue
        material_id = str(entry.get("id", "")).strip()
        is_slicer = entry.get("source") == "slicer"
        if not material_id and not is_slicer:
            continue
        source_file = str(entry.get("source_file", ""))
        name = str(entry.get("name", "")).strip() or (Path(source_file).stem if source_file else material_id)
        if not name:
            continue
        item = dict(entry)
        item.update({"id": material_id, "name": name, "brand": str(entry.get("brand", "")), "type": str(entry.get("type", ""))})
        if is_slicer:
            item["source_file"] = source_file
        unique[material_identity(item)] = item
    if not unique:
        raise ValueError("In der Auswahl wurden keine verwendbaren Profile oder Materialien gefunden.")
    return sorted(unique.values(), key=lambda item: (item["brand"].casefold(), item["name"].casefold(), item["id"], str(item.get("source_file", ""))))


def profile_initial_directory() -> Path:
    """Prefer the latest local Creality Print user-filament directory."""
    base = Path.home() / ".config" / "Creality" / "Creality Print"
    candidates = [path for path in base.glob("*/user/*/filament") if path.is_dir()]
    if candidates:
        def version_key(path):
            version = tuple(int(number) for number in re.findall(r"\d+", path.parents[2].name))
            try:
                modified = path.stat().st_mtime
                has_profiles = any(path.glob("*.json"))
            except OSError:
                modified = 0
                has_profiles = False
            return has_profiles, version, modified
        return max(candidates, key=version_key)
    return Path.home()


def profile_origin_text(entry):
    if entry.get('values_source')=='slicer':return 'Slicer – Vorrang'+(' (Cloud-ID)' if entry.get('origin')=='cloud' else ' (lokal)')
    origin=entry.get('origin')
    if origin=='local':return 'Lokal – ohne Cloud'
    if origin=='imported':return 'Cloud-Ursprung – importierter Stand'
    if entry.get('update_status')=='cached_cloud':return 'Cloud – letzter bestätigter Stand'
    if entry.get('registry_managed'):return 'Cloud – bestätigter nativer Stand'
    return 'Lokale Datei' if entry.get('source')=='slicer' else 'Standardmaterial'


def profile_sources_text(materials,status=None):
    owned=[p for p in materials if p.get('registry_managed')]
    local=sum(p.get('origin')=='local' for p in owned)
    cloud=len(owned)-local
    cached=sum(p.get('update_status')=='cached_cloud' for p in owned)
    slicer=sum(p.get('values_source')=='slicer' for p in owned)
    status=status or {}
    blocked=len(status.get('unavailable_profiles',[]))
    if not owned:return 'Profilquellen: keine verfügbaren Benutzerprofile.'+(f' {blocked} Profil(e) gesperrt; Details im Verlauf.' if blocked else ' Cloud und lokale Profile können parallel genutzt werden.')
    return f'Profilquellen dieses Druckers: {local} lokal · {cloud} mit Cloud-Ursprung'+(f' · {slicer} mit Slicer-Vorrang' if slicer else '')+(f' · davon {cached} letzter bestätigter Stand' if cached else '')+(f' · {blocked} nicht verfügbar (Verlauf)' if blocked else '')


def profile_values_text(entry: dict | None) -> str:
    if not entry or entry.get("source") not in ("slicer", "printer_cloud"):
        return "Die Bezeichnung bleibt lokal. Druckparameter werden über die Materialdatenbank des Druckers zugeordnet."
    metadata = entry.get("profile_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    values = []
    for key, label, unit in (("nozzle_temperature", "Düse", " °C"), ("flow_ratio", "Flow", ""), ("pressure_advance", "PA", "")):
        value = metadata.get(key, entry.get(key))
        if value is not None and str(value).strip():
            values.append(f"{label}: {str(value).strip()}{unit}")
    details = " · ".join(values)
    source_label = profile_origin_text(entry) if entry.get('registry_managed') else 'Profilwerte zur Anzeige'
    if entry.get('update_reason'):source_label+=' ('+entry['update_reason']+')' 
    return (f"{source_label}: {details}. " if details else source_label+". ") + "Temperatur, Flow und PA werden nicht auf den NFC-Tag geschrieben." + (' Druck läuft: Anzeige der bestätigten Druckerwerte; neue Cloudwerte folgen danach.' if entry.get('updates_deferred') else '')


class DemoBridge:
    """Bewusst getrennte, rein lokale Geräteattrappe für Oberflächentests."""

    def __init__(self, port: str):
        self.port = port
        self.profile = None

    def hello(self):
        time.sleep(0.15)
        return {"protocol": 1, "reader_version": 0x92}

    def scan(self):
        time.sleep(0.15)
        return {"uid": "11223344", "tag_type": "MIFARE_1K"}

    def read_tag(self):
        time.sleep(0.25)
        result = {
            "uid": "11223344", "tag_type": "MIFARE_1K",
            "formatted": self.profile is not None,
            "authentication": "creality" if self.profile else "default",
            "cipher_hex": "", "access_hex": "FF078069",
        }
        if self.profile:
            result["profile"] = self.profile.copy()
        return result

    def write_tag(self, expected_uid, spec, backup_dir):
        time.sleep(0.35)
        if expected_uid != "11223344":
            raise ValueError("Demo-UID stimmt nicht überein.")
        self.profile = {
            "material_id": spec.material_id, "color": spec.color,
            "weight_g": spec.weight_g, "serial": spec.serial,
            "name": spec.name,
        }
        return {
            "uid": expected_uid, "verified": True,
            "backup": "Demo: keine Datei und kein physischer Tag verändert",
        }

    def close(self):
        pass


def make_application(tk, ttk, dialogs, codec, bridge_factory, list_ports, demo=False, registry=None):
    """Create the UI with injected backend dependencies, including demo mode."""

    class WriterApp:
        def __init__(self, root):
            self.root = root
            self.demo = demo
            self.bridge = None
            self.uid = None
            from cfs_tag_feedback import TagFeedback
            self.tag_feedback = TagFeedback()
            self._tag_operation = None
            self.busy = False
            self.close_pending = False
            self.close_started = False
            self.events=queue.Queue()
            self._operation_id=0
            self._events_after=None
            self._suspend_updates=False
            self.registry = registry
            self.materials = []
            self.material_by_label = {}
            self.material_by_id = {}
            self.import_directory = profile_initial_directory()
            self.controls = []
            self.data_dir = Path(os.environ.get('CFS_APP_DATA', Path(__file__).resolve().parent))
            self.backup_dir = self.data_dir / "backups"
            self.settings_path = self.data_dir / "ui-settings.json"
            try:
                settings = json.loads(self.settings_path.read_text())
            except (OSError, ValueError):
                settings = {}
            if not isinstance(settings, dict):
                settings = {}
            self.ui_settings = dict(settings)
            self.firmware_warning = None
            self.theme_var = tk.StringVar(value="dark" if settings.get("theme") == "dark" else "light")
            saved_board = settings.get('arduino_board')
            self.board_var = tk.StringVar(value=saved_board if isinstance(saved_board, str) and saved_board in BOARDS else 'mega2560')

            try:
                self.app_icon=tk.PhotoImage(file=str(Path(__file__).with_name('cfs-tagwriter.png')))
                root.iconphoto(True,self.app_icon)
            except tk.TclError:pass
            root.title("Creality CFS Tagwriter " + APP_VERSION + (" · DEMO" if demo else ""))
            root.geometry(f"{min(1000, max(840, root.winfo_screenwidth()-80))}x{min(970, max(600, root.winfo_screenheight()-80))}")
            root.minsize(840, 600)
            root.configure(background="#F1F5F9")
            root.protocol("WM_DELETE_WINDOW", self.on_close)
            style = ttk.Style(root)
            if "clam" in style.theme_names():
                style.theme_use("clam")
            style.configure("TFrame", background="#F1F5F9")
            style.configure("TLabel", background="#F1F5F9", foreground="#0F172A")
            style.configure("Hint.TLabel", foreground="#526174")
            style.configure("Title.TLabel", font=("TkDefaultFont", 20, "bold"))
            style.configure("TLabelframe", background="#F1F5F9")
            style.configure("TLabelframe.Label", background="#F1F5F9", foreground="#0F172A")
            style.configure("TButton", padding=(10, 6))
            style.configure("Write.TButton", foreground="white", background="#0F766E", padding=(18, 10))
            style.map("Write.TButton", background=[("disabled", "#94A3B8"), ("active", "#115E59")])

            self.port_var = tk.StringVar()
            self.connection_var = tk.StringVar(value="Noch nicht verbunden. Seriellen Monitor in der Arduino IDE schließen.")
            self.tag_result_var = tk.StringVar(value="Noch kein Tag gelesen.")
            self.tag_var = tk.StringVar(value="Noch kein Tag gelesen")
            self.tag_hint_var = tk.StringVar(value="Karte oder Aufkleber auf die Antennenfläche des RC522 legen.")
            self.material_var = tk.StringVar()
            self.id_var = tk.StringVar(value="00001")
            self.name_var = tk.StringVar()
            self.color_var = tk.StringVar(value="#0088CC")
            self.weight_var=tk.StringVar(value="1000")
            self.length_var=tk.StringVar(value="330")
            self._syncing_amount=False
            self.weight_hint_var=tk.StringVar(value=weight_hint("1000"))
            from cfs_pairing import TwoTagSession
            self.pair_session=TwoTagSession()
            self.two_tags_var=tk.BooleanVar(value=False)
            self.pair_hint_var=tk.StringVar()
            self.serial_var = tk.StringVar(value=new_serial())
            self.summary_var = tk.StringVar()
            self.write_hint_var = tk.StringVar()
            self.mapping_hint_var = tk.StringVar()
            self.profile_info_var = tk.StringVar()
            self.status_var = tk.StringVar(value="Bereit. Zuerst den Arduino verbinden.")
            self.printer_hint_var = tk.StringVar(value="Mega2560 / Nano + RC522 · lokal über USB")
            self.profile_source_var=tk.StringVar(value=profile_sources_text([]))
            menubar = tk.Menu(root)
            root.configure(menu=menubar)
            if self.registry is not None and getattr(self.registry, "sync_source", "local_profiles") == "printer_cloud":
                printer = self.registry.printer
                self.printer_hint_var.set(f"USB: Mega2560 / Nano + RC522 · Drucker: {printer.get('name', 'K2 Pro')} · {printer.get('ip', '')}")
                self.printer_menu = tk.Menu(menubar, tearoff=False)
                self.printer_menu.add_command(label="Drucker auswählen…", command=self.choose_printer)
                self.printer_menu.add_command(label='Einrichtung, Dienste und Arduino…', command=self.show_setup)
                menubar.add_cascade(label="Verbindung", menu=self.printer_menu)
                self.profiles_menu = tk.Menu(menubar, tearoff=False)
                self.profiles_menu.add_command(label="Benutzerprofile exportieren…", command=self.export_printer_profiles)
                self.profiles_menu.add_command(label="Benutzerprofile importieren…", command=self.import_printer_profiles,
                                               state="disabled" if demo else "normal")
                self.profiles_menu.add_command(label="Benutzerprofile verwalten / löschen…", command=self.export_printer_profiles)
                self.profiles_menu.add_command(label='Lokale Creality-Print-Profile importieren / aktualisieren…',command=self.import_local_profiles,state='disabled' if demo else 'normal')
                menubar.add_cascade(label="Profile", menu=self.profiles_menu)
                root.configure(menu=menubar)
            help_menu = tk.Menu(menubar, tearoff=False)
            self.help_menu = help_menu
            help_menu.add_command(label='Was ist neu? · Änderungsübersicht…', command=self.show_release_notes)
            help_menu.add_command(label='Arduino-Bauanleitung und Schaltplan…', command=self.show_hardware_guide)
            help_menu.add_command(label='Beispielplatte herunterladen… (.3mf)', command=self.export_sample_plate)
            help_menu.add_command(label='SSH-Zugang am Drucker aktivieren…', command=self.show_ssh_help)
            help_menu.add_command(label='NFC-Aufkleber und erster Rollentest…',command=lambda:self.show_ssh_help(kind='tags'))
            menubar.add_cascade(label='Hilfe', menu=help_menu)
            self.settings_menu = tk.Menu(menubar,tearoff=False)
            for title, index in (('Druckersoftware und Dienstverwaltung…',0),('Arduino und IDE-Backup…',1),('Info – Funktionen und Unterstützung…',2)):
                self.settings_menu.add_command(label=title,command=lambda index=index:self.show_setup(index),state='disabled' if demo else 'normal')
            self.settings_menu.add_command(label='App aktualisieren…',command=self.show_app_updates)
            menubar.add_cascade(label='Einstellungen',menu=self.settings_menu)
            if not hasattr(self, 'printer_menu'):
                self.printer_menu = tk.Menu(menubar, tearoff=False)
                self.printer_menu.add_command(label='Drucker einrichten…', command=self.show_setup, state='disabled' if demo else 'normal')
            if not hasattr(self, 'profiles_menu'):
                self.profiles_menu = tk.Menu(menubar, tearoff=False)
                self.profiles_menu.add_command(label='Profile / Datenbank laden…', command=self.import_materials)
                for title in ('Benutzerprofile importieren…','Benutzerprofile verwalten…','Lokale Profile importieren…'):
                    self.profiles_menu.add_command(label=title,state='disabled')
            if self.registry is None:
                self.printer_menu.add_command(label='Druckerdienst nicht eingerichtet',state='disabled')
            self.printer_menu.add_command(label='Mehrere Drucker & Synchronisierung…', command=self.show_fleet)
            self.profiles_menu.add_command(label='Profile zwischen Druckern synchronisieren…', command=self.show_fleet)
            self.printer_menu.add_command(label='Anycubic-Drucker einrichten…', command=self.show_anycubic)
            help_menu.add_command(label='Drucker & NFC-Filamentwechsler…', command=self.show_compatibility)


            self.main_canvas=tk.Canvas(root,highlightthickness=0,yscrollincrement=4)
            main_scroll = ttk.Scrollbar(root, orient='vertical', command=self.main_canvas.yview)
            main_scroll.pack(side='right', fill='y')
            self.main_canvas.pack(side='left', fill='both', expand=True)
            self.main_canvas.configure(yscrollcommand=main_scroll.set)
            outer = ttk.Frame(self.main_canvas, padding=(20, 14, 20, 10))
            content_item = self.main_canvas.create_window((0,0), window=outer, anchor='nw')
            content_geometry=[None]
            def fit_content(_event=None):
                width = max(1, self.main_canvas.winfo_width())
                height = max(self.main_canvas.winfo_height(), outer.winfo_reqheight())
                if content_geometry[0]==(width,height):return
                content_geometry[0]=(width,height)
                self.main_canvas.itemconfigure(content_item,width=width,height=height)
                self.main_canvas.configure(scrollregion=(0,0,width,height))
            fit_pending=[False]
            def schedule_content_fit():
                if fit_pending[0]:return
                fit_pending[0]=True
                def finish_fit():
                    fit_pending[0]=False;fit_content()
                root.after_idle(finish_fit)
            self._schedule_content_fit=schedule_content_fit
            outer.bind('<Configure>', fit_content)
            self.main_canvas.bind('<Configure>', fit_content)
            from cfs_scroll import SmoothWheel
            main_wheel=SmoothWheel(root,self.main_canvas)
            def scroll_main(event):
                if self.main_canvas.winfo_ismapped() and event.widget.winfo_toplevel() is root and not isinstance(event.widget,(tk.Text,tk.Listbox,ttk.Combobox,ttk.Treeview,ttk.Scrollbar)):
                    main_wheel.feed(event)
            root.bind_all('<MouseWheel>', scroll_main, add='+')
            root.bind_all('<Button-4>', scroll_main, add='+'); root.bind_all('<Button-5>', scroll_main, add='+')
            outer.columnconfigure(0, weight=1)
            outer.rowconfigure(5, weight=1)

            header = ttk.Frame(outer)
            header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
            header.columnconfigure(0, weight=1)
            self.header_icon=tk.PhotoImage(file=str(Path(__file__).with_name("cfs-tagwriter-small.png")))
            ttk.Label(header,text="  CFS Tagwriter",image=self.header_icon,compound="left",style="Title.TLabel").grid(row=0,column=0,sticky="w")
            if demo:
                self.printer_hint_var.set("DEMO – keine USB-Verbindung und keine echten Schreibzugriffe")
            ttk.Label(header,textvariable=self.printer_hint_var,style="Hint.TLabel",wraplength=560).grid(row=1,column=0,columnspan=2,sticky="w",pady=(3,0))
            ttk.Label(header,textvariable=self.profile_source_var,style='Hint.TLabel',wraplength=950).grid(row=6,column=0,columnspan=4,sticky='w',pady=(5,0))
            ttk.Label(header,text=APP_VERSION,style='Badge.TLabel').grid(row=0,column=1,padx=(12,0),sticky='w')
            self.appearance_button=ttk.Button(header,text='Dunkel',command=self.toggle_appearance)
            self.appearance_button.grid(row=0,column=3,rowspan=2,sticky='e',padx=(8,0))
            if self.registry is not None and getattr(self.registry,"sync_source","")=="printer_cloud":
                first_setup = not self.registry.printer.get('ip')
                self.printer_button = ttk.Button(header, text='Einrichtung starten…' if first_setup else "Drucker auswählen…",
                                                 command=self.show_setup if first_setup else self.choose_printer)
                self.printer_button.grid(row=0,column=2,rowspan=2,sticky="e",padx=(12,0))
                self.controls.append((self.printer_button, "normal"))

            from cfs_navigation import mount
            self.navigation = mount(self, header, tk, ttk, [('Verbindung', self.printer_menu), ('Profile', self.profiles_menu), ('Hilfe', help_menu), ('Einstellungen', self.settings_menu)])
            quick=ttk.Frame(header);quick.grid(row=3,column=0,columnspan=4,sticky='ew',pady=(12,0))
            self.labels_button=ttk.Button(quick,text='Etiketten auswählen & drucken…',style='Write.TButton',command=self.show_label_home)
            self.labels_button.pack(side='left')
            self.service_button=ttk.Button(quick,text='Druckerdienst prüfen / aktualisieren…',command=self.show_setup)
            self.service_button.pack(side='left',padx=(12,0))
            self.controls.append((self.labels_button,'normal'))
            self.controls.append((self.service_button,'disabled' if demo or self.registry is None else 'normal'))
            self.nozzle_inventory_var=tk.StringVar()
            ttk.Label(header,textvariable=self.nozzle_inventory_var,style='Hint.TLabel',wraplength=850).grid(row=4,column=0,columnspan=4,sticky='w',pady=(8,0))

            sync_row=ttk.Frame(header);sync_row.grid(row=5,column=0,columnspan=4,sticky='ew',pady=(8,0))
            self.slicer_sync_button=ttk.Button(sync_row,text='Neue / geänderte Slicerprofile synchronisieren…',command=self.show_slicer_sync)
            self.slicer_sync_button.pack(side='left')
            self.controls.append((self.slicer_sync_button,'disabled' if demo or self.registry is None else 'normal'))
            self.sync_direction_var=tk.StringVar(value='Slicer → Drucker · kein Cloud-Upload')
            ttk.Label(sync_row,textvariable=self.sync_direction_var,style='Hint.TLabel').pack(side='left',padx=12)

            connection = ttk.LabelFrame(outer, text="01   Verbindung", padding=16)
            connection.grid(row=1, column=0, sticky="ew", pady=(0, 12))
            connection.columnconfigure(1, weight=1)
            ttk.Label(connection, text="USB-Port").grid(row=0, column=0, padx=(0, 10))
            self.port_combo = ttk.Combobox(connection, textvariable=self.port_var, state="readonly", width=32)
            self.port_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
            self.refresh_button = ttk.Button(connection, text="Aktualisieren", command=self.refresh_ports)
            self.refresh_button.grid(row=0, column=2, padx=(0, 8))
            self.connect_button = ttk.Button(connection, text="Verbinden", command=self.toggle_connection)
            self.connect_button.grid(row=0, column=3)
            ttk.Label(connection, textvariable=self.connection_var, style="Hint.TLabel", wraplength=810).grid(
                row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
            self.controls.extend([(self.port_combo, "readonly"), (self.refresh_button, "normal"), (self.connect_button, "normal")])

            tag = ttk.LabelFrame(outer, text="02   NFC-Tag lesen", padding=16)
            tag.grid(row=2, column=0, sticky="ew", pady=(0, 12))
            tag.columnconfigure(1, weight=1)
            self.read_button = ttk.Button(tag, text="Tag lesen", command=self.read_tag)
            self.read_button.grid(row=0, column=0, sticky="w", padx=(0, 16))
            ttk.Label(tag, textvariable=self.tag_var, font=("TkDefaultFont", 11, "bold")).grid(row=0, column=1, sticky="w")
            ttk.Label(tag, textvariable=self.tag_hint_var, style="Hint.TLabel", wraplength=810).grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

            self.tag_result_label = ttk.Label(tag, textvariable=self.tag_result_var, style='Notice.TLabel', wraplength=810)
            self.tag_result_label.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(10,0))
            pairing=ttk.Frame(tag);pairing.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(10,0))
            self.pair_check=ttk.Checkbutton(pairing,text='Zwei Tags für dieselbe Rolle',variable=self.two_tags_var,command=self.toggle_two_tags)
            self.pair_check.pack(side='left')
            self.pair_reset_button=ttk.Button(pairing,text='Zweiermodus zurücksetzen',command=self.reset_two_tags)
            self.pair_reset_button.pack(side='right')
            self.pair_hint_label=ttk.Label(tag,textvariable=self.pair_hint_var,style='Hint.TLabel',wraplength=810)
            self.pair_hint_label.grid(row=3,column=0,columnspan=2,sticky='w',pady=(6,0));self.pair_hint_label.grid_remove()
            self.controls.append((self.pair_check,'normal'))

            profile = ttk.LabelFrame(outer, text="03   Filamentprofil", padding=16)
            profile.grid(row=3, column=0, sticky="ew", pady=(0, 12))
            profile.columnconfigure(1, weight=1)
            profile.columnconfigure(3, weight=1)
            ttk.Label(profile, text="Material").grid(row=0, column=0, sticky="w", padx=(0, 8))
            self.material_combo = ttk.Combobox(profile, textvariable=self.material_var, state="readonly", width=38)
            self.material_combo.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(0, 8))
            self.material_combo.bind("<<ComboboxSelected>>", self.material_selected)
            self.import_button = ttk.Button(profile, text="Profile / Datenbank laden…", command=self.import_materials)
            if self.registry is not None and getattr(self.registry, "sync_source", "local_profiles") == "printer_cloud":
                self.import_button.configure(text="Profile aktualisieren + neue Codes")
            self.import_button.grid(row=0, column=4, columnspan=2, sticky="e")
            self.controls.extend([(self.material_combo, "readonly"), (self.import_button, "normal")])

            self.id_caption = ttk.Label(profile, text="Materialcode")
            self.id_caption.grid(row=1, column=0, sticky="w", pady=(9, 0), padx=(0, 8))
            self.id_entry = ttk.Entry(profile, textvariable=self.id_var, width=10)
            self.id_entry.grid(row=1, column=1, sticky="w", pady=(9, 0))
            ttk.Label(profile, text="Eigene Bezeichnung").grid(row=1, column=2, sticky="w", padx=(12, 8), pady=(9, 0))
            self.name_entry = ttk.Entry(profile, textvariable=self.name_var, width=28)
            self.name_entry.grid(row=1, column=3, columnspan=3, sticky="ew", pady=(9, 0))

            ttk.Label(profile, text="Farbe").grid(row=2, column=0, sticky="w", pady=(9, 0))
            self.color_entry = ttk.Entry(profile, textvariable=self.color_var, width=12)
            self.color_entry.grid(row=2, column=1, sticky="w", pady=(9, 0))
            self.color_button = ttk.Button(profile, text="Farbe wählen…", command=self.choose_color)
            self.color_button.grid(row=2, column=2, sticky="w", padx=(12, 0), pady=(9, 0))
            self.color_swatch = tk.Frame(profile, width=48, height=24, background="#0088CC", relief="solid", borderwidth=1)
            self.color_swatch.grid(row=2, column=3, sticky="w", padx=(8, 0), pady=(9, 0))
            self.color_swatch.grid_propagate(False)
            ttk.Label(profile, text="Restmenge (g)").grid(row=2, column=4, sticky="e", padx=(8, 8), pady=(9, 0))
            self.weight_combo = ttk.Combobox(profile, textvariable=self.weight_var,state="normal",values=("1000","850","800","750","600","500","250"), width=7)
            self.weight_combo.grid(row=2, column=5, sticky="e", pady=(9, 0))

            ttk.Label(profile, text="Rollennummer").grid(row=3, column=0, sticky="w", pady=(9, 0), padx=(0, 8))
            self.serial_entry = ttk.Entry(profile, textvariable=self.serial_var, width=12)
            self.serial_entry.grid(row=3, column=1, sticky="w", pady=(9, 0))
            self.new_roll_button = ttk.Button(profile, text="Neue Rolle", command=self.new_roll)
            self.new_roll_button.grid(row=3, column=2, sticky="w", padx=(12, 0), pady=(9, 0))
            ttk.Label(profile,text="Restlänge (m)").grid(row=3,column=4,sticky="e",padx=(8,8),pady=(9,0))
            self.length_entry=ttk.Entry(profile,textvariable=self.length_var,width=7)
            self.length_entry.grid(row=3,column=5,sticky="e",pady=(9,0))
            ttk.Label(profile, text="Für dieselbe Rolle die Rollennummer behalten – auch beim Hi-/Ob-Profilwechsel. „Neue Rolle“ erzeugt bewusst eine andere Nummer.", style="Hint.TLabel", wraplength=810).grid(
                row=4, column=0, columnspan=6, sticky="w", pady=(8, 0))
            ttk.Label(profile, textvariable=self.mapping_hint_var,
                      style="Hint.TLabel", wraplength=810).grid(row=6, column=0, columnspan=6, sticky="w", pady=(8, 0))
            ttk.Label(profile, textvariable=self.profile_info_var,
                      style="Hint.TLabel", wraplength=810).grid(row=7, column=0, columnspan=6, sticky="w", pady=(4, 0))
            if self.registry is not None and getattr(self.registry, "sync_source", "local_profiles") == "printer_cloud" and not demo:
                self.new_profile_button = ttk.Button(profile, text="Materialcode manuell zuweisen…", command=self.new_profile_id)
                self.new_profile_button.grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))
                ttk.Label(profile, text="Reservefunktion: ordnet einem Cloud-Profil einen fünfstelligen NFC-Materialcode zu. Neue Profile werden beim Aktualisieren automatisch zugeordnet.",
                          style="Hint.TLabel", wraplength=570).grid(row=8, column=2, columnspan=4, sticky="w", padx=(12, 0), pady=(8, 0))
                self.controls.append((self.new_profile_button, "normal"))
                self.local_profile_button=ttk.Button(profile,text='Lokale Profile importieren…',command=self.import_local_profiles)
                self.local_profile_button.grid(row=9,column=0,columnspan=2,sticky='w',pady=(8,0))
                ttk.Label(profile,text='Ohne Cloudkonto importieren und aktualisieren; benötigt Druckerdienst 2.0.0.',style='Hint.TLabel',wraplength=570).grid(row=9,column=2,columnspan=4,sticky='w',padx=(12,0),pady=(8,0))
                self.controls.append((self.local_profile_button,'normal'))
            ttk.Label(profile,textvariable=self.weight_hint_var,style="Hint.TLabel",wraplength=810).grid(row=5,column=0,columnspan=6,sticky="w",pady=(8,0))
            self.controls.extend([(self.id_entry, "normal"), (self.name_entry, "normal"), (self.color_entry, "normal"),
                                  (self.color_button, "normal"), (self.weight_combo,"normal"), (self.length_entry,"normal"),
                                  (self.serial_entry, "normal"), (self.new_roll_button, "normal")])

            # Keep the original controls and add a compact display-only filter.
            for widget in profile.winfo_children():
                info=widget.grid_info()
                if info:widget.grid_configure(row=int(info['row'])+2)
            self.search_var=tk.StringVar();self.manufacturer_filter_var=tk.StringVar(value='Alle');self.nozzle_filter_var=tk.StringVar(value='Alle')
            self.printer_brand_filter_var=tk.StringVar(value='Alle')
            self.printer_model_filter_var=tk.StringVar(value='Alle')
            self.nozzle_info_var=tk.StringVar()
            filter_frame=ttk.Frame(profile);filter_frame.grid(row=0,column=0,columnspan=6,sticky='ew',pady=(0,8));filter_frame.columnconfigure(1,weight=1)
            ttk.Label(filter_frame,text='Suche').grid(row=0,column=0,sticky='w',padx=(0,8))
            self.search_entry=ttk.Entry(filter_frame,textvariable=self.search_var,width=17);self.search_entry.grid(row=0,column=1,sticky='ew',padx=(0,12))
            ttk.Label(filter_frame,text='Hersteller').grid(row=0,column=2,padx=(0,8))
            self.manufacturer_filter=ttk.Combobox(filter_frame,textvariable=self.manufacturer_filter_var,values=('Alle',),state='readonly',width=13);self.manufacturer_filter.grid(row=0,column=3,padx=(0,12))
            ttk.Label(filter_frame,text='Düsentyp').grid(row=0,column=4,padx=(0,8))
            self.nozzle_filter=ttk.Combobox(filter_frame,textvariable=self.nozzle_filter_var,values=('Alle','High Unicorn (Hi)','Obsidian (Ob)','Nicht erfasst'),state='readonly',width=19);self.nozzle_filter.grid(row=0,column=5)
            ttk.Label(filter_frame,text='Druckerhersteller').grid(row=1,column=0,sticky='w',pady=(7,0))
            self.printer_brand_filter=ttk.Combobox(filter_frame,textvariable=self.printer_brand_filter_var,values=('Alle',),state='readonly',width=15)
            self.printer_brand_filter.grid(row=1,column=1,sticky='ew',padx=(0,12),pady=(7,0))
            ttk.Label(filter_frame,text='Druckertyp').grid(row=1,column=2,sticky='w',pady=(7,0))
            self.printer_model_filter=ttk.Combobox(filter_frame,textvariable=self.printer_model_filter_var,values=('Alle',),state='readonly',width=19)
            self.printer_model_filter.grid(row=1,column=3,columnspan=3,sticky='ew',pady=(7,0))
            self.controls.extend(((self.printer_brand_filter,'readonly'),(self.printer_model_filter,'readonly')))
            for variable in (self.printer_brand_filter_var,self.printer_model_filter_var):variable.trace_add('write',self.apply_material_filters)
            ttk.Label(profile,textvariable=self.nozzle_info_var,style='Hint.TLabel',wraplength=810).grid(row=1,column=0,columnspan=6,sticky='w',pady=(0,8))
            self.controls.extend(((self.search_entry,'normal'),(self.manufacturer_filter,'readonly'),(self.nozzle_filter,'readonly')))
            for variable in (self.search_var,self.manufacturer_filter_var,self.nozzle_filter_var):variable.trace_add('write',self.apply_material_filters)

            write = ttk.LabelFrame(outer,text="04   Schreiben und prüfen",padding=16)
            write.grid(row=4, column=0, sticky="ew", pady=(0, 12))
            write.columnconfigure(0, weight=1)
            ttk.Label(write, textvariable=self.summary_var, wraplength=610).grid(row=0, column=0, sticky="w")
            ttk.Label(write, textvariable=self.write_hint_var, style="Hint.TLabel", wraplength=610).grid(row=1, column=0, sticky="w", pady=(4, 0))
            self.write_button = ttk.Button(write, text="Tag schreiben", style="Write.TButton", command=self.write_tag)
            self.write_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
            self.label_button=ttk.Button(write,text='Etikett für dieses Filament…',command=self.label_for_selected)
            self.label_button.grid(row=2,column=1,sticky='e',pady=(10,0))

            history = ttk.Frame(outer)
            history.grid(row=5, column=0, sticky="nsew")
            history.columnconfigure(0, weight=1)
            history.rowconfigure(1, weight=1)
            ttk.Label(history, text="Verlauf", style="Hint.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 3))
            self.log_widget = tk.Text(history, height=4, wrap="word", state="disabled", background="white", foreground="#334155",
                                      font=("TkFixedFont", 9), relief="flat", padx=8, pady=6)
            self.log_widget.grid(row=1, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(history, orient="vertical", command=self.log_widget.yview)
            scrollbar.grid(row=1, column=1, sticky="ns")
            self.log_widget.configure(yscrollcommand=scrollbar.set)

            footer = ttk.Frame(outer)
            footer.grid(row=6, column=0, sticky="ew", pady=(7, 0))
            footer.columnconfigure(0, weight=1)
            ttk.Label(footer, textvariable=self.status_var, style="Hint.TLabel", wraplength=700).grid(row=0, column=0, sticky="w")
            self.progress = ttk.Progressbar(footer, mode="indeterminate", length=100)
            self.progress.grid(row=0, column=1, sticky="e", padx=(8, 0))

            for variable in (self.id_var, self.name_var, self.color_var, self.weight_var, self.serial_var):
                variable.trace_add("write", self.fields_changed)
            self.length_var.trace_add("write",self.length_changed)
            from cfs_target import TargetForm
            self.target_form = TargetForm(self, tk, ttk, dialogs, profile, write)
            initial_materials = list(codec.DEFAULT_MATERIALS)
            needs_setup=self.registry is not None and getattr(self.registry,'sync_source','')=='printer_cloud' and not self.registry.printer.get('ip')
            self.set_materials(initial_materials)
            self.refresh_ports()
            self.update_controls()
            self.log("Demo-Modus: Es werden keine echten Tags oder Sicherungsdateien geschrieben." if demo else
                     "Schreibzugriffe starten erst mit „Tag schreiben“. Vorher den Tag lesen und die Angaben prüfen.")
            if needs_setup:
                self.status_var.set('Noch kein Drucker eingerichtet. Oben auf „Einrichtung starten…“ klicken.')
                self.log('Anwendung bereit. Drucker und Arduino über „Einrichtung starten…“ einrichten.')
            self.apply_theme(persist=False)
            if not demo:
                from cfs_desktop import refresh_menu_icon
                try:
                    if refresh_menu_icon(Path(__file__).resolve().parent):self.log('Mint-Menüsymbol auf das neue Appsymbol aktualisiert.')
                except OSError:self.log('Menüsymbol konnte nicht aktualisiert werden; bei Bedarf den Mint-Menüstarter erneut installieren.')
            self._schedule_events(200)
            from cfs_update_ui import notify_after_update
            notify_after_update(self,tk,ttk)
            if self.registry is not None and not needs_setup:
                root.after(0,lambda:self.run_operation('Drucker-Firmware und Profile werden geprüft…',self.load_initial_printer,self.initial_printer_loaded))
            if not self.ui_settings.get('first_start_notice_acknowledged', False):
                root.after_idle(self.show_first_start_notice)

        def show_app_updates(self):
            from cfs_update_ui import show_updates
            return show_updates(self,tk,ttk,dialogs)

        def show_release_notes(self):
            from cfs_update_ui import show_notes
            return show_notes(self,tk,ttk)

        def load_initial_printer(self):
            result = {'firmware': None, 'firmware_error': '', 'materials': None, 'error': None}
            if not demo and self.registry.printer.get('ip'):
                from cfs_firmware_check import check_printer, FirmwareHistory
                try:
                    result['firmware'] = check_printer(self.registry, self.data_dir, self.remembered_ssh_password())
                except Exception as error:
                    result['firmware_error'] = str(error)
                    try:result['firmware'] = FirmwareHistory(self.data_dir).pending(self.registry.printer['ip'])
                    except (OSError, ValueError, AttributeError):pass
            try:result['materials'] = self.registry.materials()
            except Exception as error:result['error'] = error
            return result

        def initial_printer_loaded(self, result):
            report = result['firmware']
            if result['materials'] is not None:
                self.initial_materials_loaded(result['materials'])
            if result['firmware_error']:
                self.log('Firmwareprüfung nicht möglich: '+result['firmware_error'])
            if report and report.get('service') and report.get('ip'):
                from cfs_service_history import ServiceHistory
                try:ServiceHistory(self.data_dir).observe(report['ip'],report['service'])
                except (OSError,ValueError) as error:self.log('Dienstversion nicht gespeichert: '+str(error))
            if report:
                self.log('Drucker-Firmware: '+report['version'])
                self.status_var.set(self.status_var.get()+' · Firmware '+report['version'])
            if report and report.get('needs_repair'):
                from cfs_firmware_check import repair_message
                self.firmware_warning = report
                message = repair_message(report)
                self.status_var.set(message)
                self.log(message)
                self.root.after(0, self.open_firmware_repair)
            elif result['error'] is not None:
                self.show_error(result['error'])

        def open_firmware_repair(self):
            if self.close_pending or self.close_started:
                return
            if self.busy or self.root.grab_current() is not None:
                self.root.after(200, self.open_firmware_repair)
                return
            self.show_setup(0)

        def firmware_notice_for(self, address):
            report = self.firmware_warning
            if not report or report.get('ip') != address:
                return ''
            from cfs_firmware_check import repair_message
            return repair_message(report)

        def initial_materials_loaded(self,materials):
            self.set_materials([*codec.DEFAULT_MATERIALS,*materials])
            self.status_var.set(f'{len(materials)} Benutzerprofile geladen. Bereit.')
            self.log(f'{len(materials)} Benutzerprofile vom Drucker geladen.')

        def persist_ui_settings(self, values):
            from cfs_profile_sync import write_json
            try:
                existing = json.loads(self.settings_path.read_text())
            except (ValueError, OSError):
                existing = {}
            if not isinstance(existing, dict): existing = {}
            existing.update(values)
            write_json(self.settings_path, existing)
            self.ui_settings = existing

        def show_first_start_notice(self):
            if self.ui_settings.get('first_start_notice_acknowledged'):
                return
            from cfs_first_start import NOTICE
            window = tk.Toplevel(self.root)
            window.title('Vor der ersten Nutzung · CFS Tagwriter '+APP_VERSION)
            window.transient(self.root)
            window.geometry('900x'+str(min(710,max(550,self.root.winfo_screenheight()-100))))
            window.minsize(760,500)
            content = ttk.Frame(window, padding=18); content.pack(fill='both',expand=True)
            ttk.Label(content,text='Druckerdienst und Nutzungshinweise',font=('TkDefaultFont',15,'bold')).pack(anchor='w',pady=(0,12))
            frame=ttk.Frame(content);frame.pack(fill='both',expand=True)
            text=tk.Text(frame,wrap='word',font=('TkDefaultFont',11),relief='flat',padx=10,pady=10)
            scroll=ttk.Scrollbar(frame,orient='vertical',command=text.yview)
            scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
            text.configure(yscrollcommand=scroll.set);text.insert('1.0',NOTICE);text.configure(state='disabled')
            actions=ttk.Frame(content);actions.pack(fill='x',pady=(14,0))
            def accept():
                try:
                    self.persist_ui_settings({'first_start_notice_acknowledged':True,'first_start_notice_version':1})
                except OSError as error:
                    dialogs['messagebox'].showerror('Hinweis konnte nicht gespeichert werden',
                        'Die Bestätigung konnte nicht gespeichert werden. Bitte Schreibrechte der Benutzerablage prüfen.\n'+str(error),parent=window)
                    return
                window.destroy()
            ttk.Button(actions,text='Programm schließen',command=self.on_close).pack(side='left')
            accept_button=ttk.Button(actions,text='Verstanden und weiter',command=accept);accept_button.pack(side='right')
            self.first_start_notice_fields={'window':window,'accept':accept_button,'text':text}
            window.protocol('WM_DELETE_WINDOW',self.on_close);window.grab_set()
            self.apply_theme(persist=False)

        def apply_theme(self, persist=True):
            from cfs_theme import apply
            self.colors=apply(self.root,tk,ttk,self.theme_var.get()=='dark')
            if hasattr(self,'appearance_button'):
                self.appearance_button.configure(text='Hell' if self.theme_var.get()=='dark' else 'Dunkel')
            if persist and not demo:
                try:
                    self.persist_ui_settings({"theme": self.theme_var.get(), 'arduino_board': self.board_var.get()})
                except OSError:
                    self.log("Ansicht geändert; die Einstellung konnte nicht dauerhaft gespeichert werden.")

        def show_ssh_help(self, parent=None, kind='ssh'):
            from cfs_ssh_help import help_text
            from cfs_tag_guide import TEXT as tag_text
            parent = parent or self.root
            previous_grab = self.root.grab_current()
            window = tk.Toplevel(parent)
            window.title('NFC-Aufkleber und Rollentest' if kind=='tags' else 'SSH-Zugang am gewählten Drucker')
            window.transient(parent)
            window.geometry('850x'+str(min(640,max(450,self.root.winfo_screenheight()-100))))
            frame = ttk.Frame(window,padding=18); frame.pack(fill='both',expand=True)
            ttk.Label(frame,text='Passende NFC-Aufkleber und erster Test' if kind=='tags' else 'Root / SSH freischalten und verbinden',font=('TkDefaultFont',14,'bold')).pack(anchor='w',pady=(0,12))
            footer=ttk.Frame(frame);footer.pack(side='bottom',fill='x',pady=(12,0))
            body = ttk.Frame(frame); body.pack(fill='both',expand=True)
            text = tk.Text(body,wrap='word',relief='flat',font=('TkDefaultFont',11),padx=10,pady=10)
            scroll = ttk.Scrollbar(body,orient='vertical',command=text.yview)
            scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
            text.configure(yscrollcommand=scroll.set)
            target = self.target_form.current() if hasattr(self,'target_form') else (self.registry.printer if self.registry else {})
            setup = getattr(self,'setup_fields',{})
            if setup.get('window') is parent:
                target = {'ip':setup['ip'].get(),'model':setup['target_model']()}
            address = target.get('ip','')
            text.insert('1.0',tag_text if kind=='tags' else help_text(address, target.get('model') or target.get('printer_int_name','')))
            if kind=='tags':
                self.tag_placement_picture=tk.PhotoImage(file=str(Path(__file__).with_name('tag-position.png')))
                text.insert('1.0','\n\n')
                text.image_create('1.0',image=self.tag_placement_picture)
            text.configure(state='disabled')
            if kind=='tags':
                import webbrowser
                from cfs_tag_guide import AMAZON_URL
                ttk.Button(footer,text='Beispiel-Aufkleber auf Amazon öffnen',command=lambda:webbrowser.open(AMAZON_URL)).pack(side='left')
            def close():
                window.destroy()
                if previous_grab is not None and previous_grab.winfo_exists():
                    previous_grab.grab_set()
            close_help_button=ttk.Button(footer,text='Schließen',command=close);close_help_button.pack(side='right')
            window.protocol('WM_DELETE_WINDOW',close); window.grab_set()
            self.ssh_help_fields={'window':window,'text':text,'close':close,'close_button':close_help_button}
            self.apply_theme(persist=False)

        def remembered_ssh_password(self):
            from cfs_connections import ConnectionStore
            try:return ConnectionStore(self.data_dir).password(self.registry.printer.get('ip',''))
            except ValueError:return ''

        def show_setup(self, tab=0):
            if self.busy or demo:
                return
            existing = getattr(self, 'setup_fields', {}).get('window')
            if existing is not None and existing.winfo_exists():
                self.setup_fields['notebook'].select(tab if tab in (0, 1, 2) else 0)
                existing.lift()
                return
            window = tk.Toplevel(self.root)
            window.title('Einrichtung · App '+APP_VERSION)
            window.transient(self.root)
            window.geometry('940x'+str(min(710,max(600,self.root.winfo_screenheight()-100)))); window.minsize(820,600)
            content = ttk.Frame(window, padding=18); content.pack(fill='both', expand=True)
            content.columnconfigure(1, weight=1)
            ttk.Label(content, text=f'App {APP_VERSION} · enthaltener Dienst {SERVICE_VERSION} · Arduino-Bridge {BRIDGE_VERSION}',
                      font=('TkDefaultFont',12,'bold')).grid(row=0, column=0, columnspan=2, sticky='w')
            from cfs_printer_identity import icon_name
            self.printer_thumbnail=tk.PhotoImage(file=str(Path(__file__).with_name(icon_name((self.target_form.current().get('model') or self.target_form.current().get('printer_int_name','')) if hasattr(self,'target_form') else self.registry.printer.get('printer_int_name',''))))).subsample(2,2)
            thumbnail=ttk.Label(content,image=self.printer_thumbnail)
            thumbnail.grid(row=0,column=2,rowspan=1,sticky='e',padx=(12,0))
            notebook = ttk.Notebook(content); notebook.grid(row=1, column=0, columnspan=3, sticky='nsew', pady=14)
            content.rowconfigure(1, weight=1)
            device_tab=ttk.Frame(notebook)
            device_canvas=tk.Canvas(device_tab,highlightthickness=0,yscrollincrement=4)
            device_scroll=ttk.Scrollbar(device_tab,orient='vertical',command=device_canvas.yview)
            device_scroll.pack(side='right',fill='y');device_canvas.pack(side='left',fill='both',expand=True)
            device_canvas.configure(yscrollcommand=device_scroll.set)
            device=ttk.Frame(device_canvas,padding=14)
            device_item=device_canvas.create_window((0,0),window=device,anchor='nw')
            device_canvas.bind('<Configure>',lambda event:device_canvas.itemconfigure(device_item,width=event.width))
            device.bind('<Configure>',lambda event:device_canvas.configure(scrollregion=device_canvas.bbox('all')))
            arduino_tab=ttk.Frame(notebook)
            arduino_canvas=tk.Canvas(arduino_tab,highlightthickness=0,yscrollincrement=4)
            arduino_scroll=ttk.Scrollbar(arduino_tab,orient='vertical',command=arduino_canvas.yview)
            arduino_scroll.pack(side='right',fill='y');arduino_canvas.pack(side='left',fill='both',expand=True)
            arduino_canvas.configure(yscrollcommand=arduino_scroll.set)
            arduino=ttk.Frame(arduino_canvas,padding=14)
            arduino_item=arduino_canvas.create_window((0,0),window=arduino,anchor='nw')
            arduino_canvas.bind('<Configure>',lambda event:arduino_canvas.itemconfigure(arduino_item,width=event.width))
            arduino.bind('<Configure>',lambda event:arduino_canvas.configure(scrollregion=arduino_canvas.bbox('all')))
            from cfs_scroll import SmoothWheel
            settings_wheels=[SmoothWheel(window,device_canvas),SmoothWheel(window,arduino_canvas)]
            def scroll_settings(event):
                if isinstance(event.widget,(tk.Text,ttk.Combobox,ttk.Treeview,ttk.Scrollbar)):return
                index=notebook.index(notebook.select())
                if index in (0,1):return settings_wheels[index].feed(event)
            window.bind('<MouseWheel>',scroll_settings)
            window.bind('<Button-4>',scroll_settings);window.bind('<Button-5>',scroll_settings)
            info = ttk.Frame(notebook,padding=14)
            notebook.add(device_tab, text='Druckersoftware'); notebook.add(arduino_tab,text='Arduino Mega / Nano');notebook.add(info,text='Info')
            device.columnconfigure(1, weight=1)
            printer = self.target_form.current() if hasattr(self,'target_form') else self.registry.printer
            name_var = tk.StringVar(value=printer.get('name', 'Mein Drucker'))
            ip_var = tk.StringVar(value=printer.get('ip', ''))
            password_var = tk.StringVar()
            from cfs_connections import ConnectionStore
            connection_store=ConnectionStore(self.data_dir)
            remembered={item['ip']:item for item in self.registry.printer_choices()}
            try:remembered.update({item['ip']:item for item in connection_store.choices()})
            except ValueError as error:self.log(str(error))
            printer_labels={f"{item['name']} · {item['ip']}":item for item in remembered.values()}
            new_printer_label='Neuen Drucker eintragen…'
            remember_password_var=tk.BooleanVar(value=False)
            controls = []
            for row, label, variable in ((0, 'Drucker / Bezeichnung', name_var), (1, 'IP-Adresse', ip_var), (2, 'Root-/SSH-Passwort', password_var)):
                ttk.Label(device, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=6)
                if row == 2:
                    password_frame=ttk.Frame(device);password_frame.grid(row=row,column=1,sticky='ew',pady=6)
                    password_frame.columnconfigure(0,weight=1)
                    entry=ttk.Entry(password_frame,textvariable=variable,show='•')
                    entry.grid(row=0,column=0,sticky='ew')
                    ttk.Button(password_frame,text='SSH-Hilfe…',command=lambda:self.show_ssh_help(window)).grid(row=0,column=1,padx=(8,0))
                    remember_check=ttk.Checkbutton(password_frame,text='Passwort merken (System-Schlüsselbund)',variable=remember_password_var)
                    remember_check.grid(row=1,column=0,sticky='w',pady=(5,0));controls.append(remember_check)
                    forget_button=ttk.Button(password_frame,text='Passwort löschen',command=lambda:forget_password())
                    forget_button.grid(row=1,column=1,padx=(8,0),pady=(5,0));controls.append(forget_button)
                else:
                    if row==0:
                        entry=ttk.Combobox(device,textvariable=variable,values=[*printer_labels,new_printer_label])
                        entry.grid(row=row,column=1,sticky='ew',pady=6);printer_combo=entry
                    else:
                        ip_frame=ttk.Frame(device);ip_frame.grid(row=row,column=1,sticky='ew',pady=6)
                        entry=ttk.Entry(ip_frame,textvariable=variable);entry.pack(side='left',fill='x',expand=True)
                        name_read_button=ttk.Button(ip_frame,text='Name / Bild lesen',command=lambda:read_network_name())
                        name_read_button.pack(side='left',padx=(8,0));controls.append(name_read_button)
                controls.append(entry)
            ttk.Label(device, text='Root/SSH muss am Drucker freigeschaltet sein. Es werden unser Dienst, sein Autostart und eigene Materialeinträge eingerichtet. Die Drucker-Firmware wird nicht geflasht.',
                      style='Hint.TLabel', wraplength=810).grid(row=3, column=0, columnspan=2, sticky='w', pady=(10, 0))
            untested_var = tk.BooleanVar(value=False)
            untested = ttk.Checkbutton(device, text='Ungeprüfte Creality-CFS-Modelle nach erfolgreicher Datenprüfung zulassen', variable=untested_var)
            untested.grid(row=4, column=0, columnspan=2, sticky='w', pady=(12, 0)); controls.append(untested)
            from cfs_compatibility import model_info
            current_model = model_info(printer.get('model') or printer.get('printer_int_name',''))
            model_status_var = tk.StringVar(value='Automatisches Modell: '+current_model['manufacturer']+' '+current_model['model']+' · '+current_model['status']+'. Vor der Installation wird das native Modell erneut geprüft. Kein Anycubic-Druckerdienst verfügbar.')
            ttk.Label(device, textvariable=model_status_var,
                      style='Hint.TLabel', wraplength=810).grid(row=5, column=0, columnspan=2, sticky='w', pady=(6, 0))
            from cfs_service_history import ServiceHistory
            service_history = ServiceHistory(self.data_dir)
            def remembered_service(address):
                try:return service_history.label(address)
                except (OSError,ValueError):return 'Dieser Drucker: Dienstversion noch nicht geprüft.'
            service_version_var = tk.StringVar(value=remembered_service(ip_var.get()))
            ttk.Label(device,textvariable=service_version_var,style='Hint.TLabel',wraplength=780).grid(row=9,column=0,columnspan=2,sticky='w',pady=(0,8))
            status_var = tk.StringVar(value='Noch nicht geprüft. Zuerst SSH-Identität prüfen, dann Dienst einrichten.')
            firmware_notice_var = tk.StringVar(value=self.firmware_notice_for(ip_var.get()))
            firmware_notice = ttk.Label(device,textvariable=firmware_notice_var,style='ErrorNotice.TLabel',wraplength=780,padding=(12,10))
            firmware_notice.grid(row=6,column=0,columnspan=2,sticky='ew',pady=(14,0))
            if not firmware_notice_var.get():firmware_notice.grid_remove()
            status_label=ttk.Label(device,textvariable=status_var,style='Notice.TLabel',wraplength=780,padding=(12,10))
            status_label.grid(row=7,column=0,columnspan=2,sticky='ew',pady=(14,0))
            buttons = ttk.Frame(device); buttons.grid(row=8, column=0, columnspan=2, sticky='w', pady=14)
            state = {'identity': None, 'running': False, 'report': None,'model':printer.get('model') or printer.get('printer_int_name','')}
            service_buttons = {}

            def refresh_service_controls(report=None, *, confirmed=False):
                state['report'] = report
                if report is not None and confirmed:
                    try:
                        service_history.observe(ip_var.get().strip(),report)
                        service_version_var.set(remembered_service(ip_var.get().strip()))
                    except (ValueError,OSError) as error:self.log('Dienstversion nicht gespeichert: '+str(error))
                anycubic=str(state.get('model','')).startswith('Anycubic ')
                for key in ('scan','status'):
                    if key in service_buttons:service_buttons[key].configure(state='disabled' if anycubic else 'normal')
                if anycubic:
                    for button in service_buttons.values():button.configure(state='disabled')
                    model_status_var.set('Anycubic · experimenteller ACE-Tagmodus unter Verbindung. Kein Anycubic-Druckerdienst verfügbar.')
                    return
                known = report is not None
                installed = bool(report and report['installed'])
                running = report.get('running') if installed else None
                if 'install' in service_buttons:
                    from cfs_service_manager import install_button_text
                    service_buttons['install'].configure(text=install_button_text(report,SERVICE_VERSION),
                        state='normal' if known else 'disabled')
                    available = {'start': installed and running is False and report.get('state') != 'broken',
                                 'restart': installed and running is True,
                                 'stop': installed and running is True,
                                 'uninstall': installed}
                    for action, enabled in available.items():
                        service_buttons[action].configure(state='normal' if enabled else 'disabled')

            def address_changed(*_):
                state['identity'] = None
                state['model']=''
                password_var.set('');remember_password_var.set(False)
                refresh_service_controls()
                service_version_var.set(remembered_service(ip_var.get().strip()))
                status_var.set('Neue Adresse: Installation und SSH-Identität erneut prüfen.')
                model_status_var.set('Automatisches Modell: noch nicht bestätigt. Die Installation bestimmt das Modell aus dem nativen Katalog.')
                firmware_notice_var.set(self.firmware_notice_for(ip_var.get().strip()))
                if firmware_notice_var.get():firmware_notice.grid()
                else:firmware_notice.grid_remove()
            ip_var.trace_add('write', address_changed)

            def load_bookmark():
                address=ip_var.get().strip()
                try:
                    saved=connection_store.password(address) if address else ''
                    password_var.set(saved);remember_password_var.set(bool(saved))
                except ValueError as error:status_var.set(str(error))

            def select_bookmark(_event=None):
                item=printer_labels.get(name_var.get())
                if item is None:
                    if name_var.get()==new_printer_label:name_var.set('');ip_var.set('')
                    return
                name_var.set(item['name']);ip_var.set(item['ip']);load_bookmark()
                state['model']=item.get('model') or (printer.get('printer_int_name','') if item['ip']==printer.get('ip') else '')
                refresh_service_controls()
                self.printer_thumbnail=tk.PhotoImage(file=str(Path(__file__).with_name(icon_name(state['model'])))).subsample(2,2)
                thumbnail.configure(image=self.printer_thumbnail)
            printer_combo.bind('<<ComboboxSelected>>',select_bookmark)

            def remember_connection(result,name,address,password,remember):
                try:
                    connection_store.remember(name,address,password,remember,model=result.get('model') or state.get('model',''))
                except ValueError as error:result['_bookmark_error']=str(error)
                return result

            def read_network_name():
                from cfs_printer_identity import printer_identity,icon_name
                address=ip_var.get().strip()
                def done(result):
                    name_var.set(result['name'])
                    model=result['model'];state['model']=model
                    info=model_info(model);model_status_var.set('Gemeldetes Modell: '+info['manufacturer']+' '+info['model']+' · '+info['status']+'. Wird vor der Installation im nativen Katalog geprüft.')
                    self.printer_thumbnail=tk.PhotoImage(file=str(Path(__file__).with_name(icon_name(model)))).subsample(2,2)
                    thumbnail.configure(image=self.printer_thumbnail)
                    status_var.set('Name übernommen: '+result['name']+' · Quelle: '+result['source']+'. Lokal änderbar; der Drucker wird nicht umbenannt.')
                operate('Netzwerknamen und Druckermodell lesen…',lambda:printer_identity(address),done)

            def forget_password():
                name,address=name_var.get(),ip_var.get().strip()
                def done(_result):
                    remember_password_var.set(False);password_var.set('')
                    status_var.set('Gespeichertes Passwort gelöscht. Name und IP bleiben erhalten.')
                operate('Gespeichertes Passwort löschen…',lambda:connection_store.remember(name,address,'',False),done)

            load_bookmark()

            def close():
                if not state['running']:
                    password_var.set(''); window.destroy()

            def operate(label, function, done):
                state['running'] = True
                for control in controls: control.configure(state='disabled')
                def work():
                    try: return {'result': function()}
                    except Exception as error: return {'error': str(error)}
                def complete(reply):
                    state['running'] = False
                    for control in controls: control.configure(state='normal')
                    port_combo.configure(state='readonly')
                    board_combo.configure(state='readonly')
                    refresh_service_controls(state['report'])
                    if 'error' in reply:
                        refresh_service_controls()
                        status_var.set(reply['error']);status_label.configure(style='ErrorNotice.TLabel')
                        self.status_var.set(reply['error']);self.log(reply['error'])
                        arduino_status.set(reply['error'])
                        return
                    status_label.configure(style='Notice.TLabel')
                    done(reply['result'])
                self.run_operation(label, work, complete)

            def scan():
                from cfs_printer_setup import scan_identity
                address = ip_var.get().strip()
                def done(identity):
                    state['identity'] = identity
                    status_var.set(('Bekannte' if identity['trusted'] else 'Neue')+' SSH-Identität: '+identity['fingerprint'])
                    if not self.close_pending:
                        service('status')
                def work():
                    from cfs_printer_identity import probe_printer
                    from cfs_connection_errors import ssh_issue
                    probe_printer(address)
                    try:return scan_identity(address,Path(self.registry.path).parent/'state/known_hosts')
                    except Exception as error:raise ssh_issue(error,address,False) from error
                operate('Druckerzugang und SSH-Identität werden geprüft…',work,done)

            def identity():
                item = state['identity']
                if not item or item['address'] != ip_var.get().strip():
                    status_var.set('Zuerst die SSH-Identität dieser IP-Adresse prüfen.'); return None
                if not item['trusted'] and not dialogs['messagebox'].askyesno('Diesem Drucker vertrauen?',
                    item['address']+'\n'+item['fingerprint']+'\n\nDiesen SSH-Hostschlüssel als Geräteidentität übernehmen?', parent=window):
                    return None
                return item

            def install():
                item = identity()
                if item is None: return
                from cfs_printer_setup import setup_printer
                name, address, password, allow = name_var.get(), ip_var.get(), password_var.get(), untested_var.get()
                remember=remember_password_var.get()
                def done(result):
                    self.apply_printer_selection(result)
                    info=result.get('compatibility',model_info(result.get('model','')))
                    model_status_var.set('Automatisch eingerichtet: '+info['manufacturer']+' '+info['model']+' · '+info['status'])
                    item['trusted'] = True
                    status_var.set(f'Druckerdienst {SERVICE_VERSION} eingerichtet/aktualisiert und gestartet. {result["profile_count"]} Profile geladen.')
                    refresh_service_controls({'installed': True, 'running': True, 'state':'running', 'version': SERVICE_VERSION, 'model':result.get('model',self.registry.printer.get('printer_int_name',''))},confirmed=True)
                    if result.get('_firmware_check'):
                        if self.firmware_warning and self.firmware_warning['ip'] == address:
                            self.firmware_warning = None
                        firmware_notice_var.set('');firmware_notice.grid_remove()
                        status_var.set(status_var.get()+' · Firmware '+result['_firmware_check']['version']+' bestätigt.')
                    if result.get('_firmware_error'):
                        message='Firmwareprüfung nach Installation nicht bestätigt: '+result['_firmware_error']
                        status_var.set(status_var.get()+' · '+message);self.log(message)
                    if result.get('_bookmark_error'):status_var.set(status_var.get()+' · '+result['_bookmark_error'])
                def work():
                    result = setup_printer(self.registry,name,address,password,item,trust=True,allow_untested=allow,progress=self.report_progress)
                    from cfs_firmware_check import check_printer
                    try:result['_firmware_check'] = check_printer(self.registry,self.data_dir,password,address=address,repaired=True)
                    except Exception as error:result['_firmware_error'] = str(error)
                    return remember_connection(result,name,address,password,remember)
                operate('Kompatibilität prüfen und Druckerdienst einrichten…',
                    work,done)

            def service(action):
                item = identity()
                if item is None: return
                if action == 'uninstall' and item['address'] != self.registry.printer.get('ip'):
                    status_var.set('Zum Entfernen zuerst diesen Drucker über die Druckerauswahl verknüpfen.'); return
                if action == 'uninstall' and not dialogs['messagebox'].askyesno('Zusatzdienst entfernen?',
                    'Nur unseren Zusatzdienst samt Autostart und seinen eigenen Materialeinträgen entfernen?\n\nDie normalen Druckerdienste und Cloud-Originale bleiben erhalten. Eigene RFID-Codes werden danach nicht mehr zugeordnet. Eine Sicherung wird erstellt.', parent=window): return
                from cfs_printer_setup import trust_identity
                from cfs_service_manager import service_status, control_service, uninstall_service
                password = password_var.get()
                name,address,remember=name_var.get(),item['address'],remember_password_var.get()
                def work():
                    trust_identity(item, Path(self.registry.path).parent/'state/known_hosts')
                    if action=='status':result=service_status(self.registry,password,address)
                    elif action=='uninstall':result=uninstall_service(self.registry,password)
                    else:result=control_service(self.registry,action,password,address)
                    return remember_connection(result,name,address,password,remember)
                def done(result):
                    item['trusted'] = True
                    status_var.set(('Dienst unvollständig – neu installieren / reparieren' if result.get('state') == 'broken' else
                                    'Dienst läuft' if result['running'] else 'Dienst gestoppt' if result['installed'] else 'Dienst nicht installiert')+
                                   (' · Version '+str(result['version']) if result['version'] else '')+f' · Paketversion {SERVICE_VERSION}')
                    refresh_service_controls(result,confirmed=True)
                    if result.get('model'):
                        state['model']=result['model']
                        info=result['compatibility'];model_status_var.set('Dienstmodell: '+info['manufacturer']+' '+info['model']+' · '+info['status'])
                    if result.get('_bookmark_error'):status_var.set(status_var.get()+' · '+result['_bookmark_error'])
                    if action == 'uninstall': self.clear_tag(); self.set_materials(codec.DEFAULT_MATERIALS)
                operate('Zusatzdienst: '+action+'…', work, done)

            for index, (key, title, command) in enumerate((('scan', 'SSH-Identität / Installation prüfen', scan), ('install', 'Installieren', install),
                ('status', 'Status erneut prüfen', lambda: service('status')), ('start', 'Starten', lambda: service('start')), ('restart', 'Neu starten', lambda: service('restart')),
                ('stop', 'Stoppen', lambda: service('stop')), ('uninstall', 'Dienst entfernen', lambda: service('uninstall')))):
                button = ttk.Button(buttons, text=title, command=command)
                button.grid(row=index//3, column=index%3, sticky='ew', padx=(0, 8), pady=(0, 12)); controls.append(button)
                service_buttons[key] = button
            refresh_service_controls()
            ttk.Label(arduino, text=f'Arduino Mega2560 / Nano Classic · Bridge {BRIDGE_VERSION}', font=('TkDefaultFont', 14, 'bold')).pack(anchor='w')
            ttk.Label(arduino, text='Board und USB-Port auswählen. Das dazugehörige Programm wird automatisch verwendet. Nano gilt hier für den klassischen ATmega328P mit 5 V. Tags werden beim Upload nicht beschrieben.',
                      style='Hint.TLabel', wraplength=810).pack(anchor='w', pady=(10, 14))
            board_labels = {item['name']: key for key, item in BOARDS.items()}
            board_name = tk.StringVar(value=BOARDS[self.board_var.get()]['name'])
            board_combo = ttk.Combobox(arduino, textvariable=board_name, values=list(board_labels), state='readonly', width=58)
            board_combo.pack(anchor='w', pady=(0, 10)); controls.append(board_combo)
            def board_selected(_event=None):
                self.board_var.set(board_labels[board_name.get()])
                self.persist_ui_settings({'arduino_board':self.board_var.get()})
            board_combo.bind('<<ComboboxSelected>>', board_selected)
            guide_button = ttk.Button(arduino, text='Bauteile, Verdrahtung und Schaltplan…', command=self.show_hardware_guide)
            guide_button.pack(anchor='w', pady=(0, 12)); controls.append(guide_button)
            port_combo = ttk.Combobox(arduino, textvariable=self.port_var, values=sorted({str(p.device) for p in list_ports()}), state='readonly', width=45)
            port_combo.pack(anchor='w'); controls.append(port_combo)
            def refresh_usb():
                ports = sorted({str(p.device) for p in list_ports()})
                port_combo.configure(values=ports)
                if len(ports) == 1:
                    self.port_var.set(ports[0])
            usb_refresh = ttk.Button(arduino, text='USB-Ports aktualisieren', command=refresh_usb)
            usb_refresh.pack(anchor='w', pady=(8, 0)); controls.append(usb_refresh)
            arduino_status = tk.StringVar(value='Seriellen Monitor schließen. Bei Nano-Uploadfehlern ggf. den Eintrag mit altem Bootloader wählen.')
            ttk.Label(arduino, textvariable=arduino_status, style='Hint.TLabel', wraplength=810).pack(anchor='w', pady=14)

            def tools(upload=False):
                from cfs_arduino import prepare_tools, upload_bridge
                port = self.port_var.get()
                selected_board = self.board_var.get()
                if upload and not dialogs['messagebox'].askyesno('Arduino-Bridge aufspielen?',
                    f'Bridge {BRIDGE_VERSION} auf {BOARDS[selected_board]["name"]} an {port} spielen? Der bisherige Sketch wird ersetzt.', parent=window): return
                device_handle = self.bridge if upload else None
                if upload: self.bridge = None; self.clear_tag()
                def notify(message): self.events.put(('log', message, None))
                def work():
                    if device_handle is not None: device_handle.close()
                    if upload:return upload_bridge(port,self.data_dir,notify,board=selected_board,progress=self.report_progress)
                    prepare_tools(self.data_dir,notify,progress=self.report_progress); return {'tools_ready': True}
                def done(result):
                    arduino_status.set(f'Bridge {result["version"]} aufgespielt. Jetzt im Hauptfenster erneut verbinden.' if 'version' in result else 'Arduino-Werkzeuge sind eingerichtet.')
                operate('Arduino einrichten…', work, done)
            for title, command in (('Arduino-Werkzeuge einrichten', lambda: tools(False)), (f'Bridge {BRIDGE_VERSION} auf gewähltes Board spielen…', lambda: tools(True))):
                button = ttk.Button(arduino, text=title, command=command); button.pack(anchor='w', pady=(0, 10)); controls.append(button)
            def export_ide():
                from cfs_arduino import export_ide_sketch
                board = self.board_var.get()
                destination = dialogs['filedialog'].askdirectory(parent=window, title='Speicherort für Arduino-IDE-Backup wählen')
                if not destination: return
                folder = Path(destination)/BOARDS[board]['sketch']
                if folder.exists() and any(folder.iterdir()) and not dialogs['messagebox'].askyesno('Sketch-Export überschreiben?',
                    'Sketch und Anleitung in diesem Ordner ersetzen?\n'+str(folder), parent=window): return
                try:
                    result = export_ide_sketch(destination, board)
                except (ValueError,OSError) as error:
                    arduino_status.set(str(error)); return
                arduino_status.set('Arduino-IDE-Backup gespeichert: '+result['path'])
            ide_export_button = ttk.Button(arduino, text='Backup: Arduino-IDE-Sketch exportieren…', command=export_ide)
            ide_export_button.pack(anchor='w', pady=(0,10)); controls.append(ide_export_button)
            close_button = ttk.Button(content, text='Schließen', command=close)
            close_button.grid(row=2,column=2,sticky='e');controls.append(close_button)
            operation_frame=ttk.Frame(content);operation_frame.grid(row=2,column=0,columnspan=2,sticky='ew',padx=(0,16))
            operation_text=tk.StringVar(value='Bereit')
            ttk.Label(operation_frame,textvariable=operation_text,style='Hint.TLabel',wraplength=600).pack(anchor='w',pady=(0,5))
            operation_progress=ttk.Progressbar(operation_frame,mode='determinate',maximum=1,value=0)
            operation_progress.pack(fill='x')
            self.setup_fields = {'window': window, 'name': name_var, 'ip': ip_var, 'password': password_var,
                                 'status': status_var, 'scan': scan, 'install': install, 'service': service, 'notebook': notebook,
                                 'buttons': service_buttons, 'report': state}
            self.setup_fields.update(target_model=lambda:state.get('model',''),service_version=service_version_var,model_status=model_status_var,board=board_combo,board_name=board_name,printer=printer_combo,remember_password=remember_password_var,forget_password=forget_button,read_network_name=name_read_button,device_canvas=device_canvas,status_label=status_label,remember_check=remember_check,arduino_canvas=arduino_canvas)
            self.setup_fields['firmware_notice'] = firmware_notice_var
            self.setup_fields['ide_export']=ide_export_button
            self.setup_fields['tools']=tools
            self.setup_fields.update(progress=operation_progress,progress_text=operation_text)
            ttk.Label(info,text='Was kann CFS Tagwriter?',font=('TkDefaultFont',14,'bold')).pack(anchor='w',pady=(0,10))
            info_frame=ttk.Frame(info);info_frame.pack(fill='both',expand=True)
            info_text=tk.Text(info_frame,wrap='word',relief='flat',font=('TkDefaultFont',11),padx=10,pady=10)
            info_scroll=ttk.Scrollbar(info_frame,orient='vertical',command=info_text.yview)
            info_scroll.pack(side='right',fill='y');info_text.pack(fill='both',expand=True);info_text.configure(yscrollcommand=info_scroll.set)
            info_text.insert('1.0',
                'LIZENZ UND WEITERGABE\n'
                'Eigener Code unter PolyForm Noncommercial 1.0.0. Nichtkommerzielle Nutzung, Änderungen und Weitergabe nach den Lizenzbedingungen. Fremdkomponenten behalten ihre eigenen Rechte. Siehe LICENSE und THIRD_PARTY_NOTICES.md im Projekt.\n\n'
                'NEU IN 3.5.1\n'
                '• Eigene Auswahl für ACE Pro, ACE 2 Pro einschließlich Anschluss-/Zubehörvarianten, integrierten Kobra-X-Wechsler und unbekannte NFC-Wechsler.\n'
                '• Drucker und Wechsler werden zusammen gemerkt. Unbestätigte Ziel-Tagformate brauchen eine ausdrückliche Testfreigabe, die nicht gespeichert wird.\n\n'
                'NEU IN 3.5.0\n'
                '• Pro Drucker getrennte Daten, geteilte Rollennummern oder Profiltransfer auf denselben Druckertyp/Düsendurchmesser. Vorschau vor Übernahme, Quelle bleibt unverändert.\n'
                '• Druckerhersteller und Druckertyp als Suchfilter. Große aufklappbare Menüknöpfe, klare Tag-Ergebnisse und Wiederholen-Aktionen.\n'
                '• Experimenteller ACE-Pro-NTAG213-Modus mit optionaler Bridge 1.1.0. Kein Anycubic-Druckerdienst, kein Cloud-Kalibrierungsabgleich. Alle Anycubic-Geräte ungetestet.\n'
                '• Creality-Dienstmodell wird aus dem nativen Katalog bestimmt. K2 Pro ist Referenzgerät; andere CFS-/CFS-C-Modelle sind experimentell.\n\n'
                'TAGS UND ARDUINO\n'
                '• Aufkleberhilfe mit Beispiel-Link, Platzierung auf beiden Spulenseiten und Einlegerichtung.\n'
                '• Gespeicherte Slicerprofile synchronisieren; Slicerwerte haben Vorrang, neue Profile bekommen Materialcodes.\n'
                '• 40 × 30 mm Swatch-Etiketten als PNG oder T50M-Pro-Direktdruck per Bluetooth; Hi/Ob und Herstellersuche.\n'
                '• Cloud-Profile und unabhängige lokale Profile parallel, mit sichtbarer Herkunft und Aktualisierungsstatus.\n'
                '• MIFARE Classic 1K mit 4-Byte-UID lesen und schreiben, Farbe und freie Restmenge in ganzen Gramm oder Metern wählen.\n'
                '• Optional zwei Tags für dieselbe Rolle schreiben; Wunschwerte bleiben beim zweiten Einlesen erhalten.\n'
                '• Mega2560 oder Nano Classic ATmega328P wählen; passendes Bridge-Programm aufspielen.\n'
                '• Eigene Kabelbilder mit Breadboard, 1-kΩ-/2-kΩ-Widerständen und Zoom aufrufen; Arduino-IDE-Sketch als Backup an einen selbst gewählten Ort exportieren.\n\n'
                'PROFILE UND VERBINDUNGEN\n'
                '• Klare Meldungen bei abgelehntem Passwort, falschem Ziel, gesperrtem SSH und Zeitüberschreitung.\n'
                '• Drucker in der Einrichtung auswählen, Netzwerknamen übernehmen und Druckerskizze anzeigen.\n'
                '• Passwort auf Wunsch mit „Passwort merken“ im System-Schlüsselbund speichern und wieder löschen.\n'
                '• Bestätigte Profile vom gewählten Drucker laden und feste Materialcodes zuweisen.\n'
                '• Ein oder mehrere Profile mit Quelldruckertyp exportieren, importieren und eigene Zuordnungen entfernen.\n'
                '• Belegte fremde Codes beim Import automatisch umgehen; die Vorschau zeigt abweichende Zielcodes.\n'
                '• Druckwerte weiterhin im Slicer bearbeiten. Die App enthält keinen zweiten vollständigen Profileditor.\n'
                '• Während eines Drucks bleiben bestätigte Werte für Tags lesbar; neue Katalogänderungen warten.\n\n'
                'ZUSÄTZLICHE DRUCKERSOFTWARE\n'
                '• Für eigene automatische Creality-CFS-Profilzuordnungen ist der Zusatzdienst auf dem Drucker erforderlich.\n'
                '• Die App prüft Installation, Laufzustand und Version. Sie bietet Installieren, Reparieren, Start, Neustart, Stopp und Entfernen.\n'
                '• Beim Start wird die vollständige Drucker-Firmwareversion per SSH gelesen und je Gerät gemerkt. Bei einer Änderung öffnet sich die Dienstverwaltung zur manuellen Neuinstallation.\n'
                '• Root/SSH wird benötigt. Es werden unser Dienst, sein Autostart und eigene Materialeinträge verwaltet; Drucker- und CFS-Firmware werden nicht geflasht.\n'
                '• Der Dienst ist separat, nutzt aber native Firmware-Schnittstellen. Firmwareupdates können Anpassungen nötig machen.\n\n'
                'UNTERSTÜTZUNG\n'
                '• K2 Pro: Dienst und Materialkatalog praktisch geprüft; echter RFID-Rollentest steht noch aus.\n'
                '• Creality Hi und K2 Plus: native Referenzdaten geprüft; noch kein Gerätetest dieses Zusatzdienstes.\n'
                '• Weitere Creality-CFS-/NFC-Geräte: automatische Prüfung der nativen Daten und Dienste; ungeprüfte Modelle müssen ausdrücklich freigegeben werden.\n'
                '• Ein gemeinsames Tagformat ersetzt keine Prüfung aller Firmwareversionen und Schnittstellen. Eine pauschale Zusage für alle Creality-Drucker gibt es nicht.\n'
                '• Linux Mint geprüft. macOS und Windows sind vorgesehen und müssen praktisch getestet werden.\n\n'
                f'PAKETVERSIONEN\nApp {APP_VERSION}\nDruckerdienst {SERVICE_VERSION}\nArduino-Bridge {BRIDGE_VERSION}\n')
            info_text.configure(state='disabled')
            ttk.Button(info,text='Zur Druckersoftware / Dienstverwaltung',command=lambda:notebook.select(0)).pack(side='bottom',anchor='w',pady=(10,0),before=info_frame)
            notebook.select(tab if tab in (0,1,2) else 0)
            window.protocol('WM_DELETE_WINDOW', close); window.grab_set()
            self.apply_theme(persist=False)

        def show_fleet(self):
            if self.busy:return
            from cfs_fleet_ui import show
            show(self,tk,ttk,dialogs)

        def show_anycubic(self,printer=None):
            if self.busy:return
            from cfs_target import configure_anycubic
            if printer and printer.get('feeder_id') and printer.get('feeder_variant'):
                self.target_form.select(printer)
            else:
                configure_anycubic(self,tk,ttk,printer=printer)

        def show_compatibility(self):
            if self.busy:return
            from cfs_compatibility_ui import show
            show(self,tk,ttk)

        def tag_operation_failed(self,error):
            feedback=getattr(self,'tag_feedback',None)
            if feedback is None or feedback.phase!='busy':return False
            operation=feedback.operation
            feedback.fail(str(error))
            if operation=='read' or str(getattr(error,'code','')) in ('UID_MISMATCH','SERIAL','SERIAL_ERROR'):
                self.clear_tag()
            return True

        def shared_roll_material(self,profile):
            original=str(profile.get('material_id',''))
            if getattr(self,'demo',False) or not getattr(self,'registry',None) or not hasattr(self,'data_dir'):return original
            address=self.registry.printer.get('ip')
            if not address or not profile.get('serial'):return original
            try:
                from cfs_fleet import FleetStore
                code=FleetStore(self.data_dir).material_for_roll(address,str(profile['serial']))
                if code and code in self.material_by_id and code!=original:
                    self.log('Gemeinsame Rolle '+str(profile['serial'])+': Zielprofil '+code+' gewählt. Der Tag enthält noch '+original+'; zum Umstellen neu schreiben. Restmenge bleibt vom Tag.')
                    return code
            except (ValueError,OSError) as error:self.log('Rollenzuordnung konnte nicht gelesen werden: '+str(error))
            return original

        def remember_roll_result(self,uid,profile):
            if getattr(self,'demo',False) or not getattr(self,'registry',None) or not hasattr(self,'data_dir'):return
            address=self.registry.printer.get('ip')
            if not address or not profile.get('serial'):return
            try:
                from cfs_fleet import FleetStore
                FleetStore(self.data_dir).remember(address,'cfs',uid,str(profile['serial']),str(profile.get('material_id','')),profile.get('weight_g'),allow_reassign=True)
            except (ValueError,OSError) as error:
                self.log('Tagdaten übernommen; lokale Rollenzuordnung nicht gespeichert: '+str(error))

        def show_hardware_guide(self):
            if self.busy:
                return
            from cfs_hardware_guide import show_guide
            parent = self.root
            setup = getattr(self, 'setup_fields', {})
            if setup.get('window') is not None and setup['window'].winfo_exists():
                parent = setup['window']
            try:
                self.hardware_guide_fields = show_guide(parent, tk, ttk, board=self.board_var.get(), dark=self.theme_var.get() == 'dark')
            except Exception as error:
                self.show_error(ValueError('Bauanleitung konnte nicht geöffnet werden: '+str(error)))
                return
            window = self.hardware_guide_fields['window']
            if parent is not self.root:
                def restore_grab(event):
                    if event.widget is window:
                        try:
                            if parent.winfo_exists(): parent.grab_set()
                        except tk.TclError: pass
                window.bind('<Destroy>', restore_grab)
            self.apply_theme(persist=False)

        def log(self, message):
            stamp = time.strftime("%H:%M:%S")
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", f"{stamp}  {message}\n")
            if int(self.log_widget.index("end-1c").split(".")[0])>1200:
                self.log_widget.delete("1.0","201.0")
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")

        def refresh_ports(self):
            if self.busy:
                return
            try:
                ports = ["DEMO"] if demo else sorted({str(item.device) for item in list_ports()})
                current = self.port_var.get()
                self.port_combo.configure(values=ports)
                if current not in ports:
                    self.port_var.set("/dev/ttyACM0" if "/dev/ttyACM0" in ports else (ports[0] if ports else ""))
                if not ports and self.bridge is None:
                    self.connection_var.set("Kein USB-Port gefunden. Mega anschließen und „Aktualisieren“ klicken.")
                elif self.bridge is None:
                    self.connection_var.set("Port auswählen. Seriellen Monitor in der Arduino IDE vor dem Verbinden schließen.")
                self.update_controls()
            except Exception as error:
                self.show_error(error)

        def set_materials(self, materials):
            selected = self.material_by_label.get(self.material_var.get())
            selected_identity = material_identity(selected) if selected else None
            cleaned = prepare_materials(materials)
            self.materials = cleaned
            if hasattr(self,'profile_source_var'):
                status=getattr(self.registry,'profile_status',{}) if self.registry is not None else {}
                self.profile_source_var.set('Gespeicherter Slicer → Tag · Anycubic: kein Drucker-/Cloud-Upload.' if getattr(self,'target_form',None) and self.target_form.ace else profile_sources_text(cleaned,status))
                warning='; '.join(p['material_id']+': '+p['reason'] for p in status.get('unavailable_profiles',[]))
                if warning and warning!=getattr(self,'_source_warning',''):self.log('Nicht verfügbare Profile: '+warning)
                self._source_warning=warning
            # A declared code from profile notes is not proof of a registered
            # mapping. Only database records participate in automatic tag lookup.
            self.material_by_id = {item["id"]: item for item in cleaned
                                   if item.get("source") != "slicer" or item.get("registry_managed")}
            self.material_by_id.update({item["id"]: item for item in cleaned if item.get("registry_managed")})
            self.material_by_label = {}
            for item in cleaned:
                title = material_title(item)
                label = title if getattr(self,'target_form',None) and self.target_form.ace else f"{title} ({item['id'] or 'Code fehlt'})"
                if item.get('registry_managed'):label+=' · '+profile_origin_text(item)
                from cfs_nozzles import nozzle_code
                if nozzle_code(item):label+=' · '+nozzle_code(item)
                if label in self.material_by_label:
                    source = Path(str(item.get("source_file", ""))).name or "Materialdatenbank"
                    label = f"{label} – {source}"
                    while label in self.material_by_label:
                        label += " ·"
                self.material_by_label[label] = item
            from cfs_compatibility import material_printer
            fallback = getattr(self.registry,'printer',{}) if self.registry is not None else {}
            for item in self.material_by_label.values():
                info = material_printer(item, fallback)
                item['printer_manufacturer'], item['printer_model'] = info['manufacturer'], info['model']
            self.material_by_label = dict(sorted(self.material_by_label.items(), key=lambda pair: (pair[1]['printer_manufacturer'].casefold(), pair[1]['printer_model'].casefold(), str(pair[1].get('brand','')).casefold(), pair[0].casefold())))
            self._material_printer_fields={label:(item['printer_manufacturer'],item['printer_model']) for label,item in self.material_by_label.items()}
            if hasattr(self, 'printer_brand_filter'):
                self.printer_brand_filter.configure(values=['Alle']+sorted({item['printer_manufacturer'] for item in self.material_by_label.values()}))
                self.printer_model_filter.configure(values=['Alle']+sorted({item['printer_model'] for item in self.material_by_label.values()}))
            self._all_material_by_label=dict(self.material_by_label)
            from cfs_nozzles import search_fields
            self._material_search_fields={label:search_fields(item) for label,item in self._all_material_by_label.items()}
            if hasattr(self,'nozzle_inventory_var'):
                from cfs_nozzles import inventory_text
                self.nozzle_inventory_var.set(inventory_text(cleaned))
            self.material_combo.configure(values=list(self.material_by_label))
            current = self.id_var.get().strip()
            chosen = next((label for label, item in self.material_by_label.items() if material_identity(item) == selected_identity), None)
            if chosen is None and current:
                chosen = next((label for label, item in self.material_by_label.items() if item["id"] == current and item.get("source") != "slicer"), None)
            if chosen is None:
                chosen = next(iter(self.material_by_label))
                self.material_var.set(chosen)
                self.show_material(self.material_by_label[chosen])
            else:
                self.material_var.set(chosen)
                if not self.name_var.get().strip():
                    self.show_material(self.material_by_label[chosen])
            if hasattr(self,'manufacturer_filter'):
                from cfs_nozzles import manufacturer_name
                self.manufacturer_filter.configure(values=['Alle']+sorted({manufacturer_name(p) for p in cleaned if manufacturer_name(p)},key=str.casefold))
                self.apply_material_filters()
            self.update_controls()

        def apply_material_filters(self,*args):
            if not hasattr(self,'_all_material_by_label') or getattr(self,'_resetting_filters',False):return
            words=self.search_var.get().casefold().split();manufacturer=self.manufacturer_filter_var.get();nozzle=self.nozzle_filter_var.get()
            brand=manufacturer.casefold();wanted={'High Unicorn (Hi)':'Hi','Obsidian (Ob)':'Ob','Nicht erfasst':''}.get(nozzle,nozzle)
            filtered={label:p for label,p in self._all_material_by_label.items()
                if (manufacturer=='Alle' or self._material_search_fields[label][0]==brand)
                and (nozzle=='Alle' or self._material_search_fields[label][1]==wanted)
                and (not hasattr(self,'printer_brand_filter_var') or self.printer_brand_filter_var.get()=='Alle' or self._material_printer_fields[label][0]==self.printer_brand_filter_var.get())
                and (not hasattr(self,'printer_model_filter_var') or self.printer_model_filter_var.get()=='Alle' or self._material_printer_fields[label][1]==self.printer_model_filter_var.get())
                and all(word in self._material_search_fields[label][2] for word in words)}
            self.material_by_label=filtered;self.material_combo.configure(values=list(filtered))
            if self.material_var.get() not in filtered:
                self.material_var.set('');self.id_var.set('');self.name_var.set('')
            self.update_controls()

        def clear_material_filters(self):
            if not hasattr(self,'search_var'):return
            self._resetting_filters=True
            try:
                self.search_var.set('');self.manufacturer_filter_var.set('Alle');self.nozzle_filter_var.set('Alle')
                if hasattr(self,'printer_brand_filter_var'):
                    self.printer_brand_filter_var.set('Alle');self.printer_model_filter_var.set('Alle')
            finally:self._resetting_filters=False
            self.apply_material_filters()

        def material_selected(self,_event=None):
            if getattr(self,'target_form',None) and self.target_form.ace:
                item=self.material_by_label.get(self.material_var.get())
                if item:self.target_form.material(item)
                return
            item=self.material_by_label.get(self.material_var.get())
            if not item:return
            self.show_material(item)
            if self.registry is None or not (item.get('registry_managed') or item.get('source')=='slicer'):return
            expected=material_identity(item);snapshot=dict(item)
            def done(refreshed):
                current=self.material_by_label.get(self.material_var.get())
                if current is item and material_identity(current)==expected:
                    item.clear();item.update(refreshed)
                    from cfs_nozzles import search_fields
                    self._material_search_fields[self.material_var.get()]=search_fields(item)
                    self.show_material(item)
                    self.status_var.set('Profil aktualisiert. Bereit.')
            self.run_operation('Profilwerte werden abgeglichen…',lambda:dict(self.registry.refresh_material(snapshot)),done)

        def show_material(self,item):
            if getattr(self,'target_form',None) and self.target_form.ace:
                self.target_form.material(item);return
            self._suspend_updates=True
            try:
                
                if self.id_var.get()!=item['id']:self.id_var.set(item['id'])
                name=item['name'] if item.get('registry_managed') else material_title(item)
                if self.name_var.get()!=name:self.name_var.set(name)
                if item.get('color'):
                    color=normal_color(item['color'])
                    if re.fullmatch(r'#[0-9A-F]{6}',color) and self.color_var.get()!=color:self.color_var.set(color)
            finally:self._suspend_updates=False
            self.update_controls()

        def import_materials(self):
            if getattr(self,'target_form',None) and self.target_form.ace:
                self.target_form.load_profiles();return
            if getattr(self,'data_dir',None) and (self.data_dir/'slicer-sync-settings.json').exists():
                self.show_slicer_sync();return
            if self.registry is not None and getattr(self.registry, "sync_source", "local_profiles") == "printer_cloud":
                from cfs_auto_codes import refresh_and_assign
                def done(result):
                    if result['errors']:self.finish_progress(False)
                    self.set_materials([*codec.DEFAULT_MATERIALS,*result['materials']])
                    selected=self.material_by_label.get(self.material_var.get())
                    if selected:self.show_material(selected)
                    message=f"{len(result['materials'])} Profile geladen; {len(result['assigned'])} neue Materialcodes automatisch zugewiesen."
                    if result['pending']:message+=f" {result['pending']} Profil(e) warten auf vollständige Druckersynchronisierung."
                    if result['unassigned']:message+=f" {result['unassigned']} noch ohne Code; manuelle Zuweisung bleibt möglich."
                    if result['errors']:message+=' '+result['errors'][0]
                    self.status_var.set(message);self.log(message)
                    for row in result['assigned']:self.log(f"Neuer Materialcode {row['material_id']}: {row['name']}")
                def checked(catalog):
                    ready=any(p.get('status','unassigned')=='unassigned' for p in catalog.get('available_profiles',[]))
                    password=self.remembered_ssh_password() if ready else ''
                    if ready and not password:
                        from tkinter import simpledialog
                        password=simpledialog.askstring('Neue NFC-Materialcodes automatisch zuweisen',
                            'Neue Cloud-Profile sind am Drucker verfügbar. SSH-Passwort zum Anlegen freier Materialcodes eingeben.\nAbbrechen lädt Profile ohne neue Zuordnungen. Leer lassen bei SSH-Schlüsselanmeldung.',show='•',parent=self.root)
                        if password is None:
                            self.run_operation('Profile ohne neue Materialcodes laden…',self.registry.materials,
                                lambda rows:(self.set_materials([*codec.DEFAULT_MATERIALS,*rows]),self.status_var.set('Profile geladen. Automatische Vergabe abgebrochen; Materialcode manuell zuweisen bleibt möglich.')))
                            return
                    self.run_operation('Profile aktualisieren und freie Materialcodes vergeben…',
                        lambda:refresh_and_assign(self.registry,password,progress=self.report_progress,initial_catalog=catalog),done)
                self.run_operation('Druckerprofile und neue Cloud-Profile prüfen…',lambda:self.registry.cloud_catalog(fresh=True),checked)
                return
            paths = dialogs["filedialog"].askopenfilenames(
                parent=self.root, title="Slicer-Profile oder Materialdatenbank öffnen", initialdir=str(self.import_directory),
                filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*")])
            if not paths:
                return
            def work():
                materials, errors = [], []
                for path in paths:
                    try:
                        loaded = codec.load_materials(Path(path))
                        if self.registry is not None:
                            materials.extend(self.registry.refresh_material(item) for item in loaded)
                        else:
                            materials.extend(loaded)
                    except Exception as error:
                        errors.append(f"{Path(path).name}: {error}")
                if not materials:return {'error':"Keine Profile geladen.\n"+"\n".join(errors)}
                return {'materials':materials,'errors':errors}
            def done(reply):
                if 'error' in reply:self.show_error(ValueError(reply['error']));return
                materials,errors=reply['materials'],reply['errors']
                self.import_directory = Path(paths[0]).parent
                self.set_materials([*self.materials, *materials])
                preferred = next((entry for entry in materials if entry.get("source") == "slicer"), materials[0])
                chosen = next((label for label, entry in self.material_by_label.items() if material_identity(entry) == material_identity(preferred)), None)
                if chosen:
                    self.material_var.set(chosen)
                    self.material_selected()
                count = len({material_identity(entry) for entry in materials})
                self.log(f"{count} Profile/Materialien aus {len(paths) - len(errors)} Datei(en) geladen.")
                selected = self.material_by_label.get(self.material_var.get())
                if selected and selected.get("source") == "slicer" and not selected.get("id"):
                    self.status_var.set("Profil geladen. Für CFS fehlt noch der registrierte Materialcode.")
                elif selected and selected.get("source") == "slicer":
                    self.status_var.set("Profil geladen. Der angegebene Materialcode muss im Drucker registriert sein.")
                else:
                    self.status_var.set("Materialdatenbank geladen. Material und Farbe auswählen.")
                if errors:
                    for error in errors:
                        self.log(f"Nicht geladen: {error}")
                    dialogs["messagebox"].showwarning("Einige Dateien konnten nicht geladen werden", "\n".join(errors), parent=self.root)
            self.run_operation('Slicer-Profile und Materialdaten im Hintergrund laden…',work,done)

        def choose_printer(self):
            if self.registry is None or self.busy or self.close_pending:
                return
            existing = getattr(self, "printer_dialog", None)
            if existing is not None and existing.winfo_exists():
                existing.lift()
                return
            window = tk.Toplevel(self.root)
            self.printer_dialog = window
            window.title("Drucker auswählen und verknüpfen")
            window.transient(self.root)
            window.resizable(False, False)
            content = ttk.Frame(window, padding=20)
            content.pack(fill="both", expand=True)
            content.columnconfigure(1, weight=1)
            ttk.Label(content, text="Verbindung im Heimnetz", font=("TkDefaultFont", 14, "bold")).grid(
                row=0, column=0, columnspan=2, sticky="w")
            ttk.Label(content, text="Creality-Profile werden direkt vom gewählten Drucker geladen.\nAlle Drucker verwenden dieselbe Tagoberfläche. Anycubic hat keinen Profildienst.",
                      style="Hint.TLabel", wraplength=570).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 16))
            from cfs_connections import ConnectionStore
            choices_by_ip={item['ip']:item for item in self.registry.printer_choices()}
            try:
                for item in ConnectionStore(self.data_dir).choices():
                    choices_by_ip[item['ip']]={**choices_by_ip.get(item['ip'],{}),**item}
            except ValueError as error:self.log(str(error))
            for item in choices_by_ip.values():
                if item['ip']==self.registry.printer.get('ip') and not item.get('printer_int_name'):
                    item['printer_int_name']=self.registry.printer.get('printer_int_name','')
            choices=list(choices_by_ip.values())
            from cfs_compatibility import model_info
            labels = {}
            for item in choices:
                info=model_info(item.get('model') or item.get('printer_int_name',''))
                labels[f"{info['manufacturer']} / {info['model']} · {item['name']} · {item['ip']}"] = item
            add_label = "Weiteren Drucker hinzufügen…"
            current_ip = self.target_form.current().get("ip")
            current_label = next((label for label, item in labels.items() if item["ip"] == current_ip), "")
            selected_var = tk.StringVar(value=current_label)
            name_var = tk.StringVar()
            ip_var = tk.StringVar()
            ttk.Label(content, text="Gespeicherte Drucker").grid(row=2, column=0, sticky="w", padx=(0, 12))
            combo = ttk.Combobox(content, textvariable=selected_var, values=[*labels, add_label], state="readonly", width=44)
            combo.grid(row=2, column=1, sticky="ew")
            ttk.Label(content, text="Bezeichnung").grid(row=3, column=0, sticky="w", pady=(12, 0))
            name_entry = ttk.Entry(content, textvariable=name_var)
            name_entry.grid(row=3, column=1, sticky="ew", pady=(12, 0))
            ttk.Label(content, text="IP-Adresse").grid(row=4, column=0, sticky="w", pady=(12, 0))
            ip_entry = ttk.Entry(content, textvariable=ip_var)
            ip_entry.grid(row=4, column=1, sticky="ew", pady=(12, 0))
            ttk.Label(content, text="Weitere Creality-Drucker benötigen den eingerichteten Profildienst. Materialcodes werden je Drucker getrennt gespeichert. Anycubic verwendet dieselbe Oberfläche mit experimentellem Tagformat.",
                      style="Hint.TLabel", wraplength=570).grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))
            ttk.Label(content, text="SSH-Zugriff wird erst beim Anlegen einer neuen Profil-ID benötigt. Ein Passwort kann unter Einstellungen → Druckersoftware freiwillig im System-Schlüsselbund gemerkt werden.",
                      style="Hint.TLabel", wraplength=570).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
            result_var = tk.StringVar(value="Drucker auswählen oder eine neue IP-Adresse eintragen.")
            ttk.Label(content, textvariable=result_var, style="Hint.TLabel", wraplength=570).grid(
                row=7, column=0, columnspan=2, sticky="w", pady=(14, 0))
            actions = ttk.Frame(content)
            actions.grid(row=8, column=0, columnspan=2, sticky="e", pady=(16, 0))
            dialog_state = {"running": False}

            def selected(_event=None):
                item = labels.get(selected_var.get(), {})
                name_var.set(item.get("name", ""))
                ip_var.set(item.get("ip", ""))
                anycubic=str(item.get('model','')).startswith('Anycubic ')
                save_button.configure(text='Drucker auswählen' if anycubic else 'Verknüpfen')
                test_button.configure(text='Unterstützung anzeigen' if anycubic else 'Verbindung testen')
                result_var.set('Anycubic: selbst eingetragenes Lesezeichen, kein Druckerdienst oder Cloudprofil-Zugriff.' if anycubic else 'Noch nicht geprüft. Verknüpfen prüft die Verbindung erneut.')

            def cancel():
                if not dialog_state["running"]:
                    self.printer_dialog = None
                    window.destroy()

            def submit(save):
                if dialog_state["running"]:
                    return
                name, address = name_var.get(), ip_var.get()
                bookmark=labels.get(selected_var.get(),{})
                if str(bookmark.get('model','')).startswith('Anycubic ') and address==bookmark.get('ip'):
                    if save:
                        cancel();self.show_anycubic(printer=bookmark)
                    else:result_var.set('Experimenteller ACE-Pro-NTAG213-Modus. Kein Netzwerktest oder Profildienst für Anycubic. Modell und IP sind selbst eingetragen.')
                    return
                dialog_state["running"] = True
                for widget in (combo, name_entry, ip_entry, test_button, save_button, cancel_button):
                    widget.configure(state="disabled")
                result_var.set("Drucker und Profilzuordnungen werden geprüft…")

                def work():
                    try:
                        return {"result": self.registry.select_printer(name, address, save=save)}
                    except Exception as error:
                        return {"error": str(error)}

                def done(reply):
                    dialog_state["running"] = False
                    for widget in (name_entry, ip_entry, test_button, cancel_button):
                        widget.configure(state="normal")
                    combo.configure(state="readonly")
                    save_button.configure(state="disabled" if demo else "normal")
                    if "error" in reply:
                        result_var.set(reply["error"])
                        self.status_var.set("Druckerverbindung nicht übernommen. Vorherige Auswahl bleibt bestehen.")
                        return
                    result = reply["result"]
                    if result["saved"]:
                        self.apply_printer_selection(result)
                        cancel()
                    else:
                        info=model_info(result.get("model",""))
                        result_var.set(f"Verbindung erfolgreich: {info['manufacturer']} {info['model']} · {info['status']} · {result['profile_count']} Profile. Zum Übernehmen „Verknüpfen“ wählen.")
                        self.status_var.set("Druckerverbindung geprüft; aktive Auswahl unverändert.")

                self.run_operation("Druckerverbindung wird geprüft…", work, done)

            def add_anycubic():
                cancel();self.show_anycubic()
            ttk.Button(actions,text='Anycubic hinzufügen…',command=add_anycubic).pack(side='left',padx=(0,8))
            test_button = ttk.Button(actions, text="Verbindung testen", command=lambda: submit(False))
            test_button.pack(side="left", padx=(0, 8))
            save_button = ttk.Button(actions, text="Verknüpfen", command=lambda: submit(True), state="disabled" if demo else "normal")
            save_button.pack(side="left", padx=(0, 8))
            cancel_button = ttk.Button(actions, text="Abbrechen", command=cancel)
            cancel_button.pack(side="left")
            combo.bind("<<ComboboxSelected>>", selected)
            selected()
            # Keep handles available for accessibility and real-widget checks.
            self.printer_dialog_fields = {"selection": selected_var, "name": name_var,
                "ip": ip_var, "result": result_var, "test": test_button, "save": save_button}
            window.protocol("WM_DELETE_WINDOW", cancel)
            window.grab_set()
            combo.focus_set()

        def toggle_appearance(self):
            self.theme_var.set('light' if self.theme_var.get()=='dark' else 'dark')
            self.apply_theme()

        def show_slicer_sync(self):
            if getattr(self,'target_form',None) and self.target_form.ace:
                self.target_form.load_profiles();return
            if getattr(self,'pair_session',None) and self.pair_session.locked:
                self.status_var.set('Zuerst die Zweiergruppe abschließen oder zurücksetzen.');return
            from cfs_slicer_sync_ui import show
            return show(self,tk,ttk,dialogs,codec)

        def show_label_home(self):
            if self.busy:return
            from cfs_pages import open_page
            body,close=open_page(self,tk,ttk,'Etiketten auswählen & drucken',scroll=True)
            card=ttk.Frame(body,padding=24);card.pack(fill='both',expand=True)
            ttk.Label(card,text='Kalibrierte Filamente als 40 × 30 mm Etikett',style='Title.TLabel',wraplength=880).pack(anchor='w')
            ttk.Label(card,text='Profile suchen, Hi/Ob und Hersteller filtern, Vorschau prüfen, PNG-Bilder speichern oder direkt mit dem Katasymbol T50M Pro drucken. Die Verbindung wird in der Etikettenauswahl eingerichtet.',style='Hint.TLabel',wraplength=880).pack(anchor='w',pady=(8,20))
            ttk.Label(card,textvariable=self.nozzle_inventory_var,style='Hint.TLabel',wraplength=880).pack(anchor='w',pady=(0,16))
            actions=[]
            for title,command,hint in (
                (('Geladene Slicerprofile verwenden' if self.target_form.ace else 'Cloud-/Druckerprofile laden (bevorzugt)'),self.open_labels,'Bestätigter Profilstand des ausgewählten Druckers bzw. lokal geladene Slicerwerte. Kein Cloud-Download.'),
                ('Slicer-Profile dieses PCs laden',self.open_label_slicer_folder,'Liest die gespeicherten Benutzerprofile samt Hi/Ob. Nur Etiketten; keine NFC-Zuordnung oder Druckeränderung.'),
                ('Slicer-JSON-Dateien auswählen…',self.open_label_slicer,'Gezielt eine oder mehrere Profildateien öffnen.'),
                ('CFS-Profil-Export öffnen…',self.open_label_file,'Eine zuvor gespeicherte CFS-Exportdatei verwenden.'),
                ('Beispielplatte herunterladen… (.3mf)',self.export_sample_plate,'Vier Filamentmuster für 40 × 30 mm Etiketten. Eigene Profile im Slicer wählen; Speicherort frei wählbar. Modell: Mr.Brom / Original: 9percent · BY-NC-SA.')):
                button=ttk.Button(card,text=title,command=lambda action=command:run(action));button.pack(anchor='w',pady=(6,0));actions.append(button)
                ttk.Label(card,text=hint,style='Hint.TLabel',wraplength=880).pack(anchor='w',pady=(4,12))
            def run(action):
                if not self.busy:action()
            self.label_home_fields={'body':body,'buttons':actions,'back':self.main_page_fields['back']}
            ttk.Label(card,textvariable=self.status_var,style='Hint.TLabel',wraplength=880).pack(anchor='w',pady=10)
            self.apply_theme(persist=False)

        def export_sample_plate(self):
            if self.busy:return
            from cfs_samples import SAMPLE_NAME, export_swatch
            destination=dialogs['filedialog'].asksaveasfilename(parent=self.root,
                title='Beispielplatte als 3MF speichern',initialfile=SAMPLE_NAME,
                defaultextension='.3mf',filetypes=[('3MF-Druckplatte','*.3mf')])
            if not destination:return
            try:
                target=export_swatch(destination)
            except (OSError,ValueError) as error:
                self.show_error(error);return
            self.status_var.set('Beispielplatte gespeichert: '+str(target)+'. Im Slicer Drucker, Düse und kalibriertes Filament wählen und neu slicen.')
            self.log('Beispielplatte als 3MF exportiert. Urheber- und Lizenzangaben sind in der Datei enthalten.')

        def open_label_slicer_folder(self):
            if self.busy:return
            folder=self.import_directory
            if folder.name!='filament' or not folder.is_dir():
                folder=dialogs['filedialog'].askdirectory(parent=self.root,title='Ordner mit deinen Slicer-Benutzerprofilen wählen')
                if not folder:return
                folder=Path(folder)
            paths=sorted(folder.glob('*.json'))
            if not paths:self.show_error(ValueError('Keine Slicer-JSON-Profile in diesem Ordner.'));return
            self.open_label_slicer(paths)

        def label_for_selected(self):
            if getattr(self,'target_form',None) and self.target_form.ace:
                selected=self.material_by_label.get(self.material_var.get())
                if selected and selected.get('ace_document'):
                    from cfs_label_ui import show
                    show(self,tk,ttk,dialogs,[selected['ace_document']])
                return
            selected=self.material_by_label.get(self.material_var.get())
            if selected and selected.get('registry_managed'):self.open_labels([selected['id']])

        def open_labels(self,codes=None):
            if getattr(self,'target_form',None) and self.target_form.ace:
                from cfs_label_ui import show
                if self.target_form.documents:show(self,tk,ttk,dialogs,self.target_form.documents)
                else:self.open_label_slicer()
                return
            if self.busy or self.registry is None:return
            from cfs_labels import load_documents
            from cfs_label_ui import show
            provider=lambda:load_documents(self.registry,codes)
            def work():
                try:return {'docs':provider()}
                except Exception as error:return {'error':str(error)}
            def done(reply):
                if 'error' in reply:self.show_error(ValueError(reply['error']));return
                show(self,tk,ttk,dialogs,reply['docs'],provider)
            self.run_operation('Gespeicherte Profilwerte für Swatch-Etiketten laden…',work,done)

        def open_label_file(self):
            if self.busy:return
            source=dialogs['filedialog'].askopenfilename(parent=self.root,title='CFS-Profil-Export für Offline-Etiketten öffnen',filetypes=[('CFS-Profiltransfer','*.json')])
            if not source:return
            from cfs_profile_transfer import read_bundle
            from cfs_labels import documents_from_bundle
            from cfs_label_ui import show
            provider=lambda:documents_from_bundle(read_bundle(source),str(Path(source).resolve()))
            def work():
                try:return {'docs':provider()}
                except Exception as error:return {'error':str(error)}
            def done(reply):
                if 'error' in reply:self.show_error(ValueError(reply['error']));return
                show(self,tk,ttk,dialogs,reply['docs'],provider)
            self.run_operation('Gespeicherte Exportwerte für Etiketten laden…',work,done)

        def open_label_slicer(self,paths=None):
            if self.busy:return
            if paths is None:paths=dialogs['filedialog'].askopenfilenames(parent=self.root,title='Kalibrierte Slicer-Filamentprofile für Etiketten wählen',initialdir=str(self.import_directory),filetypes=[('Filamentprofile','*.json')])
            if not paths:return
            from cfs_labels import documents_from_slicer
            from cfs_label_ui import show
            dependency=[None]
            provider=lambda:documents_from_slicer(paths,dependency[0])
            def work():
                try:return {'docs':provider()}
                except (ValueError,OSError) as error:return {'error':str(error)}
            def done(reply):
                if 'error' in reply:
                    if 'Abhängigkeit' in reply['error']:
                        folder=dialogs['filedialog'].askdirectory(parent=self.root,title='Fehlende Vererbung: Ordner mit den Systemprofilen auswählen')
                        if folder:dependency[0]=folder;self.run_operation('Profilabhängigkeiten lesen…',work,done);return
                    self.show_error(ValueError(reply['error']));return
                show(self,tk,ttk,dialogs,reply['docs'],provider)
            self.run_operation('Gespeicherte Slicerwerte für Etiketten lesen…',work,done)

        def export_printer_profiles(self):
            if getattr(self,'target_form',None) and self.target_form.ace:
                self.show_ssh_help();return
            if self.busy or self.registry is None:
                return
            self.run_operation('Benutzerprofile werden geladen…', self.registry.materials, self.show_profile_manager)

        def show_profile_manager(self, materials):
            window = tk.Toplevel(self.root)
            window.title('Benutzerprofile auswählen, exportieren oder entfernen')
            window.transient(self.root)
            window.geometry('1000x640')
            window.minsize(820, 550)
            content = ttk.Frame(window, padding=18)
            content.pack(fill='both', expand=True)
            content.columnconfigure(0, weight=1)
            content.rowconfigure(2, weight=1)
            printer = self.registry.printer
            ttk.Label(content, text=f"Profile: {printer.get('name', 'Drucker')} · {printer['ip']}",
                      font=('TkDefaultFont', 14, 'bold')).grid(row=0, column=0, sticky='w')
            ttk.Label(content, text='Ein Profil anklicken; mehrere mit Strg oder Umschalt auswählen. Beim Export wird der Speicherort abgefragt.',
                      style='Hint.TLabel', wraplength=920).grid(row=1, column=0, sticky='w', pady=(8, 12))
            frame = ttk.Frame(content)
            frame.grid(row=2, column=0, sticky='nsew')
            frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)
            table = ttk.Treeview(frame, columns=('name', 'code', 'origin'), show='headings', selectmode='extended')
            for key, title, width in (('name', 'Benutzerprofil', 530), ('code', 'Materialcode', 110), ('origin', 'Quelle', 190)):
                table.heading(key, text=title); table.column(key, width=width, minwidth=80)
            table.grid(row=0, column=0, sticky='nsew')
            scroll = ttk.Scrollbar(frame, orient='vertical', command=table.yview)
            scroll.grid(row=0, column=1, sticky='ns'); table.configure(yscrollcommand=scroll.set)

            def fill(rows):
                table.delete(*table.get_children())
                for item in rows:
                    table.insert('', 'end', iid=item['id'], values=(item['name'], item['id'],
                        profile_origin_text(item)))
            fill(materials)
            table.selection_set(table.get_children())
            access = ttk.Frame(content); access.grid(row=3, column=0, sticky='w', pady=(12, 0))
            ttk.Label(access, text='SSH-Passwort (nur zum Entfernen)').pack(side='left', padx=(0, 10))
            password_var = tk.StringVar(value=self.remembered_ssh_password())
            password_entry = ttk.Entry(access, textvariable=password_var, show='•', width=26)
            password_entry.pack(side='left')
            result_var = tk.StringVar(value=f'{len(materials)} registrierte Benutzerprofile. Export enthält den Quelldruckertyp.')
            ttk.Label(content, textvariable=result_var, style='Hint.TLabel', wraplength=920).grid(row=4, column=0, sticky='w', pady=(10, 0))
            ttk.Label(content, text='Entfernen löscht die gewählten RFID-Zuordnungen bzw. lokalen Kopien auf diesem Drucker. Cloud-Originale bleiben erhalten; bisherige Materialcodes bleiben reserviert.',
                      style='Hint.TLabel', wraplength=920).grid(row=5, column=0, sticky='w', pady=(8, 0))
            actions = ttk.Frame(content); actions.grid(row=6, column=0, sticky='e', pady=(14, 0))
            state = {'running': False}

            def close():
                if not state['running']:
                    password_var.set(''); window.destroy()

            def start(label, work, done):
                state['running'] = True
                for widget in buttons + [password_entry]: widget.configure(state='disabled')
                def guarded():
                    try: return {'result': work()}
                    except Exception as error: return {'error': str(error)}
                def complete(reply):
                    state['running'] = False
                    for widget in buttons + [password_entry]: widget.configure(state='normal')
                    delete_button.configure(state='disabled' if demo else 'normal')
                    if 'error' in reply:
                        result_var.set(reply['error']); return
                    done(reply['result'])
                self.run_operation(label, guarded, complete)

            def selected_codes():
                codes = list(table.selection())
                if not codes: result_var.set('Bitte zuerst ein oder mehrere Profile auswählen.')
                return codes

            def export():
                codes = selected_codes()
                if not codes: return
                destination = dialogs['filedialog'].asksaveasfilename(parent=window,
                    title='Ausgewählte Benutzerprofile speichern', defaultextension='.json',
                    initialfile=f"CFS-Profile-{printer['ip']}.json", filetypes=[('CFS-Profiltransfer', '*.json')])
                if not destination: return
                from cfs_profile_transfer import export_profiles
                def done(result):
                    result_var.set(f"{result['count']} Profile gespeichert: {result['path']}")
                    self.status_var.set(f"{result['count']} Benutzerprofile exportiert.")
                start('Ausgewählte Benutzerprofile werden exportiert…', lambda: export_profiles(self.registry, destination, codes), done)

            def remove():
                if demo: return
                codes = selected_codes()
                if not codes: return
                from cfs_profile_transfer import delete_profiles
                password = password_var.get()
                def approved(preview):
                    if self.close_pending: return
                    names = '\n'.join(str(table.item(code, 'values')[0]) for code in codes)
                    if not dialogs['messagebox'].askyesno('RFID-Profile vom Drucker entfernen?',
                        f"{len(codes)} Profil(e) auf {printer['ip']} entfernen?\n\n{names}\n\nCloud-Originale bleiben erhalten. Die Tags dieser Codes werden auf diesem Drucker nicht mehr zugeordnet. Vorher wird eine wieder importierbare Sicherung erstellt.", parent=window):
                        return
                    def done(result):
                        password_var.set('')
                        self.clear_tag()
                        self.set_materials([*codec.DEFAULT_MATERIALS, *result['materials']])
                        selected = self.material_by_label.get(self.material_var.get())
                        if selected: self.show_material(selected)
                        fill(result['materials'])
                        result_var.set(f"{len(codes)} Profile entfernt. Sicherung: {result['backup_path']}")
                        self.status_var.set(f'{len(codes)} RFID-Profile entfernt; Codes bleiben reserviert.')
                    start('Gewählte RFID-Profile werden entfernt…',
                          lambda: delete_profiles(self.registry, codes, password, preview), done)
                start('Entfernung wird am Drucker geprüft…', lambda: delete_profiles(self.registry, codes, password), approved)

            all_button = ttk.Button(actions, text='Alle auswählen', command=lambda: table.selection_set(table.get_children()))
            all_button.pack(side='left', padx=(0, 8))
            export_button = ttk.Button(actions, text='Auswahl exportieren…', command=export)
            export_button.pack(side='left', padx=(0, 8))
            delete_button = ttk.Button(actions, text='Vom Drucker entfernen…', command=remove, state='disabled' if demo else 'normal')
            delete_button.pack(side='left', padx=(0, 8))
            label_button=ttk.Button(actions,text='Etiketten…',command=lambda:self.open_labels(selected_codes()) if selected_codes() else None);label_button.pack(side='left',padx=(0,8))
            close_button = ttk.Button(actions, text='Schließen', command=close); close_button.pack(side='left')
            buttons = [all_button, export_button, delete_button, label_button, close_button]
            self.profile_manager_fields = {'window': window, 'table': table, 'export': export_button,
                'delete': delete_button, 'password': password_var, 'result': result_var,'labels':label_button}
            window.protocol('WM_DELETE_WINDOW', close)
            window.grab_set()
            self.apply_theme(persist=False)

        def import_printer_profiles(self):
            if getattr(self,'target_form',None) and self.target_form.ace:
                self.show_ssh_help();return
            if demo or self.busy or self.registry is None:
                return
            source = dialogs["filedialog"].askopenfilename(parent=self.root,
                title="CFS-Benutzerprofile auf den gewählten Drucker importieren",
                filetypes=[("CFS-Profiltransfer", "*.json")])
            if not source:
                return
            from cfs_profile_transfer import read_bundle
            try:
                bundle = read_bundle(source)
            except (ValueError, OSError) as error:
                self.show_error(error)
                return
            self.show_profile_import(bundle)

        def import_local_profiles(self):
            if getattr(self,'target_form',None) and self.target_form.ace:
                self.target_form.load_profiles();return
            if demo or self.busy or self.registry is None:return
            paths=dialogs['filedialog'].askopenfilenames(parent=self.root,title='Eigene Creality-Print-Filamentprofile auswählen',
                initialdir=str(self.import_directory),filetypes=[('Creality-Print-Profile','*.json')])
            if not paths:return
            window=tk.Toplevel(self.root);window.title('Lokale Profile ohne Cloud importieren');window.transient(self.root)
            content=ttk.Frame(window,padding=20);content.pack(fill='both',expand=True);content.columnconfigure(1,weight=1)
            ttk.Label(content,text=f'{len(paths)} lokale Profil(e) · Ziel: '+self.registry.printer.get('name','Drucker'),font=('TkDefaultFont',13,'bold')).grid(row=0,column=0,columnspan=3,sticky='w')
            ttk.Label(content,text='Keine Cloud-Anmeldung nötig. Abhängigkeiten müssen vollständig vorhanden sein. Quelle und Zielcode werden vor dem Import angezeigt.',style='Hint.TLabel',wraplength=700).grid(row=1,column=0,columnspan=3,sticky='w',pady=12)
            dependencies=tk.StringVar();password=tk.StringVar(value=self.remembered_ssh_password())
            ttk.Label(content,text='Abhängigkeitsordner (optional)').grid(row=2,column=0,sticky='w',padx=(0,10))
            folder=ttk.Entry(content,textvariable=dependencies,width=35);folder.grid(row=2,column=1,sticky='ew')
            def browse():
                chosen=dialogs['filedialog'].askdirectory(parent=window,title='Ordner mit geerbten System- und Benutzerprofilen auswählen')
                if chosen:dependencies.set(chosen)
            browse_button=ttk.Button(content,text='Auswählen…',command=browse);browse_button.grid(row=2,column=2,padx=(8,0))
            ttk.Label(content,text='Root-/SSH-Passwort').grid(row=3,column=0,sticky='w',pady=12)
            secret=ttk.Entry(content,textvariable=password,show='•');secret.grid(row=3,column=1,sticky='ew',pady=12)
            message=tk.StringVar(value='JSON-Einzelprofile mit vollständiger Vererbung oder zuvor exportierte vollständige Profile verwenden. Vorhandene CFS-Transferdateien über „Benutzerprofile importieren“ öffnen.')
            ttk.Label(content,textvariable=message,style='Hint.TLabel',wraplength=700).grid(row=4,column=0,columnspan=3,sticky='w',pady=8)
            running=[False]
            def close():
                if not running[0]:password.set('');window.destroy()
            def prepare():
                if running[0]:return
                from cfs_local_profiles import prepare_local_import
                key=password.get();dependency=dependencies.get().strip() or None
                running[0]=True
                for widget in (folder,browse_button,secret,prepare_button,close_button):widget.configure(state='disabled')
                def work():
                    try:return {'bundle':prepare_local_import(self.registry,paths,key,dependency)}
                    except Exception as error:return {'error':str(error)}
                def done(reply):
                    running[0]=False
                    for widget in (folder,browse_button,secret,prepare_button,close_button):widget.configure(state='normal')
                    if 'error' in reply:message.set(reply['error']);return
                    password.set('');window.destroy();self.import_directory=Path(paths[0]).parent
                    self.show_profile_import(reply['bundle'],initial_password=key)
                self.run_operation('Lokale Vererbung, Druckermodell und Druckwerte prüfen…',work,done)
            actions=ttk.Frame(content);actions.grid(row=5,column=0,columnspan=3,sticky='e',pady=(12,0))
            prepare_button=ttk.Button(actions,text='Vorschau vorbereiten',command=prepare);prepare_button.pack(side='left',padx=(0,8))
            close_button=ttk.Button(actions,text='Schließen',command=close);close_button.pack(side='left')
            window.protocol('WM_DELETE_WINDOW',close);window.grab_set();self.apply_theme(persist=False)

        def show_profile_import(self, bundle, initial_password=None):
            window = tk.Toplevel(self.root)
            window.title("Benutzerprofile importieren – Vorschau")
            window.transient(self.root)
            window.geometry("1000x660")
            window.minsize(850, 600)
            content = ttk.Frame(window, padding=18)
            content.pack(fill="both", expand=True)
            content.columnconfigure(0, weight=1)
            content.rowconfigure(4, weight=1)
            printer = self.registry.printer
            ttk.Label(content, text=f"Ziel: {printer.get('name', 'Drucker')} · {printer['ip']}",
                      font=("TkDefaultFont", 14, "bold")).grid(row=0, column=0, sticky="w")
            ttk.Label(content, text=f"{len(bundle['profiles'])} Benutzerprofile · Modell {bundle['source']['printer_int_name']} · Düse {bundle['source']['nozzle_diameter']} mm",
                      style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
            ttk.Label(content, text="Bereits vorhandene Cloud-Profile behalten ihre aktuellen Zielwerte. Lokale Profile bleiben unabhängig lokal; Cloud-Exporte behalten ihre Herkunft als importierter Stand. Belegte Codes anderer Profile erhalten automatisch eine freie Kennung.",
                      style="Hint.TLabel", wraplength=920).grid(row=2, column=0, sticky="w", pady=(8, 0))
            access = ttk.Frame(content)
            access.grid(row=3, column=0, sticky="ew", pady=14)
            ttk.Label(access, text="SSH-Passwort des Zieldruckers").pack(side="left", padx=(0, 10))
            password_var = tk.StringVar(value=self.remembered_ssh_password() if initial_password is None else initial_password)
            password_entry = ttk.Entry(access, textvariable=password_var, show="•", width=26)
            password_entry.pack(side="left")
            ttk.Label(access, text="Bleibt nur im Speicher.", style="Hint.TLabel").pack(side="left", padx=(10, 0))
            table_frame = ttk.Frame(content)
            table_frame.grid(row=4, column=0, sticky="nsew")
            table_frame.columnconfigure(0, weight=1)
            table_frame.rowconfigure(0, weight=1)
            table = ttk.Treeview(table_frame, columns=("name", "origin", "source", "target", "action"), show="headings")
            for key, title, width in (("name", "Profil", 280), ("origin", "Herkunft", 100), ("source", "Quellcode", 100), ("target", "Zielcode", 100), ("action", "Aktion", 260)):
                table.heading(key, text=title)
                table.column(key, width=width, minwidth=60, stretch=key in ("name", "action"))
            table.grid(row=0, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            table.configure(yscrollcommand=scrollbar.set)
            result_var = tk.StringVar(value="Zuerst Vorschau laden. Dabei wird noch kein Profil importiert.")
            ttk.Label(content, textvariable=result_var, style="Hint.TLabel", wraplength=920).grid(
                row=5, column=0, sticky="w", pady=(12, 0))
            ttk.Label(content, text="Bei einem geänderten Zielcode müssen die RFID-Tags für diesen Zieldrucker neu beschrieben werden. Ein Tag kann zwei unterschiedliche Materialcodes nicht gleichzeitig enthalten.",
                      style="Hint.TLabel", wraplength=920).grid(row=6, column=0, sticky="w", pady=(8, 0))
            actions = ttk.Frame(content)
            actions.grid(row=7, column=0, sticky="e", pady=(14, 0))
            state = {"running": False, "preview": None, "applied": False}

            def cancel():
                if not state["running"]:
                    password_var.set("")
                    window.destroy()

            def submit(apply=False):
                if state["running"] or (apply and state["preview"] is None):
                    return
                from cfs_profile_transfer import transfer
                approved = state["preview"] if apply else None
                password = password_var.get()
                state["running"] = True
                for widget in (password_entry, preview_button, import_button, cancel_button):
                    widget.configure(state="disabled")
                result_var.set("Import wird ausgeführt…" if apply else "Zielbestand und freie Materialcodes werden geprüft…")

                def work():
                    try:
                        return {"result": transfer(self.registry, bundle, password, approved)}
                    except Exception as error:
                        return {"error": str(error)}

                def done(reply):
                    state["running"] = False
                    password_entry.configure(state="normal")
                    cancel_button.configure(state="normal")
                    preview_button.configure(state="normal")
                    if "error" in reply:
                        state["preview"] = None
                        import_button.configure(state="disabled")
                        result_var.set(reply["error"] + " Vorschau vor einem erneuten Versuch neu laden.")
                        self.status_var.set("Profiltransfer nicht bestätigt. Vorschau und Zielbestand prüfen.")
                        return
                    result = reply["result"]
                    table.delete(*table.get_children())
                    actions_text = {"cloud_existing": "Cloud-Profil bereits vorhanden", "cloud_linked": "Mit Ziel-Cloud verknüpfen", 'cloud_restored': 'Cloud-Zuordnung wiederherstellen',
                        "copy_created": "Lokale Kopie anlegen", "copy_updated": "Lokale Kopie aktualisieren", "copy_unchanged": "Lokale Kopie unverändert", 'copy_restored': 'Lokale Kopie wiederherstellen'}
                    for row in result["plan"]:
                        table.insert("", "end", values=(row["name"], 'Lokal' if row['identity'].startswith('local:') else 'Cloud-Ursprung', row["source_code"], row["material_id"], actions_text.get(row["action"], row["action"])))
                    changes = sum(row["retag_required"] for row in result["plan"])
                    if apply:
                        state["preview"], state["applied"] = None, True
                        password_var.set("")
                        self.clear_tag()
                        self.set_materials([*codec.DEFAULT_MATERIALS, *result["materials"]])
                        selected = self.material_by_label.get(self.material_var.get())
                        if selected:
                            self.show_material(selected)
                        message = f"Import bestätigt: {len(result['plan'])} Profile, {changes} abweichende Zielcodes."
                        result_var.set(message + (" " + result["backup_warning"] if result.get("backup_warning") else " Zuordnungsliste und Sicherung sind im state-Ordner gespeichert."))
                        self.status_var.set(message + " Tag vor dem Schreiben erneut lesen.")
                        self.log(message)
                    else:
                        state["preview"] = result
                        import_button.configure(state="normal")
                        result_var.set(f"Vorschau: {len(result['plan'])} Profile, {changes} abweichende Zielcodes. Mit „Importieren“ wird genau diese geprüfte Zuordnung übernommen.")
                        self.status_var.set("Importvorschau geladen; noch keine Profile importiert.")
                self.run_operation("Profiltransfer wird am gewählten Drucker geprüft…", work, done)

            preview_button = ttk.Button(actions, text="Vorschau laden", command=lambda: submit(False))
            preview_button.pack(side="left", padx=(0, 8))
            import_button = ttk.Button(actions, text="Importieren", state="disabled", command=lambda: submit(True))
            import_button.pack(side="left", padx=(0, 8))
            cancel_button = ttk.Button(actions, text="Schließen", command=cancel)
            cancel_button.pack(side="left")
            self.transfer_dialog_fields = {"window": window, "password": password_var, "preview": preview_button,
                "import": import_button, "result": result_var, "table": table, "state": state}
            window.protocol("WM_DELETE_WINDOW", cancel)
            window.grab_set()
            self.apply_theme(persist=False)

        def apply_printer_selection(self, result):
            if getattr(self,'target_form',None):self.target_form.select(None)
            pair=getattr(self,'pair_session',None)
            if pair is not None:pair.reset()
            self.clear_tag()
            self.set_materials([*codec.DEFAULT_MATERIALS, *result["materials"]])
            selected = self.material_by_label.get(self.material_var.get())
            if selected:
                self.show_material(selected)
            self.printer_hint_var.set(f"USB: Mega2560 / Nano + RC522 · Drucker: {result['name']} · {result['ip']}")
            if hasattr(self, 'printer_button'):
                self.printer_button.configure(text='Drucker auswählen…', command=self.choose_printer)
            self.status_var.set(f"Drucker {result['name']} verknüpft · {result['profile_count']} Profile geladen. Tag vor dem Schreiben erneut lesen.")
            self.log(f"Drucker ausgewählt: {result['name']} ({result['ip']}) · {result['profile_count']} geprüfte Profilzuordnungen.")

        def new_profile_id(self):
            if getattr(self,'target_form',None) and self.target_form.ace:
                self.show_ssh_help();return
            if demo or self.registry is None or self.busy:
                return

            def done(catalog):
                self.open_profile_id_dialog(catalog)

            self.run_operation("Neue Profile werden vom Drucker geladen…", lambda:self.registry.cloud_catalog(fresh=True), done)

        def open_profile_id_dialog(self, catalog):
            available = [p for p in catalog.get("available_profiles", []) if p.get("status", "unassigned") == "unassigned"]
            pending = len(catalog.get("available_profiles", [])) - len(available)
            if not available or catalog.get("next_material_id") is None:
                message = "Es sind keine neuen Cloud-Profile zur Vergabe verfügbar. Das neue Profil zuerst in Creality Print mit der Cloud synchronisieren und danach erneut laden."
                if pending:
                    message += f"\n\n{pending} Profil(e) sind noch nicht vollständig am Drucker synchronisiert."
                if catalog.get("next_material_id") is None:
                    message = "Es ist kein freier Materialcode im Bereich 99021–99999 mehr verfügbar."
                dialogs["messagebox"].showinfo("Neue Profil-ID", message, parent=self.root)
                return
            window = tk.Toplevel(self.root)
            window.title("NFC-Materialcode manuell zuweisen")
            window.transient(self.root)
            window.resizable(False, False)
            content = ttk.Frame(window, padding=18)
            content.grid(sticky="nsew")
            content.columnconfigure(1, weight=1)
            ttk.Label(content, text="Cloud-Profil einer fünfstelligen NFC-Kennung zuordnen", font=("TkDefaultFont", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
            ttk.Label(content, text="Cloud-Profil").grid(row=1, column=0, sticky="w", padx=(0, 12))
            labels = {}
            for item in available:
                label = f"{item['name']} · {item['type']} · {item['color']}"
                if label in labels:
                    label += " · " + item["profile_setting_id"][-6:]
                labels[label] = item
            selected_var = tk.StringVar(value=next(iter(labels)))
            combo = ttk.Combobox(content, textvariable=selected_var, values=list(labels), state="readonly", width=65)
            combo.grid(row=1, column=1, sticky="ew")
            ttk.Label(content, text="Materialcode").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(12, 0))
            code_var = tk.StringVar(value=catalog["next_material_id"])
            ttk.Entry(content, textvariable=code_var, width=10).grid(row=2, column=1, sticky="w", pady=(12, 0))
            ttk.Label(content, text="SSH-Passwort").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=(12, 0))
            password_var = tk.StringVar(value=self.remembered_ssh_password())
            ttk.Entry(content, textvariable=password_var, show="•", width=30).grid(row=3, column=1, sticky="ew", pady=(12, 0))
            ttk.Label(content, text="Passwort des Druckers; wird nur mit „Passwort merken“ in der Druckereinrichtung dauerhaft gespeichert.\nBei eingerichteter SSH-Schlüsselanmeldung kann das Feld leer bleiben.",
                      style="Hint.TLabel", wraplength=560).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
            ttk.Label(content, text="Die Zuordnung bleibt bei späteren Profiländerungen erhalten. Bestehende Codes werden nicht verändert. Ein NFC-Tag wird hier noch nicht geschrieben. Es wird der Materialcode angelegt, keine neue Cloud-Profil-ID.",
                      style="Hint.TLabel", wraplength=560).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
            error_var = tk.StringVar()
            ttk.Label(content, textvariable=error_var, foreground="#B91C1C", wraplength=560).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
            actions = ttk.Frame(content)
            actions.grid(row=7, column=0, columnspan=2, sticky="e", pady=(12, 0))

            def cancel():
                password_var.set("")
                window.destroy()

            def submit():
                from cfs_cloud_admin import validate_registration
                item = labels[selected_var.get()]
                code, password = code_var.get().strip(), password_var.get()
                try:
                    validate_registration(catalog, item["profile_setting_id"], code)
                except ValueError as error:
                    error_var.set(str(error))
                    return
                cancel()
                self.register_profile_id(item["profile_setting_id"], code, password)

            ttk.Button(actions, text="Abbrechen", command=cancel).pack(side="left", padx=(0, 8))
            ttk.Button(actions, text="Profil-ID am Drucker registrieren", command=submit).pack(side="left")
            window.protocol("WM_DELETE_WINDOW", cancel)
            window.grab_set()
            combo.focus_set()

        def register_profile_id(self, setting_id, code, password):
            if demo or self.registry is None or self.busy:
                return
            from cfs_cloud_admin import register_cloud_profile

            def done(result):
                self.set_materials([*codec.DEFAULT_MATERIALS, *result["materials"]])
                chosen = next((label for label, item in self.material_by_label.items() if item["id"] == result["material_id"] and item.get("profile_setting_id") == result["profile_setting_id"]), None)
                if chosen:
                    self.material_var.set(chosen)
                    self.show_material(self.material_by_label[chosen])
                self.status_var.set(f"Profil-ID {result['material_id']} registriert. Zum Schreiben zuerst den gewünschten Tag lesen.")
                self.log(f"Cloud-Profil „{result['name']}“ fest mit Materialcode {result['material_id']} verknüpft.")
                if result.get("backup_warning"):
                    self.log(result["backup_warning"])
                    self.status_var.set(result["backup_warning"])

            self.run_operation("Neue Profil-ID wird am Drucker registriert…", lambda:register_cloud_profile(self.registry, setting_id, code, password), done)

        def choose_color(self):
            current = normal_color(self.color_var.get())
            if len(current) != 7 or any(character not in "0123456789ABCDEF" for character in current[1:]):
                current = "#0088CC"
            _rgb, chosen = dialogs["colorchooser"].askcolor(color=current, parent=self.root, title="Filamentfarbe wählen")
            if chosen:
                self.color_var.set(chosen.upper())

        def toggle_two_tags(self):
            # The first read after enabling imports the existing roll, even if
            # another tag was already selected before switching modes.
            self.pair_session.enable(self.two_tags_var.get())
            self.update_controls()

        def reset_two_tags(self):
            self.pair_session.reset()
            self.clear_tag();self.update_controls()
            self.status_var.set('Zweiermodus zurückgesetzt. Wunschwerte prüfen und Tag 1 einlesen.')

        def new_roll(self):
            pair=getattr(self,'pair_session',None)
            if pair is not None:pair.reset(seen=bool(self.uid))
            self.serial_var.set(new_serial())
            self.status_var.set("Neue Rollennummer erstellt. Für den zweiten Aufkleber dieselbe Nummer beibehalten.")

        def make_spec(self):
            if getattr(self,'target_form',None) and self.target_form.ace:return self.target_form.spec()
            selected = self.material_by_label.get(self.material_var.get())
            if self.registry is not None and not (selected and selected.get("registry_managed")):
                if any(entry["material_id"] == self.id_var.get().strip() for entry in self.registry.entries):
                    raise ValueError("Dieser feste Code gehört zu einem Benutzerprofil. Bitte das zugehörige Benutzerprofil auswählen.")
            if selected and selected.get("registry_managed"):
                if self.id_var.get().strip() != selected["registry_material_id"]:
                    raise ValueError("Der feste Materialcode dieses Benutzerprofils darf nicht geändert werden.")
                if selected.get("registry_registration_status") != "installed":
                    raise ValueError("Die Druckereinrichtung dieses Benutzerprofils steht noch aus. Zuerst den Materialkatalog synchronisieren.")
            if selected and selected.get("source") == "slicer" and not self.id_var.get().strip():
                raise ValueError("Profil geladen. Für CFS fehlt noch der registrierte Materialcode.")
            metres=parse_metres(self.length_var.get()) if hasattr(self,'length_var') else None
            grams=parse_weight(self.weight_var.get())
            if metres is not None and int(codec.weight_to_length(grams))!=metres:
                raise ValueError('Restmenge und Restlänge passen nicht zusammen. Einen der beiden Werte erneut eingeben.')
            spec = codec.TagSpec(
                material_id=self.id_var.get().strip(), color=normal_color(self.color_var.get()),
                weight_g=grams, serial=self.serial_var.get().strip(), name=self.name_var.get().strip())
            if len(spec.name) > 100:
                raise ValueError("Die eigene Bezeichnung darf höchstens 100 Zeichen haben.")
            codec.validate_spec(spec)
            return spec

        def length_changed(self, *_args):
            if getattr(self,'_syncing_amount',False):return
            if getattr(self,'target_form',None) and self.target_form.ace:
                self.fields_changed(sync_length=False);return
            try:grams=str(codec.length_to_weight(f'{parse_metres(self.length_var.get()):04d}'))
            except ValueError:grams=''
            self._syncing_amount=True
            try:self.weight_var.set(grams)
            finally:self._syncing_amount=False
            self.fields_changed(sync_length=False)

        def fields_changed(self, *_args, sync_length=True):
            if getattr(self,'_syncing_amount',False):return
            if sync_length and hasattr(self,'length_var') and not (getattr(self,'target_form',None) and self.target_form.ace):
                try:metres=str(int(codec.weight_to_length(parse_weight(self.weight_var.get()))))
                except ValueError:metres=''
                self._syncing_amount=True
                try:
                    if self.length_var.get()!=metres:self.length_var.set(metres)
                finally:self._syncing_amount=False
            if hasattr(self,"weight_hint_var"):
                hint=weight_hint(self.weight_var.get())
                if not sync_length:
                    try:parse_metres(self.length_var.get())
                    except ValueError as error:hint=str(error)
                if self.weight_hint_var.get()!=hint:self.weight_hint_var.set(hint)
            # Variable traces are always invoked on the Tk thread.
            color = normal_color(self.color_var.get())
            if len(color) == 7 and all(character in "0123456789ABCDEF" for character in color[1:]):
                self.color_swatch.configure(background=color)
            if not getattr(self,'_suspend_updates',False):
                feedback=getattr(self,'tag_feedback',None)
                if feedback is not None:feedback.edited()
                self.update_controls()

        def update_controls(self):
            def set_value(variable,value):
                if variable.get()!=value:variable.set(value)
            def configure(widget,**values):
                if hasattr(widget,'cget'):
                    values={key:value for key,value in values.items() if str(widget.cget(key))!=str(value)}
                if values:widget.configure(**values)
            for widget, normal_state in self.controls:
                configure(widget,state="disabled" if self.busy or self.close_pending else normal_state)
            if hasattr(self, "printer_menu"):
                self.printer_menu.entryconfigure(0, state="disabled" if self.busy or self.close_pending else "normal")
                self.printer_menu.entryconfigure(1, state='disabled' if demo or self.busy or self.close_pending else 'normal')
            if hasattr(self, "profiles_menu"):
                self.profiles_menu.entryconfigure(0, state="disabled" if self.busy or self.close_pending else "normal")
                self.profiles_menu.entryconfigure(1, state="disabled" if demo or self.busy or self.close_pending else "normal")
                self.profiles_menu.entryconfigure(2, state='disabled' if self.busy or self.close_pending else 'normal')
                self.profiles_menu.entryconfigure(3,state='disabled' if demo or self.busy or self.close_pending else 'normal')
                if hasattr(self,'labels_menu'):
                    for index in range(3):self.labels_menu.entryconfigure(index,state='disabled' if self.busy or self.close_pending or index==0 and self.registry is None else 'normal')
            if hasattr(self,'settings_menu'):
                for index in range(3):
                    self.settings_menu.entryconfigure(index,state='disabled' if demo or self.busy or self.close_pending else 'normal')
                self.settings_menu.entryconfigure(3,state='disabled' if self.busy or self.close_pending else 'normal')
            connected = self.bridge is not None
            configure(self.connect_button,text="Trennen" if connected else "Verbinden")
            if not self.busy and not self.close_pending:
                configure(self.connect_button,state="normal" if connected or self.port_var.get() else "disabled")
                configure(self.port_combo,state="disabled" if connected else "readonly")
                configure(self.refresh_button,state="disabled" if connected else "normal")
            configure(self.read_button,state="normal" if connected and not self.busy and not self.close_pending else "disabled")
            if getattr(self,'target_form',None) and self.target_form.update():return
            selected = self.material_by_label.get(self.material_var.get())
            set_value(self.profile_info_var,profile_values_text(selected))
            if hasattr(self,'nozzle_info_var'):
                from cfs_nozzles import manufacturer_name,nozzle_text,nozzle_code
                set_value(self.nozzle_info_var,('Hersteller: '+(manufacturer_name(selected) or 'nicht erfasst')+' · Düsentyp: '+nozzle_text(selected)+(' ('+nozzle_code(selected)+')' if nozzle_code(selected) else '')) if selected else 'Profil auswählen. Hi = High Unicorn · Ob = Obsidian; keine automatische Zuordnung ohne Herstellerzusatz.')
            if hasattr(self,'label_button'):configure(self.label_button,state='normal' if selected and selected.get('registry_managed') and self.registry is not None and not self.busy and not self.close_pending else 'disabled')
            if selected and selected.get("registry_managed"):
                if not self.busy and not self.close_pending:
                    configure(self.id_entry,state="readonly")
                    configure(self.name_entry,state="readonly")
                    configure(self.color_entry,state="readonly")
                    configure(self.color_button,state="disabled")
                if selected.get("registry_registration_status") == "installed":
                    if selected.get("source") == "printer_cloud":
                        set_value(self.mapping_hint_var,"Feste Drucker-Profilzuordnung. Name und Farbe kommen vom gewählten Drucker; vor dem Schreiben werden die aktuellen Daten frisch abgefragt.")
                    else:
                        set_value(self.mapping_hint_var,"Feste Profilzuordnung. Katalogdatei übertragen; Erkennung mit einer echten CFS-Rolle noch prüfen. Farbe und Name kommen aus deinem gespeicherten Profil.")
                else:
                    set_value(self.mapping_hint_var,"Feste Profilzuordnung vorbereitet. Die Druckereinrichtung steht noch aus; Schreiben dieses Codes bleibt bis dahin gesperrt.")
            elif selected and selected.get("source") == "slicer":
                if not self.id_var.get().strip():
                    set_value(self.mapping_hint_var,"Profil geladen. Für CFS fehlt noch der registrierte Materialcode.")
                elif selected.get("mapping_status") == "declared" and self.id_var.get().strip() == selected.get("id"):
                    set_value(self.mapping_hint_var,"Code aus den Profilnotizen übernommen. Dieser Code muss im Drucker registriert sein.")
                else:
                    set_value(self.mapping_hint_var,"Code im Drucker registrieren, bevor du ihn verwendest.")
            else:
                set_value(self.mapping_hint_var,"Eigene Materialcodes müssen in der Drucker-Datenbank vorhanden sein. Die Bezeichnung bleibt lokal.")
            valid = False
            try:
                spec = self.make_spec()
                valid = True
                set_value(self.summary_var,
                    f"{spec.name or 'Filament'} · Code {spec.material_id} · {normal_color(spec.color)} · {spec.weight_g} g / {int(codec.weight_to_length(spec.weight_g))} m\n"
                    f"Rollennummer {spec.serial} · Ziel: {self.uid or 'noch kein Tag gelesen'}")
                if not connected:
                    set_value(self.write_hint_var,"Zum Schreiben zuerst den Arduino verbinden.")
                elif not self.uid:
                    set_value(self.write_hint_var,"Zum Schreiben zuerst den gewünschten Tag lesen.")
                else:
                    if selected and selected.get("source") == "slicer":
                        set_value(self.write_hint_var,"Code im Drucker registrieren, bevor du ihn verwendest. Beim Schreiben wird eine Sicherung angelegt.")
                    else:
                        set_value(self.write_hint_var,"„Tag schreiben“ überschreibt die Filamentdaten dieses Tags. Eine Sicherung wird angelegt.")
            except (ValueError, TypeError) as error:
                set_value(self.summary_var,"Filamentangaben ergänzen oder korrigieren.")
                set_value(self.write_hint_var,str(error))
            configure(self.write_button,state="normal" if connected and self.uid and valid and not self.busy and not self.close_pending else "disabled")
            pair=getattr(self,'pair_session',None)
            if pair is not None:
                set_value(self.pair_hint_var,pair.hint())
                if pair.enabled and self.pair_hint_label.winfo_manager()!='grid':self.pair_hint_label.grid()
                elif not pair.enabled and self.pair_hint_label.winfo_manager()=='grid':self.pair_hint_label.grid_remove()
                configure(self.pair_reset_button,state='normal' if pair.enabled and not self.busy and not self.close_pending else 'disabled')
                if pair.locked:
                    for widget in (self.material_combo,self.weight_combo,self.color_button,self.import_button):configure(widget,state='disabled')
                    if hasattr(self,'length_entry'):configure(self.length_entry,state='disabled')
                    for widget in (self.id_entry,self.name_entry,self.color_entry,self.serial_entry):configure(widget,state='readonly' if not self.busy else 'disabled')
                    if hasattr(self,'new_profile_button'):configure(self.new_profile_button,state='disabled')
                    if hasattr(self,'local_profile_button'):configure(self.local_profile_button,state='disabled')
                    if hasattr(self,'slicer_sync_button'):configure(self.slicer_sync_button,state='disabled')
                    if hasattr(self,'search_entry'):
                        for widget in (self.search_entry,self.manufacturer_filter,self.nozzle_filter):configure(widget,state='disabled')
                if pair.enabled and (self.uid and self.uid.upper() in pair.written or len(pair.written)>=2):
                    configure(self.write_button,state='disabled')
                    if len(pair.written)<2:set_value(self.pair_hint_var,pair.hint()+' Dieser Tag ist bereits geschrieben – bitte den anderen auflegen.')
            feedback=getattr(self,'tag_feedback',None)
            if feedback is not None and hasattr(self,'tag_result_var'):
                set_value(self.tag_result_var, feedback.message)
                configure(self.tag_result_label,style='ErrorNotice.TLabel' if feedback.phase=='error' else 'SuccessNotice.TLabel' if feedback.phase=='success' else 'Notice.TLabel')
                configure(self.read_button,text=feedback.caption('read'))
                configure(self.write_button,text=feedback.caption('write'))
            if hasattr(self,'_schedule_content_fit'):self._schedule_content_fit()

        def clear_tag(self):
            self.uid = None
            self.tag_var.set("Noch kein Tag gelesen")
            self.tag_hint_var.set("Karte oder Aufkleber auf die Antennenfläche des RC522 legen.")

        def report_progress(self,update):
            self.events.put(('progress',self._operation_id,update))

        def display_progress(self,update):
            from cfs_progress import describe
            self.status_var.set(describe(update))
            bars=[self.progress]
            fields=getattr(self,'setup_fields',{})
            if fields.get('window') is not None and fields['window'].winfo_exists():
                fields['progress_text'].set(describe(update));bars.append(fields['progress'])
            current,total=update.get('current'),update.get('total')
            known=isinstance(current,(int,float)) and isinstance(total,(int,float)) and total>0
            for bar in bars:
                if known:
                    bar.stop();bar.configure(mode='determinate',maximum=total,value=max(0,min(current,total)))
                elif str(bar.cget('mode'))!='indeterminate':
                    bar.configure(mode='indeterminate',maximum=100,value=0);bar.start(30)

        def finish_progress(self,success=True):
            bars=[self.progress];fields=getattr(self,'setup_fields',{})
            if fields.get('window') is not None and fields['window'].winfo_exists():
                fields['progress_text'].set('Abgeschlossen' if success else 'Fehlgeschlagen – Meldung beachten')
                bars.append(fields['progress'])
            for bar in bars:
                bar.stop();bar.configure(mode='determinate',maximum=1,value=1 if success else 0)

        def run_operation(self,label,function,on_success):
            if self.busy or self.close_started:return
            feedback=getattr(self,'tag_feedback',None)
            self._tag_operation=feedback.operation if feedback is not None and feedback.phase=='busy' else None
            navigation=getattr(self,'navigation',None)
            if navigation:navigation['close']()
            self.busy=True;self._operation_id+=1
            self.display_progress({'phase':label})
            self.update_controls()
            def worker():
                try:result=function()
                except Exception as error:self.events.put(('error',error,None))
                else:self.events.put(('success',on_success,result))
            threading.Thread(target=worker,daemon=True,name='cfs-device-operation').start()
            self._schedule_events(0)

        def _schedule_events(self,delay):
            if self._events_after is not None:self.root.after_cancel(self._events_after)
            self._events_after=self.root.after(delay,self.drain_events)

        def drain_events(self):
            self._events_after=None
            latest=None;started=time.monotonic();processed=0
            try:
                while processed<100 and time.monotonic()-started<.006:
                    kind,item,result=self.events.get_nowait();processed+=1
                    if kind=='progress':
                        if item==self._operation_id:latest=result
                        continue
                    if kind=='log':self.log(str(item));continue
                    if kind=='closed':
                        receipt=getattr(self,'pending_app_update',None)
                        if receipt:
                            from cfs_updates import launch_updated
                            try:launch_updated(receipt,self.data_dir,demo)
                            except (OSError,ValueError) as error:
                                dialogs['messagebox'].showerror('Neustart fehlgeschlagen',str(error)+'\nBitte die bisherige App erneut öffnen.',parent=self.root)
                        self.root.destroy();return
                    if latest is not None:self.display_progress(latest);latest=None
                    self.busy=False
                    self.finish_progress(kind!='error' and not (isinstance(result,dict) and 'error' in result))
                    if kind=='error':
                        if not self.tag_operation_failed(item):self.clear_tag()
                        self.update_controls()
                        if not self.close_pending:self.show_error(item)
                    else:
                        try:item(result)
                        except Exception as error:
                            self.finish_progress(False)
                            if not self.tag_operation_failed(error):self.clear_tag()
                            self.update_controls()
                            if not self.close_pending:self.show_error(error)
                    self.update_controls()
                    if self.close_pending:self.begin_close()
            except queue.Empty:pass
            if latest is not None and self.busy:self.display_progress(latest)
            if self._events_after is None:self._schedule_events(16 if self.busy or self.close_started else 200)

        def toggle_connection(self):
            if self.bridge is not None:
                device = self.bridge
                self.bridge = None
                self.clear_tag()

                def done(_result):
                    self.connection_var.set("Verbindung getrennt.")
                    self.status_var.set("Verbindung getrennt. Der Port ist wieder für die Arduino IDE frei.")
                    self.log("USB-Verbindung geschlossen.")

                self.run_operation("Verbindung wird getrennt…", device.close, done)
                return
            port = self.port_var.get().strip()
            if not port:
                return
            self.clear_tag()

            def connect():
                device = bridge_factory(port)
                try:
                    info = device.hello()
                except Exception:
                    device.close()
                    raise
                return device, info

            def done(result):
                self.bridge, info = result
                version = info.get("reader_version")
                version_text = f" · Reader 0x{version:02X}" if isinstance(version, int) else ""
                version_text += ' · Bridge '+str(info.get('firmware_version', 'Version unbekannt'))
                self.connection_var.set(f"Verbunden mit {port}{version_text}.")
                self.status_var.set("Verbunden. Jetzt den gewünschten Tag lesen.")
                self.log(f"Arduino verbunden: {port}{version_text}.")

            self.run_operation("Arduino wird verbunden…", connect, done)

        def read_tag(self):
            if self.bridge is not None and getattr(self,"target_form",None) and self.target_form.ace:
                self.target_form.read();return
            if self.bridge is None:
                return
            device = self.bridge
            pair=getattr(self,'pair_session',None)
            preserve=bool(pair and pair.preserve_values)
            self.clear_tag()
            if hasattr(self,'tag_feedback'):self.tag_feedback.begin('read')

            def done(result):
                uid = str(result.get("uid", "")).replace(" ", "").upper()
                if len(uid) != 8 or any(character not in "0123456789ABCDEF" for character in uid):
                    raise ValueError("Der Reader hat keine gültige 4-Byte-UID zurückgegeben.")
                self.uid = uid
                if hasattr(self,'tag_feedback'):self.tag_feedback.success(uid)
                spaced_uid = " ".join(uid[index:index + 2] for index in range(0, len(uid), 2))
                self.tag_var.set(f"UID {spaced_uid} · MIFARE Classic 1K")
                if pair is not None:
                    pair.read(uid)
                    if pair.enabled:
                        number=pair.number_for(uid)
                        if number is not None:self.tag_var.set(f'Tag {number} · UID {spaced_uid} · MIFARE Classic 1K')
                if preserve:
                    message=pair.last_event+' Im Zweiermodus bleiben deine Wunschwerte unverändert.'
                    self.tag_hint_var.set(message)
                    self.status_var.set(message)
                    self.log(message+f' UID {uid}.')
                    return
                if result.get("formatted"):
                    profile=result.get("profile") or {}
                    material_id = self.shared_roll_material(profile)
                    if material_id:
                        if hasattr(self,'_all_material_by_label') and not any(p.get('id')==material_id for p in self.material_by_label.values()) and any(p.get('id')==material_id for p in self._all_material_by_label.values()):self.clear_material_filters()
                        self.id_var.set(material_id)
                        candidates = [(label, entry) for label, entry in self.material_by_label.items()
                                      if entry["id"] == material_id and (entry.get("source") != "slicer" or entry.get("registry_managed"))]
                        label = next((label for label, entry in candidates if entry.get("registry_managed")),
                                     candidates[0][0] if candidates else None)
                        self.material_var.set(label or "Eigener Materialcode")
                        known = self.material_by_id.get(material_id, {})
                        self.name_var.set(profile.get("name") or (known.get("name", "") if known.get("registry_managed") else material_title(known)))
                    if profile.get("color"):
                        self.color_var.set(normal_color(profile["color"]))
                    self.weight_var.set(str(profile["weight_g"]) if profile.get("weight_g") is not None else "")
                    if profile.get("serial"):
                        self.serial_var.set(str(profile["serial"]))
                    if profile.get('weight_g') is not None:
                        self.log(f"Tagmenge übernommen: {self.weight_var.get()} g / {self.length_var.get() if hasattr(self,'length_var') else 'n. a.'} m. Profilwechsel erhält Menge und Rollennummer. Dies ist die gespeicherte Tagmenge, kein bestätigter CFS-Verbrauchsmesswert.")
                    self.remember_roll_result(uid,dict(profile,material_id=material_id))
                    self.tag_hint_var.set("Creality-Datensatz gelesen. Angaben prüfen oder für diesen Tag ändern.")
                    self.log(f"Tag {uid}: Creality-Datensatz erkannt.")
                else:
                    self.tag_hint_var.set("Kein gültiger Creality-Datensatz. Zum Beschreiben die Filamentangaben unten prüfen.")
                    self.log(f"Tag {uid}: kein gültiger Creality-Datensatz erkannt; vorhandene Filamentauswahl bleibt erhalten.")
                self.status_var.set("Tag gelesen. Filamentangaben prüfen und bei Bedarf „Tag schreiben“ klicken.")
                if pair is not None and pair.enabled:
                    message=pair.last_event+(' Vorhandene Angaben samt Rollennummer übernommen.' if result.get('formatted') else ' Kein gültiger Creality-Datensatz; Angaben selbst einstellen.')
                    self.tag_hint_var.set(message);self.status_var.set(message);self.log(message+f' UID {uid}.')

            self.run_operation("Tag wird gelesen – bitte ruhig am Reader liegen lassen…", device.read_tag, done)

        def write_tag(self):
            if self.bridge is not None and getattr(self,"target_form",None) and self.target_form.ace:
                self.target_form.write();return
            if self.bridge is None or not self.uid or self.busy:return
            selected=self.material_by_label.get(self.material_var.get())
            managed=bool(selected and selected.get('registry_managed') and self.registry is not None)
            if managed:self.show_material(selected)
            try:spec=self.make_spec()
            except (ValueError,TypeError,OSError) as error:self.show_error(error);return
            device,uid,backup_dir=self.bridge,self.uid,self.backup_dir
            snapshot=dict(selected) if managed else None
            def work():
                fresh=dict(self.registry.refresh_material(snapshot)) if managed else None
                current=spec
                if fresh is not None:
                    if fresh.get('registry_registration_status')!='installed':raise ValueError('Die Druckereinrichtung dieses Benutzerprofils steht noch aus.')
                    current=codec.TagSpec(material_id=fresh['id'],color=normal_color(fresh['color']),weight_g=spec.weight_g,serial=spec.serial,name=fresh['name'])
                    codec.validate_spec(current)
                pair=getattr(self,'pair_session',None)
                if pair is not None:pair.check_write(uid,current)
                result=device.write_tag(uid,current,backup_dir)
                result['_written_spec']=current
                result['_fresh_material']=fresh
                return result
            def done(result):
                if result.get("verified") is not True:
                    raise ValueError("Die geschriebenen Daten konnten nicht vollständig bestätigt werden. Tag erneut lesen.")
                if hasattr(self,'tag_feedback'):self.tag_feedback.success(uid,verified=True)
                written=result['_written_spec']
                self.remember_roll_result(uid,{'serial':written.serial,'material_id':written.material_id,'weight_g':written.weight_g})
                pair=getattr(self,'pair_session',None)
                if pair is not None:pair.confirmed(uid,result['_written_spec'])
                if result.get('_fresh_material') is not None:
                    selected.clear();selected.update(result['_fresh_material']);self.show_material(selected)
                if demo:
                    self.status_var.set("Demo-Schreibvorgang abgeschlossen. Kein echter Tag wurde verändert.")
                    self.log("Demo: Schreiben und Zurücklesen simuliert.")
                else:
                    self.status_var.set("Geschrieben und zurückgelesen. CFS-Test am Drucker steht noch aus.")
                    self.log(f"Tag {uid} geschrieben und zurückgelesen. CFS-Test am Drucker steht noch aus.")
                    if result.get("backup"):
                        self.log(f"Sicherung: {result['backup']}")
                if pair is not None and pair.enabled and len(pair.written)==2:
                    self.tag_hint_var.set('Beide Tags sind geschrieben und geprüft. Für die nächste Rolle „Neue Rolle“ wählen.')
                else:self.tag_hint_var.set("Für den zweiten Aufkleber: Tag wechseln, „Tag lesen“ und mit derselben Rollennummer schreiben.")
                if pair is not None and pair.enabled:
                    message=('Demo: ' if demo else '')+pair.last_event
                    self.tag_hint_var.set(message+' '+('Beide Tags sind fertig.' if len(pair.written)==2 else 'Jetzt Tag 2 einlesen.'))
                    self.status_var.set(message+(' Kein echter Tag wurde verändert.' if demo else ' CFS-Test am Drucker steht noch aus.'))
                    self.log(message+f' UID {uid}.')

            if hasattr(self,'tag_feedback'):self.tag_feedback.begin('write')
            self.run_operation("Tag wird geschrieben und geprüft – bitte nicht vom Reader entfernen…",
                               work,done)

        def show_error(self, error):
            code = str(getattr(error, "code", ""))
            descriptions = {
                "NO_TAG": "Kein Tag erkannt. Karte oder Aufkleber dicht und ruhig an die Antennenfläche halten.",
                "UID_MISMATCH": "Am Reader liegt ein anderer Tag. Diesen zuerst mit „Tag lesen“ einlesen.",
                "UNSUPPORTED_TAG": "Dieser Tag wird nicht unterstützt. Benötigt wird MIFARE Classic 1K mit 4-Byte-UID.",
                "AUTH_FAILED": "Der Tag konnte nicht geöffnet werden. Er verwendet möglicherweise einen anderen Schlüssel.",
                "ACCESS_BITS": "Dieser Tag hat andere Zugriffsrechte. Bitte einen passenden neuen Aufkleber verwenden.",
                "READER_UNAVAILABLE": "Der RC522 antwortet nicht. Versorgung und Verdrahtung prüfen.",
                "READ_FAILED": "Lesen fehlgeschlagen. Den Tag ruhig auflegen und erneut lesen.",
                "WRITE_FAILED": "Schreiben fehlgeschlagen. Den Tag erneut lesen; die vorhandene Sicherung bleibt erhalten.",
                "VERIFY_FAILED": "Die Prüfung nach dem Schreiben ist fehlgeschlagen. Den Tag erneut lesen und die Meldungen prüfen.",
                "SERIAL_ERROR": "Die USB-Verbindung ist unterbrochen oder belegt. Seriellen Monitor schließen und erneut verbinden.",
                "TIMEOUT": "Der Arduino hat nicht rechtzeitig geantwortet. Den Bridge-Sketch und den ausgewählten Port prüfen.",
            }
            message = descriptions.get(code, str(error) or "Der Vorgang konnte nicht abgeschlossen werden.")
            self.status_var.set(message)
            detail = f"{code}: {error}" if code else str(error)
            self.log(f"Fehler: {message}")
            if detail and detail != message:
                self.log(f"Details: {detail}")
            if getattr(error, "backup", None):
                message += f"\n\nSicherung: {error.backup}\nDen Tag vor dem nächsten Versuch erneut lesen."
            dialogs["messagebox"].showerror("Vorgang fehlgeschlagen", message, parent=self.root)

        def on_close(self):
            self.close_pending = True
            self.update_controls()
            if self.busy:
                self.status_var.set("Der laufende Vorgang wird beendet. Danach schließt das Fenster automatisch.")
            else:
                self.begin_close()

        def begin_close(self):
            if self.close_started:
                return
            self.close_started = True
            self._schedule_events(0)
            device, self.bridge = self.bridge, None

            def worker():
                try:
                    if device is not None:
                        device.close()
                    if getattr(self,'label_printer',None) is not None:
                        self.label_printer.disconnect()
                finally:
                    self.events.put(("closed", None, None))

            threading.Thread(target=worker, daemon=True, name="cfs-device-close").start()

    return WriterApp


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lokaler Creality-CFS-Tagwriter für Mega2560 und RC522")
    parser.add_argument("--demo", action="store_true", help="Oberfläche ohne USB-Hardware und ohne echte Schreibzugriffe testen")
    parser.add_argument("--registry", type=Path, default=None, help="Feste Benutzerprofil-Zuordnung; Standard: profil-zuordnung.json neben dem Programm")
    args = parser.parse_args(argv)
    from cfs_updates import redirect_to_update
    from cfs_versions import APP_VERSION
    update_data=Path(os.environ.get('CFS_APP_DATA', args.registry.parent if args.registry else Path(__file__).resolve().parent))
    if redirect_to_update(APP_VERSION,update_data,args.demo):return 0
    try:
        import tkinter as tk
        from tkinter import colorchooser, filedialog, messagebox, ttk
    except ImportError:
        print("Die Tkinter-Oberfläche fehlt. Installiere die benötigten Pakete:\n" + INSTALL_COMMAND, file=sys.stderr)
        return 1
    try:
        codec = importlib.import_module("cfs_codec")
        registry_module = importlib.import_module("cfs_registry")
        registry_path = args.registry or registry_module.DEFAULT_REGISTRY_PATH
        registry = registry_module.ProfileRegistry(registry_path) if registry_path.exists() else None
        if args.demo:
            bridge_factory = DemoBridge
            list_ports = lambda: []
        else:
            device = importlib.import_module("cfs_device")
            from serial.tools.list_ports import comports
            bridge_factory, list_ports = device.Bridge, comports
    except ImportError as error:
        detail = f"Benötigte Python-Komponenten fehlen ({error}).\n\nIm Terminal installieren:\n{INSTALL_COMMAND}\n\nAlle Python-Dateien dieses Pakets müssen im selben Ordner liegen."
        print(detail, file=sys.stderr)
        try:
            error_root = tk.Tk()
            error_root.withdraw()
            messagebox.showerror("Komponenten fehlen", detail, parent=error_root)
            error_root.destroy()
        except tk.TclError:
            pass
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"Das Fenster konnte nicht geöffnet werden: {error}", file=sys.stderr)
        return 1
    app_class = make_application(tk, ttk, {"colorchooser": colorchooser, "filedialog": filedialog, "messagebox": messagebox},
                                 codec, bridge_factory, list_ports, args.demo, registry)
    app_class(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

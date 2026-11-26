# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""In-app parts list and board-specific RC522 wiring diagrams."""
PINS = {
    'mega2560': {'name': 'Arduino Mega2560 R3', 'SS': '53', 'SCK': '52', 'MOSI': '51', 'MISO': '50', 'RST': '5'},
    'nano328p': {'name': 'Arduino Nano Classic ATmega328P (5 V)', 'SS': 'D10', 'SCK': 'D13', 'MOSI': 'D11', 'MISO': 'D12', 'RST': 'D9'},
}

PARTS = '''BAUTEILE

• Arduino Mega2560 R3 ODER Nano Classic mit ATmega328P (5 V / 16 MHz)
• RC522 / MFRC522-Modul für 13,56 MHz
• vier Widerstände 1 kΩ und vier Widerstände 2 kΩ
• Steckbrett und passende Jumperkabel; USB-Datenkabel für das gewählte Board
• Für Creality CFS: MIFARE Classic 1K mit 4-Byte-UID
• Nur für den experimentellen Anycubic-ACE-Modus: NTAG213 mit 7-Byte-UID
  und Bridge 1.1.0. NTAG213 sind keine CFS-Aufkleber.
• für den Nano empfohlen: fertiges 3,3-V-Reglermodul mit mindestens 100 mA
  und den laut Modul vorgesehenen Kondensatoren
• optional 100 nF und 10 µF zwischen 3,3 V und GND direkt am RC522

VERSORGUNG

Der RC522 bekommt 3,3 V. Seine Signaleingänge bekommen keine direkten 5 V.
Mega und klassischer Nano arbeiten mit 5 V: SS, SCK, MOSI und RST benötigen
je einen eigenen 1kΩ/2kΩ-Spannungsteiler. MISO kommt direkt zurück zum Arduino.
Alle GND-Anschlüsse und alle unteren 2-kΩ-Widerstände teilen dieselbe Masse.

Beim Mega kann der vorhandene 3,3-V-Ausgang verwendet werden. Der originale
Nano spezifiziert am 3,3-V-Pin maximal 50 mA; bei Nachbauten kann die Versorgung
abweichen. Für eine verlässliche Nano-Versorgung empfiehlt der Plan ein fertiges
3,3-V-Reglermodul: Arduino 5V → Reglereingang, Regler 3,3V → RC522 3.3V,
Regler-GND → gemeinsame Masse. Den RC522 niemals direkt an 5V anschließen.

Die Nano-Auswahl gilt nicht für Nano Every, Nano 33, Nano ESP32 oder ATmega168.
Sie haben andere Mikrocontroller bzw. Spannungen und benötigen eigene Builds.
'''

STEPS = '''AUFBAU UND ERSTER TEST

1. USB-Kabel abziehen. Board auswählen und nach den aufgedruckten Pinnamen
   verdrahten, nicht nach der optischen Reihenfolge auf einer Abbildung.
2. Für jede der vier Arduino-Ausgangsleitungen einen Teiler aufbauen:
   Arduino → 1 kΩ → Abgriff zum RC522; Abgriff → 2 kΩ → GND.
3. MISO direkt verbinden, Versorgung und gemeinsame Masse anschließen.
   IRQ bleibt frei. SDA am RC522 ist hier SS/Chipselect, nicht Arduino-I²C-SDA.
4. Alle Leitungen kontrollieren, dann erst USB anschließen.
5. In „Einrichtung“ unter „Arduino“ das passende Board und den USB-Port wählen.
   „Bridge aufspielen“ lädt das zum Board gehörende Programm.
6. Beim Nano zunächst „Nano Classic ATmega328P“ wählen. Meldet der Upload
   „programmer is not responding“, den Eintrag „alter Bootloader“ versuchen.
   Das wählt nur die passende Upload-Verbindung; es wird kein Bootloader gebrannt.
7. Seriellen Monitor schließen, im Hauptfenster verbinden und eine Karte lesen.
   Bei Reader-Version 0x00/0xFF zuerst Stromversorgung, gemeinsame Masse,
   SPI-Pins und Kontaktstellen prüfen. Nach dem Schreiben die Rückleseprüfung
   abwarten und den Tag noch einmal lesen.

QUELLEN
Arduino-Nano-Pinout:
https://docs.arduino.cc/resources/pinouts/A000005-full-pinout.pdf
Arduino-Mega-Pinout:
https://docs.arduino.cc/resources/pinouts/A000067-full-pinout.pdf
Nano-Prozessor-/Bootloader-Einstellungen:
https://github.com/arduino/ArduinoCore-avr/blob/master/boards.txt
MFRC522-Datenblatt:
https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf
'''


def show_guide(root, tk, ttk, *, board='mega2560', dark=False):
    """Open local, original wiring sheets; PNG viewing adds no dependency."""
    from pathlib import Path
    from PIL import Image
    from io import BytesIO

    family = 'nano328p' if board.startswith('nano') else 'mega2560'
    assets = Path(__file__).resolve().parent / 'hardware-assets'
    window = tk.Toplevel(root)
    window.title('Arduino-Bauanleitung · Mega2560 / Nano Classic')
    window.transient(root)
    height = min(900, max(550, root.winfo_screenheight()-100))
    window.geometry(str(min(1200, max(850, root.winfo_screenwidth()-80)))+'x'+str(height))
    window.minsize(850, 550)
    outer = ttk.Frame(window, padding=16)
    outer.pack(fill='both', expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(1, weight=1)
    ttk.Label(outer, text='RC522 anschließen · Bebilderte Bauanleitung',
              font=('TkDefaultFont', 14, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 12))
    tabs = ttk.Notebook(outer)
    tabs.grid(row=1, column=0, sticky='nsew')
    for title, contents in (('Bauteile & Versorgung', PARTS), ('Schrittfolge & Quellen', STEPS)):
        frame = ttk.Frame(tabs)
        tabs.add(frame, text=title)
        text = tk.Text(frame, wrap='word', relief='flat', font=('TkDefaultFont', 11), padx=16, pady=14)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        scroll.pack(side='right', fill='y')
        text.pack(fill='both', expand=True)
        text.configure(yscrollcommand=scroll.set)
        text.insert('1.0', contents)
        text.configure(state='disabled')

    viewers = []

    def image_viewer(parent):
        controls = ttk.Frame(parent)
        controls.pack(fill='x', pady=(0, 8))
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        canvas = tk.Canvas(frame, highlightthickness=0, background='#242424' if dark else '#EEEEEE')
        bar = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
        bar.grid(row=0, column=1, sticky='ns')
        canvas.grid(row=0, column=0, sticky='nsew')
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=canvas.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        canvas.configure(yscrollcommand=bar.set, xscrollcommand=horizontal.set)
        state = {'image': None, 'photo': None, 'fit': True, 'scale': 0.5, 'pending': None, 'size': None}
        percentage = tk.StringVar(value='')

        def draw():
            state['pending'] = None
            original = state['image']
            if original is None or not canvas.winfo_exists():
                return
            if state['fit']:
                # PNG is rendered at 2×: 0.5 means native diagram size.
                state['scale'] = min(0.5, max(0.05, min(
                    (canvas.winfo_width()-12)/original.width,
                    (canvas.winfo_height()-12)/original.height)))
            size = tuple(max(1, round(side*state['scale'])) for side in original.size)
            percentage.set(str(round(state['scale']*200))+' %')
            if size == state['size']:
                return
            state['size'] = size
            # Mint packages Pillow's optional ImageTk separately. Tk itself can
            # display PNG; use it directly so the installed launcher works too.
            buffer = BytesIO()
            original.resize(size, Image.Resampling.LANCZOS).save(buffer, format='PNG')
            state['photo'] = tk.PhotoImage(data=buffer.getvalue(), master=canvas)
            canvas.delete('all')
            canvas.create_image(6, 6, image=state['photo'], anchor='nw')
            canvas.configure(scrollregion=(0, 0, size[0]+12, size[1]+12))

        def schedule(_event=None):
            if state['pending'] is not None:
                canvas.after_cancel(state['pending'])
            state['pending'] = canvas.after(80, draw)

        def zoom(factor=None):
            state['fit'] = factor is None
            if factor is not None:
                state['scale'] = max(0.10, min(1.0, state['scale']*factor))
            schedule()

        def load(name):
            with Image.open(assets/name) as opened:
                state['image'] = opened.convert('RGB')
            state['size'] = None
            state['fit'] = True
            canvas.xview_moveto(0)
            canvas.yview_moveto(0)
            schedule()

        ttk.Button(controls, text='−', width=3, command=lambda: zoom(1/1.25)).pack(side='right')
        ttk.Button(controls, text='+', width=3, command=lambda: zoom(1.25)).pack(side='right', padx=4)
        ttk.Button(controls, text='Einpassen', command=zoom).pack(side='right', padx=4)
        ttk.Label(controls, textvariable=percentage, width=7).pack(side='right')
        canvas.bind('<Configure>', lambda event: schedule() if state['fit'] else None)
        viewer = {'canvas': canvas, 'controls': controls, 'load': load, 'state': state, 'zoom': zoom}
        viewers.append(viewer)
        return viewer

    circuit = ttk.Frame(tabs, padding=10)
    tabs.insert(1, circuit, text='Kabelbild · Mega / Nano')
    main = image_viewer(circuit)
    choice = tk.StringVar(value=PINS[family]['name'])
    selector = ttk.Combobox(main['controls'], textvariable=choice,
                           values=[p['name'] for p in PINS.values()], state='readonly', width=46)
    selector.pack(side='left')

    def select_board(_event=None):
        family = next(key for key, pins in PINS.items() if pins['name'] == choice.get())
        main['load'](family+'-breadboard.png')

    selector.bind('<<ComboboxSelected>>', select_board)
    select_board()
    detail = ttk.Frame(tabs, padding=10)
    tabs.insert(2, detail, text='Widerstände · 1 kΩ / 2 kΩ')
    detail_view = image_viewer(detail)
    ttk.Label(detail_view['controls'], text='Ein Teiler im Detail · Widerstands-Farbringe').pack(side='left')
    detail_view['load']('spannungsteiler-detail.png')
    tabs.select(circuit)

    def close():
        for viewer in viewers:
            state = viewer['state']
            if state['pending'] is not None:
                viewer['canvas'].after_cancel(state['pending'])
        window.destroy()

    ttk.Button(outer, text='Schließen', command=close).grid(row=2, column=0, sticky='e', pady=(10, 0))
    window.protocol('WM_DELETE_WINDOW', close)
    window.lift()
    window.grab_set()
    return {'window': window, 'selector': selector, 'choice': choice, 'canvas': main['canvas'],
            'notebook': tabs, 'viewers': viewers}

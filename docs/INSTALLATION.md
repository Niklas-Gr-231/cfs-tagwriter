# Installation auf Windows, Linux und macOS

## Fertige Anwendung ohne Python-Installation

Die zur Rechnerarchitektur passende Datei aus dem
[aktuellen Release](https://github.com/Niklas-Gr-231/cfs-tagwriter/releases/latest)
herunterladen. Ein Git-Checkout ist nicht nötig. Die nativen Pakete enthalten
Python, Tk, USB-/SSH-/Bluetooth-Bibliotheken, liblzma für T50M Pro, Schriften,
Schaltpläne, Beispielplatte und Lizenztexte.

- **Windows x64:** `CFS_Tagwriter_<Version>_windows-x86_64.exe` in einen dauerhaften
  eigenen Ordner legen und öffnen. Python wird nicht benötigt. Eine Verknüpfung
  auf diese EXE bleibt auch nach Updates nutzbar. Das Paket ist portabel, kein MSI.
- **Linux x64:** `CFS_Tagwriter_<Version>_linux-x86_64.AppImage` herunterladen,
  in den Dateieigenschaften als ausführbar markieren und öffnen.
  Im Terminal alternativ `chmod +x CFS_Tagwriter_*.AppImage` und Datei starten.
  Ohne FUSE: `APPIMAGE_EXTRACT_AND_RUN=1 ./CFS_Tagwriter_<Version>_linux-x86_64.AppImage`.
  Basis: Ubuntu 22.04 oder neuer / entsprechende Mint-Version mit grafischer Sitzung.
- **macOS:** DMG für `arm64` (Apple Silicon) oder `x86_64` (Intel) öffnen und
  „CFS Tagwriter.app“ nach Programme ziehen. Die ZIP mit derselben Architektur
  ist das Paket für den integrierten Updater. Zielbasis: macOS 15 oder neuer.
  macOS fragt beim Bluetoothzugriff nach Zustimmung. Unsignierte Pakete können
  eine ausdrückliche Freigabe unter Systemeinstellungen → Datenschutz & Sicherheit
  benötigen. Kein Apple Developer ID / keine Notarisierung ist eingerichtet;
  Sicherheitsprüfungen werden nicht deaktiviert. Windows kann SmartScreen anzeigen.

Optional per Mac-Terminal in `~/Applications` installieren:

```sh
curl -fL https://github.com/Niklas-Gr-231/cfs-tagwriter/releases/latest/download/install-macos.sh -o /tmp/cfs-install-macos.sh
sh /tmp/cfs-install-macos.sh
```

Der Installer erkennt Intel/Apple Silicon, lädt die veröffentlichte DMG samt
SHA-256-Prüfsumme und kopiert die App ins eigene Programme-Verzeichnis.
Eine bestehende Installation wird nicht überschrieben; dafür den App-Updater nutzen.

## Updates in der App

**Einstellungen → App aktualisieren → Nach Updates suchen** funktioniert mit
allen drei nativen Paketen. Download und Prüfung laufen im Hintergrund.
Nur stabile veröffentlichte Versionen des Projekt-Repositorys werden angeboten.
Die App prüft Rechnerarchitektur, Dateigröße, GitHub-SHA-256 und einen Starttest.
Anschließend bewusst **Update anwenden und neu starten** wählen.
Offene Geräteverbindungen werden vorher geschlossen. Ein laufender Schreib- oder
Installationsvorgang muss beendet sein. Es gibt keine automatische Geräteaktualisierung.

Die neue Version wird unter `data/updates/<Version>-<Kennung>` in der Benutzerablage
installiert, nicht über die gerade laufende EXE/AppImage/App geschrieben.
Dadurch entstehen keine Windows-Dateisperren und keine Administratorabfragen.
Der vorhandene Starter leitet beim nächsten Öffnen zur aktualisierten Version weiter.
Die bisherige App und ältere Releases bleiben erhalten.
Im Fehlerfall vor Aktivierung bleibt die alte App unverändert; bei einem beschädigten
Update startet der alte Starter seine ursprüngliche Version. Rückkehr zu einer alten
Version: App schließen, `app-update.json` in der Benutzerablage umbenennen und die
alte Original-App starten. Die neuere Original-App leitet nicht auf eine ältere um.
Benutzerdaten werden nicht zurückgesetzt. Alte Update-Unterordner nur bei geschlossener
App entfernen, wenn sie nicht mehr in `app-update.json` als aktive Version stehen.

Nach dem Update erscheint die Änderungsübersicht einmalig. **Hilfe → Was ist neu?**
zeigt sie jederzeit erneut an. Auf der Update-Seite können unter **Patch-Historie**
auch frühere Versionshinweise offline ausgewählt werden; die Auswahl ändert nicht
das angebotene Update. Keine Update-Suche beim Start und keine Telemetrie;
GitHub wird erst beim Klick auf „Nach Updates suchen“ kontaktiert.
Auch die Python-Ausgabe kann über diesen Weg zu einem nativen Paket wechseln;
ihre bisherige Datenablage bleibt dabei erhalten.

## Quellcode / Python-Ausgabe

Python ab 3.10 mit Tkinter und pip verwenden. Python 3.12 ist eine geeignete
gemeinsame Ausgangsbasis. Die App läuft im Benutzerkonto. Ein virtueller
Python-Ordner hält die Abhängigkeiten vom übrigen System getrennt.
Die automatischen Tests in GitHub prüfen Python 3.11 und 3.12.

1. **Windows 10/11, x64**

   Python mit Tcl/Tk von python.org installieren. Im entpackten Projektordner
   die Eingabeaufforderung oder PowerShell öffnen und ausführen.

   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe start.py --check
   .venv\Scripts\python.exe start.py
   ```

   Danach kann `start.bat` gestartet werden. Für Bluetooth LE zusätzlich
   `requirements-bluetooth.txt` mit demselben Python installieren. Windows muss
   den Arduino als COM-Port erkennen. Falls das Board einen CH340 verwendet,
   bei fehlendem Port den passenden Treiber vom Hersteller beziehen.

2. **Linux Mint / Ubuntu mit grafischer Sitzung**

   ```sh
   sudo apt install python3 python3-venv python3-pip python3-tk liblzma5
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python start.py --check
   ./start.sh
   ```

   Für Bluetooth Classic wird BlueZ mit `bluetoothctl` benötigt.
   `sudo apt install bluez` richtet es bei Bedarf ein. Für das Merken von
   Passwörtern muss ein Secret-Service-Schlüsselbund wie GNOME Keyring laufen
   und entsperrt sein. Die App speichert Passwörter ausschließlich dort.

   Ein Arduino-Port liegt gewöhnlich unter `/dev/ttyACM*` oder `/dev/ttyUSB*`.
   Bei fehlender Berechtigung kann die Person der Gruppe `dialout` hinzugefügt
   werden. Danach ab- und wieder anmelden.

   ```sh
   sudo usermod -aG dialout "$USER"
   ```

3. **macOS, Intel oder Apple Silicon**

   Python mit Tkinter von python.org installieren und im Terminal prüfen,
   ob `python3 -m tkinter` ein Fenster öffnet. Anschließend im Projektordner
   ausführen.

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements-bluetooth.txt
   .venv/bin/python start.py --check
   ./start.command
   ```

   Bei einem ZIP-Download gegebenenfalls einmal `chmod +x start.sh start.command`
   ausführen. Arduino-Ports heißen gewöhnlich `/dev/cu.usbmodem*` oder
   `/dev/cu.usbserial*`. Bluetoothzugriff muss für das verwendete Terminal bzw.
   Python in den macOS-Datenschutzeinstellungen freigegeben sein. Die
   Geräteauswahl speichert auf macOS eine CoreBluetooth-UUID, die auf einem
   anderen Rechner erneut ermittelt werden muss.
   [Bleak-Dokumentation für macOS](https://bleak.readthedocs.io/en/latest/backends/macos.html)

Der direkte T50M-Pro-Druck benötigt zusätzlich liblzma mit LZMA1EXT-Unterstützung.
Unter Mint liefert `liblzma5` diese Bibliothek. Unter macOS kann XZ beispielsweise
mit Homebrew installiert werden. Der Loader prüft die üblichen Homebrew-Pfade
für Intel und Apple Silicon.

Unter Windows eine vertrauenswürdige, zur Python-Architektur passende liblzma-DLL
verwenden und deren absoluten Dateipfad setzen. Für beide Systeme kann ein
abweichender Bibliothekspfad ausdrücklich angegeben werden.

```powershell
$env:CFS_LIBLZMA = 'C:\Libraries\xz\bin\liblzma.dll'
.venv\Scripts\python.exe start.py --check
```

```sh
export CFS_LIBLZMA=/opt/homebrew/opt/xz/lib/liblzma.dylib
.venv/bin/python start.py --check
```

Diese Pfade sind Beispiele. Die DLL bzw. dylib selbst gehört nicht ins Repository.
`--check` meldet, ob die optionale Kompression verfügbar ist. PNG-Export benötigt
Pillow und funktioniert unabhängig von der Bluetooth-Druckverbindung.
Die körperliche Verbindung zum T50M Pro ist auf Windows und macOS noch zu testen.

Die Benutzerablage liegt je nach System an folgenden Orten.

| System | Standardordner |
| --- | --- |
| Linux | `$XDG_DATA_HOME/cfs-tagwriter/data`, sonst `~/.local/share/cfs-tagwriter/data` |
| Windows | `%LOCALAPPDATA%\CFS-Tagwriter\data` |
| macOS | `~/Library/Application Support/CFS-Tagwriter/data` |

Mit `python start.py --data-dir <Ordner>` kann eine andere Ablage gewählt werden.
Eine bestehende Einrichtung vor dem Umzug vollständig sichern. Zugangsdaten im
System-Schlüsselbund werden auf einem anderen Rechner neu eingegeben.


## Lesen, Schreiben und Rollennummern ab 3.8.0

„Lesen & Schreiben“ öffnet die Tagoberfläche. Im Zwei-Tag-Modus bleiben die
Bestätigungen für Tag 1 und Tag 2 getrennt sichtbar. Erst erfolgreiches
Zurücklesen nach dem Schreiben ergibt eine grüne Schreibbestätigung.

Eine vorhandene, sechsstellige Rollennummer wird beim Lesen übernommen.
Ohne Nummer (oder bei 000000) merkt sich die App eine neue Nummer für diesen
Tag. Erneutes Lesen ändert sie nicht. Beim Schreiben eines zweiten Tags im
Zweiermodus werden Materialwerte und Rollennummer der ersten Rolle verwendet.
„Neue Rolle“ ist die bewusste Vergabe einer anderen Nummer.

Die lokale Zuordnung liegt in `data/state/roll-identities.json` innerhalb der
Benutzerablage und bleibt bei App-Updates erhalten. Sie wird nicht in öffentliche
Pakete aufgenommen. Bei ACE ist die Rollennummer ausschließlich lokal: das
native, dokumentierte Tagformat bietet dafür kein Feld. Die NFC-Formate,
Arduino-Bridge und der Druckerdienst werden hierdurch nicht verändert.

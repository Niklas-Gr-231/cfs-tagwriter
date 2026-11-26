# Installation auf Windows, Linux und macOS

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


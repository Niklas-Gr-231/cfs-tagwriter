# Fremdkomponenten und Quellen

Die Projektlizenz gilt für die eigenen Beiträge. Eigenständige Fremdkomponenten
behalten ihre Lizenzrechte, einschließlich dort erlaubter kommerzieller Nutzung.
Die nichtkommerzielle Projektlizenz schränkt diese ursprünglichen Rechte nicht ein.

| Bestandteil | Herkunft und Lizenz | Behandlung im Repository |
| --- | --- | --- |
| DejaVu Sans und DejaVu Sans Bold | DejaVu / Bitstream Vera, Änderungen der DejaVu-Mitwirkenden gemeinfrei | Unveränderte TTF-Dateien mit vollständigem Lizenzhinweis in `label-assets/FONT-LICENSE.txt` und `LICENSES/FONT-LICENSE.txt`. |
| T50M-Pro-Protokolladaption | Katasymbol Web, MIT, Commit `b3799ffba1efca180a631d0691d1a9162d2e1853` | Herkunft im Modul dokumentiert. Vollständiger Hinweis in `LICENSES/KATASYMBOL-PROTOCOL-LICENSE.txt`. Eigene Änderungen unter Projektlizenz. |
| MFRC522 1.4.12 | miguelbalboa / GithubCommunity, Unlicense | Bibliotheksquellcode wird über Arduino CLI installiert. Lizenzkopie in `LICENSES/MFRC522-Unlicense.txt`. |
| Arduino AVR Core 1.8.8 | Arduino, LGPL-2.1-or-later und weitere Hinweise einzelner Dateien | Download durch Arduino CLI. Die Git-Ausgabe verteilt Bridge-Quellcode. Kompilierte AVR-Binärdateien werden auf dem Rechner der nutzenden Person erzeugt. |
| Arduino CLI 1.5.1 | Arduino, GPL-3.0 | Separater Werkzeugdownload mit SHA-256-Prüfung. Das Programm ist kein Bestandteil des Git-Archivs. |
| pyserial | Python-Paket, BSD-3-Clause | Installation über pip, keine Bibliothekskopie im Git-Archiv. |
| cryptography | Python-Paket, Apache-2.0 / BSD-3-Clause | Installation über pip, Lizenzhinweise liegen in der installierten Distribution. |
| Paramiko | Python-Paket, LGPL-2.1 | Installation über pip. Eigene Projektdateien enthalten keine Paramiko-Quellcodekopie. |
| keyring | Python-Paket, MIT | Installation über pip, native Betriebssystem-Schlüsselbünde. |
| Pillow | Python-Paket, MIT-CMU in der geprüften Version 12.3.0, ältere Versionen HPND und zusätzliche Bibliothekshinweise je Wheel | Installation über pip. Die vollständigen Hinweise des verwendeten Wheels sind bei dessen Weiterverteilung zu berücksichtigen. |
| Bleak | Python-Paket, MIT | Optional über pip. Betriebssystemspezifische Abhängigkeiten werden von pip aufgelöst. |
| XZ / liblzma | XZ Utils, jeweilige Bibliotheks- und Distributionslizenz | Optionale dynamisch geladene Systembibliothek. Es wird keine DLL oder dylib mitgeliefert. |
| Python / Tcl/Tk | Python- und Tcl/Tk-Projekte, jeweilige Lizenzen | Laufzeitvoraussetzung auf dem Zielrechner. |

Die folgenden Originalquellen wurden geprüft oder als technische Referenz verwendet.

- [Katasymbol Web und MIT-Lizenz](https://github.com/khromov/supvan-katasymbol-printer-web-ui/tree/b3799ffba1efca180a631d0691d1a9162d2e1853)
- [MFRC522 1.4.12](https://github.com/miguelbalboa/rfid/tree/1.4.12)
- [Arduino AVR Core 1.8.8](https://github.com/arduino/ArduinoCore-avr/tree/1.8.8)
- [Arduino CLI](https://github.com/arduino/arduino-cli)
- [DejaVu-Lizenz](https://dejavu-fonts.github.io/License.html)
- [XZ-Lizenzübersicht](https://github.com/tukaani-project/xz/blob/v5.6.4/COPYING)
- [pyserial](https://github.com/pyserial/pyserial)
- [cryptography](https://github.com/pyca/cryptography)
- [Paramiko](https://github.com/paramiko/paramiko)
- [keyring](https://github.com/jaraco/keyring)
- [Pillow](https://github.com/python-pillow/Pillow)
- [Bleak](https://github.com/hbldh/bleak)

`DnG-Crafts/K2-RFID` ist eine Referenz für das öffentlich beschriebene Tagformat
und die Interoperabilitätsparameter. Bei der Prüfung am 26.11.2026 wurde dort
keine allgemeine Lizenzdatei gefunden. Dieses Repository übernimmt keine
Quellcodedateien, Datenbanken oder Grafiken dieses Projekts. Die eigenen
Python-Funktionen implementieren das Datenformat und die Standard-AES-Aufrufe.
Ein Quellenlink ist keine Erlaubnis zur Übernahme geschützter Programmteile.
Zusätzliche Übernahmen aus dieser Referenz erfordern eine geklärte Berechtigung.
[Formatreferenz](https://github.com/DnG-Crafts/K2-RFID)

Transitive Python-Abhängigkeiten und heruntergeladene Werkzeuge haben eigene
Lizenzbedingungen. Wer daraus ein Paket mit eingebetteten Bibliotheken oder
fertigen Firmwaredateien erstellt, muss diese Distribution zusätzlich prüfen
und die nötigen Quelltexte, Austauschmöglichkeiten und Hinweise bereitstellen.


## Neue Verdrahtungsbilder (3.4.3)

Die drei SVG-/PNG-Bilder in `hardware-assets` wurden für dieses Projekt aus
geometrischen Grundformen gezeichnet. Sie verwenden keine Fritzing-Bauteilgrafiken,
Arduino-Logos, Produktfotos oder kopierten Hersteller-Pinoutbilder. Sie stehen
unter der Projektlizenz PolyForm Noncommercial 1.0.0. Herstellerunterlagen wurden
nur zur Prüfung der Pinbelegung herangezogen, Links stehen in `docs/HARDWARE.md`.
Der Generator ist `tools/render_wiring.py`. Die PNG-Dateien sind aus den SVGs
abgeleitet. CairoSVG wird nur bei der Entwicklung verwendet und nicht mitgeliefert.

## Experimentelles ACE-Pro-Tagformat (3.5.0)

Feldpositionen wurden anhand der öffentlichen Dokumentation
https://github.com/Molodos/anycubic-nfc-filament/blob/main/format.md geprüft.
NTAG213-Speichergrenzen und GET_VERSION folgen dem NXP-Datenblatt
https://www.nxp.com/docs/en/data-sheet/NTAG213_215_216.pdf . Es wurden keine
Programmdateien, Dumps, Tabellen-Datenbanken oder Bilder dieser Projekte kopiert.
Die Implementierung in cfs_anycubic.py, die Bridge-Erweiterung und die Oberfläche
sind eigene Beiträge unter der Projektlizenz. Der alternative GPL-Tagger wurde
nicht eingebunden. Es gibt keine Anycubic-Cloudbibliothek im Veröffentlichungssatz.

## Anycubic-Wechslerkatalog (3.5.1)

Offizielle Produkt-/Handbuchseiten belegen Wechslerfamilien und Anschlussgruppen.
Die gemeinsame ACE-2-Pro-Datenstruktur ist zusätzlich anhand der unabhängigen
Dokumentation unter https://github.com/Simon-CR/ace2-pro-firmware-research/blob/master/docs/03-rfid-and-tags.md eingeordnet.
Es wurden nur Protokollfakten verwendet, keine Firmware, Patches, Dumps oder
Programmdateien übernommen. Quellen und Erkenntnisgrenzen: docs/ANYCUBIC.md.

## Filament-Swatch-Beispielplatte (separate Modelllizenz)

`app/creality-cfs-writer/sample-assets/Filament-Swatch-Beispielplatte.3mf`
enthält vier Muster aus „Filament swatch“ von **Mr.Brom**, einem Remix von
„Filament sample“ von **9percent**. Die mit der bereitgestellten Quelldatei
überlieferte Lizenzangabe lautet **BY-NC-SA**, ohne Versionsnummer.
Sie wird nicht durch die PolyForm-Lizenz des Programmcodes ersetzt.

- Remix: https://makerworld.com/en/models/1151175-filament-swatch
- Original: https://makerworld.com/models/37649
- Ausgabe/Änderungen: CC BY-NC-SA 4.0,
  https://creativecommons.org/licenses/by-nc-sa/4.0/
- Volltext: https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.txt

Die Geometrie und vier Platzierungen sind erhalten. Die Weitergabe wurde in
Standard-3MF umgepackt; persönliche Profile, Pfade, Geräte-/Projektkennungen,
Hersteller-Gcode und Fotos wurden weggelassen. Zuschreibung und Angaben zu den
Änderungen stehen zusätzlich direkt in der 3MF und in `sample-assets/ATTRIBUTION.txt`.
Die Originalmodellseiten waren während dieser Prüfung nicht direkt abrufbar;
Urheber- und Lizenzangaben wurden aus der bereitgestellten Datei übernommen.
Es wird keine eigene Urheberschaft am Fremdmodell behauptet.

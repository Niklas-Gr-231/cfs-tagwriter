# CFS Tagwriter

Desktop-Werkzeug für eigene Filamentprofile und RFID-Aufkleber an Creality-CFS-Systemen.
Die Anwendung liest und beschreibt MIFARE-Classic-Tags über einen Arduino,
verwaltet die Zuordnung zum Filamentprofil und erzeugt 40 × 30 mm Swatch-Etiketten.

**App 3.6.1 · Druckerdienst 2.1.0 · Arduino-Bridge 1.1.0**

Eigener Projektcode ist unter **PolyForm Noncommercial 1.0.0** verfügbar.
Nichtkommerzielle Nutzung, Änderungen und Weitergabe sind nach den
Lizenzbedingungen erlaubt. Die Rechte an Fremdkomponenten richten sich nach
deren eigenen Lizenzen. Die vollständigen Bedingungen stehen in
[LICENSE](LICENSE) und [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Das Projekt bietet folgende Funktionen.

- Arduino Mega2560 R3 und Nano Classic ATmega328P mit RC522 über USB.
- Materialcode, Farbe, Rollennummer und Restmenge lesen und geprüft schreiben.
- Optional zwei Tags derselben Spule nacheinander mit einem Leser beschreiben.
- Gespeicherte Slicerprofile abgleichen, neue Materialcodes vergeben und
  geänderte Werte mit Vorschau übernehmen. Gespeicherte Slicerwerte haben Vorrang.
- Lokale und Cloudprofile mit sichtbarer Herkunft verwenden. Export und Import
  mit Erkennung von Materialcode-Kollisionen und Zuordnung zum Druckermodell.
- Zusatzdienst per SSH installieren, prüfen, reparieren, steuern und entfernen.
- Vollständige Drucker-Firmwareversion beim Start vergleichen und bei Änderung
  die Dienstverwaltung zur manuellen Neuinstallation öffnen.
- Swatch-Etiketten aus Profilwerten erzeugen, filtern und als PNG exportieren.
  Hi/Ob-Konvention für Düsentypen, Pressure Advance und Preis sind berücksichtigt.
- Optional T50M-Pro-Etiketten direkt per Bluetooth drucken.
- Helle und dunkle Oberfläche, große einheitliche Menütasten mit aufklappbaren
  Aktionen, Fortschrittsanzeigen sowie Arduino-IDE-Export.
- Pro Drucker wählbar: getrennt, nur Rollennummern teilen oder Profile gleicher
  Druckertypen mit expliziter Vorschau übertragen. Tag-Restmengen bleiben maßgeblich.
- Filament- und Etikettensuche zusätzlich nach Druckerhersteller und Druckertyp.
- Gemeinsame Tagoberfläche mit Druckerauswahl für Creality und Anycubic; experimentelle Ziele direkt unter der Schreibaktion gekennzeichnet.
- Experimenteller Anycubic-ACE-Modus für ACE Pro und ACE 2 Pro mit NTAG213, über denselben RC522.
  Kein Anycubic-Druckerdienst und keine automatische Übernahme eigener Cloud-
  Kalibrierungsprofile. ACE 2 Pro und alle Anycubic-Geräte sind nicht praktisch geprüft.
- Sichtbare Tag-Ergebnisse mit Rücklesebestätigung und passenden Wiederholen-Tasten.

| Umgebung | Stand der Unterstützung |
| --- | --- |
| Linux Mint / Ubuntu | Desktop lokal geprüft. Mega/RC522 und T50M Pro über Bluetooth Classic im bisherigen Projektbetrieb bestätigt. Der neue Quellcode-Upload benötigt einen erneuten Gerätetest. |
| Windows 10/11, x64 | Portable Desktop-, USB-, SSH- und BLE-Anbindung vorhanden. Automatische Tests für GitHub vorbereitet. Physische Gerätetests stehen aus. |
| macOS, Intel / Apple Silicon | Portable Desktop-, USB-, SSH- und BLE-Anbindung vorhanden. Automatische Tests für GitHub vorbereitet. Physische Gerätetests stehen aus. |
| Creality K2 Pro mit CFS | Bisheriges Referenzgerät für Dienst und Profilzuordnung. Firmwareänderungen können eine Reparatur erfordern. |
| Weitere Creality-CFS-/CFS-C-Modelle | Experimentell. Native Modell-, Katalog-, Düsen-, Python- und Dienststarterprüfung vor Installation. Eine passende CFS-/CFS-C-Ausrüstung bleibt erforderlich. |
| Anycubic Kobra 3 / V2 / Max / Max V2, Kobra 4, Kobra S1 / S1 Max, Kobra X mit ACE | Getrennte Drucker-/Wechslerliste, dokumentiertes ACE-Layout und ausdrücklich freizugebende unbestätigte Formate. Keine Bestätigung am Gerät und keine Kalibrierungs-/Cloudintegration. |

Für den ersten Start werden Python ab 3.10 mit Tkinter, die Python-Abhängigkeiten,
ein unterstütztes Arduino-/RC522-Gespann und passende Aufkleber benötigt.
Für Druckerfunktionen braucht der Rechner lokalen Netzwerkzugriff und einen
am Drucker freigegebenen Root-/SSH-Zugang. Die Arduino- und Bibliotheksdownloads
benötigen bei der ersten Einrichtung Internetzugriff.

Die Einrichtung für jedes Betriebssystem ist in
[docs/INSTALLATION.md](docs/INSTALLATION.md) beschrieben. Danach wird die App
mit `start.bat` unter Windows oder `start.sh` unter Linux gestartet. Auf dem Mac
kann `start.command` verwendet werden. `python start.py --check` prüft die
Abhängigkeiten. `python start.py --demo` öffnet die Oberfläche für einen Testlauf.

Eine ausführliche, neutrale Projektvorstellung steht in [docs/GITHUB-BESCHREIBUNG.md](docs/GITHUB-BESCHREIBUNG.md).

Weitere Anleitungen liegen im Projekt.

- [Hardware und Tag-Anforderungen](docs/HARDWARE.md)
- [Druckerdienst, SSH und Firmwareupdates](docs/DRUCKERDIENST.md)
- [Rechtliche Hinweise und Quellenherkunft](docs/RECHTLICHES.md)
- [Git-Veröffentlichung und Tests](docs/VEROEFFENTLICHEN.md)
- [Datenspeicherung und Sicherheitsmeldungen](SECURITY.md)
- [Mitwirkung am Projekt](CONTRIBUTING.md)
- [Änderungen dieser Git-Ausgabe](CHANGELOG.md)

Benutzerdaten werden außerhalb des Quellcodes im Benutzerprofil gespeichert.
Eine frische Kopie startet mit leerer Drucker- und Profilzuordnung. Cloudkonto,
eigene Slicerprofile und Zugangsdaten werden von der nutzenden Person eingerichtet.
Das Projekt enthält eigene Symbole und Druckerskizzen sowie lizenzierte
DejaVu-Schriften. Es handelt sich um ein unabhängiges Community-Projekt.


Neue Funktionen: [Mehrere Drucker](docs/MEHRERE-DRUCKER.md),
[Anycubic-Experiment](docs/ANYCUBIC.md) und [Kompatibilität](docs/KOMPATIBILITAET.md).
Creality benötigt für die neuen Desktop-Funktionen keinen neuen Druckerdienst.
Die Bridge 1.1.0 wird nur für den NTAG213-Modus benötigt und niemals automatisch
aufgespielt. Die bisherige Bridge 1.0.0 bleibt für CFS nutzbar.

Ab 3.5.1 werden Anycubic-Druckertyp und Filamentwechsler getrennt ausgewählt.
ACE Pro mit Anschlussvarianten/Upgrade-Kit, beide ACE-2-Pro-Zubehörgruppen und
der integrierte Kobra-X-Wechsler sind eigene Einträge. Kobra 4 und Kobra 3 Max V2
sind ergänzt. Die App unterscheidet dokumentiertes Layout und unbestätigtes
Ziel-Tagformat, alle Anycubic-Geräte bleiben experimentell. Details in
[docs/ANYCUBIC.md](docs/ANYCUBIC.md). Alte Lesezeichen erhalten keine automatische
Zuordnung zu einer Wechslergeneration.

## Änderungen in 3.6.0

Die Arduino-Bauanleitung verwendet die PNG-Anzeige von Tk direkt und funktioniert
auch ohne die separat installierbare Pillow-Komponente ImageTk. Kabelbilder für
beide Boards, Zoom und Widerstandsdetails bleiben vorhanden.

Gespeicherte Drucker nutzen jetzt dieselbe Hauptoberfläche. Anycubic-Wechsler und
Ausführung werden einmal eingerichtet, danach wird nur der Drucker gewählt.
Unbestätigte Formate bleiben ohne ausdrückliche Testfreigabe gesperrt.
SSH-Hilfe und Dienstverwaltung beziehen sich auf den gewählten Drucker; Anycubic
zeigt ausdrücklich an, dass kein SSH-Installer oder Profildienst vorhanden ist.

Die sichtbare Abgleichrichtung ist **Slicer → Drucker**, bei Anycubic **Slicer → Tag**.
**Kein Cloud-Upload:** Ein Profil kann einen Cloud-Ursprung haben, die App schreibt
jedoch nicht in die Hersteller-Cloud und nicht zurück in Slicerdateien.
Installierte Dienstversionen werden je Drucker erfasst. Die mitgelieferte
Dienstversion 2.1.0 und die Bridge 1.1.0 benötigen für diese Ausgabe kein Update.

## Beispielplatte herunterladen · 3.6.1

Unter **Etiketten auswählen & drucken… → Beispielplatte herunterladen… (.3mf)**
oder direkt unter **Hilfe → Beispielplatte herunterladen… (.3mf)** lässt sich die
mitgelieferte Filament-Swatch-Platte offline an einem frei gewählten Ort speichern.
Die vier Muster passen zu den 40 × 30 mm Etiketten. Form und Anordnung entsprechen
der bereitgestellten Platte. Persönliche Profile, Dateipfade, Geräteangaben und
Hersteller-Startcodes sind nicht enthalten. Im Slicer den eigenen Drucker,
Düse, Druckplatte und kalibriertes Filament wählen und neu slicen. Bei kleineren
Druckplatten die Muster neu anordnen.

Das Modell ist ein Fremdmodell von Mr.Brom (Remix), basierend auf 9percent,
mit BY-NC-SA-Lizenzangabe; die bereinigte Ausgabe bleibt separat CC BY-NC-SA.
Details und Quellen: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Die App exportiert keine fertigen Druckbefehle und startet keinen Druck.

## Updates und frühere Versionen

Die freigegebenen Downloads stehen im GitHub-Bereich **Releases**. Dort ist die
neueste Ausgabe markiert; frühere Releases und Quellcode-Tags bleiben abrufbar.
Neue Ausgaben werden nach ausdrücklicher Freigabe über **Actions → Version freigeben**
veröffentlicht. Zuerst laufen die Plattformprüfungen, danach werden portable App,
Weitergabe-ZIP und Quellcode-ZIP mit Prüfsummen hochgeladen. Vorhandene Versionen
werden nicht überschrieben. Details: [Veröffentlichungsablauf](docs/VEROEFFENTLICHEN.md).

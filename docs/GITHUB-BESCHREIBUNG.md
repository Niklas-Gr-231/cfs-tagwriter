# Beschreibung für GitHub

## Kurzbeschreibung

Desktop-Tagwriter für Creality CFS und experimentelle Anycubic-ACE-Tags: Slicerprofile, Rollenzuordnung, geprüfte NFC-Schreibvorgänge und 40 × 30 mm Filamentetiketten.

## Projektübersicht

CFS Tagwriter verbindet eine lokale Desktop-Oberfläche mit einem selbst aufgebauten
Arduino-/RC522-Leser. Filamentinformationen lassen sich lesen, bearbeiten und erst
nach einem ausdrücklichen Schreibauftrag auf passende Tags übertragen. Ein
Schreibvorgang legt eine Sicherung an und prüft das Ergebnis durch Zurücklesen.
Bei einem Fehler zeigt die Oberfläche passend **Erneut lesen** oder **Erneut
schreiben** an. Die Erkennung durch die Druckerfirmware muss anschließend am
jeweiligen Gerät bestätigt werden.

**Versionen:** App 3.8.1, Creality-Druckerdienst 2.1.0, Arduino-Bridge 1.1.0.
Die Komponenten sind unabhängig versioniert. Ein App-Update spielt weder
Druckerdienst noch Arduino-Programm oder Herstellerfirmware automatisch auf.

## Einheitliche Bedienung

Ein Drucker wird einmal mit Modell und Verbindung eingerichtet und danach im
Hauptfenster ausgewählt. Creality und Anycubic verwenden dieselben Felder und
Lese-/Schreibaktionen. Anycubic zeigt zusätzlich die Felder des ACE-Tagformats.
Experimentelle Ziele tragen direkt unter der Schreibaktion einen Hinweis.
Unbekannte Formate werden nicht aufgrund eines ähnlichen Druckernamens als
bestätigt eingestuft. Die Übersicht nennt Druckermodelle, Wechslerfamilien und
den jeweiligen Prüfstand getrennt.

Die Oberfläche bietet ein helles und dunkles Erscheinungsbild, große
aufklappbare Menügruppen, passende Scrollleisten und Fortschrittsanzeigen.
Die lokale Bauanleitung enthält eigene Kabelbilder für Mega und Nano,
Breadboard-Verbindungen, vier getrennte Spannungsteiler sowie Details zu
1-kΩ- und 2-kΩ-Widerständen. Sie benötigt keine Online-Bildquelle.

## Profile und Abgleichrichtung

Gespeicherte Slicerwerte haben beim ausdrücklich bestätigten Abgleich Vorrang.
Die App liest den aktuellen Dateistand beim Öffnen der Abgleichseite und erneut
bei **Erneut synchronisieren**. Neue, geänderte und unveränderte Profile werden
in getrennten Bereichen angezeigt. Die Vorschau muss vor dem Schreiben zum
Drucker bestätigt werden. Eine inzwischen geänderte Quelldatei oder ein
abweichender Zielzustand macht die alte Vorschau ungültig.

Die Richtung ist **Slicer → ausgewählter Creality-Drucker**. Der Zusatzdienst
verwaltet dort eigene Profilzuordnungen und Materialcodes. Ein Cloud-Ursprung
eines Profils ist sichtbar, bedeutet aber keinen Upload in die Hersteller-Cloud.
Die Anwendung bietet keine offizielle Cloud-Schreibschnittstelle und überschreibt
keine Quelldateien des Slicers. Auf einem zweiten Rechner müssen die passenden
Slicerprofile weiterhin vorhanden sein. Ein Etikettenexport ändert keine Profile.

Materialcodes werden pro Creality-Drucker verwaltet. Neue geeignete Profile
können automatisch einen freien Code erhalten; eine manuelle Zuweisung bleibt
als Reservefunktion vorhanden. Import und Export berücksichtigen Modell,
Düsendurchmesser, Profilherkunft und Materialcode-Kollisionen. Profile lassen
sich einzeln oder gemeinsam auswählen. Dateien werden an einem selbst gewählten
Speicherort gespeichert bzw. geöffnet.

## Rollen und Tags

- Freie Restmengen in Gramm; die Restlänge wird passend zum jeweiligen Format angezeigt.
- Beim Lesen werden zuerst die vorhandenen Tagmengen übernommen. Das ist kein
  unabhängiger Messwert des tatsächlich verbrauchten Filaments.
- Optionaler Zwei-Tag-Ablauf: Tag 1 übernimmt alte Daten, Tag 2 behält die danach
  eingestellten Wunschwerte. Beide Tags behalten ihre eigene Hardwarekennung.
- Rollennummern lassen sich bei mehreren Druckern auf diesem Rechner lokal teilen.
  Ein Inventar-Export/-Import ermöglicht die ausdrückliche Übertragung auf andere Rechner.
- Ein Profiltransfer ist nur zwischen kompatiblen Creality-Zielen desselben
  Modells und Düsendurchmessers vorgesehen. Eine Vorschau zeigt neue Codes und
  erforderliches Neubeschreiben bereits vorhandener Tags an.

## Beispielplatte

Die App enthält eine offline speicherbare 3MF-Musterplatte mit vier Filament-
Swatches für 40 × 30 mm Etiketten. **Etiketten auswählen & drucken…** und **Hilfe**
bieten dafür einen eigenen Knopf mit frei wählbarem Speicherort. Die Geometrie
und Anordnung bleiben erhalten; private Profile, Dateipfade und Gerätekennungen
sind entfernt. Eigene Druckeinstellungen müssen vor dem Slicen gewählt werden.
Das Fremdmodell von Mr.Brom / Original 9percent hat eine separate BY-NC-SA-
Lizenzangabe. Zuschreibung und Änderungen stehen in der 3MF und den Fremdhinweisen.

## Creality-Zusatzdienst und Zugriff

Die unterstützten Profilfunktionen benötigen zusätzlich zur Desktop-App einen
Dienst auf dem Creality-Drucker. Die App kann diesen nach bestätigter
SSH-Geräteidentität installieren, prüfen, aktualisieren, reparieren, starten,
stoppen und entfernen. Installierte Dienstversion und letzter bestätigter Stand
werden für jeden Drucker getrennt angezeigt. Ein gespeicherter Stand wird nicht
als aktuelle Erreichbarkeitsprüfung ausgegeben.

Die Installation ermittelt das native Druckermodell und prüft Katalogstruktur,
Düse, Python und Dienststarter. Nicht am Referenzgerät geprüfte Modelle bleiben
experimentell. Ein CFS-/CFS-C-Anschluss allein beweist keine Unterstützung des
Zusatzdienstes. Der Dienst verändert eigene Materialzuordnungen im nativen
Katalog und benutzt Druckerschnittstellen; er flasht keine Drucker- oder
CFS-Firmware. Herstellerupdates können diese Schnittstellen verändern oder
Dienstdateien entfernen. Der App-Start prüft den gespeicherten Firmwarestand und
fordert bei erkannten Änderungen zur manuellen Reparatur auf.

Die SSH-Hilfe berücksichtigt die ausgewählte Modellfamilie. Zugangsdaten werden
am Drucker abgelesen. Die App umgeht keine gesperrte Firmware. Optional lassen
sich Passwörter im System-Schlüsselbund speichern; sie gehören nicht in
Profil- oder Git-Dateien. Die Deinstallation entfernt den eigenen Dienst und
seine Zuordnungen und legt eine Sicherung an.

## Anycubic als Experiment

ACE Pro und ACE 2 Pro verwenden den implementierten, öffentlich dokumentierten
ACE-Tagaufbau für NTAG213. Anschlussvarianten, Zubehörgruppen sowie integrierte
und unbekannte NFC-Wechsler werden getrennt erfasst. Für unbestätigte Zielformate
ist nur ein ausdrücklich freigegebener Test mit dem ACE-Format möglich; diese
Freigabe wird nicht dauerhaft gespeichert. Kein Anycubic-Gerät wurde im Rahmen
dieser Ausgabe praktisch geprüft.

**Es gibt keinen Anycubic-SSH-Installer, keinen Anycubic-Drucker-Profildienst und
keine automatische Anycubic-Cloud-Kalibrierungssynchronisierung.** Gespeicherte
Slicerwerte werden lokal für Tags und Etiketten genutzt. Die Oberfläche zeigt
hier **Slicer → Tag**. SKU und Materialtyp dienen der nativen Zuordnung; Flow,
Pressure Advance und Volumenfluss werden dadurch nicht als eigenes Profil in
der Druckerfirmware installiert. Die lokale Rollennummer ist kein erfundenes
natives ACE-Tagfeld.

## Etiketten

Aus aufgelösten Slicer-/Profilwerten entstehen 40 × 30 mm Etiketten mit
Hersteller, Filamentname und -art, Farbe, Drucker, Düsendurchmesser und Düsentyp.
Temperaturen, Flow, maximaler Volumenfluss, Pressure Advance und Preis werden
übernommen, sofern sie im Profil vorhanden sind. Fehlende Werte werden nicht
als bestätigte Kalibrierung erfunden. Die Druckplatte für die Betttemperatur ist
wählbar. Hi/Ob im Herstellerfeld kennzeichnet High Unicorn bzw. Obsidian.
Die Suche filtert unter anderem Hersteller, Düsentyp, Filamentart und Druckermodell.
Einzelne oder mehrere Etiketten lassen sich als PNG speichern. Der optionale
T50M-Pro-Direktdruck bietet Bluetooth-Verbindung und Rückmeldung; die tatsächliche
Transportunterstützung hängt von Betriebssystem und Gerät ab.

## Voraussetzungen und Plattformen

- Python 3.10 oder neuer mit Tkinter und den Abhängigkeiten in `requirements.txt`.
- Mega2560 R3 oder Nano Classic ATmega328P mit USB-Datenverbindung und RC522.
- Bei 5-V-Boards vier eigene 1-kΩ-/2-kΩ-Spannungsteiler; RC522 mit 3,3 V versorgen.
- CFS: MIFARE Classic 1K mit vier Byte UID. ACE-Testformat: NTAG213 mit sieben Byte UID.
- Für Creality-Druckerprofile: erreichbares Heimnetz und freigegebener Root-/SSH-Zugang.
- Für den Quellcode-Upload: einmaliger Download der Arduino-Werkzeuge und Bibliotheken.
  Bei Problemen lässt sich ein vollständiger Sketch für die Arduino IDE exportieren.

Linux Mint/Ubuntu wird lokal geprüft. Windows und macOS sind als Zielplattformen
vorbereitet; Startdateien, Pfadbehandlung und eine GitHub-Testmatrix liegen bei.
Automatisierte Tests ersetzen keine echten USB-, Bluetooth-, Drucker- und
Tagtests auf jeder Plattform. Der genaue Stand steht in `docs/PRUEFSTAND.md`.
Eine pauschale Plug-and-play-Zusage für alle Drucker wird nicht gegeben.

## Lizenz, Daten und Mitwirkung

Eigener Code und eigene Grafiken stehen unter **PolyForm Noncommercial 1.0.0**.
Nichtkommerzielle Verwendung, Änderungen und Weitergabe richten sich nach dem
vollständigen Lizenztext. Dies ist kein OSI-Open-Source-Projekt mit erlaubter
kommerzieller Nutzung. Fremdkomponenten behalten ihre jeweiligen Lizenzen;
Herkunft und Hinweise stehen in `THIRD_PARTY_NOTICES.md` und `LICENSES/`.
Markennamen dienen der Zuordnung; das Projekt ist nicht vom Druckerhersteller.

Die öffentliche Ausgabe enthält keine Druckerzugänge, Konten, privaten Profile,
Tag-Sicherungen oder benutzerspezifischen Einstellungen. Die Tests verwenden
künstliche Daten und simulierte Geräte. Die Veröffentlichungskontrolle schließt
Laufzeitdateien aus und sucht nach erkennbaren personenbezogenen Angaben.
Fehlermeldungen vor dem Teilen trotzdem um IP-Adressen, Kontokennungen,
Passwörter und private Profilinhalte bereinigen.

Zum Prüfen: `python tools/run_tests.py` und
`python tools/check_publication.py`. Änderungen sollten Kompatibilitätsgrenzen,
Sicherungen, Herkunftsangaben und den getrennten Versionsstand der Komponenten
erhalten. Geräteprüfungen bitte mit Modell, Firmware, Wechsler und Betriebssystem
beschreiben, ohne private Zugangsdaten zu veröffentlichen.

## Vorgeschlagene Themen

`rfid`, `nfc`, `filament`, `creality`, `cfs`, `anycubic`, `arduino`, `rc522`,
`3d-printing`, `python`, `tkinter`, `noncommercial`

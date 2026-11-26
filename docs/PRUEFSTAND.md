# Prüfstand der Git-Ausgabe 3.6.2

Am 26.11.2026 wurde die Git-Ausgabe lokal auf Linux mit Python 3.12 in einer
frischen virtuellen Umgebung geprüft. Die Installation erfolgte ausschließlich
über die enthaltene `requirements-bluetooth.txt` und deren Abhängigkeiten.

| Komponente | Installierter Prüfstand |
| --- | --- |
| pyserial | 3.5 |
| cryptography | 47.0.0 |
| Paramiko | 4.0.0 |
| keyring | 25.7.0 |
| Pillow | 12.3.0 |
| Bleak | 3.1.0 |

Die 176 enthaltenen Tests bestanden. Sie prüfen unter anderem Tagformat,
Schreibprüfung, Restmengen, Zwei-Tag-Ablauf, Firmwareverlauf, Dienstdateierkennung,
Profilimport, Materialcode-Kollisionen, Etiketten und simulierten Bluetoothdruck.
Die Tk-Oberfläche wurde mit temporären Einstellungen im Demo-Modus unter Xvfb
geöffnet und geschlossen. Das Diagnosekommando bestätigte die Kernabhängigkeiten
und die native Druckkompression.

Die bebilderte Bauanleitung wurde mit Mega- und Nano-Auswahl sowie beiden
Helligkeitsmodi geöffnet. Zoom, Einpassen und Detailreiter wurden betätigt und
ohne Tk-Fehler geprüft. Die SVG-Prüfung verbindet die realen Breadboard-Gruppen
und kontrolliert jeden gezeichneten Kabelendpunkt sowie alle acht Widerstände.
Es wurde kein neuer Hardwareaufbau dafür gesteckt.

Die Bridge-Quellen wurden tatsächlich für Mega2560, Nano ATmega328P und
Nano ATmega328P mit altem Bootloader kompiliert. Verwendet wurden Arduino CLI
1.5.1, AVR Core 1.8.8 und MFRC522 1.4.12. Die Quellcode-Uploadsteuerung wurde
mit simuliertem USB-Port und Fehlerfällen geprüft. Ein tatsächlicher USB-Upload
aus dieser Git-Ausgabe wurde dabei nicht durchgeführt.

Die Datenschutzprüfung kontrollierte den Git-Veröffentlichungssatz. Eigene
Profile, Drucker-IP, Kontokennung, Passwortablage, bekannte SSH-Hostschlüssel,
Gerätesicherungen, vorkompilierte Bridge-Dateien und SDK-Caches gehören nicht
zum Quellcodepaket. Die Prüfung ersetzt die manuelle Durchsicht nicht.

Windows und macOS wurden hier nicht auf echten Rechnern ausgeführt. Die
GitHub-Matrix ist vorbereitet und muss nach dem Hochladen tatsächlich laufen.
Physische NFC-/USB- und Bluetooth-Gerätetests auf diesen Systemen stehen aus.
Die Tests prüfen die plattformspezifischen Ablage- und Bibliothekspfade mit
simulierten Betriebssystemangaben. Das ist kein Ersatz für diese Gerätetests.


## Zusätzlicher Prüfstand 3.5.0

162 Tests bestanden, einschließlich eigenständigem ACE-Codec, Sicherung vor dem
Schreiben, NTAG-Schreibschutz, UID-Tausch, Rücklesefehler, Rollenzuordnungen und
modellgebundenem Profiltransfer. Die originale Bridge wurde als C++-Programm mit
simuliertem RC522 für beide Boardvarianten ausgeführt. CFS-Befehle bleiben auf
Sektor 1 beschränkt, NTAG-Schreibbefehle auf Nutzseiten 4–39.

Die echte Bridge 1.1.0 wurde zusätzlich mit AVR Core 1.8.8 und MFRC522 1.4.12 für
Mega2560, Nano und Nano mit altem Bootloader kompiliert. Mega: 11608 Byte Flash,
533 Byte globale RAM-Daten. Nano: 10876 Byte Flash, 461 Byte globale RAM-Daten.
Es wurde kein Arduino und kein Drucker im Rahmen dieses Updates beschrieben.

`tools/smoke_features.py` öffnete und betätigte Menügruppen, Wiederholen-Aktionen,
Drucker-Synchronisierung mit Vorschau/Übernahme, ACE-Zweiermodus, Kompatibilitäts-
übersicht, Einrichtung, Bauanleitung und Etiketten in beiden Designs. Verwendet
wurden ausschließlich synthetische Profile und simulierte USB-/SSH-Antworten.
Schmale Fenster und die scrollbare ACE-Seite wurden geprüft. Keine Tk-Fehler.
Windows/macOS sowie Anycubic- und weitere Creality-Hardware stehen weiterhin aus.

## Wechsler-Erweiterung 3.5.1

170 Tests bestanden. Neue Prüfungen decken Wechslerfamilien/Zubehörgruppen,
Kobra 4 und Kobra 3 Max V2, falsche Druckerzuordnungen, explizite Freigabe für
unbestätigte Formate sowie erhaltene Lesezeichen und Schlüsselbunddaten ab.
Unzulässige Ziele werden vor USB-Zugriff und Sicherung abgewiesen. Oberfläche in
Hell/Dunkel mit ACE-Pro- und ACE-2-Pro-Schreibablauf, integriertem Kobra-X-Testmodus,
gesperrtem Schreiben ohne Testfreigabe und wiederhergestelltem Wechsler geprüft.
Ausschließlich simulierte Geräte. Kein Firmware- oder Hardware-Update durchgeführt.
Bridge bleibt 1.1.0, Druckerdienst 2.1.0, keine neue Laufzeitabhängigkeit.

## Gemeinsame Oberfläche 3.6.0

176 veröffentlichte Tests bestanden, zusätzlich 235 lokale Regressionstests
(ein Test gegen nicht mitgelieferte historische lokale Dateien übersprungen;
isolierte Migrationsfälle separat geprüft). Die grafischen Funktionstests unter Xvfb
betätigten die echten Tk-Widgets in beiden Designs mit künstlichen Profilen und
simulierten Transporten. Abgedeckt wurden:

- Gemeinsame Creality-/Anycubic-Tagoberfläche und gespeicherte Druckerauswahl.
- Zweiermodus mit Übernahme vorhandener Gramm-/Meterwerte und unveränderten
  Wunschwerten beim zweiten Tag; Schreiben mit Rücklesebestätigung.
- Fehlgeschlagene CFS- und ACE-Schreibvorgänge mit Wiederholen-Aktion.
- Wechsel zwischen ACE Pro, ACE 2 Pro und unbestätigtem integriertem Ziel;
  Schreiben ohne ausdrückliche Testfreigabe bleibt gesperrt.
- Import eines gespeicherten Anycubic-Slicerprofils in dieselben Formularfelder,
  bei erhaltener SKU und Restmenge; Etikettenansicht aus diesem Profil.
- Anycubic-Dienstverwaltung ohne freigegebene Creality-Installationsknöpfe und
  passende SSH-Hilfe statt erfundener Anycubic-Zugangsdaten.
- Slicer-Abgleich beim Öffnen und bei erneutem Synchronisieren; getrennte
  Ergebnisgruppen und bestätigte Übernahme mit anschließender Folgeprüfung.
- Menügruppen, Profiltransfer mit Vorschau/Übernahme, Kompatibilitätsübersicht,
  Einrichtung und Etiketten in Hell und Dunkel, auch bei kleinerem Fenster.
- Mega-/Nano-Bauanleitung mit Zoom, Einpassen und Widerstandsdetails zusätzlich
  mit der installierten System-Python-Version ohne Pillow-ImageTk.
- Separate Dienstversionsstände und Deinstallation eines von mehreren Druckern;
  keine Übernahme von Passwortfeldern in diesen Verlauf.

Die neuen Desktop-Funktionen benötigen weder eine neue Bridge noch einen neuen
Druckerdienst. Während dieser Ausgabe wurden keine echten Drucker, Tags oder
Arduinos beschrieben. Windows/macOS und die experimentellen Drucker-/Wechsler-
Kombinationen benötigen weiterhin praktische Gerätetests. Die vorbereitete
GitHub-Matrix ist erst nach einem tatsächlich erfolgreichen Lauf ein CI-Nachweis.

## Beispielplatten-Export 3.6.1 · 27.11.2026

182 veröffentlichte Tests, grafische Durchläufe in Hell und Dunkel sowie
zusätzliche lokale Regressionstests geprüft. Der Download wurde über echte
Oberflächenknöpfe mit frei gewähltem Ziel und abgebrochenem Speicherdialog getestet.
Die 3MF enthält vier eigenständige Mesh-Objekte mit je 364 Punkten und 720
Dreiecken, 92 × 36 × 2 mm, und den ursprünglichen Platzierungen.
Geometrie und Transformationswerte wurden zusätzlich direkt mit der
bereitgestellten Quelldatei verglichen. Es wurde kein neuer physischer Druck
und kein zusätzlicher Windows-/macOS-Gerätetest durchgeführt.

Die Datei ist eine Standard-3MF mit Modell, Paketbeziehungen und Zuschreibung.
Die Prüfung umfasst Referenzen, Mesh-Indizes, Archivintegrität, unveränderten
Export, Fehler beim Ersetzen einer bestehenden Datei und Datenschutz auch
innerhalb des komprimierten 3MF-Archivs. Persönliche Profile, Pfade und Bilder
werden nicht mitverteilt. Die separate Modelllizenz steht in den Fremdhinweisen.

Die ausgegebene 3MF wurde zusätzlich mit lib3mf 2.5.0 im strikten Modus
eingelesen: keine Warnungen, vier gültige, geschlossene und orientierte Meshes.
Diese Bibliothek wurde nur zur Entwicklungskontrolle verwendet und wird für
den App-Betrieb oder Export nicht benötigt.

## GitHub und schnelle Schreibvorgänge 3.6.2

Die erste echte GitHub-Matrix führte die Tests unter Linux, Windows und macOS
mit Python 3.11 und 3.12 aus. Dabei wurden plattformabhängige Testpfade,
Zeilenenden der Lizenzdatei und die virtuelle Bildschirmgröße korrigiert.
Die anschließende Quellcodeprüfung war auf allen sechs Kombinationen erfolgreich.

Eine weitere Windows-Prüfung fand eine mögliche Namenskollision bei sehr schnell
aufeinanderfolgenden Sicherungen. Version 3.6.2 ergänzt dafür eine Zufallskennung
und zwei Regressionstests mit identischer Uhrzeit. Es gibt nun 190 Tests.
Sicherung vor Änderung, exklusives Anlegen und Rückleseprüfung bleiben erhalten.
Windows-/macOS-Softwaretests in GitHub sind keine physischen NFC-/Bluetoothtests.
Der Release-Workflow veröffentlicht nur nach erfolgreichen Prüfungen; der jeweils
aktuelle Stand ist im GitHub-Reiter Actions sichtbar.

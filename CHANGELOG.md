# Änderungen

**3.6.2 · 27.11.2026 · Sicherungen bei schnellen Schreibvorgängen**

- Sicherungsnamen enthalten zusätzlich eine eindeutige Zufallskennung.
  Mehrfaches Beschreiben desselben Tags im selben Uhrzeit-Takt kollidiert
  auch unter Windows nicht mehr mit der vorherigen Sicherungsdatei.
- Gilt für Creality-CFS und den experimentellen ACE-Modus. Bestehende
  Sicherungen bleiben erhalten; eine Sicherung muss vor dem Schreiben gelingen.
- Regressionstests mit festgehaltener Uhrzeit für beide Tagformate.
- GitHub-Freigabe mit automatischen Plattformprüfungen und erhaltenen Releases.
- Druckerdienst 2.1.0 und Arduino-Bridge 1.1.0 bleiben unverändert.


**3.6.1 · 27.11.2026 · Beispielplatte wieder herunterladen**

- Eigener 3MF-Downloadknopf auf der Etiketten-Startseite und unter Hilfe,
  mit frei wählbarem Speicherort und ohne Netzwerk-/Druckerzugriff.
- Vier Muster mit unveränderter Geometrie und Anordnung. Standard-3MF ohne
  persönliche Profile, Dateipfade oder Gerätekennungen; eigene Slicerwerte wählen.
- Fremdmodell, Urheber, separate BY-NC-SA-Lizenz und Änderungen ausgewiesen,
  Zuschreibung auch direkt in der Datei. Offline-Asset in Git und portabler App.
- Export prüft die eingebaute Datei und ersetzt bestehende Zieldateien atomar.
  Neue Export-, Geometrie-, Datenschutz- und Oberflächentests.
- Dienst bleibt 2.1.0, Bridge bleibt 1.1.0; keine Geräteinstallation nötig.


**3.6.0 · 26.11.2026 · Gemeinsame Oberfläche und verlässliche Bauanleitung**

- Bauanleitung ohne optionales Pillow-ImageTk: Tk zeigt die lokalen PNG-Kabelbilder
  direkt. Öffnungsfehler werden als Meldung angezeigt.
- Eine Hauptoberfläche für alle gespeicherten Drucker. Anycubic erhält die ACE-
  Felder im selben Formular, mit experimentellem Hinweis unter dem Schreiben.
- Modell und Wechsler einmal einrichten; beim täglichen Einsatz nur Drucker wählen.
  Unbekannte Formate behalten ihre ausdrückliche, nicht gespeicherte Testfreigabe.
- Druckerwechsel setzt Tagkennung und Zweiergruppe zurück. Anycubic-Aktionen greifen
  nicht auf den zuvor gewählten Creality-Profilkatalog zu.
- Slicer → Drucker bzw. Slicer → Tag stets sichtbar; kein vorgetäuschter Cloud-Upload.
- SSH-Hilfe für jede Modellfamilie, einschließlich klarer Grenzen bei Anycubic
  und unbekannten Geräten. Keine geratenen Passwörter.
- Letzte bestätigte Dienstversion und Status je Druckeradresse gespeichert;
  vor Aktionen ist weiterhin eine aktuelle Prüfung nötig.
- Öffentliche Projektbeschreibung, Datenschutzprüfung und Funktionstests ergänzt.
  Beispiele und simulierte Tags verwenden künstliche Kennungen.
- Dienst bleibt 2.1.0, Bridge bleibt 1.1.0; keine automatische Geräteinstallation.


**3.5.1 · 26.11.2026 · Anycubic-Filamentwechsler getrennt erfassen**

- Eigene Auswahl für ACE Pro einschließlich Anschluss-/Kitvarianten, ACE 2 Pro
  mit beiden Zubehörgruppen, integrierten Kobra-X-Wechsler und unbekannte NFC-Leser.
- Kobra 4 und Kobra 3 Max V2 ergänzt. Druckertyp und Wechsler getrennt gespeichert,
  bestehende Lesezeichen ohne Wechsler bleiben unbestimmt.
- Experimentelles gemeinsames ACE-V2-Layout für ACE Pro und ACE 2 Pro. Kein eigener
  Anycubic-Gerätetest. Integrierte/unbekannte Leser brauchen eine nicht gespeicherte
  Testfreigabe; inkompatible Modelle bleiben gesperrt. Kein erfundener neuer Codec.
- Übersicht unter Hilfe mit Wechsler- und Druckertypreiter. 170 Tests sowie
  reale Tk-Oberfläche in beiden Designs mit simulierten Geräten geprüft.
- Bridge unverändert 1.1.0, Druckerdienst 2.1.0. Keine neue Abhängigkeit, kein
  zusätzlicher Netzwerkabruf, keine Geräte-Firmware geändert.

**3.5.0 · 26.11.2026 · Mehrere Drucker und experimenteller ACE-Modus**

- Pro Drucker getrennte Daten, gemeinsame Rollennummern oder expliziter
  Profiltransfer auf denselben Typ und Düsendurchmesser. Quelle bleibt unverändert.
- Rollenübersicht mit Import/Export, Konfliktprüfung und Erhalt der Tag-Restmenge.
- Druckerhersteller und Druckertyp als zusätzliche Suchfilter für Filamente/Etiketten.
- Große einheitliche Menüknöpfe mit aufklappbaren Aktionen und sichtbare Tag-Ergebnisse.
- Automatische native Modellwahl bei der Dienstinstallation. Andere Creality-Modelle
  sind experimentell gekennzeichnet. Druckerdienst bleibt 2.1.0.
- Experimenteller eigenständiger ACE-Pro-NTAG213-Modus. Kein Anycubic-Druckerdienst,
  keine automatische Übernahme eigener Kalibrierungsprofile in Firmware/Cloud.
- Optionale Bridge 1.1.0 mit getrennten NTAG-Befehlen. CFS funktioniert weiter mit
  1.0.0. Keine automatische Installation. Mega und Nano einschließlich altem
  Bootloader kompiliert, Schutzgrenzen im nativen C++-Test geprüft.
- Nano-RAM für globale Daten: 461/2048 Byte. Neue Seiten/Backends werden erst bei
  Bedarf geladen. Keine neue Python-Laufzeitabhängigkeit, keine Hintergrundscans
  aller Drucker. Alle Netzwerkübertragungen und USB-Operationen bleiben im Worker.

**3.4.3 · 26.11.2026 · Bebilderte Bauanleitung**

- Eigene Kabelbilder für Mega2560 und Nano Classic mit RC522 und Breadboard.
- Vier Spannungsteiler mit jeweils beschrifteten 1-kΩ-/2-kΩ-Widerständen,
  eigene Detailansicht mit Farbringen und genauen Steckbrett-Koordinaten.
- Anleitung in der App mit Zoom, Einpassen und Boardauswahl, offline verfügbar.
- PNG und bearbeitbare SVG-Dateien, Originalgrafiken unter der Projektlizenz.
- 144 automatische Tests erfolgreich, einschließlich elektrischer Prüfung der
  gezeichneten Kabel und Breadboard-Verbindungen. Keine Änderung an Druckerdienst
  oder Arduino-Bridge, kein Hardware-Update erforderlich.

**3.4.2 · 26.11.2026 · Git-Ausgabe**

- Eigenständiger Quellcodeordner auf Basis der Desktop-App 3.4.1.
- Nichtkommerzielle Projektlizenz, Herkunftsnachweise und Fremdlizenztexte.
- Gemeinsamer Start mit Benutzerablage für Windows, Linux und macOS.
- Voraussetzungen, Hardwareanleitung, SSH-Hilfe und Veröffentlichungsprüfung.
- Arduino-Upload kompiliert den mitgelieferten Bridge-Quellcode, wenn keine
  geprüfte vorkompilierte Datei vorhanden ist. Bibliothek und Core werden
  getrennt eingerichtet. Die Bridge behält Version 1.0.0.
- Optionale liblzma-Suche für Windows sowie Intel- und Apple-Silicon-Macs,
  mit ausdrücklich wählbarem Bibliothekspfad.
- Tests mit künstlichen Daten und vorbereitete GitHub-Prüfungen je Plattform.

**3.4.1 · bisherige Desktop-Basis**

- Drucker-Firmwareversion beim Start vergleichen und Dienstverwaltung öffnen,
  wenn nach einem Versionswechsel eine manuelle Neuinstallation ansteht.
- Tatsächliche Dienstdateien und laufenden Prozess prüfen.
- Profilverwaltung, Zwei-Tag-Modus, Etikettenexport, Direktdruck und helle bzw.
  dunkle Darstellung stammen aus dem bisherigen Projektstand.


# Anycubic-Filamentwechsler · experimentell · 3.6.0

Unter **Verbindung → Anycubic-Drucker einrichten…** einmal Modell, tatsächlich
verbauten Wechsler und Ausführung hinterlegen. Anschließend im Hauptfenster
**Drucker auswählen…** verwenden. Lesen, Schreiben, Restmengen und Zweiermodus
stehen in derselben Tagoberfläche wie bei Creality. Der experimentelle Hinweis
steht direkt unter der Schreibaktion. Die SSH-Hilfe erklärt, dass kein
Anycubic-SSH-Installer oder Profildienst bereitgestellt wird.

Die Übersicht steht unter **Hilfe → Drucker & NFC-Filamentwechsler…** im Reiter
**Anycubic-Filamentwechsler**.

## Erfasste Wechsler und Varianten

| Wechsler / RFID-System | Anschluss-/Zubehörgruppe | Stand unseres Tagformats |
| --- | --- | --- |
| ACE Pro | Kobra 3 / Kobra 3 V2 | Experimentell, ACE-Version-2-Layout implementiert |
| ACE Pro | Kobra S1 | Experimentell, gleiches Taglayout |
| ACE Pro | Kobra 3 Max | Experimentell, gleiches Taglayout |
| ACE Pro mit offiziellem Kompatibilitätskit | Kobra-3-Ausführung am Kobra 3 Max | Experimentell, gleiches Taglayout, passendes Kit/Firmware prüfen |
| ACE 2 Pro | Kobra 3 / 3 V2 / 3 Max / 3 Max V2 / Kobra 4 | Experimentell, gemeinsames Taglayout aus unabhängiger Firmwareanalyse dokumentiert |
| ACE 2 Pro | Kobra S1 / S1 Max / Kobra X | Experimentell, gemeinsames Taglayout; andere Zubehör-/Anschlussgruppe |
| Kobra X, integrierter Mehrfarbwechsler mit RFID / ACE Gen 2 | Integriert, keine externe ACE-Box | RFID offiziell beschrieben, Ziel-Tagformat hier noch unbestätigt |
| Anderer / unbekannter Anycubic-NFC-Wechsler | Noch nicht zugeordnet | Nur ausdrücklicher Versuch mit dem bekannten ACE-Testformat |

Dies sind die zum Recherchezeitpunkt **26.11.2026** anhand der unten genannten
Quellen erfassten Familien und Produktvarianten. Anschlusssets sind keine erfundene
neue Taggeneration. Der integrierte Kobra-X-Wechsler und eine externe ACE 2 Pro
am Kobra X sind unterschiedliche Einträge. Ein unbestätigtes Gerät wird nicht
allein aufgrund des Namens oder eines vorhandenen NFC-Lesers als kompatibel ausgegeben.

**Es wurde hier kein Anycubic-Wechsler am echten Gerät getestet.** Das gemeinsame
ACE-Layout ist beim ACE Pro dokumentiert. Eine unabhängige Untersuchung der
ACE-2-Pro-Firmware V1.1.31 beschreibt denselben Header und dasselbe Seitenlayout.
Das ersetzt weder einen Test unserer Tags noch die Prüfung anderer Firmwarestände.
Für den integrierten Kobra-X-Leser ist deshalb keine pauschale Formatfreigabe gesetzt.

## Auswahl und Speichern

1. Tatsächlichen **Filamentwechsler** auswählen. Bei alten Lesezeichen ohne diese
   Angabe bleibt die Auswahl offen, statt automatisch ACE Pro anzunehmen.
2. **Ausführung / Zubehör** prüfen. Die passende Gruppe wird nach dem ausgewählten
   Druckertyp vorgeschlagen. Das ist keine Erkennung der angeschlossenen Hardware.
3. **Druckertyp** und Anycubic-IP prüfen, danach **Drucker übernehmen**.
   Die Wechslerwahl wird im vorhandenen lokalen Drucker-Lesezeichen gespeichert.
4. Über die Druckerauswahl im Hauptfenster auswählen. Wechsler und Variante werden wiederhergestellt.
   Eine neue Auswahl beendet eine laufende Zweiergruppe und verlangt ein erneutes
   Lesen, bevor wieder geschrieben werden kann. Filament-Wunschwerte bleiben erhalten.

Eine nicht passende Kombination, etwa ACE Pro am Kobra X oder die falsche
ACE-2-Pro-Zubehörgruppe, wird abgewiesen. Bei integrierten/unbekannten Lesern ist
Schreiben zunächst gesperrt. Nur **Unbestätigtes Ziel bewusst mit ACE-Testformat ausprobieren** in der Einrichtung gibt diesen Versuch frei. Diese Freigabe wird nicht
im Lesezeichen gespeichert und beim erneuten Laden des Lesezeichens zurückgesetzt. Erfolgreiches
Rücklesen bestätigt ausschließlich die geschriebenen Tagbytes, nicht die Erkennung
im Anycubic-Drucker. Unbekannte Geräte können dadurch mit dem vorhandenen Format
getestet werden, bekommen aber keinen eigenen, angeblich bestätigten Codec.

## Hardware und Schreiben

- Mega2560 oder Nano Classic mit einem RC522, unveränderte Verdrahtung.
- **NTAG213 mit 7-Byte-UID**, keine CFS-MIFARE-Classic-Aufkleber. NTAG215/216 sind
  in diesem Writer weiterhin nicht freigegeben.
- Bridge **1.1.0** manuell über Einstellungen → Arduino aufspielen, falls noch
  1.0.0 installiert ist. Dieses App-Update benötigt keine neuere Bridge als 1.1.0.
- **Tag lesen**, SKU/Material/Farbe, Restmenge, Länge und Temperaturbereiche prüfen,
  dann **Tag schreiben**. Bei einem gesperrten oder geschützten Tag wird nicht geschrieben.
- Vorher wird gesichert, danach vollständig zurückgelesen. UID, Sperr-, Konfigurations-
  und Passwortseiten werden nicht beschrieben. Rückmeldung und Wiederholen-Tasten
  bleiben wie bisher vorhanden.
- Im Zweiermodus übernimmt Tag 1 vorhandene Angaben. Für Tag 2 bleiben die Wunschwerte
  erhalten, einschließlich lokaler Rollennummer. Zeit und Tagnummer stehen in der Meldung.

Eine passende SKU vom Original-Tag übernehmen. Das ist weder ein Creality-Materialcode
noch die ID eines eigenen Slicerprofils. Das native Layout enthält Materialtyp,
Farbe, Temperaturbereiche, Dicke, Menge und Länge. Herstellerkennung bleibt AC.
Die Rollennummer ist bei Anycubic eine lokale UID-Zuordnung. Sie wird nicht in ein
zusätzlich erfundenes natives Tagfeld geschrieben. Ein eigenes Anycubic-Slicerprofil
muss zum ausgewählten Druckertyp passen; bei fehlender Vererbung kann ein Ordner
mit den Systemprofilen gewählt werden. Flow, PA und Volumenfluss bleiben im Slicer.

## Unveränderte Grenzen

**Kein Anycubic-Druckerdienst, keine Anmeldung an der Anycubic-Cloud und keine
vollständige automatische Zuordnung eigener Kalibrierungsprofile im Drucker.**
Die Erweiterung ergänzt Wechslerauswahl, Variantenprüfung und die Verwendung des
bekannten Taglayouts. Es werden weder Drucker- noch Wechsler-Firmware geflasht.
Die normale Creality-Funktion bleibt davon getrennt. Lokale Rollenzuordnungen
können weiter bewusst je Drucker freigegeben und exportiert/importiert werden.

## Quellen und Nachvollziehbarkeit

- [ACE Pro, offizielle Produktseite](https://eu.anycubic.com/products/ace-pro)
- [ACE-Pro-Kit für Kobra 3 Max](https://store.anycubic.com/products/ace-pro-upgrad-kit-bundle)
- [ACE 2 Pro, Modelle und Zubehörgruppen](https://store.anycubic.com/products/ace-2-pro)
- [Kobra X, integriertes Mehrfarbsystem](https://eu.anycubic.com/products/kobra-x-combo-3d-printer)
- [Kobra-X-Handbuch mit RFID-Bedienung](https://wiki.anycubic.com/kobra-x/M02010203-Kobra%20X%E7%94%A8%E6%88%B7%E6%89%8B%E5%86%8C-EN.pdf)
- [Kobra 4 Combo mit ACE 2 Pro](https://store.anycubic.com/pages/kobra-4-combo-new-launch)
- [Kobra 3 Max V2 mit ACE 2 Pro](https://store.anycubic.com/products/kobra-3-max-v2-3d-printer)
- [Öffentliche ACE-Tagformatbeschreibung](https://github.com/Molodos/anycubic-nfc-filament/blob/main/format.md)
- [Unabhängige ACE-2-Pro-RFID-Analyse](https://github.com/Simon-CR/ace2-pro-firmware-research/blob/master/docs/03-rfid-and-tags.md)
- [NXP NTAG213/215/216](https://www.nxp.com/docs/en/data-sheet/NTAG213_215_216.pdf)

Die Quellen dienen als Beleg für Produktgruppen und Protokollfakten. Es wurden
keine fremden Firmwaredateien, Patches, Programme, Dumps oder Bilder übernommen.

Beim Laden eines Slicerprofils steht **Slicer → Tag**: kein Upload zum Drucker oder zur Cloud.

# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Consumable requirements and the user's unverified example product."""
AMAZON_URL='https://www.amazon.de/dp/B0H1ZPL6XB'
TEXT='''WELCHE AUFKLEBER BRAUCHT DIESE BRIDGE?
• MIFARE Classic 1K, 13,56 MHz, ISO/IEC 14443-A.
• UID mit 4 Bytes. Die App zeigt sie beim Lesen als acht Hex-Zeichen an.
• Schreibbarer Datensektor 1 (Blöcke 4–7) mit bekannten Schlüsseln.
• Für neue, leere Tags ist normalerweise der Werksschlüssel FF FF FF FF FF FF vorhanden. Die konkrete Karte zuerst lesen und testen.
NTAG213/215/216, MIFARE Ultralight, 125-kHz-RFID und 7-Byte-UID-Tags passen nicht zu diesem Schreibverfahren. Die UID muss nicht änderbar sein.

VOM NUTZER AUSGEWÄHLTES PRODUKT
Amazon, ASIN B0H1ZPL6XB:
https://www.amazon.de/dp/B0H1ZPL6XB

Dies ist ein Beispiel-Link zu den vom Nutzer ausgewählten Aufklebern, keine bestätigte Kaufempfehlung. Die Produktseite konnte hier nicht verlässlich geprüft werden. Modell, UID-Länge und Schreibbarkeit müssen an der gelieferten Ware geprüft werden. Keine Garantie, dass dieses Angebot bzw. jede gelieferte Charge mit RC522 oder CFS funktioniert. Auch die Antennengröße und Position können die Erkennung beeinflussen.

ERSTER TEST
1. Zuerst die vorhandene Starterset-Karte lesen und mit der Bridge beschreiben. Danach erneut lesen und Materialcode/Farbe/Rollennummer vergleichen.
2. Einen neuen Aufkleber noch lose an den RC522 halten und „Tag lesen“ wählen. MIFARE Classic 1K und vier UID-Bytes prüfen. Wenn er nicht passt, nicht beschreiben.
3. Registriertes Benutzerprofil wählen, Farbe kontrollieren, Restmenge frei in ganzen Gramm oder Metern (z. B. 850 g bzw. 280 m, Gramm ohne Leergewicht der Spule) und Rollennummer setzen. Tag schreiben und bestätigtes Rücklesen abwarten.
4. Erneut lesen und Werte vergleichen; die Umrechnung in ganze Meter kann wenige Gramm Rundung ergeben. Optional vor Tag 1 „Zwei Tags für dieselbe Rolle“ aktivieren: Erstes Lesen übernimmt alte Angaben samt Rollennummer; danach Wunschwerte setzen und schreiben, dann Tag 2 lesen und schreiben. Beim zweiten Lesen bleiben die Wunschwerte erhalten. Die App meldet mit Uhrzeit „Tag 2 gelesen“ und nach erfolgreicher Prüfung „Tag 2 geschrieben und zurückgelesen“. Nach dem ersten geprüften Schreiben sind die gemeinsamen Angaben gesperrt. Jeder Tag wird einzeln gelesen und beschrieben; sein Schlüssel hängt von seiner eigenen UID ab.
5. Aufkleber außen an der Spulenflanke in der Position eines originalen Creality-RFID-Tags befestigen, möglichst am gleichen Radius. Nicht direkt auf Metall kleben. Zunächst wieder ablösbar befestigen und den CFS-Rollenwechsel bei ruhendem Drucker testen.
6. Für freie Fachwahl beide Spulenseiten mit je einem separat beschriebenen Tag bestücken. Die normale CFS besitzt zwei Leser zwischen den Fächern; die Leseseite hängt vom Fach ab. Alte Tags derselben Spule entfernen bzw. nicht gleichzeitig mitlesen lassen.
7. Rolle einlegen, Erkennung und Farbe am Drucker prüfen. Im Slicer wie gewohnt synchronisieren und das zugeordnete Profil sowie Druckwerte kontrollieren. Vor dem ersten Druck prüfen und neu slicen.

PLATZIERUNG UND EINLEGERICHTUNG (NORMALE CFS)
• Auf die flache Außenseite der Spulenflanke kleben, nicht auf Filament, Achsloch oder Lauffläche des äußeren Spulenrands. Die Spule muss frei auf den Rollen laufen.
• Den Abstand zur Achsmitte bzw. zum Außenrand von einer originalen Creality-RFID-Spule übernehmen. Ohne Referenz zuerst provisorisch befestigen und die Lesbarkeit testen. Ein universelles Millimetermaß ist hier nicht bestätigt.
• Auf beiden Seiten je einen Tag an entsprechender radialer Position anbringen. Deshalb muss für unterschiedliche CFS-Fächer nicht eigens die Rolle umgedreht werden. Materialcode, RGB, Menge und Rollennummer auf beiden Tags gleich setzen; UID und daraus berechneter Schlüssel bleiben je Tag verschieden.
• Die Spule aufrecht ins Fach stellen. Die Abwickelrichtung richtet sich nach dem Filamenteinlauf bzw. den Richtungsmarkierungen deiner CFS: Filament soll ohne Kreuzung mit Nachbarspulen, Knick oder Schleife in den Einlauf desselben Fachs laufen. Im Zweifel eine funktionierende Originalrolle in derselben Orientierung als Vorlage verwenden. Die Wickelrichtung nicht nur nach einem Foto von der anderen Spulenseite beurteilen.
• Bei einem runden Tag gibt es kein „NFC muss oben stehen“. Die Spule dreht sich bei der Suche am Leser vorbei; entscheidend sind Spulenseite und Abstand zur Achse. Bei länglichen Antennen die Orientierung der Originaletiketten übernehmen und testen.
• In den CFS-Einstellungen Einlege-Erkennung / automatisches RFID-Lesen einschalten. Nach dem Einlegen die Erkennung abwarten oder RFID-Aktualisieren auslösen. Erst einen ruhenden Test durchführen und danach Material/Farbe am Drucker sowie im Slicer kontrollieren.
• Diese Hinweise beziehen sich auf die normale CFS. Bei CFS-C, CFS Lite oder anderen Nachrüstsystemen deren eigene Ladeanleitung und Leserposition beachten.

WAS AUF DEM TAG STEHT
Materialcode, RGB-Farbe, Filamentmenge und Rollennummer. Vollständige kalibrierte Druckwerte liegen im verknüpften Profil. Bei Änderung der Werte unter derselben Profil-ID muss der Tag normalerweise nicht neu beschrieben werden; bei geändertem Materialcode schon.

PRÜFSTAND
App, Dienst und Datenformat sind geprüft; ein tatsächlicher Schreib-/Lesetest mit dieser Bridge und die anschließende Erkennung eines Rollenaufklebers am CFS stehen noch aus. Arduino-Bridge und Druckerdienst bleiben vorerst bei 1.0.0. Der Test kann zeigen, ob noch eine Anpassung nötig ist.

FORMAT- UND CFS-REFERENZEN
https://store.creality.com/blogs/all/creality-cfs-main-functions-and-workflow
https://www.creality.com/blog/k2-series-use-cfs-to-load-filament
https://github.com/DnG-Crafts/K2-RFID
https://www.nxp.com/docs/en/data-sheet/MF1S50YYX_V1.pdf
'''

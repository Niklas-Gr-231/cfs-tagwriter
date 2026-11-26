# Mehrere Drucker · 3.5.0

Unter **Verbindung → Mehrere Drucker & Synchronisierung…** oder **Profile →
Profile zwischen Druckern synchronisieren…** öffnen. Die großen Schaltflächen
oben klappen die zugehörigen Aktionen im Hauptfenster auf.

## Rollennummern

Für jeden beteiligten Drucker einzeln eine Option wählen und **Auswahl speichern**:

- **Getrennt halten** ist der Standard. Keine gemeinsame Rollenzuordnung für diesen Drucker.
- **Nur Rollennummern teilen** verbindet die physische Rolle über ihre sechsstellige
  Nummer mit den Tagkennungen beider Seiten und den bisherigen Druckerzuordnungen.
- **Rollennummern + Profile gleicher Druckertypen** erlaubt zusätzlich den unten
  beschriebenen Profiltransfer. Die Auswahl selbst schreibt nichts auf den Drucker.

Eine vorhandene CFS-Rollennummer wird immer vom Tag übernommen. Zwei physisch
verschiedene Rollen dürfen trotz gleicher Farbe verschiedene Nummern haben.
Beim Lesen eines Tags kann eine bekannte gemeinsame Rolle das bereits auf diesem
Drucker verwendete Profil auswählen. Weicht sein Materialcode vom Tag ab, zeigt
es das Protokoll an. Zum dauerhaften Umstellen den Tag neu schreiben.
Die **Restmenge und Restlänge kommen weiterhin vom gelesenen Tag**. Der lokale
Rollenbestand erhöht oder korrigiert diese Werte nicht. Er ist keine Live-Abfrage
des Verbrauchs im Drucker. Die beiden Seiten werden im Zweiermodus nacheinander gelesen.

Der Reiter **Gemeinsame Rollennummern** zeigt Nummern, Tagkennungen und zugeordnete
Drucker/Materialcodes. Diese Liste liegt lokal bei den App-Daten. Für einen anderen
PC/Mac lässt sie sich über einen selbst gewählten Speicherort exportieren und
importieren. Widersprüchliche Tagzuordnungen werden abgewiesen. Die örtlichen
Freigaben werden durch einen Import nicht eingeschaltet. Die Exportdatei enthält
IP-Zuordnungen, aber keine Passwörter. Es gibt keinen automatischen Cloud-Abgleich
dieser Rollenliste.

## Profile auf einen zweiten Drucker übertragen

1. Den Drucker mit den gewünschten aktuellen Profilen als Quelle auswählen.
   Neue Änderungen zuerst über den vorhandenen **Slicerprofil-Abgleich** übernehmen.
2. Die Mehrdrucker-Seite öffnen, den Zieldrucker wählen und Profilteilen freigeben.
3. **Quellprofile laden**, eines oder mehrere markieren und das SSH-Passwort des
   Ziels eingeben, falls es nicht im System-Schlüsselbund liegt.
4. **Synchronisierung prüfen** erstellt eine frische Vorschau. Modell und
   Düsendurchmesser müssen übereinstimmen. Quelle und Ziel müssen verschieden sein.
5. **Profile jetzt übertragen** schreibt nur auf das Ziel. Quellprofile, Slicerdateien
   und aktuell gewählter Drucker werden dadurch nicht geändert.

Die Quelle wird vor der Übernahme erneut gelesen. Geänderte Daten oder ein
veränderter Zielzustand machen die Vorschau ungültig. Der bestehende Dienst prüft
Druckzustand, Herkunft, Materialcodes und Slicer-Vorrang. Kollisionen erhalten freie
Codes. Die Vorschau kennzeichnet **Tag neu schreiben**, wenn ein Code abweicht.
Gleiche Rollennummer bedeutet deshalb nicht automatisch gleicher Materialcode.
Bei gemeinsamem Rollenbestand ergänzt eine bestätigte Übertragung fehlende
Zielzuordnungen mit dem bestätigten Zielcode. Bereits bewusst gewählte
Zielprofile bleiben erhalten. Das schreibt den Tag selbst nicht um.

Kalibrierungen werden nicht zwischen verschiedenen Druckermodellen, Düsendurchmessern
oder Herstellern übertragen. Hi/Ob gehört weiterhin zum jeweiligen gespeicherten
Filamentprofil und wird mit dessen Werten übernommen.

Für Anycubic stehen momentan lokale Rollenzuordnungen und der experimentelle
Tagmodus zur Verfügung. Es gibt keinen Anycubic-Profildienst für diesen Transfer.

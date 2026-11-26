# Drucker und Zusatzdienst einrichten

Rechner und Drucker müssen sich im lokalen Netz erreichen können. Am Drucker
den offiziell angebotenen Root-/SSH-Zugang freigeben und das dort angezeigte
Passwort verwenden. Menübezeichnungen und Zugang können mit der Firmware
wechseln. Die App verwendet Benutzer `root` und Port 22.

In **Druckerdienst prüfen / aktualisieren…** Druckermodell bzw. Bezeichnung,
IP-Adresse und Passwort eintragen. **SSH-Identität / Installation prüfen**
wählen und die Geräteidentität kontrollieren. Anschließend den angebotenen
Installations- oder Reparaturknopf verwenden. Das Passwort lässt sich nach
Wunsch im nativen System-Schlüsselbund merken.

Der Zusatzdienst läuft auf dem Linux-System des Druckers. Er verwaltet die
eigenen Materialcode-Zuordnungen in der nativen Datenbank und stellt den
Profilkatalog für die App bereit. Er verwendet Druckerdateien und Schnittstellen.
Seine Versionsnummer ist unabhängig von App und Arduino-Bridge.

**Starten**, **Stoppen** und **Neu starten** richten sich nach dem tatsächlich
erkannten Zustand. **Neu installieren / reparieren** stellt die eigenen
Dienstdateien und gesicherten Zuordnungen wieder her. **Dienst entfernen**
entfernt den Zusatzdienst, dessen Autostart und die von ihm verwalteten
Materialeinträge. Die App legt dafür eine Sicherung an. Die normalen
Druckerfunktionen sollen dabei erhalten bleiben. Verhalten und Dateipfade
müssen nach Firmwareänderungen erneut geprüft werden.

Beim Start der App wird die vollständige Firmwareversion über SSH gelesen.
Die erste erfolgreiche Prüfung speichert einen Vergleichsstand je Drucker.
Bei einer Änderung öffnet sich die Dienstverwaltung und fordert zur manuellen
Neuinstallation auf. Der Hinweis bleibt bestehen, bis eine erfolgreiche
Installation und der laufende Dienst bestätigt sind. Offline oder ohne
SSH-Anmeldung bleibt der alte Vergleichsstand erhalten. Die Ursache steht
im App-Protokoll. Fehlende Dateien werden auch bei vorhandenem Autostart erkannt.

Änderungen an Materialzuordnungen werden durch die vorhandenen Druckstatus-
prüfungen geschützt. Lesen und Schreiben bereits verfügbarer NFC-Daten bleiben
eigenständige Funktionen. Die Firmware von Drucker und CFS wird von dieser
Einrichtung nicht geflasht.

Das Referenzgerät ist der K2 Pro mit CFS. Weitere Modelle müssen die
Kompatibilitätsprüfung für Modell, Düse, native Profilstruktur, Python und
Dienststarter bestehen. Die Option für ungeprüfte Modelle ersetzt keinen
Gerätetest. Eine Cloudregistrierung ist für lokale Profile nicht erforderlich.


## Versionsstand je Drucker

Die App zeigt die mitgelieferte Dienstversion getrennt von der auf dem gewählten
Drucker bestätigten Version. Der letzte bestätigte Stand wird je Adresse lokal
abgelegt und mit Prüfzeit als solcher gekennzeichnet. Er wird nicht als aktueller
Online-Status verwendet. Nach einem Druckerwechsel sind Steuerknöpfe bis zur
neuen Prüfung gesperrt. Eine Installation aktualisiert nur den gewählten Drucker.

## Modellbezogene SSH-Hilfe

**Hilfe → SSH-Zugang am Drucker aktivieren…** erklärt die ausgewählte K2-, K1-
oder Hi-Familie. Maßgeblich sind die am Gerät angezeigten Zugangsdaten. Bei einem
unbekannten Modell ist kein Freischaltweg bestätigt. Die Hilfe steht auch bei
Anycubic zur Verfügung und erklärt dort die fehlende SSH-/Profildienstintegration.
Die Anycubic-Dienstknöpfe bleiben gesperrt; die Arduino-Verwaltung bleibt nutzbar.

Das K1-Freischaltmenü ist in den offiziellen
[Creality-Releasehinweisen](https://github.com/CrealityOfficial/K1_Series_Klipper/releases)
beschrieben. Modellhandbücher: [Creality Wiki](https://wiki.creality.com/).

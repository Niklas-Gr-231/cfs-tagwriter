# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""First-use information, shown once per persistent user data directory."""
NOTICE = '''Lizenz und Weitergabe

Eigener Projektcode unter PolyForm Noncommercial 1.0.0. Nutzung, Änderungen und Weitergabe für nichtkommerzielle Zwecke sind nach den Lizenzbedingungen gestattet. Fremdkomponenten behalten ihre eigenen Lizenzen. Vollständige Bedingungen und Hinweise stehen in LICENSE und THIRD_PARTY_NOTICES.md.
https://polyformproject.org/licenses/noncommercial/1.0.0

Zusätzlicher Dienst auf dem Drucker

Für die automatische Zuordnung eigener RFID-Materialcodes wird ein zusätzliches Programm auf dem Drucker installiert. Die App richtet diesen Dienst erst nach deiner Auswahl ein. Dafür wird Root-/SSH-Zugriff benötigt. Dabei werden sein Autostart und eigene Einträge in der Materialdatenbank angelegt.

Lokale Profile können ohne Cloudkonto verwendet werden. Cloudprofile und lokale Profile können auf demselben Drucker parallel vorhanden sein; die App zeigt ihre Herkunft an. Der NFC-Tag enthält den Materialcode und Rollenangaben. Die passenden Profilwerte müssen auf dem Drucker vorhanden sein; vollständige Slicer-Einstellungen werden nicht allein durch den Tag übertragen.

Der Zusatzdienst lässt sich in der App stoppen, reparieren und wieder entfernen. Beim Entfernen werden seine eigenen Materialeinträge entfernt; Cloud-Originalprofile und die übrigen Druckerdaten bleiben erhalten. Eigene RFID-Codes werden danach nicht mehr zugeordnet. Sicherungen werden aufbewahrt.

Der Dienst ist ein separates Programm. Er ersetzt oder flasht keine Drucker- oder CFS-Firmware. Er nutzt aber deren Dateien und Schnittstellen: Firmwareupdates können deshalb Anpassungen oder eine erneute Einrichtung erforderlich machen. Der Arduino-Upload ersetzt ausschließlich den Sketch auf dem ausgewählten Arduino.

Nutzung und Haftung

Dies ist ein privates Hilfsprogramm und kein offizielles Creality-Produkt. Es wird ohne freiwillige Garantie für Fehlerfreiheit, Verfügbarkeit oder Eignung für jeden Drucker bereitgestellt. Nutze es eigenverantwortlich, prüfe Verdrahtung und Druckwerte und bewahre Sicherungen auf. Eine pauschale Kompatibilität mit allen Creality-Druckern wird nicht zugesagt.

Im rechtlich zulässigen Umfang ist die Haftung für leicht fahrlässig verursachte Schäden ausgeschlossen. Bei Verletzung wesentlicher Vertragspflichten bleibt eine Haftung für den vorhersehbaren, vertragstypischen Schaden bestehen. Unberührt bleiben insbesondere Haftung für Vorsatz und grobe Fahrlässigkeit, für Verletzung von Leben, Körper oder Gesundheit, zwingende Produkthaftung und übernommene Garantien. Sonstige zwingende gesetzliche Rechte werden nicht eingeschränkt.

Dieser Hinweis wird nach „Verstanden und weiter“ nur einmal pro Benutzerablage automatisch angezeigt. Die Bestätigung speichert keine Zugangsdaten und installiert noch nichts auf dem Drucker.
'''

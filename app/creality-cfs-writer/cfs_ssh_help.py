# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Model-aware access guidance; no password guesses or automatic rooting."""
from cfs_compatibility import model_info, CREALITY


def help_text(address='', model='F012'):
    info = model_info(model)
    title = info['manufacturer']+' '+info['model']
    if info['manufacturer'] == 'Anycubic':
        return title.upper()+''' · ZUGANG UND UNTERSTÜTZUNG

Für dieses Anycubic-Modell stellt der Tagwriter keinen SSH-Installer und keinen
Drucker-Profildienst bereit. Es gibt hier kein allgemeines Root-Passwort und
keine bestätigte Freischaltanleitung. Keine Creality-Zugangsdaten verwenden.

Was funktioniert experimentell:
• Drucker und tatsächlich verbauten NFC-Wechsler einmal hinterlegen.
• Im gemeinsamen Hauptfenster den Drucker auswählen.
• Unterstützte ACE-NTAG213 über den angeschlossenen Arduino lesen, schreiben
  und durch Zurücklesen prüfen. Bridge 1.1.0 ist dafür erforderlich.
• Gespeicherte Slicerwerte lokal laden. Cloud und Druckerprofile werden dabei
  nicht geändert; eigene Kalibrierungen bleiben im Slicer.

ACE Pro und ACE 2 Pro: dokumentiertes gemeinsames Testformat.
Integrierte oder unbekannte Leser: Format nicht bestätigt, Schreiben gesperrt.
Die Bauanleitung steht unter Hilfe → Arduino-Bauanleitung.
Eine erfolgreiche Tagprüfung ist noch kein bestätigter Gerätetest am Drucker.

Modell-/Wechslerübersicht: https://store.anycubic.com/products/ace-2-pro
Hersteller-Anleitungen: https://wiki.anycubic.com/
'''
    if info['manufacturer'] != 'Creality' or info['model'] not in CREALITY:
        return title.upper()+''' · MODELL NOCH NICHT BESTÄTIGT

Zuerst den richtigen Drucker auswählen bzw. in der Dienstverwaltung prüfen.
Für ein unbekanntes Modell gibt es keine bestätigte SSH-Freischaltanleitung.
Die App umgeht keine Zugriffssperre. Druckertyp, Firmware und die Anleitung des
Herstellers prüfen. Ein Cloud-Konto ersetzt keinen lokalen SSH-Zugang.

Modellspezifische Anleitungen: https://wiki.creality.com/
'''
    family = 'K1-Serie' if info['model'].startswith('K1') else 'Creality Hi' if info['model'] == 'Hi' else 'K2-Serie'
    sources = ('https://github.com/CrealityOfficial/K1_Series_Klipper/releases' if family == 'K1-Serie' else
               'https://wiki.creality.com/creality_hi/f018_%E8%AF%B4%E6%98%8E%E4%B9%A6_%E8%8B%B1%E6%96%87_1030.pdf' if family == 'Creality Hi' else 'https://wiki.creality.com/en/k2-flagship-series')
    return f'''{title.upper()} · ROOT / SSH ({family})

1. AM DRUCKER FREISCHALTEN
Am Touchscreen Einstellungen → Root-Kontoinformationen / Root account
information öffnen. Je nach Modell/Firmware befindet sich der Punkt unter
Allgemein oder System. Den Hinweis vollständig lesen, die angezeigte Wartezeit
abwarten und am Drucker zustimmen. Die dort angezeigten Zugangsdaten verwenden.
Wenn der Zugriff bereits funktioniert, ist keine erneute Freischaltung nötig.
Fehlt dieser Punkt, die Anleitung zur genauen Modell-/Firmwareversion prüfen.
Die App aktiviert Root/SSH nicht automatisch und installiert keine fremde Firmware.

2. ADRESSE UND PASSWORT
Unter Einstellungen → Netzwerk die lokale IP-Adresse ablesen. Rechner und
Drucker müssen im selben erreichbaren Netz sein. Benutzer: root, Port: 22.
Maßgeblich ist das am Drucker angezeigte bzw. selbst geänderte Passwort,
nicht das Cloud-Passwort und nicht das Passwort eines anderen Modells.

3. IM TAGWRITER EINRICHTEN
Einstellungen → Druckersoftware und Dienstverwaltung öffnen. Genau diesen
Drucker auswählen. IP und Passwort eintragen, dann „SSH-Identität / Installation
prüfen“. Adresse und Host-Fingerprint kontrollieren. Danach Installieren bzw.
Neu installieren / reparieren. Die App bestimmt das Modell vor der Installation
anhand des nativen Druckerkatalogs. Ungeprüfte Modelle sind experimentell.
SSH-Zugang allein beweist keine CFS-/NFC- oder Profildienst-Kompatibilität.

OPTIONALER TERMINALTEST (Linux / macOS / Windows mit OpenSSH)
ssh root@{address or '<Drucker-IP>'}
Bei der ersten Verbindung Hostschlüssel prüfen. Beim Eingeben des Passworts
werden keine Zeichen angezeigt. Mit „exit“ die Sitzung verlassen.

PASSWORT MERKEN
Ohne Häkchen bleibt das Passwort nur für den Vorgang im Arbeitsspeicher.
Mit „Passwort merken“ wird es im System-Schlüsselbund abgelegt. „Passwort
löschen“ entfernt diese Kopie. Keine Klartext-Passwörter in Verbindungsdateien.

DIENST UND UPDATES
Die App installiert einen zusätzlichen, entfernbaren Dienst auf genau dem
gewählten Creality-Drucker. Sie flasht keine Drucker- oder CFS-Firmware.
Installierte Version und Status werden pro Drucker geprüft. Nach einem
Firmwareupdate kann eine manuelle Neuinstallation des Dienstes nötig sein.
Die App aktualisiert andere Drucker dabei nicht automatisch.

FEHLER
Connection refused: Root/SSH und Port 22 prüfen.
Zeitüberschreitung: IP, eingeschalteten Drucker und Netzwerk prüfen.
Authentication failed: Benutzer und aktuelles Druckerpasswort prüfen.
Hostschlüssel geändert: Geräteidentität vor dem Bestätigen kontrollieren.

QUELLEN UND MODELLANLEITUNGEN
{sources}
https://wiki.creality.com/
'''

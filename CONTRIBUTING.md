# Mitwirken

Änderungen zunächst mit künstlichen Profilen und `--demo` prüfen. Für Gerätetests
Betriebssystem, Pythonversion, Druckermodell, Firmware und verwendete Bridge
angeben. Ein Test auf Linux ersetzt den Test einer Bluetooth-Verbindung auf
Windows oder macOS nicht.

Eigene Beiträge werden unter der Projektlizenz PolyForm Noncommercial 1.0.0
eingereicht. Bereits vorhandene Rechte und Hinweise an Fremdcode bleiben
erhalten. Nur Beiträge einreichen, für die die erforderlichen Rechte vorliegen.
Für neue Fremdkomponenten Herkunft, exakte Version und Lizenz dokumentieren.
Code aus einer Quelle ohne klare Lizenz erst nach Klärung der Berechtigung
übernehmen. Personenbezogene Profile und Gerätezugänge durch Testdaten ersetzen.

Die Tests laufen mit `python tools/run_tests.py`. Der Veröffentlichungscheck
läuft mit `python tools/check_publication.py`. Versionsnummern für App,
Druckerdienst und Arduino-Bridge werden getrennt gepflegt. Bei einer Änderung
den passenden Abschnitt in `CHANGELOG.md` ergänzen.


## Verdrahtungsbilder bearbeiten

Die Originalzeichnungen entstehen mit `python tools/render_wiring.py` als SVG.
Für zusätzlich gerenderte PNGs in einer Entwicklungsumgebung
`python -m pip install -r requirements-artwork.txt` und danach
`python tools/render_wiring.py --png` ausführen. CairoSVG benötigt systemseitig
Cairo. Es gehört nicht zu den Voraussetzungen für die App, dort liest Pillow die
mitgelieferten PNGs. Nach Änderungen `python tools/run_tests.py` ausführen.
Die Tests prüfen die tatsächlichen gezeichneten Anschlüsse elektrisch.

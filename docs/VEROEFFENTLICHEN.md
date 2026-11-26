# Git-Veröffentlichung und Prüfung

Der Projektordner enthält den öffentlichen Quellcode, Dokumentation und
künstliche Tests. Die erste Git-Historie soll aus genau diesem Ordner entstehen.
Ein gemeinsames Arbeitsverzeichnis mit echten Druckerdateien gehört nicht in
die neue Historie. `.gitignore` schützt vor typischen Laufzeitdateien.

Vor einer Veröffentlichung die folgenden Prüfungen ausführen.

```sh
python start.py --check
python tools/run_tests.py
git init -b main
git add .
python tools/check_publication.py
git diff --cached --stat
```

Die Prüfung verlangt einen zum Index passenden Arbeitsstand. Die automatische
Datenschutzprüfung erkennt bestimmte Gerätekonfigurationen,
private Schlüssel, persönliche Home-Pfade und private Netzwerkadressen. Sie
ersetzt die Durchsicht des tatsächlichen Veröffentlichungsinhalts nicht.
Die feste AES-Konstante des kompatiblen Tagformats und künstliche Testschlüssel
sind absichtliche Protokollbestandteile. Persönliche SSH-Zugänge werden separat
im Schlüsselbund gespeichert.

Der Ordner ist für einen ersten Commit vorbereitet. Mit der eigenen
Git-Identität einen Commit erstellen, ein leeres Repository im gewünschten
Git-Host anlegen und dessen URL hinzufügen. Die Beispiel-URL durch die eigene
Adresse ersetzen.

```sh
git commit -m "Initial source release 3.6.1"
git remote add origin https://github.com/DEIN-NAME/cfs-tagwriter.git
git push -u origin main
```

Beim Anlegen des leeren Zielrepositorys keine zusätzliche Lizenzdatei erzeugen.
Die bereits enthaltene Projektlizenz und die Ausnahmen für Fremdkomponenten
gehören zusammen. Vorher gegebenenfalls erforderliche Betreiberangaben und
einen privaten Meldeweg für Sicherheitsprobleme einrichten. Ergänzende rechtliche
Punkte stehen in `docs/RECHTLICHES.md`.

Die GitHub-Prüfung unter `.github/workflows/tests.yml` ist vorbereitet. Sie
installiert die Abhängigkeiten und führt die Tests auf Linux, Windows und
macOS aus. Auf Linux wird zusätzlich die echte Tk-Oberfläche im Demo-Modus
geöffnet. Hardwarezugriffe werden in diesen Tests durch simulierte Geräte
ersetzt. Tests für die optionale Druckkompression werden bei fehlender liblzma
als übersprungen ausgewiesen. Ein erfolgreicher CI-Lauf muss im neuen
Repository tatsächlich abgewartet werden.

Ein geprüftes ZIP lässt sich mit frei gewähltem Ziel außerhalb des Repositorys
erstellen. Der Export enthält die Lizenztexte und erzeugt eine Prüfsummendatei.

```sh
python tools/build_release.py ../cfs-tagwriter-source.zip
```

Das Repository enthält keine mit fremden Bibliotheken gelinkten AVR-Binärdateien.
Wenn solche Dateien später als Download angeboten werden, sind insbesondere
die Lizenz- und Quelltextpflichten des verwendeten Arduino-Cores zu erfüllen.


## Freigabe auf Zuruf und ältere Versionen

Die Arbeitsvereinbarung steht in `AGENTS.md`: Neue Änderungen werden lokal
vorbereitet. Erst die ausdrückliche Freigabe „für Git freigeben“ beauftragt die
Veröffentlichung des geprüften Stands. Es gibt keinen Zeitplan, der unfreigegebene
Änderungen eigenständig hochlädt.

Nach der Freigabe Commit übertragen und im GitHub-Reiter **Actions** den Workflow
**Version freigeben** starten. Den zur App-Version passenden Tag eintragen,
beispielsweise `v3.6.1`. Der Workflow prüft die Version, startet die Tests unter
Linux, Windows und macOS und baut erst danach die Download-Dateien. Scheitert
eine Prüfung, wird kein fertiges Release veröffentlicht. Alternativ löst ein
bewusst gepushter Versionstag denselben Ablauf aus.

Ein Release enthält die portable Python-App, ein Weitergabe-ZIP mit Startdateien,
Quellcode-ZIP, Änderungshinweise und SHA-256-Prüfsummen. Der Workflow verwendet
nur den kurzlebigen, auf dieses Repository bezogenen GitHub-Token. Kein
persönlicher Zugriffstoken und kein Druckerpasswort ist dafür im Projekt nötig.
Schreibrechte werden nur dem abschließenden Veröffentlichungsjob gegeben.

Das neueste Release wird als **Latest** markiert. Alle früheren Releases und
Tags bleiben erhalten und können weiterhin heruntergeladen werden. Bestehende
Versionen werden nicht überschrieben; Korrekturen brauchen eine neue Version.
Ein fehlgeschlagener Upload kann einen als solchen sichtbaren Entwurf hinterlassen.
Dieser ist noch keine veröffentlichte Version und darf nicht als erfolgreich
vermeldet werden. Den Fehler beheben, bevor ein neuer Veröffentlichungsversuch
beauftragt wird.

Historische Versionen aus der Zeit vor diesem Git-Repository werden nur dann
nachträglich veröffentlicht, wenn ihre tatsächlichen bereinigten Quelldateien
und Lizenzhinweise noch vorliegen. Ein altes Versionsetikett auf aktuellem Code
wäre kein korrekter Vorgängerstand.

Lokal lassen sich die identischen Dateien vorbereiten, ohne etwas hochzuladen:

```sh
python tools/build_distribution.py ../release-assets --tag v3.6.1
```

Der Zielordner muss leer sein und außerhalb des Repositorys liegen. Ein solcher
lokaler Bau ist keine Erlaubnis, die Dateien öffentlich hochzuladen.

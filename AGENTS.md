# Projektpflege und Veröffentlichungen

Dieses Verzeichnis ist die veröffentlichbare Quelle des CFS Tagwriters.
Benutzerprofile, Druckerzugänge, Gerätedumps und lokale Arbeitsverzeichnisse
gehören nicht hierher und dürfen nicht in Commits oder Release-Dateien gelangen.

## Freigabe durch die betreuende Person

- Änderungen zunächst lokal umsetzen und passend prüfen.
- Eine neue Veröffentlichung erfolgt erst nach einer ausdrücklichen Anweisung
  wie „für Git freigeben“. Eine reine Änderungsanfrage ist keine Freigabe.
- Eine ausdrückliche Erstanweisung zum Erstellen und Veröffentlichen dieses
  Repositorys gilt als Freigabe der dafür vorbereiteten Erstversion.
- Bei Freigabe Versionsnummer, Änderungsbeschreibung, Tests, Datenschutz und
  Lizenzhinweise prüfen; dann Commit zum vorgesehenen Repository übertragen.
- Ein neues Release über den Workflow „Version freigeben“ mit dem passenden
  Tag `vX.Y.Z` erstellen. Alternativ löst ein bewusst gepushter Versionstag
  denselben Ablauf aus. GitHub führt die Plattformprüfungen vor dem Upload aus.
- Erfolgreiche Veröffentlichung, Dateien und Prüfergebnisse tatsächlich prüfen.
  Nicht behaupten, eine lediglich vorbereitete oder fehlgeschlagene Version sei online.
- Bestehende veröffentlichte Tags und Release-Dateien nicht überschreiben,
  verschieben oder löschen. Korrekturen erhalten eine neue Versionsnummer.
- Alte Versionen bleiben über Releases und Tags abrufbar. Historische Stände
  dürfen nicht nachträglich aus dem aktuellen Code rekonstruiert werden.

## Komponentenversionen

App, Druckerdienst und Arduino-Bridge bleiben getrennt versioniert.
Eine reine Änderung an Dokumentation oder dem Veröffentlichungsablauf braucht
keine Änderung der App-Version. Geräte werden durch einen Git-Upload nicht
aktualisiert. Neue App-Versionen nach Umfang erhöhen (Patch, Minor, Major).

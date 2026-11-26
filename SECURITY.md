# Daten und Sicherheitsmeldungen

Drucker-IP, Gerätename, Profilzuordnungen, Firmwareverlauf und Sicherungen
liegen in der lokalen Benutzerablage. Ein freiwillig gemerktes SSH-Passwort
liegt im System-Schlüsselbund. Die App greift über das lokale Netz mit den
eingegebenen Root-Rechten auf den Drucker zu. Der Profilkatalog kann im lokalen
Netz über Moonraker erreichbar sein und Profilnamen sowie Werte enthalten.
Der Druckerzugang sollte auf das eigene vertrauenswürdige Netz begrenzt bleiben.

Die App enthält keine eigene Telemetrie oder zentrale Kontenverwaltung.
Internetzugriffe entstehen durch angeforderte Installationen von Python-Paketen
und Arduino-Werkzeugen. Creality-Cloudverbindungen und deren Datenschutz
richten sich zusätzlich nach Slicer, Drucker und Herstellerkonto.

Vor einem Fehlerbericht Protokolle und Bilder auf IP-Adressen, Kontokennungen,
Passwörter, Profilinhalte und Dateipfade prüfen. Private Schlüssel, vollständige
Benutzerablagen und echte Profilarchive gehören nicht in öffentliche Issues.

Für sensible Schwachstellen nach Veröffentlichung die private Meldefunktion
des gewählten Git-Hosts verwenden, sofern der Betreiber sie eingerichtet hat.
Der Betreiber muss diesen Meldeweg vor einer öffentlichen Veröffentlichung
aktivieren oder eine eigene erreichbare Kontaktmöglichkeit ergänzen.


# Technische Referenzen

Herkunft und Lizenzen sind im Projekt unter
[THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md) dokumentiert.

- [MIFARE Classic EV1 1K](https://www.nxp.com/docs/en/data-sheet/MF1S50YYX_V1.pdf)
- [MFRC522-Datenblatt](https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf)
- [K2-RFID-Formatreferenz](https://github.com/DnG-Crafts/K2-RFID)
- [MFRC522-Bibliothek 1.4.12](https://github.com/miguelbalboa/rfid/tree/1.4.12)
- [Katasymbol-Protokollreferenz](https://github.com/khromov/supvan-katasymbol-printer-web-ui/tree/b3799ffba1efca180a631d0691d1a9162d2e1853)
- [Moonraker-API](https://moonraker.readthedocs.io/en/latest/external_api/printer/)

Der kompatible Rollendatensatz umfasst 48 ASCII-Zeichen mit Materialcode,
RGB-Farbe, Länge, Rollennummer und festen Formatfeldern. Die drei
AES-128-ECB-Blöcke liegen in Sektor 1. Die Authentifizierung wird aus der
vier Byte langen UID abgeleitet. Andere Sektoren werden durch die Bridge
nicht zum freien Schreiben angeboten. Die Grammangabe verwendet die bestehende
Referenzumrechnung von 330 Metern pro Kilogramm und kann runden.

Vollständige Druckwerte liegen im verknüpften Profil. Die Hi-/Ob-Erkennung
ist eine Namenskonvention der Profile. Sie ersetzt keine Kalibrierung.

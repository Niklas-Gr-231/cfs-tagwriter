# Drucker-Kompatibilität · Stand 26.11.2026

Die App zeigt denselben Stand unter **Hilfe → Drucker & NFC-Filamentwechsler…**. Hersteller-Hardwarekompatibilität ist kein Gerätetest unseres Dienstes.

| Hersteller / Modell | Status des Tagwriters |
| --- | --- |
| Creality K2 Pro mit CFS | Bisheriges Referenzgerät, Dienst und CFS-Zuordnung im Projektbetrieb getestet. Neue Desktop-Funktionen sind zunächst simuliert geprüft. |
| Creality K2, K2 Plus, Hi mit passender CFS | Experimentell. Native Struktur- und Laufzeitprüfung vor Installation. |
| Creality K1, K1 SE, K1C, K1 Max, K1C 2025, K1 Max 2025 mit passendem CFS-/CFS-C-Kit | Experimentell. Ein unnachgerüsteter K1 wird dadurch nicht zum CFS-Drucker. |
| Weitere native Creality-CFS-Modelle | Experimentell nur nach eindeutiger Modell-, Katalog-, Düsen-, Python- und Dienststarterprüfung. Unbekannte Strukturen werden abgewiesen. |
| Anycubic Kobra 3, 3 V2, 3 Max, 3 Max V2, 4, S1, S1 Max, X mit ACE | Experimenteller NTAG213-Tagmodus. Kein Profildienst, kein Cloudzugriff. Ungetestet am Gerät. Gemeinsames ACE-Pro-/ACE-2-Pro-Layout dokumentiert; integrierter Kobra-X-Leser bleibt ein unbestätigter Formattest. |

Das **Druckermodell des Creality-Dienstes wird automatisch aus dem nativen
Materialkatalog bestimmt**. Es wird keine manuell gewählte Modellkennung in den
Dienst geschrieben. Abweichende Modelle im Katalog, eine nicht passende Düse,
fehlendes Python oder ein unbekannter Dienststarter verhindern die Installation.
Nur der K2 Pro ist als Referenzgerät gekennzeichnet. Andere Modelle erfordern die
sichtbare Freigabe für ungeprüfte Creality-CFS-Modelle. Der Drucker muss die
passende CFS-/NFC-Hardware und Firmware selbst bereits mitbringen.

Anycubic-Lesezeichen sind selbst eingetragen und entsprechend nicht als automatisch
erkannte Geräte ausgegeben. Auf Anycubic wird kein Creality-Dienst installiert.

Unter Windows und macOS sind App, Dateipfade, USB und SSH plattformübergreifend
vorbereitet. Die neue Hardwarefunktion und die tatsächlichen Geräteverbindungen
wurden hier auf diesen Betriebssystemen nicht getestet.

- [Creality K2/CFS](https://www.creality.com/eu/products/k2-series-3d-printer)
- [Creality CFS-C mit offizieller Modellliste](https://www.creality.com/products/cfs-c-smart-filament-system)
- [Anycubic ACE Pro](https://eu.anycubic.com/products/ace-pro)
- [Anycubic ACE 2 Pro](https://store.anycubic.com/products/ace-2-pro)

Der neue Reiter **Anycubic-Filamentwechsler** trennt ACE Pro und seine
Anschlussvarianten/Upgrade-Kit, ACE 2 Pro mit beiden offiziellen Zubehörgruppen,
den integrierten Kobra-X-Wechsler und einen unbekannten NFC-Wechsler.
Siehe [ANYCUBIC.md](ANYCUBIC.md) für die quellengestützte Variantenliste und
Formatfreigaben. Keine automatische Hardwareerkennung, keine Firmware-Patches.

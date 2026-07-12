# Fiesta Online Discord Bot – Stand vor Statistik

Diese Version enthält:

- Ini-System
- frei wählbare Start- und Endzeiten mit Minuten pro Wochentag
- überschneidende Zeitfenster sind erlaubt
- Anmeldung, Abmeldung, Namensänderung und Reset
- Bewerbungssystem
- privates Support-/Frage-System
- dauerhafte Speicherung über `/app/data/fiesta_data.json`

Nicht enthalten:

- Monatsstatistik
- persönliche Statistiken
- Auszeichnungen
- Ini-Start-/Ende-Statistik
- Import alter Run-Zahlen

## Railway Variables

- `DISCORD_TOKEN`
- `SUPPORT_PANEL_CHANNEL_ID`
- `SUPPORT_CATEGORY_ID`

## Railway Volume

Mount Path:

`/app/data`

Hinweis: Bereits vorhandene Statistik-Felder in einer alten `fiesta_data.json` werden von dieser Version ignoriert.

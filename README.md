# Fiesta Online Discord Bot

Diese Version basiert direkt auf dem aktuell hochgeladenen Bot.

## Neu

### Zusätzliche freie Ini-Termine

Admin-Befehl:

`/ini termin_hinzufuegen`

Der Admin wählt den Wochentag und trägt Uhrzeit sowie Ini-Namen frei ein.

Beispiele:

- `19:30 — Karen`
- `ab 20 Uhr — Wald Gruppe 2`
- `21:15 — Kalzar / Stammgruppe`

Löschen:

`/ini termin_loeschen`

Ein Termin kann nur gelöscht werden, wenn dort keine Anmeldungen vorhanden sind.

### Abmelden repariert

Beim Abmelden wird der vorhandene Eintrag direkt aus einem Dropdown gewählt. Eine exakte erneute Eingabe des Namens ist nicht mehr nötig.

Damit funktionieren auch Einträge wie:

`Zaubi - Ryu und noch etwas`

## Unverändert enthalten

- bestehendes Ini-System
- freie Zeitfenster pro Wochentag
- Bewerbungssystem
- privates Support-System
- Logs
- Railway-Volume-Speicherung

## Railway

Variablen:

- `DISCORD_TOKEN`
- `SUPPORT_PANEL_CHANNEL_ID`
- `SUPPORT_CATEGORY_ID`

Volume Mount Path:

`/app/data`

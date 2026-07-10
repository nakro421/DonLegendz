# Fiesta Online Discord Bot

## Railway

1. Dateien in dein GitHub-Repository hochladen.
2. Railway-Variable setzen:
   - `DISCORD_TOKEN`
3. Railway Volume einrichten:
   - Mount Path: `/app/data`
4. Neu deployen.

## Freie Ini-Uhrzeiten pro Tag

### Hinzufügen
`/ini uhrzeit_hinzufuegen`

Tag auswählen, danach im Modal Start- und Endzeit im Format `HH:MM` eintragen.

Beispiel:
- Start: `19:15`
- Ende: `20:45`

### Bearbeiten
`/ini uhrzeit_bearbeiten`

Tag und vorhandenes Zeitfenster auswählen. Danach neue Start- und Endzeit eintragen.

Vorhandene Anmeldungen werden beim Bearbeiten automatisch in das neue Zeitfenster übernommen.

### Löschen
`/ini uhrzeit_loeschen`

Ein Zeitfenster kann nur gelöscht werden, wenn dort keine Anmeldungen vorhanden sind.

### Anzeigen
`/ini uhrzeiten_anzeigen`

Zeigt alle konfigurierten Zeitfenster des ausgewählten Tages.

## Regeln

- Jeder Wochentag hat eigene Zeitfenster.
- Stunde und Minute sind frei wählbar.
- Format: `HH:MM`
- Zeitfenster dürfen sich nicht überschneiden.
- Über-Nacht-Zeiten wie `22:30 - 00:30` sind erlaubt.
- Maximal 25 Zeitfenster pro Tag, da Discord-Dropdowns höchstens 25 Optionen unterstützen.

# Fiesta Online Discord Bot

## Railway

1. Repository mit diesen Dateien hochladen.
2. Railway Variable setzen:
   - `DISCORD_TOKEN`
3. Railway Volume anlegen:
   - Mount Path: `/app/data`
4. Deploy starten.

## Neue Uhrzeit-Verwaltung

Admin-Befehl:

`/ini uhrzeiten_festlegen`

Danach:
1. Wochentag auswählen.
2. Gewünschte Ein-Stunden-Zeitfenster markieren.
3. Auswahl speichern.

Member sehen anschließend nur die für diesen Tag freigegebenen Uhrzeiten.

Hinweis:
Eine Uhrzeit kann nicht entfernt werden, solange dort noch Anmeldungen vorhanden sind.

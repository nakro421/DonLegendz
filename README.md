# Fiesta Online Discord Bot mit privatem Support-System

## Upload

Diese Dateien in dein GitHub-Repository hochladen und Railway neu deployen.

## Railway Variables

Pflicht:

- `DISCORD_TOKEN`
- `SUPPORT_PANEL_CHANNEL_ID`
- `SUPPORT_CATEGORY_ID`

`SUPPORT_PANEL_CHANNEL_ID` ist die ID des öffentlichen Channels, in dem das Frage-Panel stehen soll.

`SUPPORT_CATEGORY_ID` ist die ID der Kategorie, in der die privaten Frage-Channels erstellt werden.

## Railway Volume

Mount Path:

`/app/data`

Die Datei `/app/data/fiesta_data.json` enthält Ini-, Bewerbungs- und Support-Daten.

## Bot-Rechte

Der Bot benötigt mindestens:

- Kanäle anzeigen
- Nachrichten senden
- Nachrichtenverlauf anzeigen
- Kanäle verwalten
- Rollen/Berechtigungen für Channels verwalten
- Links einbetten
- Dateien anhängen

## Support-Ablauf

1. Im öffentlichen Support-Channel steht der Button **Frage stellen**.
2. Der Member trägt Betreff und Frage ein.
3. Der Bot erstellt einen privaten Text-Channel.
4. Nur Fragesteller, Admin-Rolle und Bot sehen den Channel.
5. Admins antworten direkt im Channel.
6. Der Fragesteller sieht die Antworten sofort.
7. **Erledigt** sperrt nur das Schreiben; der Fragesteller kann weiterhin alles lesen.
8. **Wieder öffnen** erlaubt dem Fragesteller erneut zu schreiben.
9. **Schließen** löscht den Support-Channel nach Bestätigung.

## Admin-Befehl

`/support panel_erstellen`

Erstellt oder aktualisiert das Support-Panel manuell.

## Hinweis zur Admin-Rolle

Der Bot verwendet die bereits im Code eingestellte Rolle:

`Admin`

Ändere `ADMIN_ROLE_NAME`, falls deine Admin-Rolle anders heißt.

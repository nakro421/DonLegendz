# Fiesta Bot – Monatsstatistik und Auszeichnungen

## Enthalten
- bestehendes Ini-, Bewerbungs- und Support-System
- freie Uhrzeiten pro Wochentag
- Buttons `Ini starten` und `Ini beenden`
- mehrfaches Starten und Beenden erlaubt
- pro Ini nur eine Statistik-Gutschrift
- persönliche Statistiken
- Monatsrangliste
- automatische Auszeichnungen
- Import der vorhandenen Wald-Run-Tabelle

## Befehle
- `/statistik profil fiesta_name:<Name>`
- `/statistik monat monat:2026-07`
- `/statistik verknuepfen fiesta_name:<Name> member:@Member` (Admin)

## Berechnung
Die importierten Altwerte zählen je Run als 2 Stunden. Neue Runs verwenden die tatsächliche Zeit zwischen erstem Start-Klick und erstem statistisch gewerteten Ende-Klick. Gibt es keinen Start-Klick, werden 2 Stunden verwendet.

## Railway
Variablen:
- `DISCORD_TOKEN`
- `SUPPORT_PANEL_CHANNEL_ID`
- `SUPPORT_CATEGORY_ID`

Volume Mount Path: `/app/data`

## Wichtig
`initial_member_stats.json` muss zusammen mit `main.py` im Repository liegen. Der Import erfolgt nur einmal und wird in `fiesta_data.json` markiert.

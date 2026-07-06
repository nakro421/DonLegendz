# DonLegendz Bot

Fertiger Discord-Bot mit:

- Ini-Anmeldesystem
- dauerhafter Speicherung über Railway Volume `/app/data`
- Bewerbungssystem
- Prio-Klassen-System für Ini-Zeitfenster
- automatische Klassen-Sortierung in den Ini-Listen

## Prio-System

Ein Zeitfenster wird erst grün, wenn vorhanden sind:

- 1x Ordi
- 1x HK
- 1x Zaubi
- 1x Hexi
- 1x Gladi
- 1x TR
- 2x Joker

Solange diese Prio nicht erfüllt ist, bleibt das Zeitfenster rot.

## Railway

Volume Mount Path:

```text
/app/data
```

Variable:

```text
DISCORD_TOKEN=dein_token
```

Start über Procfile:

```text
worker: python main.py
```

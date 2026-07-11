import os
import json
from pathlib import Path
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

# =========================
# KONFIGURATION
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1212583950468255764
LOG_CHANNEL_ID = 1522722541360382144

# Datei-Speicher auf Railway Volume.
# In Railway Volume Mount Path bitte /app/data verwenden.
DATA_FILE = Path(os.getenv("DATA_FILE", "/app/data/fiesta_data.json"))

# Bewerbungssystem
BEWERBUNG_CHANNEL_ID = 1523646727461146624
ADMIN_ABSTIMMUNG_CHANNEL_ID = 1523646973524312164
MIN_BEWERBUNG_BEGRUENDUNG = 200

# Privates Frage-/Support-System
# Railway Variables:
# SUPPORT_PANEL_CHANNEL_ID = öffentlicher Channel mit dem "Frage stellen"-Button
# SUPPORT_CATEGORY_ID = Kategorie, in der private Support-Channels erstellt werden
SUPPORT_PANEL_CHANNEL_ID = int(os.getenv("SUPPORT_PANEL_CHANNEL_ID", "0"))
SUPPORT_CATEGORY_ID = int(os.getenv("SUPPORT_CATEGORY_ID", "0"))


INI_CHANNELS = {
    "Montag": 1212590388171243570,
    "Dienstag": 1212820797232783420,
    "Mittwoch": 1223042021661343864,
    "Donnerstag": 1212820853478269028,
    "Freitag": 1212820878052696093,
    "Samstag": 1212820906305523723,
    "Sonntag": 1212820935149621339,
}

ADMIN_ROLE_NAME = "Admin"
INI_ROLE_NAME = "Freund der Ini"

STANDARD_ZEITEN = [
    "09:00 - 11:00",
    "11:00 - 13:00",
    "13:30 - 15:30",
    "15:30 - 17:30",
    "18:00 - 20:00",
    "20:00 - 22:00",
    "22:30 - 00:30",
    "00:30 - 02:30",
]

# Jeder Wochentag besitzt seine eigenen, frei konfigurierbaren Zeitfenster.
zeiten_pro_tag: dict[str, list[str]] = {
    tag: list(STANDARD_ZEITEN)
    for tag in INI_CHANNELS.keys()
}

MAX_ZEITEN_PRO_TAG = 25

TAGE = list(INI_CHANNELS.keys())

# Gleiche Namen dürfen in unterschiedlichen Uhrzeiten mehrfach stehen.
# Nur im selben Zeitfenster wird ein doppelter Name blockiert.
ini_listen: dict[str, dict[str, list[dict]]] = {
    tag: {zeit: [] for zeit in zeiten_pro_tag[tag]}
    for tag in TAGE
}

# Cache, damit der Bot die feste Ini-Nachricht nicht jedes Mal neu suchen muss.
ini_message_cache: dict[str, int] = {}

# Bewerbungsdaten werden ebenfalls dauerhaft gespeichert.
bewerbungen: dict = {
    "applications": {},
    "panel_to_application": {},
}

support_daten: dict = {
    "tickets": {},
    "panel_message_id": None,
    "next_number": 1,
}


def leere_ini_listen() -> dict[str, dict[str, list[dict]]]:
    return {
        tag: {zeit: [] for zeit in zeiten_pro_tag.get(tag, [])}
        for tag in TAGE
    }


def normalisiere_ini_daten(rohdaten: object) -> dict[str, dict[str, list[dict]]]:
    """Lädt Ini-Daten passend zu den pro Tag konfigurierten Zeitfenstern."""
    neue_daten = leere_ini_listen()

    if not isinstance(rohdaten, dict):
        return neue_daten

    for tag in TAGE:
        tag_daten = rohdaten.get(tag, {})
        if not isinstance(tag_daten, dict):
            continue

        for zeit in zeiten_pro_tag.get(tag, []):
            eintraege = tag_daten.get(zeit, [])
            if isinstance(eintraege, list):
                neue_daten[tag][zeit] = [
                    eintrag for eintrag in eintraege
                    if isinstance(eintrag, dict) and "fiesta" in eintrag
                ]

        # Alte belegte Zeitfenster werden nicht verworfen.
        for zeit, eintraege in tag_daten.items():
            if (
                zeit not in neue_daten[tag]
                and isinstance(eintraege, list)
                and eintraege
            ):
                neue_daten[tag][zeit] = [
                    eintrag for eintrag in eintraege
                    if isinstance(eintrag, dict) and "fiesta" in eintrag
                ]

    return neue_daten


def leere_bewerbungsdaten() -> dict:
    return {
        "applications": {},
        "panel_to_application": {},
    }


def normalisiere_bewerbungsdaten(rohdaten: object) -> dict:
    daten = leere_bewerbungsdaten()

    if not isinstance(rohdaten, dict):
        return daten

    applications = rohdaten.get("applications", {})
    panel_to_application = rohdaten.get("panel_to_application", {})

    if isinstance(applications, dict):
        for app_id, app_data in applications.items():
            if isinstance(app_data, dict):
                app_data.setdefault("votes", {})
                daten["applications"][str(app_id)] = app_data

    if isinstance(panel_to_application, dict):
        for panel_id, app_id in panel_to_application.items():
            daten["panel_to_application"][str(panel_id)] = str(app_id)

    # Fallback: Mapping aus vorhandenen Bewerbungen neu erzeugen.
    for app_id, app_data in daten["applications"].items():
        panel_id = app_data.get("panel_message_id")
        if panel_id:
            daten["panel_to_application"][str(panel_id)] = str(app_id)

    return daten


def leere_support_daten() -> dict:
    return {
        "tickets": {},
        "panel_message_id": None,
        "next_number": 1,
    }


def normalisiere_support_daten(rohdaten: object) -> dict:
    daten = leere_support_daten()

    if not isinstance(rohdaten, dict):
        return daten

    tickets = rohdaten.get("tickets", {})
    if isinstance(tickets, dict):
        for channel_id, ticket in tickets.items():
            if isinstance(ticket, dict):
                daten["tickets"][str(channel_id)] = ticket

    panel_message_id = rohdaten.get("panel_message_id")
    if panel_message_id:
        daten["panel_message_id"] = int(panel_message_id)

    try:
        daten["next_number"] = max(1, int(rohdaten.get("next_number", 1)))
    except (TypeError, ValueError):
        daten["next_number"] = 1

    return daten


def lade_daten() -> None:
    """Lädt gespeicherte Daten aus dem Railway Volume."""
    global ini_listen, bewerbungen, zeiten_pro_tag, support_daten

    if not DATA_FILE.exists():
        zeiten_pro_tag = {
            tag: list(STANDARD_ZEITEN)
            for tag in TAGE
        }
        ini_listen = leere_ini_listen()
        support_daten = leere_support_daten()
        speichere_daten()
        print(f"Neue Datendatei erstellt: {DATA_FILE}")
        return

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            daten = json.load(file)
    except Exception as fehler:
        print(f"Konnte Datendatei nicht laden: {fehler}")
        zeiten_pro_tag = {
            tag: list(STANDARD_ZEITEN)
            for tag in TAGE
        }
        ini_listen = leere_ini_listen()
        support_daten = leere_support_daten()
        return

    settings = daten.get("settings", {})
    gespeicherte_zeiten = (
        settings.get("zeiten_pro_tag", {})
        if isinstance(settings, dict)
        else {}
    )

    neue_zeiten: dict[str, list[str]] = {}
    for tag in TAGE:
        tag_zeiten = (
            gespeicherte_zeiten.get(tag, [])
            if isinstance(gespeicherte_zeiten, dict)
            else []
        )
        if isinstance(tag_zeiten, list):
            bereinigt = [
                str(zeit).strip()
                for zeit in tag_zeiten
                if isinstance(zeit, str) and str(zeit).strip()
            ]
            neue_zeiten[tag] = list(dict.fromkeys(bereinigt))[:MAX_ZEITEN_PRO_TAG]
        else:
            neue_zeiten[tag] = []

        # Migration von älteren Dateien ohne dynamische Einstellungen.
        if not neue_zeiten[tag]:
            alte_tag_daten = daten.get("ini", {}).get(tag, {})
            if isinstance(alte_tag_daten, dict) and alte_tag_daten:
                neue_zeiten[tag] = list(alte_tag_daten.keys())[:MAX_ZEITEN_PRO_TAG]
            else:
                neue_zeiten[tag] = list(STANDARD_ZEITEN)

    zeiten_pro_tag = neue_zeiten
    for tag in TAGE:
        sortiere_zeiten(tag)

    ini_listen = normalisiere_ini_daten(daten.get("ini", {}))
    bewerbungen = normalisiere_bewerbungsdaten(daten.get("bewerbungen", {}))
    support_daten = normalisiere_support_daten(daten.get("support", {}))
    print(f"Daten geladen: {DATA_FILE}")


def speichere_daten() -> None:
    """Speichert alle wichtigen Bot-Daten dauerhaft im Railway Volume."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    daten = {
        "version": 1,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "ini": ini_listen,
        "bewerbungen": bewerbungen,
        "support": support_daten,
        "klassen": {},
        "settings": {
            "zeiten_pro_tag": zeiten_pro_tag,
        },
    }

    temp_file = DATA_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(daten, file, ensure_ascii=False, indent=2)

    temp_file.replace(DATA_FILE)

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot_ready_done = False


# =========================
# HILFSFUNKTIONEN
# =========================

def ist_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or any(
        role.name == ADMIN_ROLE_NAME for role in member.roles
    )


def hat_ini_rolle(member: discord.Member) -> bool:
    return ist_admin(member) or any(role.name == INI_ROLE_NAME for role in member.roles)


def aktive_zeiten(tag: str) -> list[str]:
    return list(zeiten_pro_tag.get(tag, []))


def zeit_zu_minuten(wert: str) -> int | None:
    try:
        zeit = datetime.strptime(wert.strip(), "%H:%M")
    except ValueError:
        return None
    return zeit.hour * 60 + zeit.minute


def zeitfenster_erstellen(start: str, ende: str) -> str | None:
    start_min = zeit_zu_minuten(start)
    ende_min = zeit_zu_minuten(ende)

    if start_min is None or ende_min is None or start_min == ende_min:
        return None

    return f"{start_min // 60:02d}:{start_min % 60:02d} - {ende_min // 60:02d}:{ende_min % 60:02d}"


def zeitfenster_minuten(zeitfenster: str) -> tuple[int, int] | None:
    try:
        start_text, ende_text = [teil.strip() for teil in zeitfenster.split("-", 1)]
    except ValueError:
        return None

    start_min = zeit_zu_minuten(start_text)
    ende_min = zeit_zu_minuten(ende_text)
    if start_min is None or ende_min is None or start_min == ende_min:
        return None

    return start_min, ende_min


def intervall_segmente(start: int, ende: int) -> list[tuple[int, int]]:
    if start < ende:
        return [(start, ende)]
    return [(start, 1440), (0, ende)]


def zeitfenster_ueberschneiden(a: str, b: str) -> bool:
    a_min = zeitfenster_minuten(a)
    b_min = zeitfenster_minuten(b)
    if a_min is None or b_min is None:
        return False

    for a_start, a_ende in intervall_segmente(*a_min):
        for b_start, b_ende in intervall_segmente(*b_min):
            if max(a_start, b_start) < min(a_ende, b_ende):
                return True
    return False


def zeitfenster_hat_ueberschneidung(
    tag: str,
    neues_zeitfenster: str,
    ignorieren: str | None = None,
) -> bool:
    for vorhandenes in aktive_zeiten(tag):
        if ignorieren is not None and vorhandenes == ignorieren:
            continue
        if zeitfenster_ueberschneiden(vorhandenes, neues_zeitfenster):
            return True
    return False


def sortiere_zeiten(tag: str) -> None:
    def sortierschluessel(zeitfenster: str) -> tuple[int, str]:
        minuten = zeitfenster_minuten(zeitfenster)
        return (minuten[0], zeitfenster) if minuten else (9999, zeitfenster)

    zeiten_pro_tag.setdefault(tag, [])
    zeiten_pro_tag[tag].sort(key=sortierschluessel)


async def zeit_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    namespace = getattr(interaction, "namespace", None)
    tag_wert = getattr(namespace, "tag", None) if namespace else None
    tag_name = tag_wert if isinstance(tag_wert, str) else ""

    current = current.strip().lower()
    return [
        app_commands.Choice(name=zeit, value=zeit)
        for zeit in aktive_zeiten(tag_name)
        if current in zeit.lower()
    ][:25]


def fiesta_name_existiert_in_zeit(tag: str, zeit: str, fiesta_name: str, ignore_index: int | None = None) -> bool:
    for index, eintrag in enumerate(ini_listen[tag][zeit]):
        if ignore_index is not None and index == ignore_index:
            continue
        if eintrag["fiesta"].lower() == fiesta_name.lower():
            return True
    return False


def gesamt_teilnehmer(tag: str) -> int:
    return sum(
        len(ini_listen.get(tag, {}).get(zeit, []))
        for zeit in aktive_zeiten(tag)
    )


def klassen_emoji(fiesta_name: str) -> str:
    name = fiesta_name.strip().lower()
    klassen = {
        "gladi": "🪓",
        "zaubi": "✨",
        "hexi": "✨",
        "tr": "🗡",
        "assa": "⚔️",
        "hk": "❤️",
        "luna": "⚔️",
        "ordi": "🛡️",
        "ss": "🏹",
    }

    for klasse, emoji in klassen.items():
        if name == klasse or name.startswith(klasse + " ") or name.startswith(klasse + "-"):
            return emoji

    return "👤"


def finde_eintrag_nach_fiesta(tag: str, fiesta_name: str):
    for zeit in aktive_zeiten(tag):
        for index, eintrag in enumerate(ini_listen[tag][zeit]):
            if eintrag["fiesta"].lower() == fiesta_name.lower():
                return zeit, index, eintrag
    return None, None, None


def finde_alle_eintraege_nach_fiesta(tag: str, fiesta_name: str) -> list[tuple[str, int, dict]]:
    treffer = []
    for zeit in aktive_zeiten(tag):
        for index, eintrag in enumerate(ini_listen[tag][zeit]):
            if eintrag["fiesta"].lower() == fiesta_name.lower():
                treffer.append((zeit, index, eintrag))
    return treffer


def alte_liste_als_text(tag: str) -> str:
    teile = []

    zeiten = aktive_zeiten(tag)

    if not zeiten:
        embed.add_field(
            name="⛔ Keine Uhrzeiten festgelegt",
            value="Ein Admin muss zuerst eine Uhrzeit hinzufügen.",
            inline=False,
        )

    for zeit in zeiten:
        daten = ini_listen.get(tag, {}).get(zeit, [])

        if daten:
            namen = "\n".join(
                f"{i}. {eintrag['fiesta']}"
                for i, eintrag in enumerate(daten, start=1)
            )
        else:
            namen = "Keine Einträge"

        teile.append(f"**{zeit}**\n{namen}")

    return "\n\n".join(teile)


def ini_embed(tag: str) -> discord.Embed:
    gesamt = gesamt_teilnehmer(tag)

    embed = discord.Embed(
        title=f"📅 Ini {tag}",
        description=(
            "**Anmeldungen für heute**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 **{gesamt} / ∞ Teilnehmer**"
        ),
        color=discord.Color.from_rgb(88, 101, 242),
        timestamp=datetime.now(),
    )

    zeiten = aktive_zeiten(tag)

    if not zeiten:
        embed.add_field(
            name="⛔ Keine Uhrzeiten festgelegt",
            value="Ein Admin muss zuerst eine Uhrzeit hinzufügen.",
            inline=False,
        )

    for zeit in zeiten:
        daten = ini_listen.get(tag, {}).get(zeit, [])
        anzahl = len(daten)

        if daten:
            teilnehmer = "\n".join(
                f"`{i:02d}.` {klassen_emoji(eintrag['fiesta'])} **{eintrag['fiesta']}**"
                for i, eintrag in enumerate(daten, start=1)
            )
            field_name = f"🟢 {zeit}  •  {anzahl} angemeldet"
            field_value = f"{teilnehmer}"
        else:
            field_name = f"🕒 {zeit}  •  0 angemeldet"
            field_value = "*Noch niemand angemeldet.*"

        embed.add_field(
            name=field_name,
            value=field_value,
            inline=False,
        )

    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━━━",
        value=f"👥 **Teilnehmer gesamt:** {gesamt}  •  🕒 **Aktualisiert:** heute um {datetime.now().strftime('%H:%M')} Uhr",
        inline=False,
    )
    return embed

async def log_senden(guild: discord.Guild, titel: str, text: str, farbe: discord.Color) -> None:
    channel = guild.get_channel(LOG_CHANNEL_ID)

    if channel is None:
        try:
            channel = await guild.fetch_channel(LOG_CHANNEL_ID)
        except Exception:
            return

    if not isinstance(channel, discord.TextChannel):
        return

    if len(text) > 3900:
        text = text[:3900] + "\n\n... gekürzt, weil der Log zu lang war."

    embed = discord.Embed(
        title=titel,
        description=text,
        color=farbe,
        timestamp=datetime.now(),
    )
    await channel.send(embed=embed)


async def get_ini_channel(tag: str) -> discord.TextChannel | None:
    channel = bot.get_channel(INI_CHANNELS[tag])

    if channel is None:
        try:
            channel = await bot.fetch_channel(INI_CHANNELS[tag])
        except Exception:
            return None

    if isinstance(channel, discord.TextChannel):
        return channel

    return None


async def finde_ini_message(channel: discord.TextChannel, tag: str) -> discord.Message | None:
    cached_id = ini_message_cache.get(tag)
    if cached_id:
        try:
            msg = await channel.fetch_message(cached_id)
            if msg.author == bot.user and msg.embeds and msg.embeds[0].title == f"📅 Ini {tag}":
                return msg
        except Exception:
            ini_message_cache.pop(tag, None)

    async for msg in channel.history(limit=100):
        if msg.author == bot.user and msg.embeds:
            if msg.embeds[0].title == f"📅 Ini {tag}":
                ini_message_cache[tag] = msg.id
                return msg
    return None


async def update_ini_message(tag: str) -> None:
    channel = await get_ini_channel(tag)

    if channel is None:
        print(f"Channel für {tag} nicht gefunden.")
        return

    msg = await finde_ini_message(channel, tag)

    if msg:
        await msg.edit(embed=ini_embed(tag), view=IniView(tag))
        ini_message_cache[tag] = msg.id
    else:
        msg = await channel.send(embed=ini_embed(tag), view=IniView(tag))
        ini_message_cache[tag] = msg.id


# =========================
# MODALS
# =========================

class AnmeldungModal(discord.ui.Modal):
    def __init__(self, tag: str, zeit: str):
        super().__init__(title=f"Anmeldung {tag} | {zeit}")
        self.tag = tag
        self.zeit = zeit

        self.name = discord.ui.TextInput(
            label="Klasse - Name eintragen",
            placeholder="Beispiel: HK - Emi",
            min_length=2,
            max_length=40,
            required=True,
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
            return

        member = interaction.user
        fiesta_name = str(self.name.value).strip()

        if not hat_ini_rolle(member):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        if fiesta_name_existiert_in_zeit(self.tag, self.zeit, fiesta_name):
            await interaction.response.send_message(
                "Dieser Fiesta-Name steht in diesem Zeitfenster bereits in der Liste.",
                ephemeral=True,
                delete_after=5,
            )
            return

        ini_listen[self.tag][self.zeit].append({
            "fiesta": fiesta_name,
            "eingetragen_von": member.id,
            "discord_user": member.id,
        })
        speichere_daten()

        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(self.tag)
        await interaction.followup.send(
            f"**{fiesta_name}** wurde für **{self.tag}** um **{self.zeit}** angemeldet.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"✅ Anmeldung - Ini {self.tag}",
                f"**Eingetragen von:** {member.mention}\n**Fiesta:** {fiesta_name}\n**Uhrzeit:** {self.zeit}",
                discord.Color.green(),
            )


class AbmeldenNameModal(discord.ui.Modal):
    def __init__(self, tag: str):
        super().__init__(title=f"Abmelden - Ini {tag}")
        self.tag = tag

        self.name = discord.ui.TextInput(
            label="Fiesta-Name zum Abmelden",
            placeholder="Name genau wie in der Liste",
            min_length=2,
            max_length=30,
            required=True,
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
            return

        if not hat_ini_rolle(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        fiesta_name = str(self.name.value).strip()
        treffer = finde_alle_eintraege_nach_fiesta(self.tag, fiesta_name)

        if not treffer:
            await interaction.response.send_message(
                f"**{fiesta_name}** wurde für **{self.tag}** nicht gefunden.",
                ephemeral=True,
                delete_after=5,
            )
            return

        await interaction.response.send_message(
            f"Wähle die Uhrzeit aus, aus der **{fiesta_name}** abgemeldet werden soll:",
            view=AbmeldenZeitView(self.tag, fiesta_name, treffer),
            ephemeral=True,
            delete_after=30,
        )


class AendernModal(discord.ui.Modal):
    def __init__(self, tag: str):
        super().__init__(title=f"Namen ändern - Ini {tag}")
        self.tag = tag

        self.alt = discord.ui.TextInput(
            label="Alter Fiesta-Name",
            placeholder="Name, der aktuell in der Liste steht",
            min_length=2,
            max_length=30,
            required=True,
        )
        self.neu = discord.ui.TextInput(
            label="Neuer Fiesta-Name",
            placeholder="Neuer Fiesta-Name",
            min_length=2,
            max_length=30,
            required=True,
        )
        self.add_item(self.alt)
        self.add_item(self.neu)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
            return

        member = interaction.user

        if not hat_ini_rolle(member):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        alter_name = str(self.alt.value).strip()
        neuer_name = str(self.neu.value).strip()

        zeit, index, eintrag = finde_eintrag_nach_fiesta(self.tag, alter_name)

        if zeit is None or index is None or eintrag is None:
            await interaction.response.send_message(
                f"**{alter_name}** wurde für **{self.tag}** nicht gefunden.",
                ephemeral=True,
                delete_after=5,
            )
            return

        if fiesta_name_existiert_in_zeit(self.tag, zeit, neuer_name, ignore_index=index):
            await interaction.response.send_message(
                "Dieser neue Fiesta-Name steht in diesem Zeitfenster bereits in der Liste.",
                ephemeral=True,
                delete_after=5,
            )
            return

        ini_listen[self.tag][zeit][index]["fiesta"] = neuer_name
        speichere_daten()
        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(self.tag)
        await interaction.followup.send(f"Geändert: **{alter_name}** → **{neuer_name}**", ephemeral=True)

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"✏️ Änderung - Ini {self.tag}",
                f"**Geändert von:** {member.mention}\n**Uhrzeit:** {zeit}\n**Alt:** {alter_name}\n**Neu:** {neuer_name}",
                discord.Color.orange(),
            )


class UhrzeitHinzufuegenModal(discord.ui.Modal):
    def __init__(self, tag: str):
        super().__init__(title=f"Uhrzeit hinzufügen - {tag}")
        self.tag = tag

        self.start = discord.ui.TextInput(
            label="Startzeit",
            placeholder="Beispiel: 19:15",
            min_length=5,
            max_length=5,
            required=True,
        )
        self.ende = discord.ui.TextInput(
            label="Endzeit",
            placeholder="Beispiel: 20:45",
            min_length=5,
            max_length=5,
            required=True,
        )
        self.add_item(self.start)
        self.add_item(self.ende)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        zeitfenster = zeitfenster_erstellen(str(self.start.value), str(self.ende.value))
        if zeitfenster is None:
            await interaction.response.send_message(
                "Ungültige Uhrzeit. Verwende `HH:MM` und unterschiedliche Start-/Endzeiten.",
                ephemeral=True,
                delete_after=10,
            )
            return

        if zeitfenster in aktive_zeiten(self.tag):
            await interaction.response.send_message(
                "Dieses Zeitfenster existiert bereits.",
                ephemeral=True,
                delete_after=8,
            )
            return

        if len(aktive_zeiten(self.tag)) >= MAX_ZEITEN_PRO_TAG:
            await interaction.response.send_message(
                f"Pro Tag sind maximal **{MAX_ZEITEN_PRO_TAG}** Zeitfenster möglich.",
                ephemeral=True,
                delete_after=8,
            )
            return

        if zeitfenster_hat_ueberschneidung(self.tag, zeitfenster):
            await interaction.response.send_message(
                "Dieses Zeitfenster überschneidet sich mit einer bereits vorhandenen Uhrzeit.",
                ephemeral=True,
                delete_after=10,
            )
            return

        zeiten_pro_tag.setdefault(self.tag, []).append(zeitfenster)
        sortiere_zeiten(self.tag)
        ini_listen.setdefault(self.tag, {})[zeitfenster] = []
        speichere_daten()

        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(self.tag)
        await interaction.followup.send(
            f"**{zeitfenster}** wurde für **{self.tag}** hinzugefügt.",
            ephemeral=True,
        )


class UhrzeitBearbeitenModal(discord.ui.Modal):
    def __init__(self, tag: str, alte_zeit: str):
        super().__init__(title=f"Uhrzeit bearbeiten - {tag}")
        self.tag = tag
        self.alte_zeit = alte_zeit

        minuten = zeitfenster_minuten(alte_zeit)
        start_vorgabe = f"{minuten[0] // 60:02d}:{minuten[0] % 60:02d}" if minuten else ""
        ende_vorgabe = f"{minuten[1] // 60:02d}:{minuten[1] % 60:02d}" if minuten else ""

        self.start = discord.ui.TextInput(
            label="Neue Startzeit",
            default=start_vorgabe,
            min_length=5,
            max_length=5,
            required=True,
        )
        self.ende = discord.ui.TextInput(
            label="Neue Endzeit",
            default=ende_vorgabe,
            min_length=5,
            max_length=5,
            required=True,
        )
        self.add_item(self.start)
        self.add_item(self.ende)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        if self.alte_zeit not in aktive_zeiten(self.tag):
            await interaction.response.send_message(
                "Das alte Zeitfenster existiert nicht mehr.",
                ephemeral=True,
                delete_after=8,
            )
            return

        neues_zeitfenster = zeitfenster_erstellen(str(self.start.value), str(self.ende.value))
        if neues_zeitfenster is None:
            await interaction.response.send_message(
                "Ungültige Uhrzeit. Verwende `HH:MM` und unterschiedliche Start-/Endzeiten.",
                ephemeral=True,
                delete_after=10,
            )
            return

        if (
            neues_zeitfenster != self.alte_zeit
            and neues_zeitfenster in aktive_zeiten(self.tag)
        ):
            await interaction.response.send_message(
                "Dieses Zeitfenster existiert bereits.",
                ephemeral=True,
                delete_after=8,
            )
            return

        if zeitfenster_hat_ueberschneidung(
            self.tag,
            neues_zeitfenster,
            ignorieren=self.alte_zeit,
        ):
            await interaction.response.send_message(
                "Das neue Zeitfenster überschneidet sich mit einer anderen Uhrzeit.",
                ephemeral=True,
                delete_after=10,
            )
            return

        index = zeiten_pro_tag[self.tag].index(self.alte_zeit)
        zeiten_pro_tag[self.tag][index] = neues_zeitfenster
        sortiere_zeiten(self.tag)

        vorhandene_eintraege = ini_listen.setdefault(self.tag, {}).pop(self.alte_zeit, [])
        ini_listen[self.tag][neues_zeitfenster] = vorhandene_eintraege
        speichere_daten()

        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(self.tag)
        await interaction.followup.send(
            f"Geändert: **{self.alte_zeit}** → **{neues_zeitfenster}**",
            ephemeral=True,
        )


# =========================
# VIEWS / BUTTONS
# =========================

class AbmeldenZeitSelect(discord.ui.Select):
    def __init__(self, tag: str, fiesta_name: str, treffer: list[tuple[str, int, dict]]):
        self.tag = tag
        self.fiesta_name = fiesta_name
        super().__init__(
            placeholder="Uhrzeit zum Abmelden auswählen",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=zeit, value=zeit, emoji="🕒")
                for zeit, _index, _eintrag in treffer[:25]
            ],
            custom_id=f"ini_abmelden_zeit_{tag}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
            return

        if not hat_ini_rolle(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        zeit = self.values[0]
        index_gefunden = None

        for index, eintrag in enumerate(ini_listen.get(self.tag, {}).get(zeit, [])):
            if eintrag["fiesta"].lower() == self.fiesta_name.lower():
                index_gefunden = index
                break

        if index_gefunden is None:
            await interaction.response.send_message(
                "Dieser Eintrag wurde bereits entfernt oder nicht gefunden.",
                ephemeral=True,
                delete_after=5,
            )
            return

        del ini_listen[self.tag][zeit][index_gefunden]
        speichere_daten()

        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(self.tag)
        await interaction.followup.send(
            f"**{self.fiesta_name}** wurde aus **{self.tag}** um **{zeit}** abgemeldet.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"❌ Abmeldung - Ini {self.tag}",
                f"**Abgemeldet von:** {interaction.user.mention}\n"
                f"**Fiesta:** {self.fiesta_name}\n"
                f"**Uhrzeit:** {zeit}",
                discord.Color.red(),
            )


class AbmeldenZeitView(discord.ui.View):
    def __init__(self, tag: str, fiesta_name: str, treffer: list[tuple[str, int, dict]]):
        super().__init__(timeout=30)
        self.add_item(AbmeldenZeitSelect(tag, fiesta_name, treffer))


class IniZeitSelect(discord.ui.Select):
    def __init__(self, tag: str):
        self.tag = tag
        optionen = [
            discord.SelectOption(label=zeit, value=zeit, emoji="🕒")
            for zeit in aktive_zeiten(tag)
        ]

        if not optionen:
            optionen = [
                discord.SelectOption(
                    label="Keine Uhrzeiten verfügbar",
                    value="__keine__",
                    emoji="⛔",
                )
            ]

        super().__init__(
            placeholder="Ini-Uhrzeit auswählen",
            min_values=1,
            max_values=1,
            options=optionen,
            custom_id=f"ini_anmelden_zeit_{tag}",
            disabled=not aktive_zeiten(tag),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
            return

        if not hat_ini_rolle(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        zeit = self.values[0]
        if zeit not in aktive_zeiten(self.tag):
            await interaction.response.send_message(
                "Diese Uhrzeit ist für diesen Tag nicht mehr aktiv.",
                ephemeral=True,
                delete_after=8,
            )
            return

        await interaction.response.send_modal(AnmeldungModal(self.tag, zeit))


class IniView(discord.ui.View):
    def __init__(self, tag: str):
        super().__init__(timeout=None)
        self.tag = tag

        self.add_item(IniZeitSelect(tag))

        abmelden = discord.ui.Button(
            label="Abmelden",
            emoji="👤",
            style=discord.ButtonStyle.danger,
            custom_id=f"ini_abmelden_{tag}",
            row=1,
        )
        abmelden.callback = self.abmelden_callback
        self.add_item(abmelden)

        aendern = discord.ui.Button(
            label="Namen ändern",
            emoji="✏️",
            style=discord.ButtonStyle.primary,
            custom_id=f"ini_aendern_{tag}",
            row=1,
        )
        aendern.callback = self.aendern_callback
        self.add_item(aendern)

        reset = discord.ui.Button(
            label="Liste resetten",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ini_reset_{tag}",
            row=1,
        )
        reset.callback = self.reset_callback
        self.add_item(reset)


    async def abmelden_callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
            return

        if not hat_ini_rolle(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        await interaction.response.send_modal(AbmeldenNameModal(self.tag))

    async def aendern_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AendernModal(self.tag))

    async def reset_callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        anzahl = gesamt_teilnehmer(self.tag)
        reset_liste = alte_liste_als_text(self.tag)

        for zeit in aktive_zeiten(self.tag):
            ini_listen[self.tag][zeit].clear()
        speichere_daten()

        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(self.tag)
        await interaction.followup.send(f"Die Liste für **{self.tag}** wurde resettet.", ephemeral=True)

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"🧹 Reset per Button - Ini {self.tag}",
                (
                    f"**Admin:** {interaction.user.mention}\n"
                    f"**Gelöschte Einträge:** {anzahl}\n\n"
                    f"**Zurückgesetzte Liste:**\n\n"
                    f"{reset_liste}"
                ),
                discord.Color.dark_blue(),
            )




# =========================
# PRIVATES FRAGE-/SUPPORT-SYSTEM
# =========================

def support_ticket_fuer_channel(channel_id: int) -> dict | None:
    ticket = support_daten.get("tickets", {}).get(str(channel_id))
    return ticket if isinstance(ticket, dict) else None


async def get_support_panel_channel() -> discord.TextChannel | None:
    if SUPPORT_PANEL_CHANNEL_ID <= 0:
        return None

    channel = bot.get_channel(SUPPORT_PANEL_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(SUPPORT_PANEL_CHANNEL_ID)
        except Exception:
            return None

    return channel if isinstance(channel, discord.TextChannel) else None


async def get_support_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    if SUPPORT_CATEGORY_ID <= 0:
        return None

    channel = guild.get_channel(SUPPORT_CATEGORY_ID)
    if channel is None:
        try:
            channel = await guild.fetch_channel(SUPPORT_CATEGORY_ID)
        except Exception:
            return None

    return channel if isinstance(channel, discord.CategoryChannel) else None


def support_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="❓ Fragen an das Team",
        description=(
            "Du hast eine Frage und möchtest dafür keine private Nachricht "
            "an eine einzelne Person senden?\n\n"
            "Klicke auf **📩 Frage stellen**. Der Bot erstellt anschließend "
            "einen privaten Bereich, den nur du und das Admin-Team sehen können."
        ),
        color=discord.Color.from_rgb(88, 101, 242),
        timestamp=datetime.now(),
    )
    embed.add_field(
        name="🔒 Privat",
        value="Andere Mitglieder können weder deine Frage noch die Antworten sehen.",
        inline=False,
    )
    embed.add_field(
        name="💬 Antworten",
        value="Admins antworten direkt im privaten Support-Channel. Du siehst die Antwort sofort.",
        inline=False,
    )
    embed.set_footer(text="Bitte erstelle für jedes Thema nur eine Anfrage.")
    return embed


def support_ticket_embed(
    *,
    member: discord.Member,
    betreff: str,
    frage: str,
    nummer: int,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📩 Support-Anfrage #{nummer:04d}",
        description=frage,
        color=discord.Color.green(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="👤 Erstellt von", value=member.mention, inline=True)
    embed.add_field(name="📌 Betreff", value=betreff, inline=True)
    embed.add_field(name="Status", value="🟢 Offen", inline=True)
    embed.set_footer(text=f"User-ID: {member.id}")
    return embed


async def erstelle_oder_aktualisiere_support_panel() -> discord.Message | None:
    channel = await get_support_panel_channel()
    if channel is None:
        print("Support-Panel-Channel nicht konfiguriert oder nicht gefunden.")
        return None

    panel_id = support_daten.get("panel_message_id")
    if panel_id:
        try:
            message = await channel.fetch_message(int(panel_id))
            await message.edit(embed=support_panel_embed(), view=SupportPanelView())
            return message
        except Exception:
            support_daten["panel_message_id"] = None

    async for message in channel.history(limit=100):
        if (
            message.author == bot.user
            and message.embeds
            and message.embeds[0].title == "❓ Fragen an das Team"
        ):
            support_daten["panel_message_id"] = message.id
            speichere_daten()
            await message.edit(embed=support_panel_embed(), view=SupportPanelView())
            return message

    message = await channel.send(embed=support_panel_embed(), view=SupportPanelView())
    support_daten["panel_message_id"] = message.id
    speichere_daten()
    return message


async def support_channel_schliessen(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
) -> None:
    ticket = support_ticket_fuer_channel(channel.id)
    if ticket is None:
        await interaction.response.send_message(
            "Dieser Channel gehört zu keiner gespeicherten Support-Anfrage.",
            ephemeral=True,
            delete_after=8,
        )
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Mitglied konnte nicht erkannt werden.",
            ephemeral=True,
            delete_after=5,
        )
        return

    user_id = int(ticket.get("user_id", 0))
    darf_schliessen = ist_admin(interaction.user) or interaction.user.id == user_id
    if not darf_schliessen:
        await interaction.response.send_message(
            "Du darfst diese Anfrage nicht schließen.",
            ephemeral=True,
            delete_after=5,
        )
        return

    ticket["status"] = "geschlossen"
    ticket["closed_by"] = interaction.user.id
    ticket["closed_at"] = datetime.now().isoformat(timespec="seconds")
    speichere_daten()

    await interaction.response.send_message(
        "Die Anfrage wird in 5 Sekunden geschlossen.",
        ephemeral=True,
    )

    if interaction.guild:
        await log_senden(
            interaction.guild,
            "🔒 Support-Anfrage geschlossen",
            (
                f"**Channel:** {channel.name}\n"
                f"**Geschlossen von:** {interaction.user.mention}\n"
                f"**Fragesteller-ID:** `{user_id}`"
            ),
            discord.Color.red(),
        )

    await discord.utils.sleep_until(
        discord.utils.utcnow() + timedelta(seconds=5)
    )
    support_daten.get("tickets", {}).pop(str(channel.id), None)
    speichere_daten()

    try:
        await channel.delete(reason=f"Support geschlossen von {interaction.user}")
    except Exception as fehler:
        print(f"Support-Channel konnte nicht gelöscht werden: {fehler}")


class SupportFrageModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Frage an das Team")

        self.betreff = discord.ui.TextInput(
            label="Betreff",
            placeholder="Worum geht es?",
            min_length=3,
            max_length=80,
            required=True,
        )
        self.frage = discord.ui.TextInput(
            label="Deine Frage",
            placeholder="Beschreibe dein Anliegen möglichst genau.",
            style=discord.TextStyle.paragraph,
            min_length=10,
            max_length=1800,
            required=True,
        )
        self.add_item(self.betreff)
        self.add_item(self.frage)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message(
                "Die Anfrage kann nur auf dem Server erstellt werden.",
                ephemeral=True,
                delete_after=8,
            )
            return

        member = interaction.user
        guild = interaction.guild

        # Pro Benutzer nur ein offenes Ticket.
        for channel_id, ticket in support_daten.get("tickets", {}).items():
            if (
                isinstance(ticket, dict)
                and int(ticket.get("user_id", 0)) == member.id
                and ticket.get("status", "offen") == "offen"
            ):
                channel = guild.get_channel(int(channel_id))
                if isinstance(channel, discord.TextChannel):
                    await interaction.response.send_message(
                        f"Du hast bereits eine offene Anfrage: {channel.mention}",
                        ephemeral=True,
                        delete_after=12,
                    )
                    return

        category = await get_support_category(guild)
        if category is None:
            await interaction.response.send_message(
                "Die Support-Kategorie ist nicht konfiguriert. Bitte informiere einen Admin.",
                ephemeral=True,
                delete_after=12,
            )
            return

        admin_role = discord.utils.get(guild.roles, name=ADMIN_ROLE_NAME)
        bot_member = guild.me

        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
        }

        if admin_role is not None:
            overwrites[admin_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )

        if bot_member is not None:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            )

        nummer = int(support_daten.get("next_number", 1))
        sicherer_name = re.sub(r"[^a-z0-9-]", "-", member.name.lower())
        sicherer_name = re.sub(r"-+", "-", sicherer_name).strip("-") or "mitglied"
        channel_name = f"frage-{nummer:04d}-{sicherer_name}"[:95]

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Private Support-Anfrage von {member} | User-ID {member.id}",
                reason=f"Support-Anfrage von {member}",
            )
        except Exception as fehler:
            await interaction.followup.send(
                f"Der private Support-Channel konnte nicht erstellt werden: `{fehler}`",
                ephemeral=True,
            )
            return

        betreff = str(self.betreff.value).strip()
        frage = str(self.frage.value).strip()

        support_daten.setdefault("tickets", {})[str(channel.id)] = {
            "number": nummer,
            "user_id": member.id,
            "user_name": str(member),
            "subject": betreff,
            "question": frage,
            "status": "offen",
            "channel_id": channel.id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        support_daten["next_number"] = nummer + 1
        speichere_daten()

        await channel.send(
            content=f"{member.mention} – das Admin-Team wurde über deine Anfrage informiert.",
            embed=support_ticket_embed(
                member=member,
                betreff=betreff,
                frage=frage,
                nummer=nummer,
            ),
            view=SupportTicketView(),
        )

        await interaction.followup.send(
            f"Deine private Anfrage wurde erstellt: {channel.mention}",
            ephemeral=True,
        )

        await log_senden(
            guild,
            "📩 Neue Support-Anfrage",
            (
                f"**Von:** {member.mention}\n"
                f"**Channel:** {channel.mention}\n"
                f"**Betreff:** {betreff}"
            ),
            discord.Color.green(),
        )


class SupportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Frage stellen",
        emoji="📩",
        style=discord.ButtonStyle.primary,
        custom_id="support_frage_stellen",
    )
    async def frage_stellen(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(SupportFrageModal())


class SupportSchliessenBestaetigungView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(
        label="Ja, schließen",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
    )
    async def bestaetigen(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "Support-Channel nicht erkannt.",
                ephemeral=True,
                delete_after=5,
            )
            return
        await support_channel_schliessen(interaction, interaction.channel)

    @discord.ui.button(
        label="Abbrechen",
        emoji="↩️",
        style=discord.ButtonStyle.secondary,
    )
    async def abbrechen(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content="Schließen abgebrochen.",
            view=None,
        )


class SupportTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Erledigt",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="support_ticket_erledigt",
    )
    async def erledigt(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        if (
            not isinstance(interaction.user, discord.Member)
            or not ist_admin(interaction.user)
            or not isinstance(interaction.channel, discord.TextChannel)
        ):
            await interaction.response.send_message(
                "Nur ein Admin kann eine Anfrage als erledigt markieren.",
                ephemeral=True,
                delete_after=6,
            )
            return

        ticket = support_ticket_fuer_channel(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message(
                "Support-Daten nicht gefunden.",
                ephemeral=True,
                delete_after=6,
            )
            return

        user_id = int(ticket.get("user_id", 0))
        member = interaction.guild.get_member(user_id) if interaction.guild else None

        if member is not None:
            overwrite = interaction.channel.overwrites_for(member)
            overwrite.send_messages = False
            overwrite.view_channel = True
            overwrite.read_message_history = True
            await interaction.channel.set_permissions(
                member,
                overwrite=overwrite,
                reason=f"Support erledigt von {interaction.user}",
            )

        ticket["status"] = "erledigt"
        ticket["resolved_by"] = interaction.user.id
        ticket["resolved_at"] = datetime.now().isoformat(timespec="seconds")
        speichere_daten()

        await interaction.response.send_message(
            f"✅ Anfrage wurde von {interaction.user.mention} als erledigt markiert.\n"
            "Der Fragesteller kann die Antworten weiterhin lesen.",
        )

    @discord.ui.button(
        label="Wieder öffnen",
        emoji="🔓",
        style=discord.ButtonStyle.secondary,
        custom_id="support_ticket_wieder_oeffnen",
    )
    async def wieder_oeffnen(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        if (
            not isinstance(interaction.user, discord.Member)
            or not ist_admin(interaction.user)
            or not isinstance(interaction.channel, discord.TextChannel)
        ):
            await interaction.response.send_message(
                "Nur ein Admin kann die Anfrage wieder öffnen.",
                ephemeral=True,
                delete_after=6,
            )
            return

        ticket = support_ticket_fuer_channel(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message(
                "Support-Daten nicht gefunden.",
                ephemeral=True,
                delete_after=6,
            )
            return

        user_id = int(ticket.get("user_id", 0))
        member = interaction.guild.get_member(user_id) if interaction.guild else None
        if member is not None:
            overwrite = interaction.channel.overwrites_for(member)
            overwrite.send_messages = True
            overwrite.view_channel = True
            overwrite.read_message_history = True
            await interaction.channel.set_permissions(
                member,
                overwrite=overwrite,
                reason=f"Support wieder geöffnet von {interaction.user}",
            )

        ticket["status"] = "offen"
        ticket["reopened_by"] = interaction.user.id
        ticket["reopened_at"] = datetime.now().isoformat(timespec="seconds")
        speichere_daten()

        await interaction.response.send_message(
            f"🔓 Anfrage wurde von {interaction.user.mention} wieder geöffnet."
        )

    @discord.ui.button(
        label="Schließen",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="support_ticket_schliessen",
    )
    async def schliessen(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "Support-Channel nicht erkannt.",
                ephemeral=True,
                delete_after=5,
            )
            return

        ticket = support_ticket_fuer_channel(interaction.channel.id)
        if ticket is None:
            await interaction.response.send_message(
                "Support-Daten nicht gefunden.",
                ephemeral=True,
                delete_after=6,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Mitglied nicht erkannt.",
                ephemeral=True,
                delete_after=5,
            )
            return

        user_id = int(ticket.get("user_id", 0))
        if not (ist_admin(interaction.user) or interaction.user.id == user_id):
            await interaction.response.send_message(
                "Du darfst diese Anfrage nicht schließen.",
                ephemeral=True,
                delete_after=5,
            )
            return

        await interaction.response.send_message(
            "Soll diese Support-Anfrage wirklich geschlossen und der Channel gelöscht werden?",
            view=SupportSchliessenBestaetigungView(),
            ephemeral=True,
        )


class SupportCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="support", description="Privates Frage-System verwalten")

    @app_commands.command(
        name="panel_erstellen",
        description="Admin: Erstellt oder aktualisiert das Frage-Panel",
    )
    async def panel_erstellen(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message(
                "Du hast dafür keine Rechte.",
                ephemeral=True,
                delete_after=5,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await erstelle_oder_aktualisiere_support_panel()
        if message is None:
            await interaction.followup.send(
                "Support-Panel konnte nicht erstellt werden. Prüfe "
                "`SUPPORT_PANEL_CHANNEL_ID` und die Bot-Rechte.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Support-Panel wurde erstellt oder aktualisiert: {message.jump_url}",
            ephemeral=True,
        )


# =========================
# BEWERBUNGSSYSTEM 2.0
# =========================

async def get_bewerbung_channel() -> discord.TextChannel | None:
    channel = bot.get_channel(BEWERBUNG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(BEWERBUNG_CHANNEL_ID)
        except Exception:
            return None
    return channel if isinstance(channel, discord.TextChannel) else None


async def get_admin_abstimmung_channel() -> discord.TextChannel | None:
    channel = bot.get_channel(ADMIN_ABSTIMMUNG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(ADMIN_ABSTIMMUNG_CHANNEL_ID)
        except Exception:
            return None
    return channel if isinstance(channel, discord.TextChannel) else None


def bewerbung_counts(app_data: dict) -> tuple[int, int, int]:
    votes = app_data.get("votes", {}) if isinstance(app_data, dict) else {}
    ja = sum(1 for v in votes.values() if isinstance(v, dict) and v.get("vote") == "ja")
    nein = sum(1 for v in votes.values() if isinstance(v, dict) and v.get("vote") == "nein")
    return ja, nein, len(votes)


def bewerbung_panel_embed(message: discord.Message, app_data: dict | None = None) -> discord.Embed:
    ja = nein = gesamt = 0
    status = "🟢 Offen"
    if app_data:
        ja, nein, gesamt = bewerbung_counts(app_data)
        status = app_data.get("status", "🟢 Offen")

    embed = discord.Embed(
        title="🗳️ Anonyme Bewerbungs-Abstimmung",
        description=(
            "Bitte stimme fair und sachlich über diese Bewerbung ab.\n\n"
            "✅ **Ja** = aufnehmen\n"
            "❌ **Nein** = ablehnen\n\n"
            f"📝 Eine Begründung mit mindestens **{MIN_BEWERBUNG_BEGRUENDUNG} Zeichen** ist Pflicht.\n"
            "🔒 Deine Stimme bleibt für normale Mitglieder anonym. Nur du selbst und die Admins sehen deine Begründung."
        ),
        color=discord.Color.from_rgb(88, 101, 242),
        timestamp=datetime.now(),
    )
    embed.add_field(name="📌 Bewerbung", value=f"[Zum Beitrag springen]({message.jump_url})", inline=False)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Stimmen", value=f"✅ {ja}  •  ❌ {nein}  •  👥 {gesamt}", inline=True)
    embed.set_footer(text="Eine Person kann genau eine Stimme abgeben. Erneutes Abstimmen ändert die eigene Stimme.")
    return embed


def bewerbung_panel_embed_from_data(app_id: str, app_data: dict) -> discord.Embed:
    ja, nein, gesamt = bewerbung_counts(app_data)
    status = app_data.get("status", "🟢 Offen")
    embed = discord.Embed(
        title="🗳️ Anonyme Bewerbungs-Abstimmung",
        description=(
            "Bitte stimme fair und sachlich über diese Bewerbung ab.\n\n"
            "✅ **Ja** = aufnehmen\n"
            "❌ **Nein** = ablehnen\n\n"
            f"📝 Eine Begründung mit mindestens **{MIN_BEWERBUNG_BEGRUENDUNG} Zeichen** ist Pflicht.\n"
            "🔒 Deine Stimme bleibt für normale Mitglieder anonym. Nur du selbst und die Admins sehen deine Begründung."
        ),
        color=discord.Color.from_rgb(88, 101, 242),
        timestamp=datetime.now(),
    )
    embed.add_field(name="📌 Bewerbung", value=f"[Zum Beitrag springen]({app_data.get('message_url', '')})", inline=False)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Stimmen", value=f"✅ {ja}  •  ❌ {nein}  •  👥 {gesamt}", inline=True)
    embed.set_footer(text=f"Bewerbungs-ID: {app_id}")
    return embed


def admin_bewerbung_summary_embed(app_id: str, app_data: dict) -> discord.Embed:
    ja, nein, gesamt = bewerbung_counts(app_data)
    status = app_data.get("status", "🟢 Offen")
    embed = discord.Embed(
        title="📋 Admin-Auswertung Bewerbung",
        description=f"**Status:** {status}\n**Bewerbung:** [Zum Beitrag springen]({app_data.get('message_url', '')})",
        color=discord.Color.dark_blue(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="Zusammenfassung", value=f"✅ Ja: **{ja}**\n❌ Nein: **{nein}**\n👥 Gesamt: **{gesamt}**", inline=True)
    embed.add_field(name="Bewerbungs-ID", value=f"`{app_id}`", inline=True)

    votes = app_data.get("votes", {})
    if votes:
        lines = []
        for i, vote_data in enumerate(votes.values(), start=1):
            vote_icon = "✅" if vote_data.get("vote") == "ja" else "❌"
            user_name = vote_data.get("user_name", "Unbekannt")
            updated_at = vote_data.get("updated_at", "")
            lines.append(f"**{i}.** {vote_icon} {user_name} • {updated_at}")
        embed.add_field(name="Stimmen", value="\n".join(lines[:20]) or "Noch keine Stimmen", inline=False)
        if len(lines) > 20:
            embed.add_field(name="Hinweis", value=f"Weitere {len(lines) - 20} Stimmen sind gespeichert. Nutze `/bewerbung export`. ", inline=False)
    else:
        embed.add_field(name="Stimmen", value="Noch keine Stimmen", inline=False)

    return embed


def admin_vote_embed(*, member: discord.Member, vote: str, reason: str, application_id: str, application_url: str, changed: bool) -> discord.Embed:
    vote_text = "✅ Ja" if vote == "ja" else "❌ Nein"
    title = "🗳️ Stimme aktualisiert" if changed else "🗳️ Neue Stimme"
    color = discord.Color.green() if vote == "ja" else discord.Color.red()
    embed = discord.Embed(title=title, color=color, timestamp=datetime.now())
    embed.add_field(name="Abstimmer", value=f"{member.mention}\n`{member.id}`", inline=True)
    embed.add_field(name="Stimme", value=vote_text, inline=True)
    embed.add_field(name="Bewerbung", value=f"[Zum Beitrag springen]({application_url})\n`{application_id}`", inline=False)

    reason = reason.strip()
    chunks = [reason[i:i + 1000] for i in range(0, len(reason), 1000)] or ["-"]
    for i, chunk in enumerate(chunks[:3], start=1):
        name = f"Begründung ({len(reason)} Zeichen)" if i == 1 else f"Begründung Teil {i}"
        embed.add_field(name=name, value=chunk, inline=False)
    return embed


async def update_admin_bewerbung_summary(app_id: str, app_data: dict) -> None:
    admin_channel = await get_admin_abstimmung_channel()
    if admin_channel is None:
        return

    embed = admin_bewerbung_summary_embed(app_id, app_data)
    msg_id = app_data.get("admin_summary_message_id")
    if msg_id:
        try:
            msg = await admin_channel.fetch_message(int(msg_id))
            await msg.edit(embed=embed)
            return
        except Exception:
            pass

    msg = await admin_channel.send(embed=embed)
    app_data["admin_summary_message_id"] = msg.id
    speichere_daten()


async def update_bewerbung_panel(app_id: str) -> None:
    app_data = bewerbungen["applications"].get(str(app_id))
    if not app_data:
        return

    channel = bot.get_channel(int(app_data.get("channel_id", BEWERBUNG_CHANNEL_ID)))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(app_data.get("channel_id", BEWERBUNG_CHANNEL_ID)))
        except Exception:
            return
    if not isinstance(channel, discord.TextChannel):
        return

    try:
        panel = await channel.fetch_message(int(app_data["panel_message_id"]))
        await panel.edit(embed=bewerbung_panel_embed_from_data(str(app_id), app_data), view=BewerbungVoteView())
    except Exception as fehler:
        print(f"Konnte Bewerbungspanel nicht aktualisieren: {fehler}")

    await update_admin_bewerbung_summary(str(app_id), app_data)


async def erstelle_bewerbungs_panel(message: discord.Message) -> None:
    """Erstellt unter einer Bewerbung eine Abstimmungsnachricht mit Buttons und speichert die IDs dauerhaft."""
    if message.author.bot or message.channel.id != BEWERBUNG_CHANNEL_ID:
        return

    app_id = str(message.id)
    if app_id in bewerbungen["applications"]:
        return

    panel = await message.reply(
        embed=bewerbung_panel_embed(message),
        view=BewerbungVoteView(),
        mention_author=False,
    )

    bewerbungen["applications"][app_id] = {
        "channel_id": message.channel.id,
        "author_id": message.author.id,
        "author_name": str(message.author),
        "message_id": message.id,
        "message_url": message.jump_url,
        "panel_message_id": panel.id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "🟢 Offen",
        "votes": {},
    }
    bewerbungen["panel_to_application"][str(panel.id)] = app_id
    speichere_daten()
    await update_admin_bewerbung_summary(app_id, bewerbungen["applications"][app_id])


async def finde_oder_repariere_bewerbung_zu_panel(panel_message: discord.Message) -> tuple[str | None, dict | None]:
    panel_id = str(panel_message.id)
    app_id = bewerbungen["panel_to_application"].get(panel_id)
    if app_id and app_id in bewerbungen["applications"]:
        return app_id, bewerbungen["applications"][app_id]

    # Reparatur: Wenn das Panel eine Antwort auf die Bewerbung ist, kann die Bewerbungs-ID aus der Referenz gelesen werden.
    ref = panel_message.reference
    ref_id = getattr(ref, "message_id", None) if ref else None
    if ref_id is not None:
        app_id = str(ref_id)
        app_data = bewerbungen["applications"].get(app_id)
        if app_data:
            app_data["panel_message_id"] = panel_message.id
            bewerbungen["panel_to_application"][panel_id] = app_id
            speichere_daten()
            return app_id, app_data

    return None, None


class BewerbungVoteModal(discord.ui.Modal):
    def __init__(self, vote: str, panel_message_id: int):
        titel = "Ja begründen" if vote == "ja" else "Nein begründen"
        super().__init__(title=titel)
        self.vote = vote
        self.panel_message_id = panel_message_id
        self.reason = discord.ui.TextInput(
            label=f"Begründung, mindestens {MIN_BEWERBUNG_BEGRUENDUNG} Zeichen",
            placeholder="Schreibe sachlich, warum du so abstimmst. Niemand außer dir und den Admins sieht diesen Text.",
            style=discord.TextStyle.paragraph,
            min_length=MIN_BEWERBUNG_BEGRUENDUNG,
            max_length=1800,
            required=True,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
            return

        # Mapping über Panel-ID finden. Falls es fehlt, wird es über die Reply-Referenz repariert.
        panel_msg = interaction.message
        if panel_msg is None:
            await interaction.response.send_message("Panel-Nachricht nicht erkannt. Bitte Admin informieren.", ephemeral=True, delete_after=10)
            return

        app_id, app_data = await finde_oder_repariere_bewerbung_zu_panel(panel_msg)
        if app_id is None or app_data is None:
            await interaction.response.send_message(
                "Diese Abstimmung wurde nicht gefunden. Bitte einen Admin bitten, `/bewerbung reparieren` oder `/bewerbung starten` zu nutzen.",
                ephemeral=True,
                delete_after=15,
            )
            return

        if app_data.get("closed") is True:
            await interaction.response.send_message("Diese Abstimmung ist bereits geschlossen.", ephemeral=True, delete_after=10)
            return

        reason = str(self.reason.value).strip()
        if len(reason) < MIN_BEWERBUNG_BEGRUENDUNG:
            await interaction.response.send_message(
                f"Deine Begründung ist zu kurz. Mindestlänge: {MIN_BEWERBUNG_BEGRUENDUNG} Zeichen.",
                ephemeral=True,
                delete_after=10,
            )
            return

        user_id = str(interaction.user.id)
        votes = app_data.setdefault("votes", {})
        changed = user_id in votes
        votes[user_id] = {
            "vote": self.vote,
            "reason": reason,
            "user_id": interaction.user.id,
            "user_name": str(interaction.user),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        speichere_daten()

        admin_channel = await get_admin_abstimmung_channel()
        if admin_channel is not None:
            await admin_channel.send(embed=admin_vote_embed(
                member=interaction.user,
                vote=self.vote,
                reason=reason,
                application_id=app_id,
                application_url=app_data.get("message_url", ""),
                changed=changed,
            ))

        await update_bewerbung_panel(app_id)

        vote_text = "✅ Ja" if self.vote == "ja" else "❌ Nein"
        await interaction.response.send_message(
            f"Deine Stimme **{vote_text}** wurde gespeichert. Du kannst erneut abstimmen, um deine eigene Stimme zu ändern.",
            ephemeral=True,
            delete_after=15,
        )


class BewerbungVoteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ja", emoji="✅", style=discord.ButtonStyle.success, custom_id="bewerbung_vote_ja")
    async def vote_ja(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if not interaction.message:
            await interaction.response.send_message("Panel nicht erkannt.", ephemeral=True, delete_after=5)
            return
        app_id, app_data = await finde_oder_repariere_bewerbung_zu_panel(interaction.message)
        if app_id is None or app_data is None:
            await interaction.response.send_message("Diese Abstimmung wurde nicht gefunden. Bitte Admin informieren.", ephemeral=True, delete_after=10)
            return
        if app_data.get("closed") is True:
            await interaction.response.send_message("Diese Abstimmung ist bereits geschlossen.", ephemeral=True, delete_after=10)
            return
        await interaction.response.send_modal(BewerbungVoteModal("ja", interaction.message.id))

    @discord.ui.button(label="Nein", emoji="❌", style=discord.ButtonStyle.danger, custom_id="bewerbung_vote_nein")
    async def vote_nein(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        if not interaction.message:
            await interaction.response.send_message("Panel nicht erkannt.", ephemeral=True, delete_after=5)
            return
        app_id, app_data = await finde_oder_repariere_bewerbung_zu_panel(interaction.message)
        if app_id is None or app_data is None:
            await interaction.response.send_message("Diese Abstimmung wurde nicht gefunden. Bitte Admin informieren.", ephemeral=True, delete_after=10)
            return
        if app_data.get("closed") is True:
            await interaction.response.send_message("Diese Abstimmung ist bereits geschlossen.", ephemeral=True, delete_after=10)
            return
        await interaction.response.send_modal(BewerbungVoteModal("nein", interaction.message.id))


def bewerbung_stimmen_text(app_id: str, app_data: dict) -> str:
    ja, nein, gesamt = bewerbung_counts(app_data)
    return (
        f"**Bewerbung:** [Zum Beitrag springen]({app_data.get('message_url', '')})\n"
        f"**Status:** {app_data.get('status', '🟢 Offen')}\n"
        f"**Ja:** {ja}\n"
        f"**Nein:** {nein}\n"
        f"**Gesamt:** {gesamt}\n"
        f"**Bewerbungs-ID:** `{app_id}`"
    )


class BewerbungsCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="bewerbung", description="Bewerbungs-Abstimmungen verwalten")

    @app_commands.command(name="starten", description="Admin: Erstellt eine Abstimmung für eine Bewerbungs-Nachricht")
    async def starten(self, interaction: discord.Interaction, message_id: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        channel = await get_bewerbung_channel()
        if channel is None:
            await interaction.followup.send("Bewerbungschannel nicht gefunden.", ephemeral=True)
            return
        try:
            message = await channel.fetch_message(int(message_id))
        except Exception:
            await interaction.followup.send("Nachricht nicht gefunden. Prüfe die Message-ID der Bewerbung.", ephemeral=True)
            return
        if message.author.bot:
            await interaction.followup.send("Für Bot-Nachrichten wird kein Bewerbungspanel erstellt.", ephemeral=True)
            return
        if str(message.id) in bewerbungen["applications"]:
            await interaction.followup.send("Für diese Bewerbung gibt es bereits eine Abstimmung.", ephemeral=True)
            return
        await erstelle_bewerbungs_panel(message)
        await interaction.followup.send("Abstimmung wurde erstellt.", ephemeral=True)

    @app_commands.command(name="neueste", description="Admin: Erstellt eine Abstimmung für die letzte Bewerbung im Bewerbungschannel")
    async def neueste(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = await get_bewerbung_channel()
        if channel is None:
            await interaction.followup.send("Bewerbungschannel nicht gefunden.", ephemeral=True)
            return
        async for message in channel.history(limit=30):
            if not message.author.bot:
                if str(message.id) in bewerbungen["applications"]:
                    await interaction.followup.send("Die neueste Bewerbung hat bereits eine Abstimmung.", ephemeral=True)
                    return
                await erstelle_bewerbungs_panel(message)
                await interaction.followup.send("Abstimmung für die neueste Bewerbung wurde erstellt.", ephemeral=True)
                return
        await interaction.followup.send("Keine passende Bewerbung gefunden.", ephemeral=True)

    @app_commands.command(name="reparieren", description="Admin: Repariert die Abstimmungs-Zuordnung über die Panel-Message-ID")
    async def reparieren(self, interaction: discord.Interaction, panel_message_id: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = await get_bewerbung_channel()
        if channel is None:
            await interaction.followup.send("Bewerbungschannel nicht gefunden.", ephemeral=True)
            return
        try:
            panel_msg = await channel.fetch_message(int(panel_message_id))
        except Exception:
            await interaction.followup.send("Panel-Nachricht nicht gefunden.", ephemeral=True)
            return
        app_id, app_data = await finde_oder_repariere_bewerbung_zu_panel(panel_msg)
        if app_id is None or app_data is None:
            ref_id = getattr(panel_msg.reference, "message_id", None) if panel_msg.reference else None
            if ref_id is None:
                await interaction.followup.send("Dieses Panel ist keine Antwort auf eine Bewerbung. Reparatur nicht möglich.", ephemeral=True)
                return
            try:
                app_msg = await channel.fetch_message(int(ref_id))
            except Exception:
                await interaction.followup.send("Original-Bewerbung nicht gefunden.", ephemeral=True)
                return
            app_id = str(app_msg.id)
            bewerbungen["applications"][app_id] = {
                "channel_id": app_msg.channel.id,
                "author_id": app_msg.author.id,
                "author_name": str(app_msg.author),
                "message_id": app_msg.id,
                "message_url": app_msg.jump_url,
                "panel_message_id": panel_msg.id,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "status": "🟢 Offen",
                "votes": {},
            }
            bewerbungen["panel_to_application"][str(panel_msg.id)] = app_id
            speichere_daten()
        await update_bewerbung_panel(app_id)
        await interaction.followup.send(f"Abstimmung repariert: `{app_id}`", ephemeral=True)

    @app_commands.command(name="stimmen", description="Admin: Zeigt die aktuelle Abstimmungs-Zusammenfassung")
    async def stimmen(self, interaction: discord.Interaction, message_id: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return
        key = str(message_id)
        app_id = key
        app_data = bewerbungen["applications"].get(app_id)
        if app_data is None:
            app_id = bewerbungen["panel_to_application"].get(key, "")
            app_data = bewerbungen["applications"].get(app_id)
        if app_data is None:
            await interaction.response.send_message("Keine Abstimmung zu dieser ID gefunden.", ephemeral=True, delete_after=10)
            return
        await interaction.response.send_message(bewerbung_stimmen_text(app_id, app_data), ephemeral=True)

    @app_commands.command(name="schliessen", description="Admin: Schließt eine Bewerbung und deaktiviert weitere Stimmen")
    async def schliessen(self, interaction: discord.Interaction, message_id: str, angenommen: bool = False) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        key = str(message_id)
        app_id = key
        app_data = bewerbungen["applications"].get(app_id)
        if app_data is None:
            app_id = bewerbungen["panel_to_application"].get(key, "")
            app_data = bewerbungen["applications"].get(app_id)
        if app_data is None:
            await interaction.followup.send("Keine Abstimmung zu dieser ID gefunden.", ephemeral=True)
            return
        app_data["closed"] = True
        app_data["status"] = "✅ Geschlossen: Angenommen" if angenommen else "🔒 Geschlossen"
        app_data["closed_by"] = interaction.user.id
        app_data["closed_at"] = datetime.now().isoformat(timespec="seconds")
        speichere_daten()
        await update_bewerbung_panel(app_id)
        await interaction.followup.send("Abstimmung wurde geschlossen.", ephemeral=True)

    @app_commands.command(name="meine_stimme", description="Zeigt dir deine eigene Stimme zu einer Bewerbung")
    async def meine_stimme(self, interaction: discord.Interaction, message_id: str) -> None:
        key = str(message_id)
        app_id = key
        app_data = bewerbungen["applications"].get(app_id)
        if app_data is None:
            app_id = bewerbungen["panel_to_application"].get(key, "")
            app_data = bewerbungen["applications"].get(app_id)
        if app_data is None:
            await interaction.response.send_message("Keine Abstimmung zu dieser ID gefunden.", ephemeral=True, delete_after=10)
            return
        vote = app_data.get("votes", {}).get(str(interaction.user.id))
        if not vote:
            await interaction.response.send_message("Du hast bei dieser Bewerbung noch nicht abgestimmt.", ephemeral=True, delete_after=10)
            return
        vote_text = "✅ Ja" if vote.get("vote") == "ja" else "❌ Nein"
        await interaction.response.send_message(
            f"**Deine Stimme:** {vote_text}\n\n**Deine Begründung:**\n{vote.get('reason', '')}",
            ephemeral=True,
        )

# =========================
# SLASH COMMANDS
# =========================

class IniCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="ini", description="Ini-Anmeldungen verwalten")

    @app_commands.command(name="liste", description="Zeigt eine Ini-Liste an")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def liste(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
    ) -> None:
        await interaction.response.send_message(embed=ini_embed(tag.value), ephemeral=True, delete_after=15)

    @app_commands.command(name="anmelden_fuer", description="Meldet jemanden für eine Ini an")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    @app_commands.autocomplete(zeit=zeit_autocomplete)
    async def anmelden_fuer(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
        zeit: str,
        fiesta_name: str,
        mitglied: discord.Member | None = None,
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
            return

        if not hat_ini_rolle(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        tag_name = tag.value
        zeit_name = zeit.strip()
        fiesta_name = fiesta_name.strip()

        if zeit_name not in aktive_zeiten(tag_name):
            await interaction.response.send_message(
                "Diese Uhrzeit ist für diesen Tag nicht aktiv.",
                ephemeral=True,
                delete_after=5,
            )
            return

        if len(fiesta_name) < 2:
            await interaction.response.send_message("Der Fiesta-Name ist zu kurz.", ephemeral=True, delete_after=5)
            return

        if fiesta_name_existiert_in_zeit(tag_name, zeit_name, fiesta_name):
            await interaction.response.send_message(
                "Dieser Fiesta-Name steht in diesem Zeitfenster bereits in der Liste.",
                ephemeral=True,
                delete_after=5,
            )
            return

        ini_listen[tag_name][zeit_name].append({
            "fiesta": fiesta_name,
            "eingetragen_von": interaction.user.id,
            "discord_user": mitglied.id if mitglied else None,
        })
        speichere_daten()

        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(tag_name)

        ziel_text = mitglied.mention if mitglied else "Ohne Discord-Mitglied"

        await interaction.followup.send(
            f"**{fiesta_name}** wurde für **{tag_name}** um **{zeit_name}** angemeldet.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"✅ Anmeldung für andere Person - Ini {tag_name}",
                (
                    f"**Eingetragen von:** {interaction.user.mention}\n"
                    f"**Discord-Mitglied:** {ziel_text}\n"
                    f"**Fiesta:** {fiesta_name}\n"
                    f"**Uhrzeit:** {zeit_name}"
                ),
                discord.Color.green(),
            )

    @app_commands.command(name="entfernen", description="Admin: Entfernt einen Fiesta-Namen")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    @app_commands.autocomplete(zeit=zeit_autocomplete)
    async def entfernen(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
        zeit: str,
        fiesta_name: str,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        tag_name = tag.value
        zeit_name = zeit.strip()

        if zeit_name not in ini_listen.get(tag_name, {}):
            await interaction.response.send_message(
                "Diese Uhrzeit wurde für diesen Tag nicht gefunden.",
                ephemeral=True,
                delete_after=5,
            )
            return

        index_gefunden = None
        for index, eintrag in enumerate(ini_listen[tag_name][zeit_name]):
            if eintrag["fiesta"].lower() == fiesta_name.lower():
                index_gefunden = index
                break

        if index_gefunden is None:
            await interaction.response.send_message(
                "Dieser Fiesta-Name ist in diesem Zeitfenster nicht angemeldet.",
                ephemeral=True,
                delete_after=5,
            )
            return

        del ini_listen[tag_name][zeit_name][index_gefunden]
        speichere_daten()
        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(tag_name)

        await interaction.followup.send(
            f"**{fiesta_name}** wurde aus **{tag_name}** um **{zeit_name}** entfernt.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"🛡️ Admin-Entfernung - Ini {tag_name}",
                f"**Admin:** {interaction.user.mention}\n**Fiesta:** {fiesta_name}\n**Uhrzeit:** {zeit_name}",
                discord.Color.dark_blue(),
            )

    @app_commands.command(name="clear", description="Admin: Leert eine Ini-Liste")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def clear(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        tag_name = tag.value
        anzahl = gesamt_teilnehmer(tag_name)
        reset_liste = alte_liste_als_text(tag_name)

        for zeit in aktive_zeiten(tag_name):
            ini_listen[tag_name][zeit].clear()
        speichere_daten()

        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(tag_name)

        await interaction.followup.send(f"Die Liste für **{tag_name}** wurde geleert.", ephemeral=True)

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"🧹 Liste geleert - Ini {tag_name}",
                (
                    f"**Admin:** {interaction.user.mention}\n"
                    f"**Gelöschte Einträge:** {anzahl}\n\n"
                    f"**Zurückgesetzte Liste:**\n\n"
                    f"{reset_liste}"
                ),
                discord.Color.dark_blue(),
            )

    @app_commands.command(
        name="uhrzeit_hinzufuegen",
        description="Admin: Fügt einem Tag ein freies Zeitfenster hinzu",
    )
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def uhrzeit_hinzufuegen(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        await interaction.response.send_modal(UhrzeitHinzufuegenModal(tag.value))

    @app_commands.command(
        name="uhrzeit_bearbeiten",
        description="Admin: Bearbeitet ein vorhandenes Zeitfenster",
    )
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    @app_commands.autocomplete(zeit=zeit_autocomplete)
    async def uhrzeit_bearbeiten(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
        zeit: str,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        zeit = zeit.strip()
        if zeit not in aktive_zeiten(tag.value):
            await interaction.response.send_message(
                "Dieses Zeitfenster wurde nicht gefunden.",
                ephemeral=True,
                delete_after=8,
            )
            return

        await interaction.response.send_modal(
            UhrzeitBearbeitenModal(tag.value, zeit)
        )

    @app_commands.command(
        name="uhrzeit_loeschen",
        description="Admin: Löscht ein leeres Zeitfenster",
    )
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    @app_commands.autocomplete(zeit=zeit_autocomplete)
    async def uhrzeit_loeschen(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
        zeit: str,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        tag_name = tag.value
        zeit = zeit.strip()

        if zeit not in aktive_zeiten(tag_name):
            await interaction.response.send_message(
                "Dieses Zeitfenster wurde nicht gefunden.",
                ephemeral=True,
                delete_after=8,
            )
            return

        if ini_listen.get(tag_name, {}).get(zeit):
            await interaction.response.send_message(
                "Dieses Zeitfenster kann nicht gelöscht werden, solange dort Anmeldungen vorhanden sind.",
                ephemeral=True,
                delete_after=10,
            )
            return

        zeiten_pro_tag[tag_name].remove(zeit)
        ini_listen.get(tag_name, {}).pop(zeit, None)
        speichere_daten()

        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(tag_name)
        await interaction.followup.send(
            f"**{zeit}** wurde für **{tag_name}** gelöscht.",
            ephemeral=True,
        )

    @app_commands.command(
        name="uhrzeiten_anzeigen",
        description="Zeigt alle Zeitfenster eines Tages",
    )
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def uhrzeiten_anzeigen(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
    ) -> None:
        zeiten = aktive_zeiten(tag.value)
        inhalt = "\n".join(
            f"**{index}.** {zeit}"
            for index, zeit in enumerate(zeiten, start=1)
        ) or "*Keine Uhrzeiten festgelegt.*"

        await interaction.response.send_message(
            f"## Ini-Uhrzeiten für {tag.value}\n{inhalt}",
            ephemeral=True,
        )

    @app_commands.command(name="neu_erstellen", description="Admin: Erstellt die Ini-Nachricht neu")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def neu_erstellen(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        await interaction.response.defer(ephemeral=True, thinking=False)
        await update_ini_message(tag.value)

        await interaction.followup.send(
            f"Die Ini-Nachricht für **{tag.value}** wurde geprüft/erstellt.",
            ephemeral=True,
        )



@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if message.channel.id == BEWERBUNG_CHANNEL_ID:
        try:
            await erstelle_bewerbungs_panel(message)
        except Exception as fehler:
            print(f"Konnte Bewerbungspanel nicht erstellen: {fehler}")

    await bot.process_commands(message)

# =========================
# BOT START
# =========================

@bot.event
async def on_ready() -> None:
    global bot_ready_done

    print(f"Eingeloggt als {bot.user}")

    if bot_ready_done:
        return

    bot_ready_done = True

    lade_daten()

    guild = discord.Object(id=GUILD_ID)

    bot.add_view(BewerbungVoteView())
    bot.add_view(SupportPanelView())
    bot.add_view(SupportTicketView())
    for tag in TAGE:
        bot.add_view(IniView(tag))

    try:
        bot.tree.add_command(IniCommands(), guild=guild)
    except app_commands.CommandAlreadyRegistered:
        pass

    try:
        bot.tree.add_command(BewerbungsCommands(), guild=guild)
    except app_commands.CommandAlreadyRegistered:
        pass

    try:
        bot.tree.add_command(SupportCommands(), guild=guild)
    except app_commands.CommandAlreadyRegistered:
        pass

    await bot.tree.sync(guild=guild)

    for tag in TAGE:
        await update_ini_message(tag)

    if SUPPORT_PANEL_CHANNEL_ID > 0:
        await erstelle_oder_aktualisiere_support_panel()

    print("Bot ist bereit.")


if TOKEN is None:
    raise RuntimeError("DISCORD_TOKEN fehlt. Trage ihn bei Railway unter Variables ein.")

bot.run(TOKEN)
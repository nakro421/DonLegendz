import os
import json
from pathlib import Path
from datetime import datetime

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

ZEITEN = [
    "09:00 - 11:00",
    "11:00 - 13:00",
    "13:30 - 15:30",
    "15:30 - 17:30",
    "18:00 - 20:00",
    "20:00 - 22:00",
    "22:30 - 00:30",
    "00:30 - 02:30",
]

BUTTON_LABELS = {
    "09:00 - 11:00": "09:00",
    "11:00 - 13:00": "11:00",
    "13:30 - 15:30": "13:30",
    "15:30 - 17:30": "15:30",
    "18:00 - 20:00": "18:00",
    "20:00 - 22:00": "20:00",
    "22:30 - 00:30": "22:30",
    "00:30 - 02:30": "00:30",
}

TAGE = list(INI_CHANNELS.keys())

# Gleiche Namen dürfen in unterschiedlichen Uhrzeiten mehrfach stehen.
# Nur im selben Zeitfenster wird ein doppelter Name blockiert.
ini_listen: dict[str, dict[str, list[dict]]] = {
    tag: {zeit: [] for zeit in ZEITEN}
    for tag in TAGE
}

# Cache, damit der Bot die feste Ini-Nachricht nicht jedes Mal neu suchen muss.
ini_message_cache: dict[str, int] = {}

# Bewerbungsdaten werden ebenfalls dauerhaft gespeichert.
bewerbungen: dict = {
    "applications": {},
    "panel_to_application": {},
}


def leere_ini_listen() -> dict[str, dict[str, list[dict]]]:
    return {tag: {zeit: [] for zeit in ZEITEN} for tag in TAGE}


def normalisiere_ini_daten(rohdaten: object) -> dict[str, dict[str, list[dict]]]:
    """Sorgt dafür, dass neue Tage/Zeiten nach Code-Updates sauber angelegt werden."""
    neue_daten = leere_ini_listen()

    if not isinstance(rohdaten, dict):
        return neue_daten

    for tag in TAGE:
        tag_daten = rohdaten.get(tag, {})
        if not isinstance(tag_daten, dict):
            continue

        for zeit in ZEITEN:
            eintraege = tag_daten.get(zeit, [])
            if isinstance(eintraege, list):
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


def lade_daten() -> None:
    """Lädt gespeicherte Daten aus dem Railway Volume."""
    global ini_listen, bewerbungen

    if not DATA_FILE.exists():
        ini_listen = leere_ini_listen()
        speichere_daten()
        print(f"Neue Datendatei erstellt: {DATA_FILE}")
        return

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            daten = json.load(file)
    except Exception as fehler:
        print(f"Konnte Datendatei nicht laden: {fehler}")
        ini_listen = leere_ini_listen()
        return

    ini_listen = normalisiere_ini_daten(daten.get("ini", {}))
    bewerbungen = normalisiere_bewerbungsdaten(daten.get("bewerbungen", {}))
    print(f"Daten geladen: {DATA_FILE}")


def speichere_daten() -> None:
    """Speichert alle wichtigen Bot-Daten dauerhaft im Railway Volume."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    daten = {
        "version": 1,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "ini": ini_listen,
        "bewerbungen": bewerbungen,
        "klassen": {},
        "settings": {},
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


def fiesta_name_existiert_in_zeit(tag: str, zeit: str, fiesta_name: str, ignore_index: int | None = None) -> bool:
    for index, eintrag in enumerate(ini_listen[tag][zeit]):
        if ignore_index is not None and index == ignore_index:
            continue
        if eintrag["fiesta"].lower() == fiesta_name.lower():
            return True
    return False


def gesamt_teilnehmer(tag: str) -> int:
    return sum(len(ini_listen[tag][zeit]) for zeit in ZEITEN)


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
    for zeit in ZEITEN:
        for index, eintrag in enumerate(ini_listen[tag][zeit]):
            if eintrag["fiesta"].lower() == fiesta_name.lower():
                return zeit, index, eintrag
    return None, None, None


def finde_alle_eintraege_nach_fiesta(tag: str, fiesta_name: str) -> list[tuple[str, int, dict]]:
    treffer = []
    for zeit in ZEITEN:
        for index, eintrag in enumerate(ini_listen[tag][zeit]):
            if eintrag["fiesta"].lower() == fiesta_name.lower():
                treffer.append((zeit, index, eintrag))
    return treffer


def alte_liste_als_text(tag: str) -> str:
    teile = []

    for zeit in ZEITEN:
        daten = ini_listen[tag][zeit]

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

    for zeit in ZEITEN:
        daten = ini_listen[tag][zeit]
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


# =========================
# VIEWS / BUTTONS
# =========================

class AbmeldenZeitView(discord.ui.View):
    def __init__(self, tag: str, fiesta_name: str, treffer: list[tuple[str, int, dict]]):
        super().__init__(timeout=30)
        self.tag = tag
        self.fiesta_name = fiesta_name

        for button_index, (zeit, _index, _eintrag) in enumerate(treffer[:8]):
            button = discord.ui.Button(
                label=BUTTON_LABELS.get(zeit, zeit),
                emoji="🕒",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ini_abmelden_zeit_{tag}_{button_index}",
                row=button_index // 4,
            )
            button.callback = self.make_abmelden_callback(zeit)
            self.add_item(button)

    def make_abmelden_callback(self, zeit: str):
        async def callback(interaction: discord.Interaction) -> None:
            if not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
                return

            if not hat_ini_rolle(interaction.user):
                await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
                return

            index_gefunden = None
            for index, eintrag in enumerate(ini_listen[self.tag][zeit]):
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
                    f"**Abgemeldet von:** {interaction.user.mention}\n**Fiesta:** {self.fiesta_name}\n**Uhrzeit:** {zeit}",
                    discord.Color.red(),
                )

        return callback


class IniView(discord.ui.View):
    def __init__(self, tag: str):
        super().__init__(timeout=None)
        self.tag = tag

        for index, zeit in enumerate(ZEITEN):
            row = 0 if index < 5 else 1
            button = discord.ui.Button(
                label=BUTTON_LABELS.get(zeit, zeit),
                emoji="🕒",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ini_anmelden_{tag}_{index}",
                row=row,
            )
            button.callback = self.make_anmelden_callback(zeit)
            self.add_item(button)

        abmelden = discord.ui.Button(
            label="Abmelden",
            emoji="👤",
            style=discord.ButtonStyle.danger,
            custom_id=f"ini_abmelden_{tag}",
            row=2,
        )
        abmelden.callback = self.abmelden_callback
        self.add_item(abmelden)

        aendern = discord.ui.Button(
            label="Namen ändern",
            emoji="✏️",
            style=discord.ButtonStyle.primary,
            custom_id=f"ini_aendern_{tag}",
            row=2,
        )
        aendern.callback = self.aendern_callback
        self.add_item(aendern)

        reset = discord.ui.Button(
            label="Liste resetten",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ini_reset_{tag}",
            row=2,
        )
        reset.callback = self.reset_callback
        self.add_item(reset)

    def make_anmelden_callback(self, zeit: str):
        async def callback(interaction: discord.Interaction) -> None:
            if not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True, delete_after=5)
                return

            if not hat_ini_rolle(interaction.user):
                await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
                return

            await interaction.response.send_modal(AnmeldungModal(self.tag, zeit))

        return callback

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

        for zeit in ZEITEN:
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
    @app_commands.choices(
        tag=[app_commands.Choice(name=t, value=t) for t in TAGE],
        zeit=[app_commands.Choice(name=z, value=z) for z in ZEITEN],
    )
    async def anmelden_fuer(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
        zeit: app_commands.Choice[str],
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
        zeit_name = zeit.value
        fiesta_name = fiesta_name.strip()

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
    @app_commands.choices(
        tag=[app_commands.Choice(name=t, value=t) for t in TAGE],
        zeit=[app_commands.Choice(name=z, value=z) for z in ZEITEN],
    )
    async def entfernen(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
        zeit: app_commands.Choice[str],
        fiesta_name: str,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        tag_name = tag.value
        zeit_name = zeit.value

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

        for zeit in ZEITEN:
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

    try:
        bot.tree.add_command(IniCommands(), guild=guild)
    except app_commands.CommandAlreadyRegistered:
        pass

    try:
        bot.tree.add_command(BewerbungsCommands(), guild=guild)
    except app_commands.CommandAlreadyRegistered:
        pass

    await bot.tree.sync(guild=guild)

    for tag in TAGE:
        await update_ini_message(tag)

    print("Bot ist bereit.")


if TOKEN is None:
    raise RuntimeError("DISCORD_TOKEN fehlt. Trage ihn bei Railway unter Variables ein.")

bot.run(TOKEN)

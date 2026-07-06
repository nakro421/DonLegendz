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
        "gladi": "⚔️",
        "zaubi": "🔮",
        "hexi": "✨",
        "tr": "🛡️",
        "assa": "🗡️",
        "hk": "❤️",
        "luna": "🌙",
        "ordi": "📖",
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
            label="Fiesta-Charaktername",
            placeholder="Dein Fiesta-Name oder Name von jemand anderem",
            min_length=2,
            max_length=30,
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
# BEWERBUNGSSYSTEM
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


def bewerbung_panel_embed(message: discord.Message) -> discord.Embed:
    embed = discord.Embed(
        title="🗳️ Anonyme Bewerbungs-Abstimmung",
        description=(
            "Stimme für diese Bewerbung ab.\n\n"
            "✅ **Ja** = aufnehmen\n"
            "❌ **Nein** = ablehnen\n\n"
            f"📝 Eine Begründung mit mindestens **{MIN_BEWERBUNG_BEGRUENDUNG} Zeichen** ist Pflicht.\n"
            "🔒 Deine Stimme ist für normale Mitglieder anonym. Nur du selbst und Admins können sie sehen."
        ),
        color=discord.Color.from_rgb(88, 101, 242),
        timestamp=datetime.now(),
    )
    embed.add_field(name="Bewerbung", value=f"[Zum Beitrag springen]({message.jump_url})", inline=False)
    embed.set_footer(text="Bitte fair und sachlich abstimmen.")
    return embed


def admin_vote_embed(
    *,
    member: discord.Member,
    vote: str,
    reason: str,
    application_id: str,
    application_url: str,
    changed: bool,
) -> discord.Embed:
    vote_text = "✅ Ja" if vote == "ja" else "❌ Nein"
    title = "🗳️ Bewerbungs-Stimme aktualisiert" if changed else "🗳️ Neue Bewerbungs-Stimme"
    color = discord.Color.green() if vote == "ja" else discord.Color.red()

    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=datetime.now(),
    )
    embed.add_field(name="Abstimmer", value=f"{member.mention}\n`{member.id}`", inline=True)
    embed.add_field(name="Stimme", value=vote_text, inline=True)
    embed.add_field(name="Bewerbung", value=f"[Zum Beitrag springen]({application_url})\n`{application_id}`", inline=False)
    embed.add_field(name=f"Begründung ({len(reason)} Zeichen)", value=reason[:1000], inline=False)
    if len(reason) > 1000:
        embed.add_field(name="Begründung Fortsetzung", value=reason[1000:2000], inline=False)
    return embed


async def erstelle_bewerbungs_panel(message: discord.Message) -> None:
    """Erstellt unter einer Bewerbung eine Abstimmungsnachricht mit Buttons."""
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
        "message_id": message.id,
        "message_url": message.jump_url,
        "panel_message_id": panel.id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "votes": {},
    }
    bewerbungen["panel_to_application"][str(panel.id)] = app_id
    speichere_daten()


async def finde_bewerbung_zu_panel(panel_message_id: int) -> tuple[str | None, dict | None]:
    panel_id = str(panel_message_id)
    app_id = bewerbungen["panel_to_application"].get(panel_id)
    if not app_id:
        return None, None
    return app_id, bewerbungen["applications"].get(app_id)


class BewerbungVoteModal(discord.ui.Modal):
    def __init__(self, vote: str, panel_message_id: int):
        titel = "Ja begründen" if vote == "ja" else "Nein begründen"
        super().__init__(title=titel)
        self.vote = vote
        self.panel_message_id = panel_message_id

        self.reason = discord.ui.TextInput(
            label=f"Begründung, mindestens {MIN_BEWERBUNG_BEGRUENDUNG} Zeichen",
            placeholder="Schreibe sachlich, warum du so abstimmst.",
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

        app_id, app_data = await finde_bewerbung_zu_panel(self.panel_message_id)
        if app_id is None or app_data is None:
            await interaction.response.send_message(
                "Diese Abstimmung wurde nicht gefunden. Bitte einen Admin informieren.",
                ephemeral=True,
                delete_after=10,
            )
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
            await admin_channel.send(
                embed=admin_vote_embed(
                    member=interaction.user,
                    vote=self.vote,
                    reason=reason,
                    application_id=app_id,
                    application_url=app_data.get("message_url", ""),
                    changed=changed,
                )
            )

        vote_text = "✅ Ja" if self.vote == "ja" else "❌ Nein"
        await interaction.response.send_message(
            f"Deine Stimme **{vote_text}** wurde gespeichert. Deine Begründung ist nur für dich und Admins sichtbar.",
            ephemeral=True,
            delete_after=15,
        )


class BewerbungVoteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ja abstimmen",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="bewerbung_vote_ja",
    )
    async def vote_ja(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_modal(BewerbungVoteModal("ja", interaction.message.id))

    @discord.ui.button(
        label="Nein abstimmen",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        custom_id="bewerbung_vote_nein",
    )
    async def vote_nein(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_modal(BewerbungVoteModal("nein", interaction.message.id))


def bewerbung_stimmen_text(app_id: str, app_data: dict) -> str:
    votes = app_data.get("votes", {})
    ja = sum(1 for v in votes.values() if v.get("vote") == "ja")
    nein = sum(1 for v in votes.values() if v.get("vote") == "nein")
    return (
        f"**Bewerbung:** [Zum Beitrag springen]({app_data.get('message_url', '')})\n"
        f"**Ja:** {ja}\n"
        f"**Nein:** {nein}\n"
        f"**Gesamt:** {len(votes)}\n"
        f"**Bewerbungs-ID:** `{app_id}`"
    )


class BewerbungsCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="bewerbung", description="Bewerbungs-Abstimmungen verwalten")

    @app_commands.command(name="panel_erstellen", description="Admin: Erstellt eine Abstimmung für eine Bewerbung per Message-ID")
    async def panel_erstellen(self, interaction: discord.Interaction, message_id: str) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True, delete_after=5)
            return

        channel = await get_bewerbung_channel()
        if channel is None:
            await interaction.response.send_message("Bewerbungschannel nicht gefunden.", ephemeral=True, delete_after=10)
            return

        try:
            message = await channel.fetch_message(int(message_id))
        except Exception:
            await interaction.response.send_message("Nachricht nicht gefunden. Prüfe die Message-ID.", ephemeral=True, delete_after=10)
            return

        if message.author.bot:
            await interaction.response.send_message("Für Bot-Nachrichten wird kein Bewerbungspanel erstellt.", ephemeral=True, delete_after=10)
            return

        if str(message.id) in bewerbungen["applications"]:
            await interaction.response.send_message("Für diese Bewerbung gibt es bereits ein Panel.", ephemeral=True, delete_after=10)
            return

        await erstelle_bewerbungs_panel(message)
        await interaction.response.send_message("Abstimmungspanel wurde erstellt.", ephemeral=True, delete_after=10)

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

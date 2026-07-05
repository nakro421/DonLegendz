import os
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
    beschreibung = []

    for zeit in ZEITEN:
        daten = ini_listen[tag][zeit]

        if daten:
            teilnehmer = "\n".join(
                f"`{i:02d}.` **{eintrag['fiesta']}**"
                for i, eintrag in enumerate(daten, start=1)
            )
        else:
            teilnehmer = "*Noch niemand angemeldet.*"

        beschreibung.append(f"### {zeit}\n{teilnehmer}")

    embed = discord.Embed(
        title=f"📅 Ini {tag}",
        description="\n\n".join(beschreibung),
        color=discord.Color.dark_blue(),
        timestamp=datetime.now(),
    )
    embed.set_footer(text=f"Teilnehmer gesamt: {gesamt_teilnehmer(tag)}")
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

    guild = discord.Object(id=GUILD_ID)

    try:
        bot.tree.add_command(IniCommands(), guild=guild)
    except app_commands.CommandAlreadyRegistered:
        pass

    await bot.tree.sync(guild=guild)

    for tag in TAGE:
        await update_ini_message(tag)

    print("Bot ist bereit.")


if TOKEN is None:
    raise RuntimeError("DISCORD_TOKEN fehlt. Trage ihn bei Railway unter Variables ein.")

bot.run(TOKEN)

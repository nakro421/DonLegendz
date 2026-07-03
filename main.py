import os
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands

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
    "14:00 - 16:00",
    "16:00 - 18:00",
    "18:00 - 20:00",
    "20:00 - 22:00",
    "22:00 - 00:00",
]

TAGE = list(INI_CHANNELS.keys())

ini_listen = {
    tag: {zeit: {} for zeit in ZEITEN}
    for tag in TAGE
}

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot_ready_done = False


def ist_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or any(
        role.name == ADMIN_ROLE_NAME for role in member.roles
    )


def hat_ini_rolle(member: discord.Member) -> bool:
    return ist_admin(member) or any(role.name == INI_ROLE_NAME for role in member.roles)


def finde_eintrag(tag: str, user_id: int):
    for zeit in ZEITEN:
        if user_id in ini_listen[tag][zeit]:
            return zeit, ini_listen[tag][zeit][user_id]
    return None, None


def fiesta_name_existiert(tag: str, fiesta_name: str, ignore_user_id: int | None = None) -> bool:
    for zeit in ZEITEN:
        for user_id, name in ini_listen[tag][zeit].items():
            if ignore_user_id is not None and user_id == ignore_user_id:
                continue
            if name.lower() == fiesta_name.lower():
                return True
    return False


def gesamt_teilnehmer(tag: str) -> int:
    return sum(len(ini_listen[tag][zeit]) for zeit in ZEITEN)


def ini_embed(tag: str) -> discord.Embed:
    beschreibung = ""

    for zeit in ZEITEN:
        daten = ini_listen[tag][zeit]

        if daten:
            teilnehmer = "\n".join(
                f"**{i}.** {name}"
                for i, name in enumerate(daten.values(), start=1)
            )
        else:
            teilnehmer = "*Noch niemand angemeldet.*"

        beschreibung += f"🕒 **{zeit}**\n{teilnehmer}\n\n"

    embed = discord.Embed(
        title=f"📅 Ini {tag}",
        description=beschreibung,
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"Teilnehmer gesamt: {gesamt_teilnehmer(tag)}")
    return embed


async def log_senden(guild: discord.Guild, titel: str, text: str, farbe: discord.Color):
    channel = guild.get_channel(LOG_CHANNEL_ID)

    if channel is None:
        try:
            channel = await guild.fetch_channel(LOG_CHANNEL_ID)
        except Exception:
            return

    embed = discord.Embed(
        title=titel,
        description=text,
        color=farbe,
        timestamp=datetime.now(),
    )
    await channel.send(embed=embed)


async def get_ini_channel(tag: str):
    channel = bot.get_channel(INI_CHANNELS[tag])

    if channel is None:
        try:
            channel = await bot.fetch_channel(INI_CHANNELS[tag])
        except Exception:
            return None

    return channel


class AnmeldungModal(discord.ui.Modal):
    def __init__(self, tag: str, zeit: str):
        super().__init__(title=f"Anmeldung {tag} | {zeit}")
        self.tag = tag
        self.zeit = zeit

        self.name = discord.ui.TextInput(
            label="Fiesta-Charaktername",
            placeholder="Dein Fiesta-Name",
            min_length=2,
            max_length=30,
            required=True,
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True)
            return

        member = interaction.user
        fiesta_name = str(self.name.value).strip()

        if not hat_ini_rolle(member):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)
            return

        alte_zeit, _ = finde_eintrag(self.tag, member.id)

        if alte_zeit is not None:
            await interaction.response.send_message(
                f"Du bist für **{self.tag}** bereits bei **{alte_zeit}** angemeldet.",
                ephemeral=True,
            )
            return

        if fiesta_name_existiert(self.tag, fiesta_name):
            await interaction.response.send_message(
                "Dieser Fiesta-Name steht an diesem Tag bereits in der Liste.",
                ephemeral=True,
            )
            return

        ini_listen[self.tag][self.zeit][member.id] = fiesta_name
        await update_ini_message(self.tag)

        await interaction.response.send_message(
            f"Du wurdest für **{self.tag}** um **{self.zeit}** mit **{fiesta_name}** angemeldet.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"✅ Anmeldung - Ini {self.tag}",
                f"**Discord:** {member.mention}\n**Fiesta:** {fiesta_name}\n**Uhrzeit:** {self.zeit}",
                discord.Color.green(),
            )


class AendernModal(discord.ui.Modal):
    def __init__(self, tag: str):
        super().__init__(title=f"Namen ändern - Ini {tag}")
        self.tag = tag

        self.name = discord.ui.TextInput(
            label="Neuer Fiesta-Charaktername",
            placeholder="Neuer Fiesta-Name",
            min_length=2,
            max_length=30,
            required=True,
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True)
            return

        member = interaction.user
        neuer_name = str(self.name.value).strip()
        zeit, alter_name = finde_eintrag(self.tag, member.id)

        if zeit is None:
            await interaction.response.send_message(
                f"Du bist für **{self.tag}** nicht angemeldet.",
                ephemeral=True,
            )
            return

        if fiesta_name_existiert(self.tag, neuer_name, ignore_user_id=member.id):
            await interaction.response.send_message(
                "Dieser Fiesta-Name steht an diesem Tag bereits in der Liste.",
                ephemeral=True,
            )
            return

        ini_listen[self.tag][zeit][member.id] = neuer_name
        await update_ini_message(self.tag)

        await interaction.response.send_message(
            f"Geändert: **{alter_name}** → **{neuer_name}**",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"✏️ Änderung - Ini {self.tag}",
                f"**Discord:** {member.mention}\n**Uhrzeit:** {zeit}\n**Alt:** {alter_name}\n**Neu:** {neuer_name}",
                discord.Color.orange(),
            )


class ZeitAuswahl(discord.ui.Select):
    def __init__(self, tag: str):
        self.tag = tag

        options = [
            discord.SelectOption(label=zeit, value=zeit, emoji="🕒")
            for zeit in ZEITEN
        ]

        super().__init__(
            placeholder="Wähle eine Uhrzeit aus",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"zeit_select_{tag}",
        )

    async def callback(self, interaction: discord.Interaction):
        zeit = self.values[0]
        await interaction.response.send_modal(AnmeldungModal(self.tag, zeit))


class ZeitAuswahlView(discord.ui.View):
    def __init__(self, tag: str):
        super().__init__(timeout=120)
        self.add_item(ZeitAuswahl(tag))


class IniView(discord.ui.View):
    def __init__(self, tag: str):
        super().__init__(timeout=None)
        self.tag = tag

        anmelden = discord.ui.Button(
            label="Anmelden",
            emoji="✅",
            style=discord.ButtonStyle.green,
            custom_id=f"ini_anmelden_{tag}",
        )
        anmelden.callback = self.anmelden_callback
        self.add_item(anmelden)

        abmelden = discord.ui.Button(
            label="Abmelden",
            emoji="❌",
            style=discord.ButtonStyle.red,
            custom_id=f"ini_abmelden_{tag}",
        )
        abmelden.callback = self.abmelden_callback
        self.add_item(abmelden)

        aendern = discord.ui.Button(
            label="Namen ändern",
            emoji="✏️",
            style=discord.ButtonStyle.blurple,
            custom_id=f"ini_aendern_{tag}",
        )
        aendern.callback = self.aendern_callback
        self.add_item(aendern)

    async def anmelden_callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True)
            return

        if not hat_ini_rolle(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Wähle eine Uhrzeit für **{self.tag}** aus:",
            view=ZeitAuswahlView(self.tag),
            ephemeral=True,
        )

    async def abmelden_callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True)
            return

        member = interaction.user
        zeit, alter_name = finde_eintrag(self.tag, member.id)

        if zeit is None:
            await interaction.response.send_message(
                f"Du bist für **{self.tag}** nicht angemeldet.",
                ephemeral=True,
            )
            return

        del ini_listen[self.tag][zeit][member.id]
        await update_ini_message(self.tag)

        await interaction.response.send_message(
            f"Du wurdest von **{self.tag}** um **{zeit}** abgemeldet.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"❌ Abmeldung - Ini {self.tag}",
                f"**Discord:** {member.mention}\n**Fiesta:** {alter_name}\n**Uhrzeit:** {zeit}",
                discord.Color.red(),
            )

    async def aendern_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AendernModal(self.tag))


async def finde_ini_message(channel: discord.TextChannel, tag: str):
    async for msg in channel.history(limit=50):
        if msg.author == bot.user and msg.embeds:
            if msg.embeds[0].title == f"📅 Ini {tag}":
                return msg
    return None


async def update_ini_message(tag: str):
    channel = await get_ini_channel(tag)

    if channel is None:
        print(f"Channel für {tag} nicht gefunden.")
        return

    msg = await finde_ini_message(channel, tag)

    if msg:
        await msg.edit(embed=ini_embed(tag), view=IniView(tag))
    else:
        await channel.send(embed=ini_embed(tag), view=IniView(tag))


class IniCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="ini", description="Ini-Anmeldungen verwalten")

    @app_commands.command(name="liste", description="Zeigt eine Ini-Liste an")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def liste(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
    ):
        await interaction.response.send_message(embed=ini_embed(tag.value), ephemeral=True)

    @app_commands.command(name="entfernen", description="Admin: Entfernt ein Mitglied")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def entfernen(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
        mitglied: discord.Member,
    ):
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)
            return

        tag_name = tag.value
        zeit, alter_name = finde_eintrag(tag_name, mitglied.id)

        if zeit is None:
            await interaction.response.send_message(
                "Dieses Mitglied ist dort nicht angemeldet.",
                ephemeral=True,
            )
            return

        del ini_listen[tag_name][zeit][mitglied.id]
        await update_ini_message(tag_name)

        await interaction.response.send_message(
            f"{mitglied.mention} wurde aus **{tag_name}** entfernt.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"🛡️ Admin-Entfernung - Ini {tag_name}",
                f"**Admin:** {interaction.user.mention}\n**Entfernt:** {mitglied.mention}\n**Fiesta:** {alter_name}\n**Uhrzeit:** {zeit}",
                discord.Color.dark_blue(),
            )

    @app_commands.command(name="clear", description="Admin: Leert eine Ini-Liste")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def clear(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
    ):
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)
            return

        tag_name = tag.value
        anzahl = gesamt_teilnehmer(tag_name)

        for zeit in ZEITEN:
            ini_listen[tag_name][zeit].clear()

        await update_ini_message(tag_name)

        await interaction.response.send_message(
            f"Die Liste für **{tag_name}** wurde geleert.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"🧹 Liste geleert - Ini {tag_name}",
                f"**Admin:** {interaction.user.mention}\n**Gelöschte Einträge:** {anzahl}",
                discord.Color.dark_blue(),
            )

    @app_commands.command(name="neu_erstellen", description="Admin: Erstellt die Ini-Nachricht neu")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def neu_erstellen(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
    ):
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)
            return

        await update_ini_message(tag.value)

        await interaction.response.send_message(
            f"Die Ini-Nachricht für **{tag.value}** wurde geprüft/erstellt.",
            ephemeral=True,
        )


@bot.event
async def on_ready():
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

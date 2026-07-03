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

TAGE = list(INI_CHANNELS.keys())
ini_listen: dict[str, dict[int, str]] = {tag: {} for tag in TAGE}

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


def ini_embed(tag: str) -> discord.Embed:
    daten = ini_listen[tag]

    if daten:
        teilnehmer = "\n".join(
            f"**{i}.** {name}" for i, name in enumerate(daten.values(), start=1)
        )
    else:
        teilnehmer = "*Noch niemand angemeldet.*"

    embed = discord.Embed(
        title=f"📅 Ini {tag}",
        description=f"👥 **Teilnehmer**\n\n{teilnehmer}",
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"Teilnehmer: {len(daten)}")
    return embed


async def log_senden(
    guild: discord.Guild,
    titel: str,
    text: str,
    farbe: discord.Color
) -> None:
    channel = guild.get_channel(LOG_CHANNEL_ID)

    if channel is None:
        try:
            channel = await guild.fetch_channel(LOG_CHANNEL_ID)
        except Exception:
            return

    if isinstance(channel, discord.TextChannel):
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
            fetched = await bot.fetch_channel(INI_CHANNELS[tag])
            if isinstance(fetched, discord.TextChannel):
                return fetched
        except Exception:
            return None

    if isinstance(channel, discord.TextChannel):
        return channel

    return None


class AnmeldungModal(discord.ui.Modal):
    def __init__(self, tag: str):
        super().__init__(title=f"Anmeldung für Ini {tag}")
        self.tag = tag

        self.name = discord.ui.TextInput(
            label="Fiesta-Charaktername",
            placeholder="Dein Fiesta-Name",
            min_length=2,
            max_length=30,
            required=True,
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True)
            return

        member = interaction.user
        tag = self.tag
        fiesta_name = str(self.name.value).strip()

        if not hat_ini_rolle(member):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)
            return

        if member.id in ini_listen[tag]:
            await interaction.response.send_message(
                f"Du bist für **{tag}** bereits angemeldet.",
                ephemeral=True,
            )
            return

        if fiesta_name.lower() in [n.lower() for n in ini_listen[tag].values()]:
            await interaction.response.send_message(
                "Dieser Fiesta-Name steht bereits in der Liste.",
                ephemeral=True,
            )
            return

        ini_listen[tag][member.id] = fiesta_name
        await update_ini_message(tag)

        await interaction.response.send_message(
            f"Du wurdest für **{tag}** mit **{fiesta_name}** angemeldet.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"✅ Anmeldung - Ini {tag}",
                f"**Discord:** {member.mention}\n**Fiesta:** {fiesta_name}",
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

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True)
            return

        member = interaction.user
        tag = self.tag
        neuer_name = str(self.name.value).strip()

        if member.id not in ini_listen[tag]:
            await interaction.response.send_message(
                f"Du bist für **{tag}** nicht angemeldet.",
                ephemeral=True,
            )
            return

        if neuer_name.lower() in [
            n.lower() for uid, n in ini_listen[tag].items() if uid != member.id
        ]:
            await interaction.response.send_message(
                "Dieser Fiesta-Name steht bereits in der Liste.",
                ephemeral=True,
            )
            return

        alter_name = ini_listen[tag][member.id]
        ini_listen[tag][member.id] = neuer_name

        await update_ini_message(tag)

        await interaction.response.send_message(
            f"Geändert: **{alter_name}** → **{neuer_name}**",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"✏️ Änderung - Ini {tag}",
                f"**Discord:** {member.mention}\n**Alt:** {alter_name}\n**Neu:** {neuer_name}",
                discord.Color.orange(),
            )


class IniView(discord.ui.View):
    def __init__(self, tag: str):
        super().__init__(timeout=None)
        self.tag = tag

    @discord.ui.button(
        label="Anmelden",
        emoji="✅",
        style=discord.ButtonStyle.green,
        custom_id="ini_button_anmelden"
    )
    async def anmelden(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(AnmeldungModal(self.tag))

    @discord.ui.button(
        label="Abmelden",
        emoji="❌",
        style=discord.ButtonStyle.red,
        custom_id="ini_button_abmelden"
    )
    async def abmelden(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Fehler: Mitglied nicht erkannt.", ephemeral=True)
            return

        member = interaction.user
        tag = self.tag

        if member.id not in ini_listen[tag]:
            await interaction.response.send_message(
                f"Du bist für **{tag}** nicht angemeldet.",
                ephemeral=True,
            )
            return

        alter_name = ini_listen[tag].pop(member.id)
        await update_ini_message(tag)

        await interaction.response.send_message(
            f"Du wurdest von **{tag}** abgemeldet.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"❌ Abmeldung - Ini {tag}",
                f"**Discord:** {member.mention}\n**Fiesta:** {alter_name}",
                discord.Color.red(),
            )

    @discord.ui.button(
        label="Namen ändern",
        emoji="✏️",
        style=discord.ButtonStyle.blurple,
        custom_id="ini_button_aendern"
    )
    async def aendern(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(AendernModal(self.tag))


async def finde_ini_message(channel: discord.TextChannel, tag: str) -> discord.Message | None:
    async for msg in channel.history(limit=50):
        if msg.author == bot.user and msg.embeds:
            if msg.embeds[0].title == f"📅 Ini {tag}":
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
        tag: app_commands.Choice[str]
    ) -> None:
        await interaction.response.send_message(embed=ini_embed(tag.value), ephemeral=True)

    @app_commands.command(name="entfernen", description="Admin: Entfernt ein Mitglied")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def entfernen(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str],
        mitglied: discord.Member
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)
            return

        tag_name = tag.value

        if mitglied.id not in ini_listen[tag_name]:
            await interaction.response.send_message(
                "Dieses Mitglied ist dort nicht angemeldet.",
                ephemeral=True,
            )
            return

        alter_name = ini_listen[tag_name].pop(mitglied.id)
        await update_ini_message(tag_name)

        await interaction.response.send_message(
            f"{mitglied.mention} wurde aus **{tag_name}** entfernt.",
            ephemeral=True,
        )

        if interaction.guild:
            await log_senden(
                interaction.guild,
                f"🛡️ Admin-Entfernung - Ini {tag_name}",
                f"**Admin:** {interaction.user.mention}\n**Entfernt:** {mitglied.mention}\n**Fiesta:** {alter_name}",
                discord.Color.dark_blue(),
            )

    @app_commands.command(name="clear", description="Admin: Leert eine Ini-Liste")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def clear(
        self,
        interaction: discord.Interaction,
        tag: app_commands.Choice[str]
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)
            return

        tag_name = tag.value
        anzahl = len(ini_listen[tag_name])
        ini_listen[tag_name].clear()

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
        tag: app_commands.Choice[str]
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or not ist_admin(interaction.user):
            await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)
            return

        await update_ini_message(tag.value)

        await interaction.response.send_message(
            f"Die Ini-Nachricht für **{tag.value}** wurde geprüft/erstellt.",
            ephemeral=True,
        )


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

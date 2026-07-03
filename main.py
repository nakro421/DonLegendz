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
ini_listen = {tag: {} for tag in TAGE}

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def ist_admin(member):
    return member.guild_permissions.administrator or any(role.name == ADMIN_ROLE_NAME for role in member.roles)


def hat_ini_rolle(member):
    return any(role.name == INI_ROLE_NAME for role in member.roles) or ist_admin(member)


def ini_embed(tag):
    daten = ini_listen[tag]
    teilnehmer = "\n".join(f"**{i}.** {name}" for i, name in enumerate(daten.values(), 1)) if daten else "*Noch niemand angemeldet.*"

    embed = discord.Embed(
        title=f"📅 Ini {tag}",
        description=f"👥 **Teilnehmer**\n\n{teilnehmer}",
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"Teilnehmer: {len(daten)}")
    return embed


async def log_senden(guild, titel, text, farbe):
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        embed = discord.Embed(title=titel, description=text, color=farbe, timestamp=datetime.now())
        await channel.send(embed=embed)


class AnmeldungModal(discord.ui.Modal):
    def __init__(self, tag):
        super().__init__(title=f"Anmeldung für Ini {tag}")
        self.tag = tag
        self.name = discord.ui.TextInput(label="Fiesta-Charaktername", min_length=2, max_length=30)
        self.add_item(self.name)

    async def on_submit(self, interaction):
        member = interaction.user
        tag = self.tag
        fiesta_name = str(self.name.value).strip()

        if not hat_ini_rolle(member):
            return await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)

        if member.id in ini_listen[tag]:
            return await interaction.response.send_message(f"Du bist für **{tag}** bereits angemeldet.", ephemeral=True)

        if fiesta_name.lower() in [n.lower() for n in ini_listen[tag].values()]:
            return await interaction.response.send_message("Dieser Fiesta-Name steht bereits in der Liste.", ephemeral=True)

        ini_listen[tag][member.id] = fiesta_name
        await update_ini_message(tag)

        await interaction.response.send_message(f"Du wurdest für **{tag}** mit **{fiesta_name}** angemeldet.", ephemeral=True)
        await log_senden(interaction.guild, f"✅ Anmeldung - Ini {tag}", f"**Discord:** {member.mention}\n**Fiesta:** {fiesta_name}", discord.Color.green())


class AendernModal(discord.ui.Modal):
    def __init__(self, tag):
        super().__init__(title=f"Namen ändern - Ini {tag}")
        self.tag = tag
        self.name = discord.ui.TextInput(label="Neuer Fiesta-Charaktername", min_length=2, max_length=30)
        self.add_item(self.name)

    async def on_submit(self, interaction):
        member = interaction.user
        tag = self.tag
        neuer_name = str(self.name.value).strip()

        if member.id not in ini_listen[tag]:
            return await interaction.response.send_message(f"Du bist für **{tag}** nicht angemeldet.", ephemeral=True)

        if neuer_name.lower() in [n.lower() for uid, n in ini_listen[tag].items() if uid != member.id]:
            return await interaction.response.send_message("Dieser Fiesta-Name steht bereits in der Liste.", ephemeral=True)

        alter_name = ini_listen[tag][member.id]
        ini_listen[tag][member.id] = neuer_name
        await update_ini_message(tag)

        await interaction.response.send_message(f"Geändert: **{alter_name}** → **{neuer_name}**", ephemeral=True)
        await log_senden(interaction.guild, f"✏️ Änderung - Ini {tag}", f"**Discord:** {member.mention}\n**Alt:** {alter_name}\n**Neu:** {neuer_name}", discord.Color.orange())


class IniView(discord.ui.View):
    def __init__(self, tag):
        super().__init__(timeout=None)
        self.tag = tag

    @discord.ui.button(label="Anmelden", emoji="✅", style=discord.ButtonStyle.green)
    async def anmelden(self, interaction, button):
        await interaction.response.send_modal(AnmeldungModal(self.tag))

    @discord.ui.button(label="Abmelden", emoji="❌", style=discord.ButtonStyle.red)
    async def abmelden(self, interaction, button):
        member = interaction.user
        tag = self.tag

        if member.id not in ini_listen[tag]:
            return await interaction.response.send_message(f"Du bist für **{tag}** nicht angemeldet.", ephemeral=True)

        alter_name = ini_listen[tag].pop(member.id)
        await update_ini_message(tag)

        await interaction.response.send_message(f"Du wurdest von **{tag}** abgemeldet.", ephemeral=True)
        await log_senden(interaction.guild, f"❌ Abmeldung - Ini {tag}", f"**Discord:** {member.mention}\n**Fiesta:** {alter_name}", discord.Color.red())

    @discord.ui.button(label="Namen ändern", emoji="✏️", style=discord.ButtonStyle.blurple)
    async def aendern(self, interaction, button):
        await interaction.response.send_modal(AendernModal(self.tag))


async def finde_ini_message(channel, tag):
    async for msg in channel.history(limit=50):
        if msg.author == bot.user and msg.embeds and msg.embeds[0].title == f"📅 Ini {tag}":
            return msg
    return None


async def update_ini_message(tag):
    channel = bot.get_channel(INI_CHANNELS[tag])
    if not channel:
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
    async def liste(self, interaction, tag):
        await interaction.response.send_message(embed=ini_embed(tag.value), ephemeral=True)

    @app_commands.command(name="entfernen", description="Admin: Entfernt ein Mitglied")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def entfernen(self, interaction, tag, mitglied: discord.Member):
        if not ist_admin(interaction.user):
            return await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)

        tag_name = tag.value

        if mitglied.id not in ini_listen[tag_name]:
            return await interaction.response.send_message("Dieses Mitglied ist dort nicht angemeldet.", ephemeral=True)

        alter_name = ini_listen[tag_name].pop(mitglied.id)
        await update_ini_message(tag_name)

        await interaction.response.send_message(f"{mitglied.mention} wurde aus **{tag_name}** entfernt.", ephemeral=True)
        await log_senden(interaction.guild, f"🛡️ Admin-Entfernung - Ini {tag_name}", f"**Admin:** {interaction.user.mention}\n**Entfernt:** {mitglied.mention}\n**Fiesta:** {alter_name}", discord.Color.dark_blue())

    @app_commands.command(name="clear", description="Admin: Leert eine Ini-Liste")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def clear(self, interaction, tag):
        if not ist_admin(interaction.user):
            return await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)

        tag_name = tag.value
        anzahl = len(ini_listen[tag_name])
        ini_listen[tag_name].clear()
        await update_ini_message(tag_name)

        await interaction.response.send_message(f"Die Liste für **{tag_name}** wurde geleert.", ephemeral=True)
        await log_senden(interaction.guild, f"🧹 Liste geleert - Ini {tag_name}", f"**Admin:** {interaction.user.mention}\n**Gelöschte Einträge:** {anzahl}", discord.Color.dark_blue())

    @app_commands.command(name="neu_erstellen", description="Admin: Erstellt die Ini-Nachricht neu")
    @app_commands.choices(tag=[app_commands.Choice(name=t, value=t) for t in TAGE])
    async def neu_erstellen(self, interaction, tag):
        if not ist_admin(interaction.user):
            return await interaction.response.send_message("Du hast dafür keine Rechte.", ephemeral=True)

        await update_ini_message(tag.value)
        await interaction.response.send_message(f"Die Ini-Nachricht für **{tag.value}** wurde geprüft/erstellt.", ephemeral=True)


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")

    guild = discord.Object(id=GUILD_ID)

    try:
        bot.tree.add_command(IniCommands(), guild=guild)
    except app_commands.CommandAlreadyRegistered:
        pass

    await bot.tree.sync(guild=guild)

    for tag in TAGE:
        bot.add_view(IniView(tag))
        await update_ini_message(tag)

    print("Bot ist bereit.")


bot.run(TOKEN)
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import os
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Données par serveur
xp_data = defaultdict(lambda: defaultdict(int))  # guild_id -> user_id -> xp
levels_data = defaultdict(
    lambda: defaultdict(int))  # guild_id -> user_id -> level
level_channels = {}  # guild_id -> channel_id pour messages de niveau
monthly_channels = {}  # guild_id -> channel_id pour reset mensuel

LEVEL_XP = 60  # XP nécessaire pour monter d'un niveau
XP_PER_INTERVAL = 1  # XP gagné toutes les 60 sec


@bot.event
async def on_ready():
    await tree.sync()
    print(f"{bot.user} est prêt.")
    if not voice_xp_loop.is_running():
        voice_xp_loop.start()
    if not reset_monthly_leaderboard.is_running():
        reset_monthly_leaderboard.start()


# Boucle qui ajoute de l'XP aux membres en vocal toutes les 60 secondes
@tasks.loop(seconds=60)
async def voice_xp_loop():
    for guild in bot.guilds:
        for member in guild.members:
            if member.voice and member.voice.channel and not member.bot:
                xp_data[guild.id][member.id] += XP_PER_INTERVAL
                old_level = levels_data[guild.id][member.id]
                new_level = xp_data[guild.id][member.id] // LEVEL_XP
                if new_level > old_level:
                    levels_data[guild.id][member.id] = new_level
                    await send_level_up_message(guild, member, new_level)


async def send_level_up_message(guild, member, level):
    channel_id = level_channels.get(guild.id)
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        return

    embed = discord.Embed(
        title="🎉 Niveau atteint !",
        description=
        f"Félicitations {member.mention}, vous êtes désormais **niveau {level}** !",
        color=discord.Color.gold())
    embed.set_thumbnail(url=member.display_avatar.url)
    await channel.send(embed=embed)


# Commandes de configuration (admins uniquement)
@tree.command(name="setuplvl",
              description="Définir le salon pour les messages de niveau.")
@app_commands.checks.has_permissions(administrator=True)
async def setuplvl(interaction: discord.Interaction,
                   channel: discord.TextChannel):
    level_channels[interaction.guild.id] = channel.id
    await interaction.response.send_message(
        f"✅ Salon de niveau défini sur {channel.mention}", ephemeral=True)


@tree.command(name="setupmonth",
              description="Définir le salon pour les messages mensuels.")
@app_commands.checks.has_permissions(administrator=True)
async def setupmonth(interaction: discord.Interaction,
                     channel: discord.TextChannel):
    monthly_channels[interaction.guild.id] = channel.id
    await interaction.response.send_message(
        f"✅ Salon mensuel défini sur {channel.mention}", ephemeral=True)


# Commande pour voir son niveau actuel
@tree.command(name="levelazer", description="Voir votre niveau actuel.")
async def levelazer(interaction: discord.Interaction):
    user_xp = xp_data[interaction.guild.id].get(interaction.user.id, 0)
    user_level = levels_data[interaction.guild.id].get(interaction.user.id, 0)
    embed = discord.Embed(
        title="📊 Votre progression",
        description=
        f"**XP :** {user_xp} / {LEVEL_XP * (user_level + 1)}\n**Niveau :** {user_level}",
        color=discord.Color.blue())
    embed.set_author(name=interaction.user.name,
                     icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


# Fonction pour récupérer le top 3 des membres d'un serveur
def get_top_members(guild_id):
    data = xp_data[guild_id]
    sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
    return sorted_data[:3]


# Commande classement mensuel
@tree.command(name="leadearboarz", description="Voir le top 3 mensuel.")
async def leadearboarz(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    top_members = get_top_members(guild_id)
    embed = discord.Embed(title="🏆 Classement Mensuel",
                          color=discord.Color.purple())
    for i, (member_id, xp) in enumerate(top_members, 1):
        member = interaction.guild.get_member(member_id)
        if member:
            embed.add_field(name=f"{i}. {member.display_name}",
                            value=f"{xp} XP",
                            inline=False)
    await interaction.response.send_message(embed=embed)


# Commande classement global (pour l'instant idem mensuel, tu peux modifier)
@tree.command(name="generalleaderboardz", description="Voir le top 3 global.")
async def generalleaderboardz(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    top_members = get_top_members(guild_id)
    embed = discord.Embed(title="🌐 Classement Global",
                          color=discord.Color.green())
    for i, (member_id, xp) in enumerate(top_members, 1):
        member = interaction.guild.get_member(member_id)
        if member:
            embed.add_field(name=f"{i}. {member.display_name}",
                            value=f"{xp} XP",
                            inline=False)
    await interaction.response.send_message(embed=embed)


# Réinitialisation automatique chaque 1er du mois à 00:00 UTC
@tasks.loop(minutes=1)
async def reset_monthly_leaderboard():
    now = datetime.utcnow()
    if now.day == 1 and now.hour == 0 and now.minute == 0:
        for guild in bot.guilds:
            top_members = get_top_members(guild.id)
            channel_id = monthly_channels.get(guild.id)
            if channel_id:
                channel = bot.get_channel(channel_id)
                if channel:
                    embed = discord.Embed(
                        title="🔄 Réinitialisation Mensuelle",
                        description=
                        "Le classement du mois a été réinitialisé ! Voici les 3 meilleurs du mois précédent :",
                        color=discord.Color.orange())
                    for i, (member_id, xp) in enumerate(top_members, 1):
                        member = guild.get_member(member_id)
                        if member:
                            embed.add_field(name=f"{i}. {member.display_name}",
                                            value=f"{xp} XP",
                                            inline=False)
                    await channel.send(embed=embed)
        for guild_id in xp_data:
            xp_data[guild_id].clear()
            levels_data[guild_id].clear()


# Serveur web pour Replit (pour éviter que le bot se ferme)
app = Flask('')


@app.route('/')
def home():
    return "Le bot est en ligne !"


def run():
    app.run(host='0.0.0.0', port=8080)


Thread(target=run).start()

# Chargement du token depuis .env
load_dotenv()
bot.run(os.getenv("DISCORD_BOT_TOKEN"))

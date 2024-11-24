import discord

from discord import app_commands
from discord.ext import commands
from utils import SDGException, DiscordClient, Achievement


@app_commands.guild_only()
class AchievementCog(commands.GroupCog, group_name='achievement'):
    def __init__(self, client):
        self.client: DiscordClient = client


async def setup(bot):
    await bot.add_cog(AchievementCog(bot))

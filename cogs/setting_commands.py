import discord

from discord import app_commands
from discord.ext import commands
from utils import SDGException, DiscordClient


@app_commands.guild_only()
class SettingCog(commands.GroupCog, group_name='settings'):
    def __init__(self, client):
        self.client: DiscordClient = client


async def setup(bot):
    await bot.add_cog(SettingCog(bot))

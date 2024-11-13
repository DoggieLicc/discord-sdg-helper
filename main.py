import asyncio

import aiohttp
import discord
import os

from dotenv import load_dotenv
from discord.ext.commands import when_mentioned_or


from utils import DiscordClient

cogs = [
    'cogs.context_commands',
    'cogs.faction_commands',
    'cogs.infotag_commands',
    'cogs.random_commands',
    'cogs.subalignment_commands',
    'cogs.trust_commands',
    'cogs.misc_commands',
    'cogs.dev_commands',
    'cogs.error_handler',
    'cogs.events'
]

load_dotenv()

DISCORD_TOKEN = os.getenv('BOT_TOKEN')

DEV_GUILD_ID = os.getenv('DEVELOPMENT_GUILD')
MY_GUILD = discord.Object(id=int(DEV_GUILD_ID)) if DEV_GUILD_ID else None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


client = DiscordClient(
    intents=intents,
    test_guild=MY_GUILD,
    command_prefix=when_mentioned_or('sdg.'),
    help_command=None
)

client.allowed_mentions = discord.AllowedMentions(users=True, replied_user=True, everyone=False, roles=False)


async def main():
    client.cogs_list = cogs
    for cog in cogs:
        await client.load_extension(cog)
        print(f'Loaded cog {cog}')

    async with aiohttp.ClientSession() as session:
        await client.start(DISCORD_TOKEN)


if __name__ == '__main__':
    asyncio.run(main())

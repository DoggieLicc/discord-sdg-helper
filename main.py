import os
import asyncio
import aiohttp
import discord

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
    'cogs.account_commands',
    'cogs.achievement_commands',
    'cogs.setting_commands',
    'cogs.misc_commands',
    'cogs.dev_commands',
    'cogs.error_handler',
    'cogs.events'
]

load_dotenv()

DISCORD_TOKEN = os.getenv('BOT_TOKEN')

DEV_GUILD_ID = os.getenv('DEVELOPMENT_GUILD')
MY_GUILD = discord.Object(id=int(DEV_GUILD_ID)) if DEV_GUILD_ID else None

DO_FIRST_SYNC = os.getenv('DO_FIRST_SYNC') or 'false'
DO_FIRST_SYNC = DO_FIRST_SYNC.lower().strip() == 'true'

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
allowed_mentions = discord.AllowedMentions(users=True, replied_user=True, everyone=False, roles=False)


client = DiscordClient(
    intents=intents,
    test_guild=MY_GUILD,
    do_first_sync=DO_FIRST_SYNC,
    command_prefix=when_mentioned_or('sdg.'),
    allowed_mentions=allowed_mentions,
    help_command=None
)


async def main():
    client.cogs_list = cogs
    for cog in cogs:
        await client.load_extension(cog)
        print(f'Loaded cog {cog}')

    async with aiohttp.ClientSession():
        await client.start(DISCORD_TOKEN)


if __name__ == '__main__':
    asyncio.run(main())

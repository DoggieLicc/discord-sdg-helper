import os
import asyncio
import logging
import inspect

import aiohttp
import discord

from dotenv import load_dotenv
from discord.ext.commands import when_mentioned_or
from discord.ext.prometheus import PrometheusCog, PrometheusLoggingHandler
from loguru import logger

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
GUIDE_CHANNEL_ID = os.getenv('GUIDE_CHANNEL_ID')
PROMETHEUS_PORT = os.getenv('PROMETHEUS_PORT')
PROMETHEUS_PORT = int(PROMETHEUS_PORT) if PROMETHEUS_PORT else 8000
DISABLE_PROMETHEUS = os.getenv('DISABLE_PROMETHEUS') or 'false'
DISABLE_PROMETHEUS = DISABLE_PROMETHEUS.lower().strip() == 'true'
DATABASE_FILENAME = os.getenv('DATABASE_FILENAME') or 'guild_info.db'

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
allowed_mentions = discord.AllowedMentions(users=True, replied_user=True, everyone=False, roles=False)

class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


async def main():
    discord.utils.setup_logging(handler=InterceptHandler())

    client = DiscordClient(
        intents=intents,
        test_guild=MY_GUILD,
        guide_channel_id=GUIDE_CHANNEL_ID,
        database_filename=DATABASE_FILENAME,
        do_first_sync=DO_FIRST_SYNC,
        command_prefix=when_mentioned_or('sdg.'),
        allowed_mentions=allowed_mentions,
        help_command=None
    )

    client.cogs_list = cogs

    if not DISABLE_PROMETHEUS:
        logger.add(PrometheusLoggingHandler())
        await client.add_cog(PrometheusCog(client, port=PROMETHEUS_PORT, ignore_text_commands=True))
        logger.info('Enabled Prometheus on port {} (DISABLE_PROMETHEUS)', PROMETHEUS_PORT)
    else:
        logger.info('Prometheus is disabled! (DISABLE_PROMETHEUS)')

    for cog in cogs:
        await client.load_extension(cog)
        logger.info('Loaded cog {}', cog)

    async with aiohttp.ClientSession():
        try:
            await client.start(DISCORD_TOKEN)
        finally:
            await client.close()


if __name__ == '__main__':
    asyncio.run(main())

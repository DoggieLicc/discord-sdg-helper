import asyncio

import aiohttp
import discord
import os
import traceback

from dotenv import load_dotenv
from discord import app_commands

import utils.classes

from utils import DiscordClient, SDGException

cogs = [
    'cogs.context_commands',
    'cogs.faction_commands',
    'cogs.infotag_commands',
    'cogs.random_commands',
    'cogs.subalignment_commands',
    'cogs.trust_commands',
    'cogs.misc_commands',
    'cogs.dev_commands',
    'cogs.events'
]

load_dotenv()

DISCORD_TOKEN = os.getenv('BOT_TOKEN')

DEV_GUILD_ID = os.getenv('DEVELOPMENT_GUILD')
MY_GUILD = discord.Object(id=int(DEV_GUILD_ID)) if DEV_GUILD_ID else None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = DiscordClient(intents=intents, test_guild=MY_GUILD, command_prefix='sdg.', help_command=None)

client.allowed_mentions = discord.AllowedMentions(users=True, replied_user=True, everyone=False, roles=False)


@client.tree.error
async def error_handler(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error_message = None

    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original

    if isinstance(error, app_commands.TransformerError):
        error_message = f'Invalid option "{error.value}" for {error.type}'

    if isinstance(error, app_commands.CheckFailure):
        error_message = 'You aren\'t allowed to use that command!'

    if isinstance(error, app_commands.MissingPermissions):
        error_message = f'You are missing the following permissions: {error.missing_permissions}'

    if isinstance(error, app_commands.BotMissingPermissions):
        error_message = f'The bot is missing the following permissions: {error.missing_permissions}'

    if isinstance(error, SDGException):
        error_message = str(error)

    if not error_message:
        error_message = f'An unknown error occurred: {error}\n\nError info will be sent to owner'

        etype = type(error)
        trace = error.__traceback__
        lines = traceback.format_exception(etype, error, trace)
        traceback_t: str = ''.join(lines)

        print(traceback_t)
        file = utils.str_to_file(traceback_t, filename='traceback.py')

        owner: discord.User = await client.get_owner()

        if owner:
            owner_embed = utils.create_embed(
                interaction.user,
                title='Unhandled error occurred!',
                color=discord.Color.red()
            )

            owner_embed.add_field(name='Unhandled Error!:', value=f"Error {error}", inline=False)
            owner_embed.add_field(name='Command:', value=str(interaction.data)[:1000], inline=False)

            owner_embed.add_field(
                name='Extra Info:',
                value=f'Guild: {interaction.guild}: {getattr(interaction.guild, "id", "None")}\n'
                      f'Channel: {interaction.channel.mention}:{interaction.channel.id}', inline=False
            )

            await owner.send(embed=owner_embed, files=[file])

    embed = utils.create_embed(
        interaction.user,
        title='Error while running command!',
        description=error_message,
        color=discord.Color.brand_red()
    )

    try:
        await interaction.response.send_message(embed=embed)
    except (discord.InteractionResponded, discord.NotFound):
        try:
            await interaction.channel.send(embed=embed)
        except discord.DiscordException:
            print(f'Unable to respond to exception in {interaction.channel.name} ({interaction.channel.id})')


async def main():
    client.cogs_list = cogs
    for cog in cogs:
        await client.load_extension(cog)

    async with aiohttp.ClientSession() as session:
        await client.start(DISCORD_TOKEN)


if __name__ == '__main__':
    asyncio.run(main())

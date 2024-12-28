import traceback

import discord

from discord import app_commands
from discord.ext import commands
from loguru import logger

import utils


class ErrorCog(commands.Cog):
    def __init__(self, client):
        self.client: utils.DiscordClient = client
        self._old_tree_error = None

    async def cog_load(self):
        tree = self.client.tree
        self._old_tree_error = tree.on_error
        tree.on_error = self.error_handler

    async def cog_unload(self):
        if self._old_tree_error:
            tree = self.client.tree
            tree.on_error = self._old_tree_error

    async def error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        error_message = None
        ephemeral = utils.get_interaction_parameter(interaction, 'ephemeral', False)

        if isinstance(error, app_commands.CommandInvokeError):
            error = error.original

        if isinstance(error, app_commands.TransformerError):
            transformer_class = type(error.transformer)
            transformer_name = transformer_class.__name__.replace('Transformer', '')
            error_message = f'Invalid option "{error.value}" for {transformer_name}!'
            if transformer_class.autocomplete is utils.ChoiceTransformer.autocomplete:
                if error.value == '0':
                    error_message += '\n(Select options in order, as the autocomplete changes based on your options)'
                else:
                    error_message += '\n(You need to select the autocomplete options provided)'

        if isinstance(error, app_commands.CheckFailure):
            command = interaction.command
            error_message = 'You aren\'t allowed to use that command!'

            if command and command.checks:
                if command.checks[0] is utils.mod_check:
                    error_message = 'You need either "Manage Channels" or have Trust (/trust add) to run this command!'
                elif command.checks[0] is utils.admin_check:
                    error_message = 'You need Administrator permissions to run this command!'

        if isinstance(error, app_commands.MissingPermissions):
            error_message = f'You are missing the following permissions: {error.missing_permissions}'

        if isinstance(error, app_commands.BotMissingPermissions):
            error_message = f'The bot is missing the following permissions: {error.missing_permissions}'

        if isinstance(error, utils.SDGException):
            error_message = str(error)

        if not error_message:
            error_message = f'An unknown error occurred: {error}\n\nError info will be sent to owner'

            etype = type(error)
            trace = error.__traceback__
            lines = traceback.format_exception(etype, error, trace)
            traceback_t: str = ''.join(lines)

            logger.error(traceback_t)
            file = utils.str_to_file(traceback_t, filename='traceback.py')

            owner: discord.User = await self.client.get_owner()

            if owner:
                owner_embed = utils.create_embed(
                    interaction.user,
                    title='Unhandled error occurred!',
                    color=discord.Color.red()
                )

                owner_embed.add_field(name='Unhandled Error!:', value=f"Error {str(error)[:1000]}", inline=False)
                owner_embed.add_field(name='Command:', value=str(interaction.data)[:1000], inline=False)

                owner_embed.add_field(
                    name='Extra Info:',
                    value=f'Guild: {interaction.guild}: {getattr(interaction.guild, "id", "None")}\n'
                          f'Channel: {interaction.channel}:{interaction.channel.id}', inline=False
                )

                await owner.send(embed=owner_embed, files=[file])

        embed = utils.create_embed(
            interaction.user,
            title='Error while running command!',
            description=error_message[:4000],
            color=discord.Color.brand_red()
        )

        try:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        except (discord.InteractionResponded, discord.NotFound):
            try:
                await interaction.edit_original_response(embed=embed)
            except (discord.InteractionResponded, discord.NotFound):
                try:
                    await interaction.channel.send(embed=embed)
                except discord.DiscordException:
                    logger.info(
                        'Unable to respond to exception in %s (%s)',
                        interaction.channel.name, interaction.channel.id
                    )


async def setup(bot):
    await bot.add_cog(ErrorCog(bot))

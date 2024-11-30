import discord

from discord import app_commands
from discord.ext import commands

import utils
from utils import SDGException, DiscordClient


@app_commands.guild_only()
class SettingCog(commands.GroupCog, group_name='settings'):
    """Commands to view and modify server settings"""

    def __init__(self, client):
        self.client: DiscordClient = client

    @app_commands.check(utils.admin_check)
    @app_commands.command(name='view')
    async def view_settings(self, interaction: discord.Interaction):
        """View the current server settings"""
        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)
        settings = guild_info.guild_settings

        embed = utils.create_embed(
            interaction.user,
            title='Server Settings:',
            description=f'**Accounts creatable by anyone?:** {settings.accounts_creatable}\n'
                        f'**Maximum # of scrolls:** {settings.max_scrolls}\n\n'
                        f'**Roles are scrollable?:** {settings.roles_are_scrollable}\n'
                        f'**Subalignments are scrollable?:** {settings.subalignments_are_scrollable}\n'
                        f'**Factions are scrollable?:** {settings.factions_are_scrollable}\n\n'
                        f'**Role scroll multiplier:** {settings.role_scroll_multiplier}\n'
                        f'**Subalignment scroll multiplier:** {settings.subalignment_scroll_multiplier}\n'
                        f'**Faction scroll multiplier:** {settings.faction_scroll_multiplier}\n'
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.check(utils.admin_check)
    @app_commands.command(name='edit')
    @app_commands.describe(accounts_creatable='Whether to allow anyone to create accounts for themselves')
    @app_commands.describe(max_scrolls='The maximum amount of scrolls a player can equip per type')
    @app_commands.describe(roles_are_scrollable='Whether to allow roles to be scrollable')
    @app_commands.describe(subalignments_are_scrollable='Whether to allow subalignments to be scrollable')
    @app_commands.describe(factions_are_scrollable='Whether to allow factions to be scrollable')
    @app_commands.describe(role_scroll_multiplier='Multiplier for role scrolls')
    @app_commands.describe(subalignment_scroll_multiplier='Multiplier for subalignment scrolls')
    @app_commands.describe(faction_scroll_multiplier='Multiplier for faction scrolls')
    async def edit_settings(
            self,
            interaction: discord.Interaction,
            accounts_creatable: bool | None = None,
            max_scrolls: app_commands.Range[int, 1, 20] | None = None,
            roles_are_scrollable: bool | None = None,
            subalignments_are_scrollable: bool | None = None,
            factions_are_scrollable: bool | None = None,
            role_scroll_multiplier: app_commands.Range[int, 1] | None = None,
            subalignment_scroll_multiplier: app_commands.Range[int, 1] | None = None,
            faction_scroll_multiplier: app_commands.Range[int, 1] | None = None
    ):
        """Edit the server settings"""
        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)
        settings = guild_info.guild_settings

        new_settings = utils.GuildSettings(
            accounts_creatable=accounts_creatable if accounts_creatable is not None else settings.accounts_creatable,
            max_scrolls=max_scrolls or settings.max_scrolls,
            roles_are_scrollable=roles_are_scrollable if roles_are_scrollable is not None else settings.roles_are_scrollable,
            subalignments_are_scrollable=subalignments_are_scrollable if subalignments_are_scrollable is not None else settings.subalignments_are_scrollable,
            factions_are_scrollable=factions_are_scrollable if factions_are_scrollable is not None else settings.factions_are_scrollable,
            role_scroll_multiplier=role_scroll_multiplier or settings.role_scroll_multiplier,
            subalignment_scroll_multiplier=subalignment_scroll_multiplier or settings.subalignment_scroll_multiplier,
            faction_scroll_multiplier=faction_scroll_multiplier or settings.faction_scroll_multiplier
        )

        guild_info.guild_settings = new_settings
        self.client.replace_guild_info(guild_info)

        await self.client.modify_settings_in_db(new_settings, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Server settings modified!',
            description='The server\'s settings have been modified successfully'
        )

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(SettingCog(bot))

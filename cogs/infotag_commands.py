import discord

from discord import app_commands, Interaction
from discord.ext import commands
from utils import mod_check, InfoCategory, InfoTag

import utils


@app_commands.guild_only()
class InfotagCog(commands.GroupCog, group_name='infotag'):
    """Commands to create, view, and modify infotags"""
    def __init__(self, client):
        self.client: utils.DiscordClient = client

    @app_commands.command(name='add')
    @app_commands.describe(forum_channel='The forum channel to associate with the infotag category')
    @app_commands.describe(name='The name to give the category')
    @app_commands.check(mod_check)
    async def infotag_add(self, interaction: Interaction, forum_channel: discord.ForumChannel, name: str):
        """Adds an infotag category"""

        guild_info = utils.get_guild_info(interaction)
        infotag_category = InfoCategory(name, forum_channel.id)
        guild_info.info_categories.append(infotag_category)

        self.client.replace_guild_info(guild_info)

        embed = utils.create_embed(
            interaction.user,
            title='Infotag Category added',
            description=f'Added {name} to {forum_channel.mention}'
        )

        await self.client.sync_infotags(infotag_category)
        await self.client.add_item_to_db(infotag_category, 'infotags')

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='remove')
    @app_commands.describe(info_category='The infotag category to remove')
    @app_commands.check(mod_check)
    async def infotag_remove(
            self,
            interaction: discord.Interaction,
            info_category: app_commands.Transform[InfoCategory, utils.InfoCategoryTransformer],
    ):
        """Removes an infotag"""
        guild_info = utils.get_guild_info(interaction)
        guild_info.info_categories.remove(info_category)

        for info_tag in guild_info.info_tags.copy():
            if info_tag.info_category == info_category:
                guild_info.info_tags.remove(info_tag)

        self.client.replace_guild_info(guild_info)

        embed = utils.create_embed(
            interaction.user,
            title='Removed subalignment',
            description=f'Removed {info_category.name}'
        )

        await self.client.sync_guild(interaction.guild)
        await self.client.delete_item_from_db(info_category, 'infotags')

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='view')
    @app_commands.describe(info_category='The infotag category to get the tag of')
    @app_commands.describe(info_tag='The infotag to view')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def infotag_view(
            self,
            interaction: discord.Interaction,
            info_category: app_commands.Transform[InfoCategory, utils.InfoCategoryTransformer],
            info_tag: app_commands.Transform[InfoTag, utils.InfoTagTransformer],
            ephemeral: bool = False
    ):
        """View an infotag"""
        guild_info = utils.get_guild_info(interaction)

        embed = await utils.role_or_infotag_to_embed(interaction, info_tag)
        keywords = utils.KeywordView.get_keywords(embed.description, guild_info, info_tag)
        view = discord.utils.MISSING
        if keywords:
            view = utils.KeywordView(interaction.user, guild_info, info_tag, keywords)

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral, view=view)


async def setup(bot):
    await bot.add_cog(InfotagCog(bot))

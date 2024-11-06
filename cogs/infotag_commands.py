import discord

from discord import app_commands, Interaction
from discord.ext import commands
from utils import mod_check, InfoCategory, InfoTag

import utils


@app_commands.guild_only()
class InfotagCog(commands.GroupCog, group_name='infotag'):
    def __init__(self, client):
        self.client = client

    @app_commands.command(name='add')
    @app_commands.describe(forum_channel='The forum channel to associate with the infotag category')
    @app_commands.describe(name='The name to give the category')
    @app_commands.check(mod_check)
    async def infotag_add(self, interaction: Interaction, forum_channel: discord.ForumChannel, name: str):
        """Adds an infotag category"""

        guild_info = utils.get_guild_info(interaction)
        infotag_category = InfoCategory(name, forum_channel.id)
        guild_info.info_categories.append(infotag_category)

        try:
            self.client.guild_info.remove([gi for gi in self.client.guild_info if gi.guild_id == interaction.guild_id][0])
        except ValueError:
            pass

        self.client.guild_info.append(guild_info)

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

        try:
            self.client.guild_info.remove([gi for gi in self.client.guild_info if gi.guild_id == interaction.guild_id][0])
        except ValueError:
            pass

        self.client.guild_info.append(guild_info)

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
    async def infotag_view(
            self,
            interaction: discord.Interaction,
            info_category: app_commands.Transform[InfoCategory, utils.InfoCategoryTransformer],
            info_tag: app_commands.Transform[InfoTag, utils.InfoTagTransformer]
    ):
        """View an infotag"""
        info_cat_channel = interaction.guild.get_channel_or_thread(info_category.id)
        info_tag_thread = info_cat_channel.get_thread(info_tag.id)

        if not info_tag_thread:
            await self.client.add_archived_threads(info_cat_channel, force=True)
            info_tag_thread = info_cat_channel.get_thread(info_tag.id)

        info_tag_msg = info_tag_thread.starter_message or await info_tag_thread.fetch_message(info_tag_thread.id)
        message_image = info_tag_msg.attachments[0] if info_tag_msg.attachments else None

        embed = utils.create_embed(
            interaction.user,
            title=f'Infotag {info_category.name}:{info_tag.name}',
            thumbnail=message_image,
            description=f'{info_tag_thread.mention}\n\n' + info_tag_msg.content
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(InfotagCog(bot))

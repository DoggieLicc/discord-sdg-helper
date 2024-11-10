import discord

from discord import app_commands, Interaction
from discord.ext import commands
from utils import mod_check, Faction, Subalignment

import utils


@app_commands.guild_only()
class SubalaignmentCog(commands.GroupCog, group_name='subalignment'):
    def __init__(self, client):
        self.client = client

    @app_commands.command(name='add')
    @app_commands.describe(faction='The faction to add the subalignment to')
    @app_commands.describe(
        forum_tag='The forum tag to associate with the subalignment, you need to select faction before this one')
    @app_commands.check(mod_check)
    async def subalignment_add(
            self,
            interaction: Interaction,
            faction: app_commands.Transform[Faction, utils.FactionTransformer],
            forum_tag: app_commands.Transform[discord.ForumTag, utils.ForumTagTransformer]
    ):
        """Add a subalignment to a faction"""
        guild_info = utils.get_guild_info(interaction)
        subalignment = Subalignment(forum_tag.name, forum_tag.id)
        guild_info.subalignments.append(subalignment)

        self.client.replace_guild_info(guild_info)

        embed = utils.create_embed(
            interaction.user,
            title='Subalignment added',
            description=f'Added {forum_tag.emoji} {forum_tag} to <#{faction.id}>'
        )

        await self.client.sync_faction(faction)
        await self.client.add_item_to_db(subalignment, 'subalignments')

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='view')
    @app_commands.describe(subalignment='The subalignment to view')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def subalignment_view(
            self,
            interaction: discord.Interaction,
            subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer],
            ephemeral: bool = False
    ):
        """Get info for a subalignment"""
        roles = self.client.get_subalignment_roles(subalignment)
        faction = self.client.get_subalignment_faction(subalignment)
        faction_channel = self.client.get_channel(faction.id)

        for tag in faction_channel.available_tags:
            if tag.id == subalignment.id:
                forum_tag = tag

        embed = utils.create_embed(
            interaction.user,
            title='Subalignment info',
            description=f'**Name:** {forum_tag.emoji} {subalignment.name.title()}\n'
                        f'**Main faction:** <#{faction.id}>\n'
                        f'**Amount of roles:** {len(roles)}'
        )

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name='remove')
    @app_commands.check(mod_check)
    @app_commands.describe(subalignment='The subalignment to remove')
    async def subalignment_remove(
            self,
            interaction: discord.Interaction,
            subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer]
    ):
        """Removes a subalignment from the bot"""
        faction = self.client.get_subalignment_faction(subalignment)

        guild_info = utils.get_guild_info(interaction)

        for role in self.client.get_subalignment_roles(subalignment):
            guild_info.roles.remove(role)

        guild_info.subalignments.remove(subalignment)

        self.client.replace_guild_info(guild_info)

        embed = utils.create_embed(
            interaction.user,
            title='Removed subalignment',
            description=f'Removed {subalignment.name} from <#{faction.id}>'
        )

        await self.client.sync_faction(faction)
        await self.client.delete_item_from_db(subalignment, 'subalignments')

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='list')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to True')
    async def subalignment_list(
            self,
            interaction: discord.Interaction,
            faction: app_commands.Transform[Faction, utils.FactionTransformer],
            ephemeral: bool = True
    ):
        """Lists all of a faction's subalignments"""
        subalignments = self.client.get_faction_subalignments(faction)
        faction_channel = self.client.get_channel(faction.id)

        if not subalignments:
            raise utils.SDGException('No subalignments defined yet! Use /subalignment add...')

        embed = utils.create_embed(
            user=interaction.user,
            title=f'Listing {len(subalignments)} subalignments in {faction.name}'
        )

        for subalignment in subalignments:
            roles = self.client.get_subalignment_roles(subalignment)

            for tag in faction_channel.available_tags:
                if tag.id == subalignment.id:
                    forum_tag = tag

            embed.add_field(
                inline=False,
                name=str(forum_tag.emoji) + ' ' + subalignment.name,
                value=f'**Number of roles:** {len(roles)}'
            )

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)


async def setup(bot):
    await bot.add_cog(SubalaignmentCog(bot))

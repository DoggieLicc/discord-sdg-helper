import discord

from discord import app_commands, Interaction
from discord.ext import commands
from utils import mod_check, Faction, GuildInfo

import utils


@app_commands.guild_only()
class FactionCog(commands.GroupCog, group_name='faction'):
    def __init__(self, client):
        self.client = client

    @app_commands.command(name='add')
    @app_commands.describe(forum_channel='The forum channel to assign the faction to')
    @app_commands.describe(name='The name to give the faction')
    @app_commands.check(mod_check)
    async def faction_add(self, interaction: Interaction, forum_channel: discord.ForumChannel, name: str):
        """Adds a faction to your server"""

        name = name.title()

        faction_info = utils.classes.Faction(id=forum_channel.id, name=name)
        guild_info = utils.get_guild_info(interaction)

        duplicates = [d for d in guild_info.factions if d.id == forum_channel.id or d.name == name]

        if duplicates:
            raise app_commands.AppCommandError('Duplicate faction')

        guild_info.factions.append(faction_info)

        try:
            self.client.guild_info.remove([gi for gi in self.client.guild_info if gi.guild_id == interaction.guild_id][0])
        except ValueError:
            pass

        self.client.guild_info.append(guild_info)

        embed = utils.create_embed(
            interaction.user,
            title='Faction added',
            description=f'Added {name} from {forum_channel.mention}'
        )

        await self.client.add_item_to_db(faction_info, 'factions')

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='view')
    @app_commands.describe(faction='The faction to view')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def faction_view(
            self,
            interaction: discord.Interaction,
            faction: app_commands.Transform[Faction, utils.FactionTransformer],
            ephemeral: bool = False
    ):
        """Get faction info"""
        roles = self.client.get_faction_roles(faction)
        subalignments = self.client.get_faction_subalignments(faction)

        embed = utils.create_embed(
            interaction.user,
            title='Faction info',
            description=f'{faction.name}: <#{faction.id}>\n\n'
                        f'**Amount of roles:** {len(roles)}\n'
                        f'**Amount of subalignments:** {len(subalignments)}'

        )

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name='remove')
    @app_commands.describe(faction='The faction to remove from the bot database')
    @app_commands.check(mod_check)
    async def faction_remove(
            self,
            interaction: discord.Interaction,
            faction: app_commands.Transform[Faction, utils.FactionTransformer]
    ):
        """Removes a faction"""
        guild_info: GuildInfo = utils.get_guild_info(interaction)
        faction_roles = self.client.get_faction_roles(faction)
        client = interaction.client

        guild_info.factions.remove(faction)

        for role in faction_roles:
            guild_info.roles.remove(role)

        try:
            client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == interaction.guild_id][0])
        except ValueError:
            pass

        client.guild_info.append(guild_info)

        embed = utils.create_embed(
            user=interaction.user,
            title='Faction Removed',
            description=f'Removed <#{faction.id}>'
        )

        await client.delete_item_from_db(faction, 'factions')

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='sync')
    @app_commands.describe(faction='The faction to sync')
    @app_commands.check(mod_check)
    async def faction_sync(
            self,
            interaction: discord.Interaction,
            faction: app_commands.Transform[Faction, utils.FactionTransformer]
    ):
        """Sync faction's roles and subalignments manually"""
        roles, failed_roles = await self.client.sync_faction(faction)

        failed_str = '\n'.join(r.mention for r in failed_roles)
        if failed_str:
            failed_str = f'\n\nThreads unable to be synced due to lack of subalignment tag:\n' + failed_str

        embed = utils.create_embed(
            interaction.user,
            title='Faction Synced',
            description=f'Faction {faction.name} synced {len(roles)} roles' + failed_str
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(FactionCog(bot))

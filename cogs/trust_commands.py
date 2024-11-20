import discord

from discord import app_commands
from discord.ext import commands

import utils


@app_commands.guild_only()
@app_commands.default_permissions()
class TrustCog(commands.GroupCog, group_name='trust'):
    def __init__(self, client):
        self.client: utils.DiscordClient = client

    @app_commands.command(name='add')
    @app_commands.describe(trustee='The member or role you want to give trust to')
    async def trust_add(self, interaction: discord.Interaction, trustee: discord.Member | discord.Role):
        """Allow a role/member access to special commands"""
        guild_info = utils.get_guild_info(interaction)

        if trustee.id in guild_info.trusted_ids:
            embed = utils.create_embed(
                interaction.user,
                title='Role/member already trusted!',
                description='The provided role/member is already trusted',
                color=discord.Color.red()
            )

            return await interaction.response.send_message(embed=embed)

        guild_info.trusted_ids.append(trustee.id)

        self.client.replace_guild_info(guild_info)

        await self.client.add_trusted_id_in_db(trustee.id, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Added trustee!',
            description=f'Added trust to {trustee.mention}'
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='remove')
    @app_commands.describe(trustee='The trusted member or role you want remove')
    async def trust_remove(self, interaction: discord.Interaction, trustee: discord.Member | discord.Role):
        """Removes trust from role or member"""
        guild_info = utils.get_guild_info(interaction)

        try:
            guild_info.trusted_ids.remove(trustee.id)
        except ValueError:
            embed = utils.create_embed(
                interaction.user,
                title='Role/member not in list!',
                description='The provided role/member isn\'t in the trustee list',
                color=discord.Color.red()
            )

            return await interaction.response.send_message(embed=embed)

        self.client.replace_guild_info(guild_info)

        await self.client.delete_trusted_id_in_db(trustee.id)

        embed = utils.create_embed(
            interaction.user,
            title='Deleted trustee!',
            description=f'Deleted trust from {trustee.mention}'
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='list')
    async def trust_view(self, interaction: discord.Interaction):
        """List all members/roles that are trusted"""
        guild_info = utils.get_guild_info(interaction)

        trusted_strs = []

        for trusted in guild_info.trusted_ids:
            role = interaction.guild.get_role(trusted)
            if role:
                trusted_strs.append(role.mention)
                continue

            trusted_strs.append(f'<@{trusted}>')

        trusted_str = '\n'.join(trusted_strs) or 'No roles or members are trusted yet! (/trust add)'

        embed = utils.create_embed(
            interaction.user,
            title='List of trusted members/roles:',
            description=trusted_str
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(TrustCog(bot))

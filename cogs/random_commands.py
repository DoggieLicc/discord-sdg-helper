import copy
import random

import discord

from discord import app_commands, Interaction
from discord.ext import commands
from utils import Faction, Subalignment

import utils


@app_commands.guild_only()
class RandomCog(commands.GroupCog, group_name='random'):
    def __init__(self, client):
        self.client = client

    @app_commands.command(name='roles')
    @app_commands.describe(faction='Only get roles from this faction')
    @app_commands.describe(amount='Amount of roles to generate, defaults to 1')
    @app_commands.describe(subalignment='Only get roles from this subalignment')
    @app_commands.describe(individuality='Whether to generate unique roles, defaults to false')
    @app_commands.describe(
        include_tags='Only include roles containing atleast one of the provided comma-seperated list of forum tags')
    @app_commands.describe(
        exclude_tags='Exclude roles that contain atleast one of the provided comma-seperated list of forum tags')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def random_roles(
            self,
            interaction: Interaction,
            amount: app_commands.Range[int, 1, 100] = 1,
            faction: app_commands.Transform[Faction, utils.FactionTransformer] | None = None,
            subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer] | None = None,
            individuality: bool = False,
            include_tags: str | None = '',
            exclude_tags: str | None = '',
            ephemeral: bool = False
    ):
        """Get random roles!"""
        guild_info = utils.get_guild_info(interaction)
        split_include_tags = include_tags.split(',')
        split_exclude_tags = exclude_tags.split(',')

        valid_roles = []
        for role in guild_info.roles:
            if faction and role.faction.id != faction.id:
                continue

            if subalignment and role.subalignment.id != subalignment.id:
                continue

            role_thread = interaction.guild.get_channel_or_thread(role.id)
            role_thread_tags = [t.name.lower().strip() for t in role_thread.applied_tags]
            has_included_tag = not bool(include_tags)
            has_excluded_tag = False

            for exclude_tag in split_exclude_tags:
                normalized_e_tag = exclude_tag.lower().strip()
                if normalized_e_tag in role_thread_tags:
                    has_excluded_tag = True

            for include_tag in split_include_tags:
                normalized_i_tag = include_tag.lower().strip()
                if normalized_i_tag in role_thread_tags:
                    has_included_tag = True

            if has_excluded_tag or not has_included_tag:
                continue

            valid_roles.append(role)

        len_valid_roles = len(valid_roles)
        chosen_roles = []
        for _ in range(amount):
            if len(valid_roles) <= 0:
                raise app_commands.AppCommandError('Not enough valid roles')

            chosen_role = random.choice(valid_roles)
            chosen_roles.append(chosen_role)
            if individuality:
                valid_roles.remove(chosen_role)

        chosen_roles_str = '\n'.join([f'{r.name} (<#{r.id}>)' for r in chosen_roles])

        embed = utils.create_embed(
            interaction.user,
            title=f'Generated {len(chosen_roles)} roles out of {len_valid_roles} possible roles!',
            description=chosen_roles_str
        )

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name='faction')
    @app_commands.describe(amount='Amount of factions to generate, defaults to 1')
    @app_commands.describe(individuality='Whether to generate unique factions, defaults to false')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def random_faction(
            self,
            interaction: Interaction,
            amount: app_commands.Range[int, 1, 100] = 1,
            individuality: bool = False,
            ephemeral: bool = False
    ):
        """Generate random factions"""
        guild_info = utils.get_guild_info(interaction)

        valid_factions = copy.deepcopy(guild_info.factions)
        len_valid_factions = len(valid_factions)
        chosen_factions = []
        for _ in range(amount):
            if len(valid_factions) <= 0:
                raise app_commands.AppCommandError('Not enough valid factions')

            chosen_faction = random.choice(valid_factions)
            chosen_factions.append(chosen_faction)
            if individuality:
                valid_factions.remove(chosen_faction)

        chosen_factions_str = '\n'.join([f'<#{r.id}>' for r in chosen_factions])

        embed = utils.create_embed(
            interaction.user,
            title=f'Generated {len(chosen_factions)} factions out of {len_valid_factions} possible factions!',
            description=chosen_factions_str
        )

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name='members')
    @app_commands.describe(amount='Amount of members to generate, defaults to 1')
    @app_commands.describe(individuality='Whether to generate unique members, defaults to true')
    @app_commands.describe(role='Only get members from this role')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def random_members(
            self,
            interaction: Interaction,
            amount: app_commands.Range[int, 1, 100] = 1,
            individuality: bool = True,
            role: discord.Role | None = None,
            ephemeral: bool = False
    ):
        """Get random server members!"""
        valid_members = role.members if role else list(interaction.guild.members)
        len_valid_members = len(valid_members)
        chosen_members = []
        for _ in range(amount):
            if len(valid_members) <= 0:
                raise app_commands.AppCommandError('Not enough valid members')

            chosen_member = random.choice(valid_members)
            chosen_members.append(chosen_member)
            if individuality:
                valid_members.remove(chosen_member)

        chosen_members_str = '\n'.join([m.mention for m in chosen_members])

        embed = utils.create_embed(
            interaction.user,
            title=f'Generated {len(chosen_members)} members out of {len_valid_members} possible members!',
            description=chosen_members_str
        )

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)


async def setup(bot):
    await bot.add_cog(RandomCog(bot))

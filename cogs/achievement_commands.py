import discord

from discord import app_commands
from discord.ext import commands
from utils import SDGException, DiscordClient, Achievement, Role, Subalignment, Faction, AchievementTransformer
import utils


class AchievementMenu(utils.PaginatedMenu):
    def format_line(self, item: Achievement) -> str:
        associated_type = item.role or item.subalignment or item.faction
        associated_type_str = associated_type.name if associated_type else 'General'
        return f'**{item.name} - {associated_type_str}**\n```{item.description}```'

    async def get_page_contents(self) -> dict:
        page = self.paginator.pages[self.current_page - 1]
        embed = utils.create_embed(
            self.owner,
            title=f'Listing {len(self.items)} achievements ({self.current_page}/{self.max_page})',
            description=page
        )
        return {'embed': embed}


@app_commands.guild_only()
class AchievementCog(commands.GroupCog, group_name='achievement'):
    """Commands to create, view, modify, award, and unaward achievements"""

    def __init__(self, client):
        self.client: DiscordClient = client

    @app_commands.command(name='create')
    @app_commands.check(utils.mod_check)
    @app_commands.describe(name='The name to give the achievement')
    @app_commands.describe(description='The description to give the achievement')
    @app_commands.describe(role='The role to associate with this achievement')
    @app_commands.describe(subalignment='The subalignment to associate with this achievement')
    @app_commands.describe(faction='The faction to associate with this achievement')
    async def achievement_create(
            self,
            interaction: discord.Interaction,
            name: str,
            description: str,
            role: app_commands.Transform[Role, utils.RoleTransformer] = None,
            subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer] = None,
            faction: app_commands.Transform[Faction, utils.FactionTransformer] = None
    ):
        """Creates an achievement"""

        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)
        name = name.strip()
        description = description.strip()

        if sum(1 for a in [role, subalignment, faction] if a is not None) > 1:
            raise SDGException('Can\'t associate an achievement with more than one of role, subalignment, or faction!')

        if len(name) > 100:
            raise SDGException('Achievement name can\'t be longer than 100 characters!')

        if len(description) > 1000:
            raise SDGException('Achievement description can\'t be longer than 2000 characters')

        if not name or not description:
            raise SDGException('Name or description is empty.')

        dupe_achievement = [a for a in guild_info.achievements if a.name.lower().strip() == name.lower()]

        if dupe_achievement:
            raise SDGException(f'There already exists an achievement with the name "{dupe_achievement[0].name}"')

        achievement = Achievement(
            id=interaction.id,
            name=name,
            description=description,
            role=role,
            subalignment=subalignment,
            faction=faction
        )

        guild_info.achievements.append(achievement)
        self.client.replace_guild_info(guild_info)
        await self.client.add_achievement_to_db(achievement, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Achievement created!',
            description=f'Created achievement "{name}" successfully!'
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='delete')
    @app_commands.describe(achievement='The achievement to delete')
    @app_commands.check(utils.mod_check)
    async def achievement_delete(
            self,
            interaction: discord.Interaction,
            achievement: app_commands.Transform[Achievement, AchievementTransformer]
    ):
        """Delete an achievement"""

        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)

        for account in guild_info.accounts:
            if achievement in account.accomplished_achievements:
                account.accomplished_achievements.remove(achievement)
                await self.client.modify_account_in_db(account, interaction.guild_id)

        guild_info.achievements.remove(achievement)
        self.client.replace_guild_info(guild_info)

        await self.client.delete_achievement_from_db(achievement, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Achievement deleted',
            description=f'The achievement "{achievement.name}" has been deleted.'
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='view')
    @app_commands.describe(achievement='The achievement to view')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def achievement_view(
            self,
            interaction: discord.Interaction,
            achievement: app_commands.Transform[Achievement, AchievementTransformer],
            ephemeral: bool = False
    ):
        """View information on an achievement!"""

        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)
        amount_achieved = sum(1 for a in guild_info.accounts if achievement in a.accomplished_achievements)

        embed = utils.create_embed(
            interaction.user,
            title=achievement.name,
            description=achievement.description
        )

        associated_type = achievement.role or achievement.subalignment or achievement.faction
        associated_type_str = 'General'
        if associated_type:
            associated_type_str = associated_type.name

        embed.add_field(name='Achievement Type: ', value=associated_type_str)
        embed.add_field(name='Times achieved:', value=str(amount_achieved), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name='list')
    @app_commands.describe(member='List achievements this member has. By default will list all achievements')
    @app_commands.describe(role='List achievements associated with this role')
    @app_commands.describe(subalignment='List achievements associated with this subalignment')
    @app_commands.describe(faction='List achievements associated with this faction')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def list_achievements(
            self,
            interaction: discord.Interaction,
            member: discord.Member = None,
            role: app_commands.Transform[Role, utils.RoleTransformer] | None = None,
            subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer] | None = None,
            faction: app_commands.Transform[Faction, utils.FactionTransformer] | None = None,
            ephemeral: bool = False
    ):
        """Lists all achievements that fit the filters"""

        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)
        account = None

        if sum(1 for a in [role, subalignment, faction] if a is not None) > 1:
            raise SDGException('Can\'t associate an achievement with more than one of role, subalignment, or faction!')

        if member:
            account = guild_info.get_account(member.id)

            if not account:
                raise SDGException(f'The member {member.mention} does not have an account!')

        associated_type = role or subalignment or faction

        achievements_list = account.accomplished_achievements if member else guild_info.achievements
        valid_achievements = []

        for achievement in achievements_list:
            ach_type = role or subalignment or faction
            if associated_type == ach_type:
                valid_achievements.append(achievement)

        if not valid_achievements:
            raise SDGException('No valid achievements fit the filters.')

        valid_achievements.sort(key=lambda a: a.name)

        view = AchievementMenu(
            owner=interaction.user,
            items=valid_achievements
        )

        contents = await view.get_page_contents()

        if view.max_page == 1:
            view = discord.utils.MISSING

        await interaction.response.send_message(view=view, ephemeral=ephemeral, **contents)

    @app_commands.command(name='award')
    @app_commands.describe(achievement='The achievement to award')
    @app_commands.describe(member='The member to award the achievement to')
    @app_commands.check(utils.mod_check)
    async def award_achievement(
            self,
            interaction: discord.Interaction,
            achievement: app_commands.Transform[Achievement, AchievementTransformer],
            member: discord.Member
    ):
        """Award an achievement to a member, they must have an account to be able to earn achievements"""
        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)

        account = guild_info.get_account(member.id)

        if not account:
            raise SDGException('That member does not have an account!')

        if achievement in account.accomplished_achievements:
            raise SDGException('That member already has this achievement!')

        account.accomplished_achievements.append(achievement)
        self.client.replace_guild_info(guild_info)
        await self.client.modify_account_in_db(account, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Achievement awarded!',
            description=f'Awarded achievement "{achievement.name}" to {member.mention}!'
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='unaward')
    @app_commands.describe(achievement='The achievement to unaward')
    @app_commands.describe(member='The member to remove the achievement from')
    @app_commands.check(utils.mod_check)
    async def unaward_achievement(
            self,
            interaction: discord.Interaction,
            achievement: app_commands.Transform[Achievement, AchievementTransformer],
            member: discord.Member
    ):
        """Removes an achievement from a member"""
        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)

        account = guild_info.get_account(member.id)

        if not account:
            raise SDGException('That member does not have an account!')

        if achievement not in account.accomplished_achievements:
            raise SDGException('That member doesn\'t have that achievement!')

        account.accomplished_achievements.remove(achievement)
        self.client.replace_guild_info(guild_info)
        await self.client.modify_account_in_db(account, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Achievement removed!',
            description=f'Removed achievement "{achievement.name}" from {member.mention}!'
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.check(utils.mod_check)
    @app_commands.command(name='modify')
    @app_commands.describe(achievement='The achievement to modify')
    @app_commands.describe(new_name='The new name to give the achievement')
    @app_commands.describe(new_description='The new description to give the achievement')
    @app_commands.describe(new_role='The role to associate with this achievement')
    @app_commands.describe(new_subalignment='The subalignment to associate with this achievement')
    @app_commands.describe(new_faction='The faction to associate with this achievement')
    async def achievement_modify(
            self,
            interaction: discord.Interaction,
            achievement: app_commands.Transform[Achievement, AchievementTransformer],
            new_name: str | None = None,
            new_description: str | None = None,
            new_role: app_commands.Transform[Role, utils.RoleTransformer] = None,
            new_subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer] = None,
            new_faction: app_commands.Transform[Faction, utils.FactionTransformer] = None
    ):
        """Edit an existing achievement"""

        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)
        name = new_name.strip() if new_name else achievement.name
        description = new_description.strip() if new_description else achievement.description
        role = new_role or (achievement.role if not any([new_subalignment, new_faction]) else None)
        subalignment = new_subalignment or (achievement.subalignment if not any([new_role, new_faction]) else None)
        faction = new_faction or (achievement.faction if not any([new_subalignment, new_role]) else None)

        if sum(1 for a in [new_role, new_subalignment, new_faction] if a is not None) > 1:
            raise SDGException('Can\'t associate an achievement with more than one of role, subalignment, or faction!')

        if len(name) > 100:
            raise SDGException('Achievement name can\'t be longer than 100 characters!')

        if len(description) > 1000:
            raise SDGException('Achievement description can\'t be longer than 2000 characters')

        if not name or not description:
            raise SDGException('Name or description is empty.')

        dupe_achievement = [
            a for a in guild_info.achievements if a.name.lower().strip() == name.lower() and a.id != achievement.id
        ]

        if dupe_achievement:
            raise SDGException(f'There already exists an achievement with the name "{dupe_achievement[0].name}"')

        new_achievement = Achievement(
            id=achievement.id,
            name=name,
            description=description,
            role=role,
            subalignment=subalignment,
            faction=faction
        )

        guild_info.achievements.remove(achievement)
        guild_info.achievements.append(new_achievement)
        self.client.replace_guild_info(guild_info)
        await self.client.modify_achievement_in_db(new_achievement, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Achievement modified!',
            description=f'Modified achievement "{name}" successfully!'
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AchievementCog(bot))

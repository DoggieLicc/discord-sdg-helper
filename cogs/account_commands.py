import discord

from discord import app_commands, Interaction
from discord.ext import commands

import utils
from utils import SDGException, DiscordClient, Account, Role, Subalignment, Faction, RSFTransformer, ScrollTransformer

import typing


class DeleteConfirm(discord.ui.View):
    def __init__(self, owner: discord.User):
        super().__init__()
        self.value = None
        self.owner = owner
        self.message = None

    @discord.ui.button(label='Delete Account', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = utils.create_embed(
            interaction.user,
            title='Account Deleted',
            description='The account has been deleted.'
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        self.value = True
        await self.on_timeout()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.green)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = utils.create_embed(
            interaction.user,
            title='Deletion cancelled',
            description='The account has not been deleted.'
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        self.value = False
        await self.on_timeout()

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        await interaction.response.defer()
        self.message = interaction.message

        if interaction.user != self.owner:
            await interaction.followup.send('You didn\'t use this command!', ephemeral=True)
            return False

        return True

    async def on_timeout(self) -> None:
        children = self.children
        for child in children:
            child.disabled = True
        self._children = children

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

        self.stop()


@app_commands.guild_only()
class AccountCog(commands.GroupCog, group_name='account'):
    scroll_group = app_commands.Group(name='scroll', description='Scroll commands')

    def __init__(self, client):
        self.client: DiscordClient = client

    @app_commands.command(name='create')
    @app_commands.describe(member='The member to create the account for, if not specified, it creates one for you')
    async def create_account(self, interaction: Interaction, member: discord.Member | None = None):
        """Create an account for either yourself or another member"""

        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)

        if member and not await utils.mod_check(interaction):
            raise SDGException('You aren\'t allowed to create accounts for other members.')

        member = member or interaction.user

        if member.bot:
            raise SDGException('Can\'t create account for a bot!')

        if guild_info.get_account(member.id):
            raise SDGException(f'Member {member.mention} already has an account!')

        if member == interaction.user and not await utils.mod_check(interaction) and not guild_info.guild_settings.accounts_creatable:
            raise SDGException('Accounts are not currently creatable by normal users.')

        account = Account(
            id=member.id,
            num_wins=0,
            num_loses=0,
            num_draws=0,
            blessed_scrolls=[],
            cursed_scrolls=[],
            accomplished_achievements=[]
        )

        guild_info.accounts.append(account)

        await self.client.add_account_to_db(account, interaction.guild_id)
        self.client.replace_guild_info(guild_info)

        embed = utils.create_embed(
            interaction.user,
            title='Account created!',
            description=f'An account has been created for {member.mention}'
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='view')
    @app_commands.describe(member='The member to view the account of. By default this will be your account')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Scroll information is shown if True. Defaults to False')
    async def view_account(
            self,
            interaction: Interaction,
            member: discord.User | None = None,
            ephemeral: bool = False
    ):
        """View account info"""

        member = member or interaction.user
        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)

        account = guild_info.get_account(member.id)

        if not account:
            raise SDGException(f'Member {member.mention} does not have an account.')

        total_games = account.num_wins + account.num_draws + account.num_loses

        if account.num_loses == 0:
            wl_ratio = float(account.num_wins)
        else:
            wl_ratio = account.num_wins / account.num_loses

        if ephemeral and (interaction.user == member or await utils.mod_check(interaction)):
            blessed_scrolls_str = ', '.join(s.name for s in account.blessed_scrolls) or 'No scrolls'
            cursed_scrolls_str = ', '.join(s.name for s in account.cursed_scrolls) or 'No scrolls'
        elif ephemeral:
            blessed_scrolls_str = 'No access'
            cursed_scrolls_str = 'No access'
        else:
            blessed_scrolls_str = 'Hidden - Use ephemeral option to view'
            cursed_scrolls_str = 'Hidden - Use ephemeral option to view'

        embed = utils.create_embed(
            interaction.user,
            title=f'Account info for {member}',
            description=f'**Games played:** {total_games}\n\n'
                        f'**Wins:** {account.num_wins}\n'
                        f'**Losses:** {account.num_loses}\n'
                        f'**Draws:** {account.num_draws}\n'
                        f'**W/L:** {wl_ratio}\n\n'
                        f'**Accomplished Achievements:** {len(account.accomplished_achievements)}\n'
                        f'**Blessed Scrolls:** {blessed_scrolls_str}\n'
                        f'**Cursed Scrolls:** {cursed_scrolls_str}'
        )

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name='delete')
    @app_commands.describe(member='The member to delete the account of')
    @app_commands.check(utils.admin_check)
    async def delete_account(self, interaction: Interaction, member: discord.User):
        """Delete an user's account. This action is not reversible!"""
        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)
        account = guild_info.get_account(member.id)

        if not account:
            raise SDGException(f'The member {member.mention} does not have an account.')

        total_games = account.num_wins + account.num_draws + account.num_loses
        num_achives = len(account.accomplished_achievements)

        confirm_embed = utils.create_embed(
            interaction.user,
            color=discord.Color.red(),
            title='Are you SURE you want to delete this account?',
            description=f'THIS WILL DELETE <@{account.id}>\'s ACCOUNT PERMANENTLY\n\n'
                        f'This account has **{total_games}** games played and **{num_achives}** achievements!\n'
                        f'Account deletion is completely irreversible, proceed with caution!'
        )

        view = DeleteConfirm(interaction.user)
        await interaction.response.send_message(embed=confirm_embed, view=view)
        await view.wait()

        if view.value is None:
            await interaction.channel.send('Timed out while waiting for confirmation')
        elif view.value:
            guild_info.accounts.remove(account)
            await self.client.delete_account_from_db(account, interaction.guild_id)
            self.client.replace_guild_info(guild_info)
        else:
            pass

    @scroll_group.command(name='view')
    @app_commands.describe(member='The member to view scrolls of. You need to be trusted to view other\'s scrolls')
    async def scroll_view(self, interaction: Interaction, member: discord.User | None = None):
        """View your own or someone else's equipped scrolls"""
        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)

        if interaction.user != member and not await utils.mod_check(interaction):
            raise SDGException('You don\'t have permission to view other account\'s scrolls.')

        member = member or interaction.user
        account = guild_info.get_account(member.id)

        if not account:
            raise SDGException(f'The member {member.mention} does not have an account!')

        embed = utils.create_embed(
            interaction.user,
            title=f'Listing {member}\'s scrolls'
        )

        embed.add_field(
            name='Blessed Scrolls',
            value='\n'.join(s.name for s in account.blessed_scrolls) or 'No scrolls',
            inline=False
        )

        embed.add_field(
            name='Cursed Scrolls',
            value='\n'.join(s.name for s in account.cursed_scrolls) or 'No scrolls',
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @scroll_group.command(name='add')
    @app_commands.describe(role_subalignment_faction='The role, subalignment, or faction to scroll for')
    @app_commands.describe(scroll_type='Scroll type, Blessed increases chance, Cursed decreases chance,')
    async def scroll_add(
            self,
            interaction: Interaction,
            role_subalignment_faction: app_commands.Transform[Role | Subalignment | Faction, RSFTransformer],
            scroll_type: typing.Literal['Blessed', 'Cursed']
    ):
        """Add a scroll to your account"""
        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)
        account = guild_info.get_account(interaction.user.id)
        settings = guild_info.guild_settings

        if not account:
            raise SDGException(f'The member {interaction.user.mention} does not have an account.')

        if role_subalignment_faction in account.blessed_scrolls:
            raise SDGException(f'The scroll "{role_subalignment_faction.name}" is already equipped in blessed scrolls')

        if role_subalignment_faction in account.cursed_scrolls:
            raise SDGException(f'The scroll "{role_subalignment_faction.name}" is already equipped in cursed scrolls')

        if not settings.roles_are_scrollable and isinstance(role_subalignment_faction, Role):
            raise SDGException(f'Role scrolling is disabled in this server')

        if not settings.subalignments_are_scrollable and isinstance(role_subalignment_faction, Subalignment):
            raise SDGException(f'Subalignment scrolling is disabled in this server')

        if not settings.factions_are_scrollable and isinstance(role_subalignment_faction, Faction):
            raise SDGException(f'Faction scrolling is disabled in this server')

        if scroll_type == 'Cursed' and not isinstance(role_subalignment_faction, Role):
            raise SDGException(f'Can only cursed scroll for roles')

        if scroll_type == 'Blessed':
            if len(account.blessed_scrolls) + 1 > settings.max_scrolls:
                raise SDGException(f'The server limit for scrolls is {settings.max_scrolls}')
            account.blessed_scrolls.append(role_subalignment_faction)
        else:
            if len(account.cursed_scrolls) + 1 > settings.max_scrolls:
                raise SDGException(f'The limit for scrolls is {settings.max_scrolls}')
            account.cursed_scrolls.append(role_subalignment_faction)

        self.client.replace_guild_info(guild_info)
        await self.client.modify_account_in_db(account, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Scroll Added!',
            description=f'Added "{role_subalignment_faction.name}" to {scroll_type}!'
        )

        await interaction.response.send_message(embed=embed)

    @scroll_group.command(name='remove')
    @app_commands.describe(scroll='The scroll to remove')
    async def scroll_remove(
            self,
            interaction: Interaction,
            scroll: app_commands.Transform[Role | Subalignment | Faction, ScrollTransformer],
    ):
        """Removes a scroll from your account"""
        guild_info: utils.GuildInfo = utils.get_guild_info(interaction)
        account = guild_info.get_account(interaction.user.id)
        scroll_type = ''

        if scroll in account.blessed_scrolls:
            account.blessed_scrolls.remove(scroll)
            scroll_type = 'Blessed'

        if scroll in account.cursed_scrolls:
            account.cursed_scrolls.remove(scroll)
            scroll_type = 'Cursed'

        self.client.replace_guild_info(guild_info)
        await self.client.modify_account_in_db(account, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Scroll removed!',
            description=f'Removed scroll {scroll_type} - {scroll.name} successfully!'
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(AccountCog(bot))

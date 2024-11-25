import discord

from discord import app_commands, Interaction
from discord.ext import commands

import utils
from utils import SDGException, DiscordClient, Account


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


async def setup(bot):
    await bot.add_cog(AccountCog(bot))

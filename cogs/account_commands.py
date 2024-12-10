import io
import csv
import typing
import dataclasses

import discord

from discord import app_commands, Interaction
from discord.ext import commands

import utils
from utils import SDGException, DiscordClient, Account, Role, Subalignment, Faction, RSFTransformer, ScrollTransformer


class DeleteConfirm(utils.CustomView):
    def __init__(self, owner: discord.User):
        super().__init__(owner=owner)
        self.value = None

    @discord.ui.button(label='Delete Account', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        embed = utils.create_embed(
            interaction.user,
            title='Account Deleted',
            description='The account has been deleted.'
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        self.value = True
        await self.on_timeout()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.green)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        embed = utils.create_embed(
            interaction.user,
            title='Deletion cancelled',
            description='The account has not been deleted.'
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        self.value = False
        await self.on_timeout()


@app_commands.guild_only()
class AccountCog(commands.GroupCog, group_name='account'):
    """Commands to create, view, modify, and delete accounts"""

    scroll_group = app_commands.Group(name='scroll', description='Scroll commands')
    game_group = app_commands.Group(name='game', description='Game commands')

    def __init__(self, client):
        self.client: DiscordClient = client

    @staticmethod
    def csv_dict(old_dict: dict):
        for k, v in old_dict.items():
            if isinstance(v, list):
                if v:
                    old_dict[k] = '"' + ','.join([str(i['id']) for i in v]) + '"'
                else:
                    old_dict[k] = None
            if isinstance(v, int) and len(str(v)) > 15:
                old_dict[k] = f'"{v}"'

        return old_dict

    @app_commands.command(name='create')
    @app_commands.describe(member='The member to create the account for, if not specified, it creates one for you')
    async def create_account(self, interaction: Interaction, member: discord.Member | None = None):
        """Create an account for either yourself or another member"""

        guild_info = utils.get_guild_info(interaction)

        if member and not await utils.mod_check(interaction):
            raise SDGException('You aren\'t allowed to create accounts for other members.')

        member = member or interaction.user

        if member.bot:
            raise SDGException('Can\'t create account for a bot!')

        if guild_info.get_account(member.id):
            raise SDGException(f'Member {member.mention} already has an account!')

        if (
                member == interaction.user and
                not await utils.mod_check(interaction) and
                not guild_info.guild_settings.accounts_creatable
        ):
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

    @app_commands.command(name='masscreate')
    @app_commands.check(utils.admin_check)
    async def mass_create_accounts(self, interaction: Interaction):
        """Create accounts for ALL server members"""
        guild_info = utils.get_guild_info(interaction)

        await interaction.response.defer()

        new_accounts = []
        for member in interaction.guild.members:
            existing_account = guild_info.get_account(member.id)
            if member.bot or existing_account:
                continue

            new_account = Account(
                id=member.id,
                num_wins=0,
                num_loses=0,
                num_draws=0,
                blessed_scrolls=[],
                cursed_scrolls=[],
                accomplished_achievements=[]
            )

            await self.client.add_account_to_db(new_account, interaction.guild_id)
            new_accounts.append(new_account)

        if not new_accounts:
            raise SDGException('All members already have accounts!')

        guild_info.accounts += new_accounts
        self.client.replace_guild_info(guild_info)

        embed = utils.create_embed(
            interaction.user,
            title='Accounts created!',
            description=f'Created {len(new_accounts)} accounts successfully!'
        )

        await interaction.followup.send(embed=embed)

    @app_commands.command(name='view')
    @app_commands.describe(member='The member to view the account of. By default this will be your account')
    @app_commands.describe(
        ephemeral='Whether to only show the response to you. Scroll information is shown if True. Defaults to False'
    )
    async def view_account(
            self,
            interaction: Interaction,
            member: discord.User | None = None,
            ephemeral: bool = False
    ):
        """View account info"""

        member = member or interaction.user
        guild_info = utils.get_guild_info(interaction)

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
        guild_info = utils.get_guild_info(interaction)
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

    @app_commands.command(name='export')
    @app_commands.describe(blank_data='Make the exported data blank. Useful if you will reimport later with ADD')
    @app_commands.describe(mentions_message='If specified, will only export accounts of mentioned players')
    @app_commands.check(utils.admin_check)
    async def export_accounts(
            self,
            interaction: Interaction,
            blank_data: bool = False,
            mentions_message: app_commands.Transform[discord.Message, utils.MessageTransformer] = None
    ):
        """Export accounts as a .csv file. When using a spreadsheet program use "Format quoted field as text"."""
        guild_info = utils.get_guild_info(interaction)

        if not guild_info.accounts:
            raise SDGException('This server has no accounts!')

        valid_accounts = guild_info.accounts

        if mentions_message:
            mention_ids = [m.id for m in mentions_message.mentions]
            valid_accounts = [a for a in guild_info.accounts if a.id in mention_ids]

        if not valid_accounts:
            raise SDGException('No mentioned users have accounts!')

        file_buffer = io.StringIO()
        with file_buffer as csvfile:
            fields = [f.name for f in dataclasses.fields(Account)]
            fields = ['username'] + fields
            csvwriter = csv.DictWriter(csvfile, fields)
            csvwriter.writeheader()

            for account in valid_accounts:
                try:
                    user = self.client.get_user(account.id) or await self.client.fetch_user(account.id)
                    username = user.name
                except discord.NotFound:
                    username = 'Unknown User'

                account_dict = dataclasses.asdict(account)
                account_dict = self.csv_dict(account_dict)
                account_dict['username'] = username
                if blank_data:
                    account_dict['num_wins'] = None
                    account_dict['num_loses'] = None
                    account_dict['num_draws'] = None
                    account_dict['blessed_scrolls'] = None
                    account_dict['cursed_scrolls'] = None
                    account_dict['accomplished_achievements'] = None

                csvwriter.writerow(account_dict)

            file_buffer.seek(0)
            file = discord.File(file_buffer, 'accounts.csv')

        await interaction.response.send_message(file=file, ephemeral=True)

    @app_commands.command(name='import')
    @app_commands.describe(csv_file='The csv file of accounts to import')
    @app_commands.describe(mode='ADD=Add the values to account values, SET=Sets the values to accounts')
    @app_commands.check(utils.admin_check)
    async def import_accounts(
            self,
            interaction: Interaction,
            csv_file: discord.Attachment,
            mode: typing.Literal['SET', 'ADD']
    ):
        """Import a csv file of accounts"""
        guild_info = utils.get_guild_info(interaction)
        all_rsf = guild_info.roles + guild_info.subalignments + guild_info.factions

        await interaction.response.defer()

        csv_bytes = await csv_file.read()
        csv_data = csv_bytes.decode('utf-8')
        csv_buffer = io.StringIO(csv_data)

        new_accounts = []
        csvreader = csv.DictReader(csv_buffer, delimiter=',')
        for row in csvreader:
            row: dict[str, str]

            for k, v in row.items():
                val = v.strip('", ')
                row[k] = val

            account_id = int(row['id'])
            existing_account = guild_info.get_account(account_id)

            if not existing_account:
                continue

            num_wins = int(row['num_wins'])
            num_losses = int(row['num_loses'])
            num_draws = int(row['num_draws'])
            blessed_scrolls_list = row['blessed_scrolls'].split(',')
            cursed_scrolls_list = row['cursed_scrolls'].split(',')
            achievements_list = row['accomplished_achievements'].split(',')

            blessed_scrolls = []
            cursed_scrolls = []
            achievements = []

            for scroll_id in blessed_scrolls_list:
                if scroll_id:
                    scroll_id = int(scroll_id)
                    rsf = [r for r in all_rsf if scroll_id == r.id]
                    if rsf:
                        blessed_scrolls.append(rsf[0])

            for scroll_id in cursed_scrolls_list:
                if scroll_id:
                    scroll_id = int(scroll_id)
                    rsf = [r for r in all_rsf if scroll_id == r.id]
                    if rsf:
                        cursed_scrolls.append(rsf[0])

            for ach_id in achievements_list:
                if ach_id:
                    ach_id = int(ach_id)
                    ach = [a for a in guild_info.achievements if a.id == ach_id]
                    if ach:
                        achievements.append(ach[0])

            if mode == 'SET':
                new_wins = num_wins
                new_losses = num_losses
                new_draws = num_draws
                new_blessed_scrolls = blessed_scrolls
                new_cursed_scrolls = cursed_scrolls
                new_achievements = achievements
            else:
                new_wins = num_wins + existing_account.num_wins
                new_losses = num_losses + existing_account.num_loses
                new_draws = num_draws + existing_account.num_draws

                new_blessed_scrolls = [s for s in blessed_scrolls if s not in existing_account.blessed_scrolls]
                new_blessed_scrolls += existing_account.blessed_scrolls

                new_cursed_scrolls = [s for s in cursed_scrolls if s not in existing_account.cursed_scrolls]
                new_cursed_scrolls += existing_account.cursed_scrolls
                new_cursed_scrolls = [s for s in new_cursed_scrolls if isinstance(s, Role) and
                                      s not in new_blessed_scrolls]

                new_achievements = [a for a in existing_account.accomplished_achievements if a not in achievements]
                new_achievements += existing_account.accomplished_achievements

            new_account = Account(
                id=account_id,
                num_wins=new_wins,
                num_loses=new_losses,
                num_draws=new_draws,
                blessed_scrolls=new_blessed_scrolls,
                cursed_scrolls=new_cursed_scrolls,
                accomplished_achievements=new_achievements
            )

            if new_account != existing_account:
                new_accounts.append(new_account)

        if not new_accounts:
            raise SDGException('All account data remained the same!')

        unmodified_accounts = []
        modified_account_ids = [a.id for a in new_accounts]
        for account in guild_info.accounts:
            if account.id not in modified_account_ids:
                unmodified_accounts.append(account)

        guild_info.accounts = unmodified_accounts + new_accounts

        self.client.replace_guild_info(guild_info)

        for account in new_accounts:
            await self.client.modify_account_in_db(account, interaction.guild_id)

        embed = utils.create_embed(
            interaction.user,
            title='Import successful!',
            description=f'Modified {len(new_accounts)} accounts!'
        )

        await interaction.followup.send(embed=embed)

    @scroll_group.command(name='view')
    @app_commands.describe(member='The member to view scrolls of. You need to be trusted to view other\'s scrolls')
    async def scroll_view(self, interaction: Interaction, member: discord.User | None = None):
        """View your own or someone else's equipped scrolls"""
        guild_info = utils.get_guild_info(interaction)

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
        guild_info = utils.get_guild_info(interaction)
        account = guild_info.get_account(interaction.user.id)
        settings = guild_info.guild_settings

        if not account:
            raise SDGException(f'The member {interaction.user.mention} does not have an account.')

        if role_subalignment_faction in account.blessed_scrolls:
            raise SDGException(f'The scroll "{role_subalignment_faction.name}" is already equipped in blessed scrolls')

        if role_subalignment_faction in account.cursed_scrolls:
            raise SDGException(f'The scroll "{role_subalignment_faction.name}" is already equipped in cursed scrolls')

        if not settings.roles_are_scrollable and isinstance(role_subalignment_faction, Role):
            raise SDGException('Role scrolling is disabled in this server')

        if not settings.subalignments_are_scrollable and isinstance(role_subalignment_faction, Subalignment):
            raise SDGException('Subalignment scrolling is disabled in this server')

        if not settings.factions_are_scrollable and isinstance(role_subalignment_faction, Faction):
            raise SDGException('Faction scrolling is disabled in this server')

        if scroll_type == 'Cursed' and not isinstance(role_subalignment_faction, Role):
            raise SDGException('Can only cursed scroll for roles')

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
        guild_info = utils.get_guild_info(interaction)
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

    @app_commands.check(utils.mod_check)
    @game_group.command(name='add')
    @app_commands.describe(result='The game result to add')
    @app_commands.describe(member='Add a game to this singular member')
    @app_commands.describe(mentions_message='Add a game to all players mentioned in this message ID')
    async def game_add(
            self,
            interaction: Interaction,
            result: typing.Literal['WIN', 'LOSS', 'DRAW'],
            member: discord.User = None,
            mentions_message: app_commands.Transform[discord.Message, utils.MessageTransformer] = None
    ):
        """Add a game result to a player or multiple players"""
        guild_info = utils.get_guild_info(interaction)

        if member is None and mentions_message is None:
            raise SDGException('You need to specify either member or mentions_message')

        if member and mentions_message:
            raise SDGException('Can\'t use both members and member_mentions_message_id!')

        members = [member] if member else mentions_message.mentions
        accounts = [guild_info.get_account(m.id) for m in members]
        accounts = [a for a in accounts if a]

        if not accounts:
            raise SDGException('No members provided have accounts!')

        for account in accounts:
            if result == 'WIN':
                account.num_wins += 1
            elif result == 'LOSS':
                account.num_loses += 1
            else:
                account.num_draws += 1

            await self.client.modify_account_in_db(account, interaction.guild_id)

        self.client.replace_guild_info(guild_info)

        embed = utils.create_embed(
            interaction.user,
            title='Accounts updated!',
            description=f'Successfully added a {result} to {len(accounts)} accounts!'
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.check(utils.mod_check)
    @game_group.command(name='set')
    @app_commands.describe(result='The game result to set')
    @app_commands.describe(amount='The amount to set')
    @app_commands.describe(member='Set the games of this singular member')
    @app_commands.describe(mentions_message='Set games to all players mentioned in this message ID')
    async def game_set(
            self,
            interaction: Interaction,
            result: typing.Literal['WIN', 'LOSS', 'DRAW'],
            amount: int,
            member: discord.User = None,
            mentions_message: app_commands.Transform[discord.Message, utils.MessageTransformer] = None
    ):
        """Sets the amount of games to a player or multiple players"""
        guild_info = utils.get_guild_info(interaction)

        if member is None and mentions_message is None:
            raise SDGException('You need to specify either member or mentions_message')

        if member and mentions_message:
            raise SDGException('Can\'t use both members and member_mentions_message_id!')

        members = [member] if member else mentions_message.mentions
        accounts = [guild_info.get_account(m.id) for m in members]
        accounts = [a for a in accounts if a]

        if not accounts:
            raise SDGException('No members provided have accounts!')

        for account in accounts:
            if result == 'WIN':
                account.num_wins = amount
            elif result == 'LOSS':
                account.num_loses = amount
            else:
                account.num_draws = amount

            await self.client.modify_account_in_db(account, interaction.guild_id)

        self.client.replace_guild_info(guild_info)

        embed = utils.create_embed(
            interaction.user,
            title='Accounts updated!',
            description=f'Successfully set {result}={amount} to {len(accounts)} accounts!'
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AccountCog(bot))

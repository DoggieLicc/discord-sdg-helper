import random
import typing
from dataclasses import dataclass
from abc import abstractmethod

import emoji
import discord

from discord import app_commands, Member
from discord.ext import commands
from discord.app_commands import Transform
from utils import GuildInfo, Faction, Role, mod_check, get_guild_info, SDGException, Subalignment, PaginatedMenu

import utils


@dataclass(slots=True)
class Player:
    user: discord.User
    role: Role
    weight: tuple[list[Role], list[int]] | None


class RoleFactionMenu(PaginatedMenu):
    def __init__(self, client, *args, **kwargs):
        self.client: utils.DiscordClient = client
        super().__init__(*args, **kwargs)

    def format_line(self, item: Role) -> str:
        faction_channel = self.client.get_channel(item.faction.id)
        sub_tag = faction_channel.get_tag(item.subalignment.id)
        emoji_str = str(sub_tag.emoji) + ' ' if sub_tag.emoji else ''
        return f'{emoji_str}{item.name} (<#{item.id}>)'

    async def get_page_contents(self) -> dict:
        page = self.paginator.pages[self.current_page - 1]
        embed = utils.create_embed(
            self.owner,
            title=f'Listing {len(self.items)} roles ({self.current_page}/{self.max_page})',
            description=page
        )
        return {'embed': embed}


class LeaderboardMenu(PaginatedMenu):
    def __init__(self, *args, **kwargs):
        self.rank = 1
        super().__init__(*args, **kwargs)

    @abstractmethod
    def get_num(self, item: utils.Account) -> str:
        ...

    def format_line(self, item: utils.Account) -> str:
        string = f'#{self.rank} - <@{item.id}> - {self.get_num(item)}'
        self.rank += 1
        return string

    async def get_page_contents(self) -> dict:
        page = self.paginator.pages[self.current_page - 1]
        embed = utils.create_embed(
            self.owner,
            title=f'Leaderboard - {len(self.items)} players ({self.current_page}/{self.max_page})',
            description=page
        )
        return {'embed': embed}


class WinLeaderboardMenu(LeaderboardMenu):
    def get_num(self, item: utils.Account) -> str:
        return f'{item.num_wins} Wins'


class WLRatioLeaderboardMenu(LeaderboardMenu):
    def get_num(self, item: utils.Account) -> str:
        if item.num_loses == 0:
            ratio = float(item.num_wins)
        else:
            ratio = item.num_wins / item.num_loses

        return f'{ratio:.2f} W/L'


class AchievementLeaderboardMenu(LeaderboardMenu):
    def get_num(self, item: utils.Account) -> str:
        return f'{len(item.accomplished_achievements)} Achievements'


class GamesPlayedLeaderboardMenu(LeaderboardMenu):
    def get_num(self, item: utils.Account) -> str:
        return f'{item.num_wins + item.num_loses + item.num_draws} Games Played'


class MiscCog(commands.Cog):
    def __init__(self, client):
        self.client: utils.DiscordClient = client

    def generate_lots(self, player, roles, guild_info: GuildInfo, use_scrolls: bool) -> list[int]:
        lots: list[int] = []

        account = guild_info.get_account(player.id)
        blessed_scrolls = account.blessed_scrolls if account else []
        cursed_scrolls = account.cursed_scrolls if account else []

        role_multiplier = guild_info.guild_settings.role_scroll_multiplier
        subalignment_multiplier = guild_info.guild_settings.subalignment_scroll_multiplier
        faction_multiplier = guild_info.guild_settings.faction_scroll_multiplier
        default_lots = 10

        for role in roles:
            lots_num = default_lots

            if use_scrolls:
                for blessed_scroll in blessed_scrolls:
                    if isinstance(blessed_scroll, utils.Role):
                        if blessed_scroll == role:
                            lots_num += default_lots * role_multiplier
                    if isinstance(blessed_scroll, Subalignment):
                        subalignment_roles = self.client.get_subalignment_roles(blessed_scroll)
                        if role in subalignment_roles:
                            lots_num += default_lots * subalignment_multiplier
                    if isinstance(blessed_scroll, Faction):
                        faction_roles = self.client.get_faction_roles(blessed_scroll)
                        if role in faction_roles:
                            lots_num += default_lots * faction_multiplier

                for cursed_scroll in cursed_scrolls:
                    if role == cursed_scroll:
                        lots_num = 1

            lots.append(lots_num)

        return lots

    def assign_roles_to_players(
            self,
            players: list[discord.User | discord.Member],
            roles: list[Role],
            guild_info: GuildInfo,
            use_scrolls: bool = True,
            no_randomize: bool = False
    ) -> list[Player]:
        if no_randomize:
            assigned_players = [Player(player, role, None) for player, role in zip(players, roles)]
            return assigned_players

        random.shuffle(players)
        random.shuffle(roles)

        assigned_players = []

        for player in players:
            role_lots = self.generate_lots(player, roles, guild_info, use_scrolls)

            chosen_role = random.choices(roles, weights=role_lots)[0]
            tup = roles.copy(), role_lots
            gen_player = Player(player, chosen_role, tup)
            roles.remove(chosen_role)

            assigned_players.append(gen_player)

        random.shuffle(assigned_players)

        return assigned_players

    @app_commands.command(name='role')
    @app_commands.guild_only()
    @app_commands.describe(role='The role to view')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def get_role(
            self,
            interaction: discord.Interaction,
            role: Transform[Role, utils.RoleTransformer],
            ephemeral: bool = False
    ):
        """Get info on a role"""
        thread_channel = interaction.guild.get_channel_or_thread(role.id)
        starter_message = thread_channel.starter_message or await thread_channel.fetch_message(thread_channel.id)
        role_str = starter_message.content
        message_image = starter_message.attachments[0] if starter_message.attachments else None
        forum_channel = thread_channel.parent or await interaction.guild.fetch_channel(thread_channel.parent_id)

        reaction_str = ''

        if forum_channel.default_reaction_emoji:
            emoji_ = forum_channel.default_reaction_emoji
            reaction = None

            for react in starter_message.reactions:
                if isinstance(react.emoji, str):
                    if react.emoji == str(emoji_):
                        reaction = react
                        break
                    continue

                if str(react.emoji) == str(emoji_) or react.emoji.id == emoji_.id:
                    reaction = react
                    break

            if reaction:
                num_reactions = reaction.normal_count

                reaction_str = f' | {num_reactions} {emoji_}'

        embed = utils.create_embed(
            interaction.user,
            title=f'{role.name}',
            thumbnail=message_image,
            description=f'Post: {thread_channel.mention}{reaction_str}\n\n'
                        f'{role_str[:4000]}'
        )

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    @app_commands.command(name='maintenance')
    @app_commands.guild_only()
    @app_commands.check(mod_check)
    async def maintenance(
            self,
            interaction: discord.Interaction,
    ):
        """Get maintenance info for this server"""

        await interaction.response.defer()

        failed_factions = await self.client.sync_guild(interaction.guild)

        guild_info: GuildInfo = get_guild_info(interaction)

        len_factions = len(guild_info.factions)
        len_subalignments = len(guild_info.subalignments)
        len_infocategories = len(guild_info.info_categories)
        len_roles = len(guild_info.roles)
        len_infotags = len(guild_info.info_tags)

        embed = utils.create_embed(
            interaction.user,
            title='Maintenance info!',
            description=f'If there are failed roles, make sure your subalignments are set up properly!\n\n'
                        f'**Factions:** {len_factions}\n'
                        f'**Subalignments:** {len_subalignments}\n'
                        f'**Info Categories:** {len_infocategories}\n\n'
                        f'**Roles:** {len_roles}\n'
                        f'**Info tags:** {len_infotags}'
        )

        for k, v in failed_factions.items():
            if not v:
                continue

            faction = guild_info.get_faction(k)
            failed_str = '\n'.join(r.mention for r in v)
            embed.add_field(
                name=f'Failed roles in {faction.name}',
                value=failed_str[:1000],
                inline=False
            )
            embed.colour = discord.Color.yellow()

        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name='anonpoll')
    @app_commands.describe(poll_question='The question to ask')
    @app_commands.describe(poll_options='The comma-seperated list of options, defaults to "INNOCENT, GUILTY, ABSTAIN"')
    @app_commands.describe(whitelist='If set, only the users and roles set here will be allowed to vote')
    @app_commands.describe(blacklist='If set, the users and roles set here will not be allowed to vote')
    @app_commands.guild_only()
    async def start_anonpoll(
            self,
            interaction: discord.Interaction,
            poll_question: str,
            poll_options: str = 'INNOCENT, GUILTY, ABSTAIN',
            whitelist: Transform[list[discord.Role | Member], utils.GreedyMemberRoleTransformer] = None,
            blacklist: Transform[list[discord.Role | Member], utils.GreedyMemberRoleTransformer] = None
    ):
        """Starts a hidden poll that sends votes to a private thread"""

        poll_options = poll_options.split(',')
        poll_options = [o.strip() for o in poll_options]

        if not poll_options:
            raise SDGException('No poll options!')

        if len(poll_options) > 25:
            raise SDGException('You can only have up to 25 options!')

        fake_message = utils.FakeMessage(interaction.guild, poll_question)
        cleaned_question = fake_message.clean_content

        private_thread = await interaction.channel.create_thread(
            name=f'Poll results: {cleaned_question}',
            invitable=False
        )

        whitelist_text = ' '.join(w.mention for w in whitelist) if whitelist else 'None'
        blacklist_text = ' '.join(b.mention for b in blacklist) if blacklist else 'None'
        private_thread_embed = utils.create_embed(
            None,
            title=f'"{cleaned_question}"',
            description='Live voting updates will be posted in this thread!\n\n'
                        f'**Whitelist:** {whitelist_text}\n'
                        f'**Blacklist:** {blacklist_text}'
        )
        await private_thread.send(interaction.user.mention, embed=private_thread_embed)

        view = discord.ui.View(timeout=None)
        select = utils.PollSelect(
            thread=private_thread,
            whitelist=whitelist,
            blacklist=blacklist,
            placeholder=cleaned_question
        )
        button = utils.PollSelectButton(allowed_user=interaction.user, custom_id=f'button:stop:{private_thread.id}')

        view.add_item(select)
        view.add_item(button)
        fake_ctx = utils.FakeContext(bot=interaction.client, guild=interaction.guild)
        emoji_converter = commands.PartialEmojiConverter()

        for option in poll_options[:25]:
            split_option = option.split(maxsplit=1)
            real_option = option
            p_emoji = None
            if len(split_option) >= 2:
                emoji_str = split_option[0].strip()
                try:
                    p_emoji = await emoji_converter.convert(fake_ctx, emoji_str) # type: ignore
                    real_option = split_option[1]
                except (commands.BadArgument, commands.CommandError):
                    if emoji.is_emoji(emoji_str):
                        p_emoji = emoji_str
                        real_option = split_option[1]
            fake_option_message = utils.FakeMessage(interaction.guild, real_option)
            select.add_option(label=fake_option_message.clean_content[:100], emoji=p_emoji)

        await interaction.response.send_message(
            poll_question,
            view=view,
            allowed_mentions=discord.AllowedMentions.none()
        )

    @app_commands.guild_only()
    @app_commands.command(name='listroles')
    @app_commands.describe(faction='List roles part of this faction')
    @app_commands.describe(subalignment='List roles part of this subalignment')
    @app_commands.describe(include_tags='List roles that has atleast one of these comma-seperated forum tags')
    @app_commands.describe(exclude_tags='Don\'t list roles that have any of these comma-seperated forum tags')
    async def list_roles(
            self,
            interaction: discord.Interaction,
            faction: Transform[Faction, utils.FactionTransformer] | None = None,
            subalignment: Transform[Subalignment, utils.SubalignmentTransformer] | None = None,
            include_tags: str | None = '',
            exclude_tags: str | None = '',
            ephemeral: bool = False
    ):
        """Lists all roles that fit the filters"""
        guild_info = get_guild_info(interaction)

        valid_roles = utils.get_valid_roles(
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            guild_info=guild_info,
            faction=faction,
            subalignment=subalignment,
            guild=interaction.guild
        )

        valid_roles.sort(key=lambda r: r.subalignment.name)

        if not valid_roles:
            raise SDGException('No valid roles fit those filters!')

        view = RoleFactionMenu(
            client=self.client,
            owner=interaction.user,
            items=valid_roles
        )

        contents = await view.get_page_contents()

        if view.max_page == 1:
            view = discord.utils.MISSING

        await interaction.response.send_message(view=view, ephemeral=ephemeral, **contents)

    @app_commands.guild_only()
    @app_commands.command(name='leaderboard')
    @app_commands.describe(ranking='The ranking to view')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def leaderboard(
            self,
            interaction: discord.Interaction,
            ranking: typing.Literal[
                '# of Wins',
                'W/L Ratio',
                '# of Achievements',
                '# of Games Played'
            ],
            ephemeral: bool = False
    ):
        """View the server leaderboard"""
        guild_info: utils.GuildInfo = get_guild_info(interaction)
        accounts = guild_info.accounts

        if not accounts:
            raise SDGException('This server has no accounts!')

        if ranking == '# of Wins':
            accounts.sort(key=lambda a: a.num_wins, reverse=True)
            view = WinLeaderboardMenu(interaction.user, accounts)
        elif ranking == '# of Achievements':
            accounts.sort(key=lambda a: len(a.accomplished_achievements), reverse=True)
            view = AchievementLeaderboardMenu(interaction.user, accounts)
        elif ranking == '# of Games Played':
            accounts.sort(key=lambda a: a.num_wins + a.num_loses + a.num_draws, reverse=True)
            view = GamesPlayedLeaderboardMenu(interaction.user, accounts)
        else:
            accounts.sort(
                key=lambda a: (a.num_wins / a.num_loses) if a.num_loses != 0 else float(a.num_wins),
                reverse=True
            )
            view = WLRatioLeaderboardMenu(interaction.user, accounts)

        contents = await view.get_page_contents()

        if view.max_page == 1:
            view = discord.utils.MISSING

        await interaction.response.send_message(view=view, ephemeral=ephemeral, **contents)

    @app_commands.guild_only()
    @app_commands.command(name='assignroles')
    @app_commands.describe(mentions_message='Message ID or link to get mentions from. (Use google to search how)')
    @app_commands.describe(roles_message='Message ID or link containing the output of "Generate Rolelist Roles"')
    @app_commands.describe(use_account_scrolls='Whether to use account scrolls. Defaults to True')
    @app_commands.describe(
        no_randomize='Don\'t distribute the roles randomly, instead it assigns by order. Defaults to False'
    )
    @app_commands.describe(details='Display additional details about role distribution. Defaults to False')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to True')
    @app_commands.check(mod_check)
    async def assign_roles_cmd(
            self,
            interaction: discord.Interaction,
            mentions_message: Transform[discord.Message, utils.MessageTransformer],
            roles_message: Transform[discord.Message, utils.MessageTransformer],
            use_account_scrolls: bool = True,
            no_randomize: bool = False,
            details: bool = False,
            ephemeral: bool = True,
    ):
        """Assign generated roles to players using their account scrolls."""
        guild_info: utils.GuildInfo = get_guild_info(interaction)
        raw_message_mentions: list[int] = mentions_message.raw_mentions
        settings = guild_info.guild_settings

        generated_roles = []
        for channel_id in roles_message.raw_channel_mentions:
            for role_ in guild_info.roles:
                if role_.id == channel_id:
                    generated_roles.append(role_)

        message_mentions = []
        for mention in raw_message_mentions:
            member = interaction.guild.get_member(mention)
            if member:
                message_mentions.append(member)

        if not generated_roles:
            raise SDGException('No roles found in provided message!')

        if len(generated_roles) != len(message_mentions):
            raise SDGException('Mismatch between amount of provided roles '
                               f'({len(generated_roles)}) and amount of mentioned players ({len(message_mentions)})')

        if not message_mentions:
            raise SDGException('No users or roles are mentioned in that message!')

        if not interaction.channel.type == discord.ChannelType.text:
            raise SDGException('Can\'t use in non-text channels!')

        await interaction.response.defer(ephemeral=ephemeral)

        distributed_players = self.assign_roles_to_players(
            message_mentions.copy(),
            generated_roles,
            guild_info,
            use_account_scrolls,
            no_randomize
        )

        sorted_players = []
        for i in range(len(distributed_players)):
            user = message_mentions[i]
            for player in distributed_players:
                if player.user == user:
                    sorted_players.append(player)
                    break

        role_str = '\n'.join(f'{p.user.mention} - {p.role.name} (<#{p.role.id}>)' for p in sorted_players)

        distributed_users = [p.user for p in sorted_players]
        distributed_roles = [p.role for p in sorted_players]

        embed = utils.create_embed(
            interaction.user,
            title='Roles distributed!',
            description=role_str
        )

        file = None

        if details and not no_randomize:
            details_str = f'ROLE SCROLL MULTIPLIER: {settings.role_scroll_multiplier}\n' \
                          f'SUBALIGNMENT SCROLL MULTIPLIER: {settings.subalignment_scroll_multiplier}\n' \
                          f'FACTION SCROLL MULTIPLIER: {settings.faction_scroll_multiplier}\n\n' \
                          f'------------ SCROLLS ------------\n'

            # Scroll details
            for player in sorted_players:
                user = player.user
                player_scroll_str = f'{user}:\n'
                account = guild_info.get_account(user.id)
                if not account:
                    player_scroll_str += 'No account!\n'
                else:
                    blessed_scroll_str = 'Blessed: '
                    blessed_scrolls = account.blessed_scrolls
                    if not blessed_scrolls:
                        blessed_scroll_str += 'None'
                    else:
                        blessed_scroll_str += ', '.join(s.name for s in blessed_scrolls)
                    player_scroll_str += blessed_scroll_str + '\n'

                    cursed_scroll_str = 'Cursed: '
                    cursed_scrolls = account.cursed_scrolls
                    if not cursed_scrolls:
                        cursed_scroll_str += 'None'
                    else:
                        cursed_scroll_str += ', '.join(s.name for s in cursed_scrolls)
                    player_scroll_str += cursed_scroll_str + '\n'

                details_str += player_scroll_str + '\n'

            details_str += '------------ ROLE WEIGHTS ------------\n'

            for player in sorted_players:
                roles = player.weight[0]
                weight_nums = player.weight[1]
                weight_str = f'{player.user}: '

                for i, role in enumerate(roles):
                    weight_num = weight_nums[i]
                    weight_str += f'{role.name}:{weight_num} | '

                details_str += weight_str + '\n'

            file = utils.str_to_file(details_str.strip('\n |'), filename='details.txt')

        view = utils.GenerateCSVView(interaction.user, distributed_users, distributed_roles, ephemeral)

        await interaction.edit_original_response(
            embed=embed,
            view=view,
            attachments=[file] if file else discord.utils.MISSING
        )

    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_threads=True, create_private_threads=True)
    @app_commands.checks.bot_has_permissions(manage_threads=True, create_private_threads=True)
    @app_commands.command(name='generatethreads')
    @app_commands.describe(mentions_message='Message ID or link to get mentions from. (Use google to search how)')
    @app_commands.describe(
        additional_message='Additional message to send to each thread. Useful for mentioning a role etc.'
    )
    @app_commands.describe(thread_name='The name to give the threads, by default it will be "Mod Thread"')
    @app_commands.describe(invitable='Whether to allow non-moderators to add others to their thread. Defaults to False')
    @app_commands.describe(roles_message='Message ID or link containing the output of "Generate Rolelist Roles"')
    @app_commands.describe(
        use_account_scrolls='Whether to use account scrolls if roles_link is specified. Defaults to True'
    )
    async def generate_mod_threads(
            self,
            interaction: discord.Interaction,
            mentions_message: Transform[discord.Message, utils.MessageTransformer],
            additional_message: str = '',
            thread_name: str = 'Mod Thread',
            invitable: bool = False,
            roles_message: Transform[discord.Message, utils.MessageTransformer] | None = None,
            use_account_scrolls: bool = True
    ):
        """Generate mod threads using mentions from the provided message"""

        guild_info: utils.GuildInfo = get_guild_info(interaction)
        raw_message_mentions: list[int] = mentions_message.raw_mentions

        generated_roles = []
        if roles_message:
            for channel_id in roles_message.raw_channel_mentions:
                for role_ in guild_info.roles:
                    if role_.id == channel_id:
                        generated_roles.append(role_)

        message_mentions = []
        for mention in raw_message_mentions:
            member = interaction.guild.get_member(mention)
            if member:
                message_mentions.append(member)

        if roles_message and not generated_roles:
            raise SDGException('No roles found in provided message!')

        if generated_roles:
            if len(generated_roles) != len(message_mentions):
                raise SDGException(f'Mismatch between amount of provided roles ({len(generated_roles)}) '
                                   f'and amount of mentioned players ({len(message_mentions)})')

        if not message_mentions:
            raise SDGException('No users or roles are mentioned in that message!')

        if not interaction.channel.type == discord.ChannelType.text:
            raise SDGException('Can\'t use in non-text channels!')

        await interaction.response.defer(ephemeral=True)

        fake_message = utils.FakeMessage(interaction.guild, thread_name)
        thread_name = fake_message.clean_content

        distributed_players = []
        distributed_users = None
        distributed_roles = None
        if generated_roles:
            distributed_players = self.assign_roles_to_players(
                message_mentions.copy(),
                generated_roles,
                guild_info,
                use_account_scrolls
            )

            sorted_players = []
            for i in range(len(distributed_players)):
                user = message_mentions[i]
                for player in distributed_players:
                    if player.user == user:
                        sorted_players.append(player)
                        break

            distributed_users = [p.user for p in sorted_players]
            distributed_roles = [p.role for p in sorted_players]

        for member in message_mentions:
            thread = await interaction.channel.create_thread(
                name=f'{member} {thread_name}',
                auto_archive_duration=10080,
                invitable=invitable
            )

            message_to_send = member.mention + ' ' + interaction.user.mention + '\n\n' + additional_message

            if distributed_players:
                player = [p for p in distributed_players if p.user == member][0]
                random_role = player.role
                message_to_send = message_to_send.strip()
                message_to_send += f'\n\n**You are the {random_role.name} (<#{random_role.id}>)**'

            await thread.send(message_to_send, allowed_mentions=discord.AllowedMentions.all())
            await thread.leave()

        embed = utils.create_embed(
            interaction.user,
            title='Threads created!',
            description=f'Generated {len(message_mentions)} private threads'
        )

        view = utils.GenerateCSVView(interaction.user, distributed_users or message_mentions, distributed_roles)

        await interaction.edit_original_response(embed=embed, view=view)

    @app_commands.command(name='guide')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to True')
    async def guide_cmd(self, interaction: discord.Interaction, ephemeral: bool = True):
        """View the guide on how to use this bot!"""
        if not self.client.guides:
            raise SDGException('No guides are loaded. (Tell the hoster)')

        embed = utils.create_embed(
            interaction.user,
            title='Bot Guide!',
            description='Select an option below to see the guide for it!'
        )
        view = utils.GuideMenuView(interaction, self.client.guides)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)


async def setup(bot):
    await bot.add_cog(MiscCog(bot))

import asyncio
import random
import re
from dataclasses import dataclass

import discord

from discord import app_commands
from discord.ext import commands
from utils import GuildInfo, Faction, Role, mod_check, get_guild_info, SDGException, Subalignment, PaginatedMenu

import utils


@dataclass(slots=True)
class Player:
    user: discord.User
    role: Role


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
        page = self.paginator.pages[self.current_page-1]
        embed = utils.create_embed(
            self.owner,
            title=f'Listing {len(self.items)} roles ({self.current_page}/{self.max_page})',
            description=page
        )
        return {'embed': embed}


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
            players: list[discord.User],
            roles: list[Role],
            guild_info: GuildInfo,
            use_scrolls: bool = True
    ) -> list[Player]:
        random.shuffle(players)
        random.shuffle(roles)

        assigned_players = []

        for player in players:
            role_lots = self.generate_lots(player, roles, guild_info, use_scrolls)

            chosen_role = random.choices(roles, weights=role_lots)[0]
            gen_player = Player(player, chosen_role)
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
            role: app_commands.Transform[Role, utils.RoleTransformer],
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
            emoji = forum_channel.default_reaction_emoji
            reaction = None

            for react in starter_message.reactions:
                if isinstance(react.emoji, str):
                    if react.emoji == str(emoji):
                        reaction = react
                        break
                    continue

                if str(react.emoji) == str(emoji) or react.emoji.id == emoji.id:
                    reaction = react
                    break

            if reaction:
                num_reactions = reaction.normal_count

                reaction_str = f' | {num_reactions} {emoji}'

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

        await interaction.followup.send(embed=embed)

    @app_commands.command(name='anonpoll')
    @app_commands.describe(poll_question='The question to ask')
    @app_commands.describe(poll_options='The comma-seperated list of options, defaults to "INNOCENT, GUILTY, ABSTAIN"')
    @app_commands.describe(include_role_1='If included roles are set, only members with those roles can vote')
    @app_commands.describe(exclude_role_1='Players with excluded roles can\'t vote')
    @app_commands.guild_only()
    async def start_anonpoll(
            self,
            interaction: discord.Interaction,
            poll_question: str,
            poll_options: str = 'INNOCENT, GUILTY, ABSTAIN',
            include_role_1: discord.Role | None = None,
            include_role_2: discord.Role | None = None,
            include_role_3: discord.Role | None = None,
            exclude_role_1: discord.Role | None = None,
            exclude_role_2: discord.Role | None = None,
            exclude_role_3: discord.Role | None = None
    ):
        """Starts a hidden poll that sends votes to a private thread"""

        include_role_1 = [include_role_1] if include_role_1 else list()
        include_role_2 = [include_role_2] if include_role_2 else list()
        include_role_3 = [include_role_3] if include_role_3 else list()
        exclude_role_1 = [exclude_role_1] if exclude_role_1 else list()
        exclude_role_2 = [exclude_role_2] if exclude_role_2 else list()
        exclude_role_3 = [exclude_role_3] if exclude_role_3 else list()

        included_roles = include_role_1 + include_role_2 + include_role_3
        excluded_roles = exclude_role_1 + exclude_role_2 + exclude_role_3

        poll_options = poll_options.split(',')
        poll_options = [o.strip() for o in poll_options]

        if not poll_options:
            raise SDGException('No poll options!')

        private_thread = await interaction.channel.create_thread(name=f'Poll results: {poll_question}', invitable=False)
        await private_thread.send(interaction.user.mention)

        view = discord.ui.View(timeout=None)
        select = utils.PollSelect(
            thread=private_thread,
            included_roles=included_roles,
            excluded_roles=excluded_roles,
            placeholder=poll_question
        )
        button = utils.PollSelectButton(allowed_user=interaction.user, custom_id=f'button:stop:{private_thread.id}')

        view.add_item(select)
        view.add_item(button)

        for option in poll_options[:25]:
            select.add_option(label=option[:100])

        await interaction.response.send_message(poll_question, view=view)

    @app_commands.command(name='listroles')
    @app_commands.describe(faction='List roles part of this faction')
    @app_commands.describe(subalignment='List roles part of this subalignment')
    @app_commands.describe(include_tags='List roles that has atleast one of these comma-seperated forum tags')
    @app_commands.describe(exclude_tags='Don\'t list roles that have any of these comma-seperated forum tags')
    async def list_roles(
            self,
            interaction: discord.Interaction,
            faction: app_commands.Transform[Faction, utils.FactionTransformer] | None = None,
            subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer] | None = None,
            include_tags: str | None = '',
            exclude_tags: str | None = '',
            ephemeral: bool = False
    ):
        """Lists all roles that fit the filters"""
        guild_info = get_guild_info(interaction)
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
    @app_commands.checks.has_permissions(manage_threads=True, create_private_threads=True)
    @app_commands.checks.bot_has_permissions(manage_threads=True, create_private_threads=True)
    @app_commands.command(name='generatethreads')
    @app_commands.describe(mentions_message_id='The ID of the message to get mentions from. (Use google to search how)')
    @app_commands.describe(additional_message='Additonal message to send to each thread. Useful for mentioning a role etc.')
    @app_commands.describe(thread_name='The name to give the threads, by default it will be "Mod Thread"')
    @app_commands.describe(invitable='Whether to allow non-moderators to add others to their thread. Defaults to False')
    @app_commands.describe(roles_link='Link to message containing the output of "Generate Rolelist Roles"')
    @app_commands.describe(use_account_scrolls='Whether to use account scrolls if roles_link is specified. Defaults to True')
    async def generate_mod_threads(
            self,
            interaction: discord.Interaction,
            mentions_message_id: app_commands.Transform[discord.Message, utils.MessageTransformer],
            additional_message: str = '',
            thread_name: str = 'Mod Thread',
            invitable: bool = False,
            roles_link: str = '',
            use_account_scrolls: bool = True
    ):
        """Generate mod threads using mentions from the provided message"""

        message = mentions_message_id
        guild_info = get_guild_info(interaction)

        message_mentions = message.mentions
        role_mentions = message.role_mentions

        link_regex = re.compile(
            r"https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com"
            r"/channels/[0-9]{15,19}/(?P<channel_id>"
            r"[0-9]{15,19})/(?P<message_id>[0-9]{15,19})/?"
        )

        channel_mention_regex = re.compile(r'<#([0-9]{15,20})>')

        generated_roles = []
        match = re.search(link_regex, roles_link)
        if match:
            channel_id = match.group('channel_id')
            message_id = match.group('message_id')

            channel = interaction.guild.get_channel_or_thread(channel_id) or await interaction.guild.fetch_channel(channel_id)
            message = await channel.fetch_message(message_id)

            for match in re.finditer(channel_mention_regex, message.content):
                channel_id = match.group(1)
                role = [r for r in guild_info.roles if int(channel_id) == r.id]
                if role:
                    generated_roles.append(role[0])

        random.shuffle(generated_roles)

        for role in role_mentions:
            for member in role.members:
                if member not in message_mentions:
                    message_mentions.append(member)

        if roles_link and not match:
            raise SDGException(f'Invalid roles link! It must be a Discord link to a message')

        if roles_link and not generated_roles:
            raise SDGException(f'No roles found in provided message!')

        if generated_roles:
            if len(generated_roles) != len(message_mentions):
                raise SDGException(f'Mismatch between amount of provided roles '
                                   f'({len(generated_roles)}) and amount of mentioned players ({len(message_mentions)})')

        if not message_mentions:
            raise SDGException('No users or roles are mentioned in that message!')

        if not interaction.channel.type == discord.ChannelType.text:
            raise SDGException('Can\'t use in non-text channels!')

        await interaction.response.defer(ephemeral=True)

        distributed_players = []
        if generated_roles:
            distributed_players = self.assign_roles_to_players(message_mentions, generated_roles, guild_info, use_account_scrolls)

        for member in message_mentions:
            thread = await message.channel.create_thread(
                name=f'{member} {thread_name}',
                auto_archive_duration=10080,
                invitable=invitable
            )

            message_to_send = member.mention + ' ' + interaction.user.mention + '\n\n' + additional_message

            if distributed_players:
                player = [p for p in distributed_players if p.user == member][0]
                random_role = player.role
                message_to_send = message_to_send.strip() + f'\n\n**You are the {random_role.name} (<#{random_role.id}>)**'

            await thread.send(message_to_send, allowed_mentions=discord.AllowedMentions.all())
            await thread.leave()

        embed = utils.create_embed(
            interaction.user,
            title='Threads created!',
            description=f'Generated {len(message_mentions)} private threads'
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MiscCog(bot))

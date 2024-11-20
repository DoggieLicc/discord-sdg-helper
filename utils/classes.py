from __future__ import annotations

import copy
import discord
import asqlite

from dataclasses import dataclass
from collections import Counter
from thefuzz import process
from typing import Any, TypeVar

from discord import app_commands, Interaction
from discord.app_commands import Choice
from discord.ext.commands import Bot
from discord.state import ConnectionState

from utils.funcs import get_guild_info, create_embed
from utils.db_helper import DatabaseHelper, BaseTable, BaseColumn


@dataclass(slots=True)
class SDGObject:
    name: str
    id: int


S = TypeVar('S', bound=SDGObject)


FactionTable = BaseTable(
    name='factions',
    columns=[
        BaseColumn(
            name='channel_id',
            datatype='integer',
            addit_schema='PRIMARY KEY'
        ),
        BaseColumn(
            name='name',
            datatype='string'
        )
    ]
)

SubalignmentTable = BaseTable(
    name='subalignments',
    columns=[
        BaseColumn(
            name='channel_id',
            datatype='integer',
            addit_schema='PRIMARY KEY'
        ),
        BaseColumn(
            name='name',
            datatype='string'
        )
    ]
)

InfotagTable = BaseTable(
    name='infotags',
    columns=[
        BaseColumn(
            name='channel_id',
            datatype='integer',
            addit_schema='PRIMARY KEY'
        ),
        BaseColumn(
            name='name',
            datatype='string'
        )
    ]
)

TrustedIds = BaseTable(
    name='trusted_ids',
    columns=[
        BaseColumn(
            name='id',
            datatype='integer',
            addit_schema='PRIMARY KEY'
        ),
        BaseColumn(
            name='guild_id',
            datatype='integer'
        )
    ]
)


class CustomConnectionState(ConnectionState):
    """Custon ConectionState that doesn't remove archived threads from internal cache"""

    def parse_thread_update(self, data) -> None:
        guild_id = int(data['guild_id'])
        guild = self._get_guild(guild_id)
        if guild is None:
            return

        raw = discord.RawThreadUpdateEvent(data)
        raw.thread = thread = guild.get_thread(raw.thread_id)
        self.dispatch('raw_thread_update', raw)
        if thread is not None:
            old = copy.copy(thread)
            thread._update(data)
            # "if thread.archived: ...remove_thread"  removed here
            self.dispatch('thread_update', old, thread)
        else:
            thread = discord.Thread(guild=guild, state=guild._state, data=data)
            if not thread.archived:
                guild._add_thread(thread)
            self.dispatch('thread_join', thread)


class DiscordClient(Bot):
    def __init__(self, test_guild, do_first_sync: bool, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TEST_GUILD = test_guild
        self.guild_info: list[GuildInfo] = list()
        self.db_helper = DatabaseHelper(
            [FactionTable, SubalignmentTable, InfotagTable, TrustedIds],
            'guild_info.db',
            check_same_thread=False
        )
        self.db_loaded = False
        self.first_sync = False
        self.populated_forum_ids: list[int] = list()
        self.owner = None
        self.cogs_list: list[str] = list()
        self.do_first_sync = do_first_sync

    def _get_state(self, **options: Any):
        return CustomConnectionState(dispatch=self.dispatch, handlers=self._handlers, hooks=self._hooks, http=self.http, **options)

    async def get_owner(self) -> discord.User:
        if not self.owner:
            info = await self.application_info()
            self.owner = info.owner

        return self.owner

    async def sync_faction(self, faction: Faction):
        forum_channel = self.get_channel(faction.id)
        guild_info = self.get_guild_info(forum_channel.guild.id)
        subalignments = guild_info.subalignments

        failed_roles = []
        roles = []

        guild_info_roles = [r for r in guild_info.roles if r.faction.id != faction.id]
        pre_faction_roles = [r for r in guild_info.roles if r.faction.id == faction.id]
        pre_faction_roles_ids = [r.id for r in pre_faction_roles]

        roles += pre_faction_roles

        await self.add_archived_threads(forum_channel)

        for thread in forum_channel.threads:
            subalignment = None

            if thread.flags.pinned:
                continue

            if thread.id in pre_faction_roles_ids:
                continue

            for tag in thread.applied_tags:
                for subalign in subalignments:
                    if subalign.id == tag.id:
                        subalignment = subalign
                        break
                if subalignment:
                    break

            if subalignment:
                forum_tags = [str(t).lower() for t in thread.applied_tags if t.id != subalignment.id]
                roles.append(Role(thread.name, thread.id, faction, subalignment, set(forum_tags)))

            if not subalignment:
                failed_roles.append(thread)

        guild_info_roles += roles
        guild_info.roles = guild_info_roles

        self.replace_guild_info(guild_info)

        return roles, failed_roles

    async def sync_infotags(self, info_category: InfoCategory):
        forum_channel = self.get_channel(info_category.id)
        guild_info = self.get_guild_info(forum_channel.guild.id)

        failed_tags = []
        tags = []

        guild_info_tags = [r for r in guild_info.info_tags if r.id != info_category.id]
        guild_info_tags_ids = [t.id for t in guild_info_tags]

        await self.add_archived_threads(forum_channel)

        for thread in forum_channel.threads:
            if thread.flags.pinned:
                continue

            if thread.id in guild_info_tags_ids:
                continue

            tags.append(InfoTag(name=thread.name, id=thread.id, info_category=info_category))

        guild_info_tags += tags
        guild_info.info_tags = guild_info_tags

        self.replace_guild_info(guild_info)

        return tags, failed_tags

    async def sync_guild(self, guild: discord.Guild) -> dict[int, list[discord.Thread]]:
        guild_info = self.get_guild_info(guild.id)

        failed_factions = {}

        for faction in copy.deepcopy(guild_info.factions):
            _, failed_roles = await self.sync_faction(faction)
            failed_factions[faction.id] = failed_roles

        for info_cat in guild_info.info_categories:
            await self.sync_infotags(info_cat)

        return failed_factions

    def get_faction_roles(self, faction: Faction) -> list[Role]:
        forum_channel = self.get_channel(faction.id)
        guild_info = self.get_guild_info(forum_channel.guild.id)
        roles = []

        for role in guild_info.roles:
            if role.faction.id == faction.id:
                roles.append(role)

        return roles

    def get_faction_subalignments(self, faction: Faction) -> list[Subalignment]:
        forum_channel = self.get_channel(faction.id)
        guild_info = self.get_guild_info(forum_channel.guild.id)

        subalignments = []
        for tag in forum_channel.available_tags:
            for subalignment in guild_info.subalignments:
                if tag.id == subalignment.id:
                    subalignments.append(subalignment)

        return subalignments

    def get_subalignment_roles(self, subalignment: Subalignment) -> list[Role]:
        guild_info = [gi for gi in self.guild_info if subalignment in gi.subalignments][0]
        roles = []

        for role in guild_info.roles:
            if role.subalignment.id == subalignment.id:
                roles.append(role)

        return roles

    def get_subalignment_faction(self, subalignment: Subalignment) -> Faction:
        for channel in self.get_all_channels():
            if isinstance(channel, discord.ForumChannel):
                for tag in channel.available_tags:
                    if tag.id == subalignment.id:
                        guild = channel.guild
                        guild_info = self.get_guild_info(guild.id)
                        faction = [f for f in guild_info.factions if f.id == channel.id][0]

                        return faction

    async def add_archived_threads(self, forum_channel: discord.ForumChannel, force: bool = False):
        if forum_channel.id in self.populated_forum_ids and not force:
            return

        async for thread in forum_channel.archived_threads(limit=None):
            # Add to dpy's internal cache lol
            thread.guild._add_thread(thread)

        if not force:
            self.populated_forum_ids.append(forum_channel.id)

    async def start_database(self):
        await self.db_helper.startup()

    async def load_db_item(self, table_name: str) -> dict[int, str]:
        items = {}

        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                for row in await cursor.execute(f'SELECT * FROM {table_name}'):
                    channel_id: int = row['channel_id']
                    item_name: str = row['name']

                    items[channel_id] = item_name

            return items

    async def load_trusted_ids(self, guild_id: int) -> list[int]:
        trusted_ids = []
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                for row in await cursor.execute('SELECT * FROM trusted_ids WHERE guild_id = (?)', (guild_id,)):
                    trusted_id: int = row['id']
                    trusted_ids.append(trusted_id)

        return trusted_ids

    async def setup_hook(self):
        self.guild_task = self.loop.create_task(self.load_guild_info())

        if self.do_first_sync:
            if self.TEST_GUILD:
                self.tree.copy_global_to(guild=self.TEST_GUILD)
                await self.tree.sync(guild=self.TEST_GUILD)

            await self.tree.sync()
            print('Synced commands automatically (DO_FIRST_SYNC)')
        else:
            print('Not syncing commands on start (DO_FIRST_SYNC)')

    async def load_guild_info(self):
        await self.start_database()

        faction_data = await self.load_db_item('factions')
        subalignment_data = await self.load_db_item('subalignments')
        infotag_data = await self.load_db_item('infotags')

        all_data: list[tuple[dict[int, str], type[S]]] = [
            (faction_data, Faction),
            (infotag_data, InfoCategory)
        ]

        await self.wait_until_ready()

        for guild in self.guilds:
            forum_channels = [c for c in guild.channels if isinstance(c, discord.ForumChannel)]
            compiled_classes = []

            for forum_channel in forum_channels:
                for data in all_data:
                    if not data[0]:
                        continue

                    for channel_id, name in data[0].items():
                        base_class = data[1]

                        if forum_channel.id == channel_id:
                            compiled_class: SDGObject = base_class(name, channel_id)
                            compiled_classes.append(compiled_class)

            factions = [f for f in compiled_classes if isinstance(f, Faction)]
            subalignments = []

            for faction in factions:
                forum_channel = self.get_channel(faction.id)
                for forum_tag in forum_channel.available_tags:
                    for subalignment_channel, subalignment_name in subalignment_data.items():
                        if forum_tag.id == subalignment_channel:
                            subalignments.append(Subalignment(subalignment_name, subalignment_channel))

            info_categories = [i for i in compiled_classes if isinstance(i, InfoCategory)]

            trusted_ids = await self.load_trusted_ids(guild.id)

            guild_info = GuildInfo(
                guild_id=guild.id,
                factions=factions,
                subalignments=subalignments,
                roles=list(),
                info_categories=info_categories,
                info_tags=list(),
                trusted_ids=trusted_ids
            )

            self.guild_info.append(guild_info)

        self.db_loaded = True

    def replace_guild_info(self, guild_info: GuildInfo):
        try:
            self.guild_info.remove([gi for gi in self.guild_info if gi.guild_id == guild_info.guild_id][0])
        except ValueError:
            pass

        self.guild_info.append(guild_info)

    def get_guild_info(self, guild_id: int) -> GuildInfo | None:
        guild_info = [g for g in self.guild_info if g.guild_id == guild_id]
        if guild_info:
            return guild_info[0]

        return None

    async def add_item_to_db(self, item: S, table_name: str):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f'INSERT OR IGNORE INTO {table_name} VALUES (?, ?)',
                    (
                        item.id,
                        item.name
                    )
                )

            await conn.commit()

    async def delete_item_from_db(self, item: S, table_name: str):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f'DELETE FROM {table_name} WHERE channel_id = (?)',
                    (
                        item.id,
                    )
                )

            await conn.commit()

    async def modify_item_in_db(self, item: type[S], table_name: str):
        await self.delete_item_from_db(item, table_name)
        await self.add_item_to_db(item, table_name)

    async def add_trusted_id_in_db(self, trusted_id: int, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f'INSERT OR IGNORE INTO trusted_ids VALUES (?, ?)',
                    (
                        trusted_id,
                        guild_id
                    )
                )

            await conn.commit()

    async def delete_trusted_id_in_db(self, trusted_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f'DELETE FROM trusted_ids WHERE id = (?)',
                    (
                        trusted_id,
                    )
                )

            await conn.commit()


@dataclass(slots=True)
class Faction(SDGObject):
    ...


@dataclass(slots=True)
class Subalignment(SDGObject):
    ...


@dataclass(slots=True)
class InfoCategory(SDGObject):
    ...


@dataclass(slots=True)
class InfoTag(SDGObject):
    info_category: InfoCategory


@dataclass(slots=True)
class Role(SDGObject):
    faction: Faction
    subalignment: Subalignment
    forum_tags: set[str] | None = None




@dataclass(slots=True)
class GuildInfo:
    guild_id: int
    factions: list[Faction]
    subalignments: list[Subalignment]
    roles: list[Role]
    info_categories: list[InfoCategory]
    info_tags: list[InfoTag]
    trusted_ids: list[int]

    def _get_item_by_id(self, attribute: str, id_:  int) -> type[S] | None:
        items = getattr(self, attribute)
        item = [i for i in items if i.id == id_]
        if item:
            return item[0]

    def get_role(self, id_:  int) -> Role | None:
        return self._get_item_by_id('roles', id_)

    def get_faction(self, id_:  int) -> Faction | None:
        return self._get_item_by_id('factions', id_)

    def get_subalignment(self, id_:  int) -> Subalignment | None:
        return self._get_item_by_id('subalignments', id_)

    def get_info_category(self, id_:  int) -> InfoCategory | None:
        return self._get_item_by_id('info_categories', id_)

    def get_info_tag(self, id_:  int) -> InfoTag | None:
        return self._get_item_by_id('info_tags', id_)


class SDGException(Exception):
    def __init__(self, *args):
        super().__init__(*args)


class MessageTransformer(app_commands.Transformer):
    async def transform(self, interaction: Interaction, value: str, /) -> Any:
        try:
            message = await interaction.channel.fetch_message(int(value))
            return message
        except discord.DiscordException:
            raise SDGException('Invalid message ID! Message must be in the same channel as this one')


class ChoiceTransformer(app_commands.Transformer):
    async def transform(self, interaction: Interaction, value: Any, /) -> Any:
        return self.get_value(interaction, value)

    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        ...

    def get_value(self, interaction: Interaction, value: Any) -> Any:
        ...

    async def autocomplete(
            self, interaction: Interaction, value: int | float | str, /
    ) -> list[Choice[int | float | str]]:
        choices = self.get_choices(interaction)
        if not value:
            return choices[:25]

        choices_dict = {c.value: c.name for c in choices}
        matches = process.extract(str(value), choices_dict, limit=25)
        choice_matches = {m[2]: m[0] for m in matches}
        choices = [Choice(name=v, value=k) for k, v in choice_matches.items()]
        return choices


class FactionTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)
        choice_list = []
        for faction in guild_info.factions:
            choice_list.append(app_commands.Choice(name=faction.name, value=str(faction.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Faction:
        guild_info: GuildInfo = get_guild_info(interaction)
        faction = guild_info.get_faction(int(value))
        return faction


class SubalignmentTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)
        choice_list = []
        for subalignment in guild_info.subalignments:
            choice_list.append(app_commands.Choice(name=subalignment.name, value=str(subalignment.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Subalignment:
        guild_info: GuildInfo = get_guild_info(interaction)
        subalignment = guild_info.get_subalignment(int(value))
        return subalignment


class InfoCategoryTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)
        choice_list = []
        for information_category in guild_info.info_categories:
            choice_list.append(app_commands.Choice(name=information_category.name, value=str(information_category.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> InfoCategory:
        guild_info: GuildInfo = get_guild_info(interaction)
        info_category = guild_info.get_info_category(int(value))
        return info_category


class InfoTagTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)

        info_cat_id = interaction.data['options'][0]['options'][0]['value']

        if not info_cat_id or not info_cat_id.isnumeric():
            return [app_commands.Choice(name='Select valid info category first!', value='0')]

        info_cat_id = int(info_cat_id)

        choice_list = []
        for info_tag in guild_info.info_tags:
            if info_tag.info_category.id == info_cat_id:
                choice_list.append(app_commands.Choice(name=info_tag.name,value=str(info_tag.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> InfoTag:
        guild_info: GuildInfo = get_guild_info(interaction)
        info_tag = guild_info.get_info_tag(int(value))

        return info_tag


class RoleTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)
        choice_list = []
        for role in guild_info.roles:
            choice_list.append(app_commands.Choice(name=role.name, value=str(role.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Role:
        guild_info: GuildInfo = get_guild_info(interaction)
        role = guild_info.get_role(int(value))
        return role


class ForumTagTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)
        faction_id = interaction.data['options'][0]['options'][0]['value']

        if not faction_id or not faction_id.isnumeric():
            return [app_commands.Choice(name='Select faction first!', value='0')]

        faction_id = int(faction_id)

        faction_channel = interaction.guild.get_channel(faction_id)

        choice_list = []
        for tag in faction_channel.available_tags:
            if tag.id not in [s.id for s in guild_info.subalignments]:
                choice_list.append(app_commands.Choice(name=tag.name, value=str(tag.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> discord.ForumTag:
        faction_id = int(interaction.data['options'][0]['options'][0]['value'])
        faction_channel = interaction.guild.get_channel(faction_id)

        return faction_channel.get_tag(int(value))


class PollSelect(discord.ui.Select):
    def __init__(self, thread: discord.Thread, included_roles, excluded_roles, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_options: dict[int, str] = {}
        self.included_roles: list[discord.Role] = included_roles
        self.excluded_roles: list[discord.Role] = excluded_roles
        self.thread = thread

    async def callback(self, interaction: discord.Interaction):
        valid_user = not self.included_roles

        if self.included_roles:
            for role in self.included_roles:
                if interaction.user in role.members:
                    valid_user = True
                    continue

        if self.excluded_roles:
            for role in self.excluded_roles:
                if interaction.user in role.members:
                    await interaction.response.send_message('You are in the excluded roles list!', ephemeral=True)
                    return

        if not valid_user:
            await interaction.response.send_message('You aren\'t in the included roles list', ephemeral=True)
            return

        await self.thread.send(f'{interaction.user} selected {self.values[0]}')

        self.selected_options[interaction.user.id] = self.values[0]
        await interaction.response.defer()


class PollSelectButton(discord.ui.Button):
    def __init__(self, allowed_user: discord.Member, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_user = allowed_user
        self.style = discord.ButtonStyle.danger
        self.label = 'Stop poll'

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if interaction.user == self.allowed_user:
            self.disabled = True
            self.view.children[0].disabled = True
            thread = self.view.children[0].thread
            selected_options = self.view.children[0].selected_options

            counts = Counter(selected_options.values())
            counts_msg = '\n'.join(f'**"{discord.utils.escape_markdown(c[0])}"** got {c[1]} votes!' for c in
                                   counts.most_common())

            selected_msg = '\n'.join(f'<@{k}> voted {v}' for k, v in selected_options.items())

            full_msg = counts_msg + '\n\n' + selected_msg if selected_options else 'No one voted!'

            embed = create_embed(
                user=self.allowed_user,
                title='Poll ended!',
                description=full_msg
            )

            await interaction.message.edit(view=self.view)
            await thread.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            self.view.stop()
        else:
            await interaction.followup.send('Not your button!', ephemeral=True)

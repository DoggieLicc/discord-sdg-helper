from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any, TypeVar

import discord
from discord.ext.commands import Bot
from discord.state import ConnectionState

import asqlite
from utils.db_helper import *

__all__ = [
    'SDGObject',
    'DiscordClient',
    'Role',
    'Subalignment',
    'Faction',
    'GuildInfo',
    'SDGException',
    'InfoTag',
    'InfoCategory',
    'Account',
    'Achievement',
    'GuildSettings',
    'GuideItem'
]


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

AchievementsTable = BaseTable(
    name='achievements',
    columns=[
        BaseColumn(
            name='id',
            datatype='integer'
        ),
        BaseColumn(
            name='guild_id',
            datatype='integer'
        ),
        BaseColumn(
            name='name',
            datatype='string'
        ),
        BaseColumn(
            name='description',
            datatype='string'
        ),
        BaseColumn(
            name='role_id',
            datatype='integer'
        ),
        BaseColumn(
            name='subalignment_id',
            datatype='integer'
        ),
        BaseColumn(
            name='faction_id',
            datatype='integer'
        ),
    ]
)

AccountsTable = BaseTable(
    name='accounts',
    columns=[
        BaseColumn(
            name='user_id',
            datatype='integer'
        ),
        BaseColumn(
            name='guild_id',
            datatype='integer'
        ),
        BaseColumn(
            name='num_wins',
            datatype='integer'
        ),
        BaseColumn(
            name='num_loses',
            datatype='integer'
        ),
        BaseColumn(
            name='num_draws',
            datatype='integer'
        ),
        BaseColumn(
            name='blessed_scrolls',
            datatype='string'
        ),
        BaseColumn(
            name='cursed_scrolls',
            datatype='string'
        ),
        BaseColumn(
            name='accomplished_achievements',
            datatype='string'
        ),
    ]
)

GuildSettingsTable = BaseTable(
    name='guild_settings',
    columns=[
        BaseColumn(
            name='guild_id',
            datatype='integer'
        ),
        BaseColumn(
            name='max_scrolls',
            datatype='integer'
        ),
        BaseColumn(
            name='roles_are_scrollable',
            datatype='boolean'
        ),
        BaseColumn(
            name='factions_are_scrollable',
            datatype='boolean'
        ),
        BaseColumn(
            name='subalignments_are_scrollable',
            datatype='boolean'
        ),
        BaseColumn(
            name='role_scroll_multiplier',
            datatype='integer'
        ),
        BaseColumn(
            name='subalignment_scroll_multiplier',
            datatype='integer'
        ),
        BaseColumn(
            name='faction_scroll_multiplier',
            datatype='integer'
        ),
        BaseColumn(
            name='accounts_creatable',
            datatype='boolean'
        )
    ]
)

USER_VERSION = 0


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
    def __init__(self, test_guild, do_first_sync: bool, guide_channel_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_guild = test_guild
        self.guild_info: list[GuildInfo] = []
        self.guild_task = None
        self.db_helper = DatabaseHelper(
            [
                FactionTable,
                SubalignmentTable,
                InfotagTable,
                TrustedIds,
                AccountsTable,
                AchievementsTable,
                GuildSettingsTable
            ],
            USER_VERSION,
            'guild_info.db',
            check_same_thread=False
        )
        self.db_loaded = False
        self.first_sync = False
        self.populated_forum_ids: list[int] = []
        self.owner = None
        self.cogs_list: list[str] = []
        self.do_first_sync = do_first_sync
        self.guide_channel_id = int(guide_channel_id) if guide_channel_id else None
        self.guides = []

    def _get_state(self, **options: Any):
        return CustomConnectionState(
            dispatch=self.dispatch,
            handlers=self._handlers,
            hooks=self._hooks,
            http=self.http, **options
        )

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

    def get_subalignment_faction(self, subalignment: Subalignment) -> Faction | None:
        for channel in self.get_all_channels():
            if isinstance(channel, discord.ForumChannel):
                for tag in channel.available_tags:
                    if tag.id == subalignment.id:
                        guild = channel.guild
                        guild_info = self.get_guild_info(guild.id)
                        faction = [f for f in guild_info.factions if f.id == channel.id][0]

                        return faction

        return None

    async def add_archived_threads(self, forum_channel: discord.ForumChannel, force: bool = False):
        if forum_channel.id in self.populated_forum_ids and not force:
            return None

        async for thread in forum_channel.archived_threads(limit=None):
            # Add to dpy's internal cache lol
            thread.guild._add_thread(thread)

        if not force:
            self.populated_forum_ids.append(forum_channel.id)

    async def start_database(self):
        await self.db_helper.startup()

    async def get_db_version(self) -> int:
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            pragma = await conn.execute('PRAGMA user_version')
            pragma = await pragma.fetchall()
            return pragma[0][0]

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

    async def load_achievements(
            self,
            guild_info: GuildInfo
    ) -> list[Achievement]:
        achievements = []
        roles = guild_info.roles
        subalignments = guild_info.subalignments
        factions = guild_info.factions
        guild_id = guild_info.guild_id
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                for row in await cursor.execute('SELECT * FROM achievements WHERE guild_id = (?)', (guild_id,)):
                    achievement_id = row['id']
                    achievement_name = row['name']
                    achievement_description = row['description']
                    achievement_role_id = row['role_id']
                    achievement_subalignment_id = row['subalignment_id']
                    achievement_faction_id = row['faction_id']

                    achievement_role = [r for r in roles if r.id == achievement_role_id]
                    achievement_subalignment = [s for s in subalignments if s.id == achievement_subalignment_id]
                    achievement_faction = [f for f in factions if f.id == achievement_faction_id]

                    achievements.append(
                        Achievement(
                            id=achievement_id,
                            name=achievement_name,
                            description=achievement_description,
                            role=achievement_role[0] if achievement_role else None,
                            subalignment=achievement_subalignment[0] if achievement_subalignment else None,
                            faction=achievement_faction[0] if achievement_faction else None
                        )
                    )

        return achievements

    async def load_accounts(self, guild_info: GuildInfo) -> list[Account]:
        accounts = []
        rsf_list = guild_info.roles + guild_info.subalignments + guild_info.factions

        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                for row in await cursor.execute('SELECT * FROM accounts WHERE guild_id = (?)', (guild_info.guild_id,)):
                    account_id = row['user_id']
                    account_wins = row['num_wins']
                    account_losses = row['num_loses']
                    account_draws = row['num_draws']
                    account_blessed_scrolls = str(row['blessed_scrolls']).split(',')
                    account_cursed_scrolls = str(row['cursed_scrolls']).split(',')
                    account_achievements = str(row['accomplished_achievements']).split(',')

                    blessed_scrolls = []
                    for blessed_scroll in account_blessed_scrolls:
                        if blessed_scroll:
                            scroll_id = int(blessed_scroll)
                            rsf = [r for r in rsf_list if r.id == scroll_id]
                            if rsf:
                                blessed_scrolls.append(rsf[0])

                    cursed_scrolls = []
                    for cursed_scroll in account_cursed_scrolls:
                        if cursed_scroll:
                            scroll_id = int(cursed_scroll)
                            role = [r for r in guild_info.roles if r.id == scroll_id]
                            if role:
                                cursed_scrolls.append(role[0])

                    achievements = []
                    for achievement in account_achievements:
                        if achievement:
                            achievement_id = int(achievement)
                            ach = [a for a in guild_info.achievements if a.id == achievement_id]
                            if ach:
                                achievements.append(ach[0])

                    accounts.append(
                        Account(
                            id=account_id,
                            num_wins=account_wins,
                            num_loses=account_losses,
                            num_draws=account_draws,
                            blessed_scrolls=blessed_scrolls,
                            cursed_scrolls=cursed_scrolls,
                            accomplished_achievements=achievements
                        )
                    )

        return accounts

    async def load_settings(self, guild_id: int) -> GuildSettings:
        settings = None

        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                for row in await cursor.execute('SELECT * FROM guild_settings WHERE guild_id = (?)', (guild_id,)):
                    settings = GuildSettings(
                        max_scrolls=row['max_scrolls'],
                        roles_are_scrollable=bool(row['roles_are_scrollable']),
                        subalignments_are_scrollable=bool(row['subalignments_are_scrollable']),
                        factions_are_scrollable=bool(row['factions_are_scrollable']),
                        role_scroll_multiplier=row['role_scroll_multiplier'],
                        subalignment_scroll_multiplier=row['subalignment_scroll_multiplier'],
                        faction_scroll_multiplier=row['faction_scroll_multiplier'],
                        accounts_creatable=bool(row['accounts_creatable'])
                )

        if not settings:
            settings = GuildSettings(
                max_scrolls=5,
                roles_are_scrollable=True,
                subalignments_are_scrollable=True,
                factions_are_scrollable=True,
                role_scroll_multiplier=10,
                subalignment_scroll_multiplier=10,
                faction_scroll_multiplier=10,
                accounts_creatable=True
            )

            await self.add_settings_to_db(settings, guild_id)

        return settings

    async def load_guides(self):
        guides = []
        if self.guide_channel_id is None:
            return

        guide_channel = self.get_channel(self.guide_channel_id)

        if guide_channel is None:
            logging.warning('Unable to get channel from %s', self.guide_channel_id)
            return

        if not isinstance(guide_channel, discord.ForumChannel):
            logging.warning('%s is not a forum channel', guide_channel.name)
            return

        await self.add_archived_threads(guide_channel)

        for thread in guide_channel.threads:
            pages = []
            async for message in thread.history(oldest_first=True):
                if message.content:
                    pages.append(message.content)

            if pages:
                guides.append(GuideItem(thread.name, pages))

        self.guides = guides

    async def setup_hook(self):
        self.guild_task = self.loop.create_task(self.load_guild_info())

        if self.do_first_sync:
            if self.test_guild:
                self.tree.copy_global_to(guild=self.test_guild)
                await self.tree.sync(guild=self.test_guild)

            await self.tree.sync()
            logging.info('Synced commands automatically (DO_FIRST_SYNC)')
        else:
            logging.info('Not syncing commands on start (DO_FIRST_SYNC)')

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
            guild_settings = await self.load_settings(guild.id)

            guild_info = GuildInfo(
                guild_id=guild.id,
                factions=factions,
                subalignments=subalignments,
                roles=[],
                info_categories=info_categories,
                info_tags=[],
                trusted_ids=trusted_ids,
                achievements=[],
                accounts=[],
                guild_settings=guild_settings
            )

            self.guild_info.append(guild_info)

        self.db_loaded = True

    async def post_guild_info_load(self):
        for guild_info in self.guild_info:
            guild_info.achievements = await self.load_achievements(guild_info)
            guild_info.accounts = await self.load_accounts(guild_info)

            self.replace_guild_info(guild_info)

    def replace_guild_info(self, guild_info: GuildInfo) -> None:
        try:
            self.guild_info.remove([gi for gi in self.guild_info if gi.guild_id == guild_info.guild_id][0])
        except ValueError:
            pass

        self.guild_info.append(guild_info)

    def get_guild_info(self, guild_id: int) -> GuildInfo | None:
        for guild_info in self.guild_info:
            if guild_info.guild_id == guild_id:
                return guild_info

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

    async def modify_item_in_db(self, item: S, table_name: str):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f'UPDATE {table_name} SET name = ? WHERE channel_id = ?',
                    (
                        item.name,
                        item.id
                    )
                )
            await conn.commit()

    async def add_trusted_id_in_db(self, trusted_id: int, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'INSERT OR IGNORE INTO trusted_ids VALUES (?, ?)',
                    (
                        trusted_id,
                        guild_id
                    )
                )

            await conn.commit()

    async def delete_trusted_id_in_db(self, trusted_id: int, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'DELETE FROM trusted_ids WHERE id = (?) AND guild_id = (?)',
                    (
                        trusted_id,
                        guild_id
                    )
                )

            await conn.commit()

    async def add_achievement_to_db(self, achievement: Achievement, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'INSERT OR IGNORE INTO achievements VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (
                        achievement.id,
                        guild_id,
                        achievement.name,
                        achievement.description,
                        achievement.role.id if achievement.role else None,
                        achievement.subalignment.id if achievement.subalignment else None,
                        achievement.faction.id if achievement.faction else None
                    )
                )

            await conn.commit()

    async def delete_achievement_from_db(self, achievement: Achievement, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'DELETE FROM achievements WHERE id = (?) AND guild_id = (?)',
                    (
                        achievement.id,
                        guild_id
                    )
                )

            await conn.commit()

    async def modify_achievement_in_db(self, achievement: Achievement, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'UPDATE achievements SET '
                    'name = ?, '
                    'description = ?, '
                    'role_id = ?, '
                    'subalignment_id = ?, '
                    'faction_id = ? '
                    'WHERE id = ? AND guild_id = ?',
                    (
                        achievement.name,
                        achievement.description,
                        achievement.role.id if achievement.role else None,
                        achievement.subalignment.id if achievement.subalignment else None,
                        achievement.faction.id if achievement.faction else None,
                        achievement.id,
                        guild_id
                    )
                )
            await conn.commit()

    async def add_account_to_db(self, account: Account, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'INSERT OR IGNORE INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (
                        account.id,
                        guild_id,
                        account.num_wins,
                        account.num_loses,
                        account.num_draws,
                        ','.join(str(s.id) for s in account.blessed_scrolls),
                        ','.join(str(s.id) for s in account.cursed_scrolls),
                        ','.join(str(s.id) for s in account.accomplished_achievements),
                    )
                )

            await conn.commit()

    async def delete_account_from_db(self, account: Account, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'DELETE FROM accounts WHERE user_id = (?) AND guild_id = (?)',
                    (
                        account.id,
                        guild_id
                    )
                )

            await conn.commit()

    async def modify_account_in_db(self, account: Account, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'UPDATE accounts SET '
                    'num_wins = ?, '
                    'num_loses = ?, '
                    'num_draws = ?, '
                    'blessed_scrolls = ?, '
                    'cursed_scrolls = ?, '
                    'accomplished_achievements = ? '
                    'WHERE user_id = ? AND guild_id = ?',
                    (
                        account.num_wins,
                        account.num_loses,
                        account.num_draws,
                        ','.join(str(s.id) for s in account.blessed_scrolls),
                        ','.join(str(s.id) for s in account.cursed_scrolls),
                        ','.join(str(s.id) for s in account.accomplished_achievements),
                        account.id,
                        guild_id
                    )
                )
            await conn.commit()

    async def add_settings_to_db(self, settings: GuildSettings, guild_id: int) -> None:
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'INSERT OR IGNORE INTO guild_settings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (
                        guild_id,
                        settings.max_scrolls,
                        settings.roles_are_scrollable,
                        settings.factions_are_scrollable,
                        settings.subalignments_are_scrollable,
                        settings.role_scroll_multiplier,
                        settings.subalignment_scroll_multiplier,
                        settings.faction_scroll_multiplier,
                        settings.accounts_creatable
                    )
                )

            await conn.commit()

    async def delete_settings_from_db(self, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'DELETE FROM guild_settings WHERE guild_id = (?)',
                    (
                        guild_id
                    )
                )

            await conn.commit()

    async def modify_settings_in_db(self, settings: GuildSettings, guild_id: int):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    'UPDATE guild_settings SET '
                    'max_scrolls = ?, '
                    'roles_are_scrollable = ?, '
                    'factions_are_scrollable = ?, '
                    'subalignments_are_scrollable = ?, '
                    'role_scroll_multiplier = ?, '
                    'subalignment_scroll_multiplier = ?, '
                    'faction_scroll_multiplier = ?, '
                    'accounts_creatable = ? '
                    'WHERE guild_id = ?',
                    (
                        settings.max_scrolls,
                        settings.roles_are_scrollable,
                        settings.factions_are_scrollable,
                        settings.subalignments_are_scrollable,
                        settings.role_scroll_multiplier,
                        settings.subalignment_scroll_multiplier,
                        settings.faction_scroll_multiplier,
                        settings.accounts_creatable,
                        guild_id
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
class Achievement:
    id: int
    name: str
    description: str
    role: Role | None = None
    subalignment: Subalignment | None = None
    faction: Faction | None = None


@dataclass(slots=True)
class Account:
    id: int
    num_wins: int
    num_loses: int
    num_draws: int
    blessed_scrolls: list[Role | Subalignment | Faction]
    cursed_scrolls: list[Role]
    accomplished_achievements: list[Achievement]


@dataclass(slots=True)
class GuildSettings:
    max_scrolls: int
    roles_are_scrollable: bool
    subalignments_are_scrollable: bool
    factions_are_scrollable: bool
    role_scroll_multiplier: int
    subalignment_scroll_multiplier: int
    faction_scroll_multiplier: int
    accounts_creatable: bool


@dataclass(slots=True)
class GuildInfo:
    guild_id: int
    factions: list[Faction]
    subalignments: list[Subalignment]
    roles: list[Role]
    info_categories: list[InfoCategory]
    info_tags: list[InfoTag]
    trusted_ids: list[int]
    achievements: list[Achievement]
    accounts: list[Account]
    guild_settings: GuildSettings

    def _get_item_by_id(self, attribute: str, id_:  int) -> type[S] | None:
        items = getattr(self, attribute)
        for item in items:
            if item.id == id_:
                return item

        return None

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

    def get_achievement(self, id_: int) -> Achievement | None:
        return self._get_item_by_id('achievements', id_)

    def get_account(self, id_: int) -> Account | None:
        return self._get_item_by_id('accounts', id_)


@dataclass(slots=True)
class GuideItem:
    name: str
    pages: list[str]

class SDGException(Exception):
    def __init__(self, *args):
        super().__init__(*args)

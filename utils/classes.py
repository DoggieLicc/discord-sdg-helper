import io
import textwrap
import discord
import asqlite

from dataclasses import dataclass
from collections import Counter
from contextlib import redirect_stdout
from thefuzz import process
from typing import Any

from discord import app_commands, Interaction
from discord.app_commands import Choice

from utils.funcs import get_guild_info, create_embed, cleanup_code, format_error, str_to_file
from utils.db_helper import DatabaseHelper, BaseTable, BaseColumn


@dataclass
class SDGObject:
    name: str
    id: int


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


class DiscordClient(discord.Client):
    def __init__(self, test_guild, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = app_commands.CommandTree(self)
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
                for row in await cursor.execute(f'SELECT * FROM trusted_ids WHERE guild_id = (?)', (guild_id,)):
                    trusted_id: int = row['id']
                    trusted_ids.append(trusted_id)

        return trusted_ids

    async def setup_hook(self):
        self.guild_task = self.loop.create_task(self.load_guild_info())

        if self.TEST_GUILD:
            #  self.tree.copy_global_to(guild=self.TEST_GUILD)
            await self.tree.sync(guild=self.TEST_GUILD)

        await self.tree.sync()

    async def load_guild_info(self):
        await self.start_database()

        faction_data = await self.load_db_item('factions')
        subalignment_data = await self.load_db_item('subalignments')
        infotag_data = await self.load_db_item('infotags')

        all_data: list[tuple[dict[int, str], type[SDGObject]]] = [
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

    async def add_item_to_db(self, item: type[SDGObject], table_name: str):
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

    async def delete_item_from_db(self, item: type[SDGObject], table_name: str):
        async with asqlite.connect('guild_info.db', check_same_thread=False) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f'DELETE FROM {table_name} WHERE channel_id = (?)',
                    (
                        item.id,
                    )
                )

            await conn.commit()

    async def modify_item_in_db(self, item: type[SDGObject], table_name: str):
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

@dataclass
class Faction(SDGObject):
    ...


@dataclass
class Subalignment(SDGObject):
    ...


@dataclass
class InfoCategory(SDGObject):
    ...


@dataclass
class InfoTag(SDGObject):
    ...

@dataclass
class Role(SDGObject):
    faction: Faction
    subalignment: Subalignment
    forum_tags: set[str] | None = None


@dataclass
class GuildInfo:
    guild_id: int
    factions: list[Faction]
    subalignments: list[Subalignment]
    roles: list[Role]
    info_categories: list[InfoCategory]
    info_tags: list[InfoTag]
    trusted_ids: list[int]


class SDGException(Exception):
    def __init__(self, *args):
        super().__init__(*args)


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
        faction = [f for f in guild_info.factions if f.id == int(value)][0]
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
        subalignment = [f for f in guild_info.subalignments if f.id == int(value)][0]
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
        info_category = [f for f in guild_info.info_categories if f.id == int(value)][0]
        return info_category


class InfoTagTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)

        info_cat_id = interaction.data['options'][0]['options'][0]['value']

        if not info_cat_id or not info_cat_id.isnumeric():
            return [app_commands.Choice(name='Select valid info category first!', value='0')]

        info_cat_id = int(info_cat_id)

        info_cat_channel = interaction.guild.get_channel(info_cat_id)

        choice_list = []
        for thread in info_cat_channel.threads:
            info_tag = [i for i in guild_info.info_tags if i.id == thread.id]
            if info_tag:
                choice_list.append(app_commands.Choice(
                    name=info_tag[0].name,
                    value=str(info_tag[0].id)
                ))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> InfoTag:
        guild_info: GuildInfo = get_guild_info(interaction)
        info_tag = [i for i in guild_info.info_tags if int(value) == i.id][0]

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
        role = [f for f in guild_info.roles if f.id == int(value)][0]
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


class DevEval(discord.ui.Modal, title='Dev Eval'):
    code = discord.ui.TextInput(label='Code', style=discord.TextStyle.paragraph)

    async def eval_code(self, interaction: discord.Interaction) -> discord.Embed | discord.File:
        env = {
            'client': interaction.client,
            'interaction': interaction,
            'channel': interaction.channel,
            'user': interaction.user,
            'guild': interaction.guild,
        }

        env.update(globals())
        code = cleanup_code(self.code.value)
        to_compile = f'async def func():\n{textwrap.indent(code, "  ")}'
        stdout = io.StringIO()

        try:
            exec(to_compile, env)
        except Exception as e:
            embed = format_error(interaction.user, e)
            return embed

        func = env['func']

        try:
            with redirect_stdout(stdout):
                ret = await func()

        except Exception as e:
            embed = format_error(interaction.user, e)
            return embed

        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    if len(value) < 4000:
                        embed = create_embed(
                            interaction.user,
                            title="Exec result:",
                            description=f'```py\n{value}\n```'
                        )

                        return embed
                    else:
                        return str_to_file(value)

                else:
                    embed = create_embed(interaction.user, title="Eval code executed!")
                    return embed

            else:
                if isinstance(ret, discord.Embed):
                    return ret

                if isinstance(ret, discord.File):
                    return ret

                if isinstance(ret, discord.Asset):
                    embed = create_embed(interaction.user, image=ret)
                    return embed

                else:
                    ret = repr(ret)

                    if len(ret) < 4000:
                        embed = create_embed(
                            interaction.user,
                            title="Exec result:",
                            description=f'```py\n{ret}\n```'
                        )

                    else:
                        return str_to_file(ret)

                    return embed

    async def on_submit(self, interaction: discord.Interaction):
        ret = await self.eval_code(interaction)
        code = cleanup_code(self.code.value)
        formatted_code = '```py\n' + code + '\n```'

        if isinstance(ret, discord.Embed):
            await interaction.response.send_message(formatted_code, embed=ret)

        if isinstance(ret, discord.File):
            await interaction.response.send_message(formatted_code, files=[ret])


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
    def __init__(self, allowed_user: discord.Member,*args, **kwargs):
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

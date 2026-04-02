import io
import csv
import re

from datetime import datetime
from typing import TYPE_CHECKING, TypeVar

import discord
from discord import Embed, User, Member

from utils.classes import Role, Subalignment, Faction, InfoTag
from utils.filter import FactionedRole, get_flex_faction

if TYPE_CHECKING:
    import utils
    OptionalGuildInfo = None | utils.GuildInfo


__all__ = [
    'get_guild_info',
    'create_embed',
    'user_friendly_dt',
    'str_to_file',
    'mod_check',
    'admin_check',
    'get_interaction_parameter',
    'get_or_fetch_channel',
    'get_valid_roles',
    'generate_gamestate_csv',
    'get_valid_emoji',
    'get_faction_emote',
    'format_generated_roles',
    'message_text_to_roles',
    'role_or_infotag_to_embed'
]

T = TypeVar('T')

def get_guild_info(interaction: discord.Interaction) -> 'OptionalGuildInfo':
    for g in interaction.client.guild_info:
        if g.guild_id == interaction.guild_id:
            return g

    return None


def create_embed(user: User | Member | None, *, image=None, thumbnail=None, **kwargs) -> Embed:
    """Makes a discord.Embed with options for image and thumbnail URLs, and adds a footer with author name"""

    kwargs['color'] = kwargs.get('color', discord.Color.green())

    embed = discord.Embed(**kwargs)
    embed.set_image(url=fix_url(image))
    embed.set_thumbnail(url=fix_url(thumbnail))

    if user:
        embed.set_footer(text=f'Command sent by {user}', icon_url=fix_url(user.display_avatar))

    return embed


def user_friendly_dt(dt: datetime) -> str:
    """Format a datetime as "short_date (relative_date)" """
    return discord.utils.format_dt(dt, style='f') + f' ({discord.utils.format_dt(dt, style="R")})'


def str_to_file(string: str, *, filename: str = 'file.txt', encoding: str = 'utf-8') -> discord.File:
    """Converts a given str to a discord.File ready for sending"""

    _bytes = bytes(string, encoding)
    buffer = io.BytesIO(_bytes)
    file = discord.File(buffer, filename=filename)
    return file


def fix_url(url):
    if not url:
        return None

    return str(url)


async def mod_check(interaction: discord.Interaction) -> bool:
    guild_info = get_guild_info(interaction)

    owner = await interaction.client.get_owner()

    if interaction.user == owner:
        return True

    if interaction.user.guild_permissions.manage_channels:
        return True

    if interaction.user.id in guild_info.trusted_ids:
        return True

    for role in interaction.user.roles:
        if role.id in guild_info.trusted_ids:
            return True

    return False


async def admin_check(interaction: discord.Interaction) -> bool:
    owner = await interaction.client.get_owner()

    if interaction.user == owner:
        return True

    if interaction.user.guild_permissions.administrator:
        return True

    return False


def get_interaction_parameter(interaction: discord.Interaction, name: str, default=None) -> str:
    value = None
    try:
        options = interaction.data.get('options')
        value = discord.utils.find(lambda o: o['name'] == name, options)
        if not value:
            options = options[0]['options']
            value = discord.utils.find(lambda o: o['name'] == name, options)
    except (TypeError, KeyError):
        pass

    if not value:
        return default

    return value['value']


async def get_or_fetch_channel(guild: discord.Guild, channel_id: int):
    return guild.get_channel_or_thread(channel_id) or await guild.fetch_channel(channel_id)


async def get_valid_roles(
        include_tags: str,
        exclude_tags: str,
        guild_info: 'utils.GuildInfo',
        faction: 'utils.Faction',
        subalignment: 'utils.Subalignment',
        guild: discord.Guild
) -> list['utils.Role']:
    valid_roles = []
    split_include_tags = include_tags.split()
    split_exclude_tags = exclude_tags.split()

    for role in guild_info.roles:
        if faction and role.faction.id != faction.id:
            continue

        if subalignment and role.subalignment.id != subalignment.id:
            continue

        role_thread = await get_or_fetch_channel(guild, role.id)
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

    return valid_roles


def generate_gamestate_csv(
        users: list[discord.User],
        roles: list['utils.FactionedRole'] | None
) -> discord.File:
    file_buffer = io.StringIO()
    with file_buffer as csvfile:
        fields = ['#', 'Player', 'Role', 'Status Effects']
        for i in range(5):
            fields.append(f'D{i+1}')
            fields.append(f'N{i+1}')
        csvwriter = csv.DictWriter(csvfile, fields)
        csvwriter.writeheader()

        for i, user in enumerate(users):
            role = roles[i] if roles else None
            role_str = ''
            marks_str = ''

            if role:
                role_str += role.role.name
                if role.flex_faction:
                    role_str += f' ({role.faction_name})'

                marks_str = ', '.join(role.marks)

            user_dict = {
                '#': i+1,
                'Player': str(user),
                'Role': f'"{role_str}"' if role_str else None,
                'Status Effects': f'"{marks_str}"' if marks_str else None
            }
            csvwriter.writerow(user_dict)

        file_buffer.seek(0)
        return discord.File(file_buffer, 'gamestate.csv')

def get_valid_emoji(emoji: T, client: discord.Client) -> discord.Emoji | T | None:
    if emoji is None:
        return None

    if isinstance(emoji, str):
        return None

    if emoji.is_unicode_emoji():
        return emoji

    full_emoji = client.get_emoji(emoji.id)

    if not full_emoji:
        return None

    return full_emoji.available


async def get_faction_emote(
        faction: str | Role | Subalignment | Faction,
        interaction: discord.Interaction
    ) -> discord.Emoji | str | None:
    if isinstance(faction, Subalignment):
        subs_faction = interaction.client.get_subalignment_faction(faction)
        if subs_faction:
            forum_channel = await get_or_fetch_channel(interaction.guild, subs_faction.id)
            sub_tag = forum_channel.get_tag(faction.id)
            if sub_tag and sub_tag.emoji:
                return sub_tag.emoji
        faction = faction.name

    if isinstance(faction, Role):
        forum_channel = await get_or_fetch_channel(interaction.guild, faction.faction.id)
        sub_tag = forum_channel.get_tag(faction.subalignment.id)
        if sub_tag and sub_tag.emoji:
            return sub_tag.emoji
        faction = faction.name

    if isinstance(faction, str) or isinstance(faction, Faction):
        f_name = faction
        if isinstance(faction, Faction):
            f_name = faction.name

        m_emotes = [e for e in interaction.guild.emojis if e.name.lower() == f_name.lower()]
        if m_emotes:
            return m_emotes[0]

    if isinstance(faction, Faction):
        fac_subs = interaction.client.get_faction_subalignments(faction)
        forum_channel = await get_or_fetch_channel(interaction.guild, faction.id)
        for fac_sub in fac_subs:
            sub_tag = forum_channel.get_tag(fac_sub.id)
            if sub_tag and sub_tag.emoji:
                return sub_tag.emoji
        faction = faction.name

    m_emotes = [e for e in interaction.guild.emojis if faction.lower() in e.name.lower()]
    if m_emotes:
        return m_emotes[0]

    return None

async def format_generated_roles(roles: list, interaction: discord.Interaction) -> str:
    roles_str_list = []

    for role in roles:
        og_role = role.role
        role_emoji = await get_faction_emote(og_role, interaction) or ''
        fac_str = ''
        p_fac_str = ''
        m_str = ''
        if role.flex_faction:
            ff_name = role.faction_name
            fac_str = f'({ff_name}) '
            fac_emote = await get_faction_emote(role.flex_faction, interaction)
            p_fac_str = f'{fac_emote} ' if fac_emote else ''

        if role.marks:
            m_str = '{' + ', '.join(role.marks) + '} '

        roles_str_list.append(f'{p_fac_str}{role_emoji} {og_role.name} {fac_str}{m_str}[<#{og_role.id}>]')

    return '\n'.join(roles_str_list)

def message_text_to_roles(msg_text: str, guild_info: 'utils.GuildInfo') -> list[FactionedRole]:
    generated_roles = []

    for line in msg_text.splitlines():
        channel_match = re.search(r'<#(\d+)>', line)
        if not channel_match:
            continue

        channel_id = int(channel_match.group(1))
        channel_role = guild_info.get_role(channel_id)

        if not channel_role:
            continue

        marks = []
        marks_m = re.findall(r'{(.*?)}', line)
        f_faction = None

        if marks_m:
            marks_m_s = marks_m[0]
            marks = [m.strip() for m in marks_m_s.split(',')]

        f_faction_m = re.findall(r'\((.*?)\)', line)
        if f_faction_m:
            f_faction_m = f_faction_m[0]
            f_faction = get_flex_faction(f_faction_m, guild_info)

        generated_roles.append(FactionedRole(channel_role, f_faction, marks))

    return generated_roles

async def role_or_infotag_to_embed(interaction: discord.Integration, keyword) -> discord.Embed:
    thread_channel = await get_or_fetch_channel(interaction.guild, keyword.id)
    starter_message = thread_channel.starter_message or await thread_channel.fetch_message(thread_channel.id)
    kw_str = starter_message.content
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

    header = f'Post: {thread_channel.mention}{reaction_str}\n\n'
    title = keyword.name
    if isinstance(keyword, InfoTag):
        title = f'Infotag {keyword.info_category.name}:{keyword.name}'

    embed = create_embed(
        interaction.user,
        title=title,
        thumbnail=message_image,
        description=header + kw_str[:4000]
    )

    return embed

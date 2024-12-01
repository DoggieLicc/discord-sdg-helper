import io
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import Embed, User, Member

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
    'get_valid_roles'
]


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


def get_valid_roles(
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

        role_thread = guild.get_channel_or_thread(role.id)
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

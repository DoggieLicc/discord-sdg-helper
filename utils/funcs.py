import io
import discord

from discord import Embed, User, Member
from datetime import datetime


__all__ = [
    'get_guild_info',
    'create_embed',
    'user_friendly_dt',
    'str_to_file',
    'mod_check',
    'admin_check',
    'get_interaction_parameter'
]


def get_guild_info(interaction: discord.Interaction):
    for g in interaction.client.guild_info:
        if g.guild_id == interaction.guild_id:
            return g


def create_embed(user: User | Member | None, *, image=None, thumbnail=None, **kwargs) -> Embed:
    """Makes a discord.Embed with options for image and thumbnail URLs, and adds a footer with author name"""

    kwargs['color'] = kwargs.get('color', discord.Color.green())

    embed = discord.Embed(**kwargs)
    embed.set_image(url=fix_url(image))
    embed.set_thumbnail(url=fix_url(thumbnail))

    if user:
        embed.set_footer(text=f'Command sent by {user}', icon_url=fix_url(user.display_avatar))

    return embed


def user_friendly_dt(dt: datetime):
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


def get_interaction_parameter(interaction: discord.Interaction, name: str, default=None):
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


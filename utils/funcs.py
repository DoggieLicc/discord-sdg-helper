import io
import traceback
import discord

from discord import Embed, User, Member
from datetime import datetime


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


def cleanup_code(content):
    if content.startswith('```') and content.endswith('```'):
        return '\n'.join(content.split('\n')[1:-1])
    return content.strip('` \n')


def format_error(author: discord.User, error: Exception) -> discord.Embed:
    error_lines = traceback.format_exception(type(error), error, error.__traceback__)
    embed = create_embed(
        author,
        title="Error!",
        description=f'```py\n{"".join(error_lines)}\n```',
        color=discord.Color.red()
    )

    return embed



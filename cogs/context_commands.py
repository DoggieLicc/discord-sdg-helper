import discord

from discord import app_commands
from discord.ext import commands
from utils import SDGException, generate_rolelist_roles

import utils
import re


class ContextMenuCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.generate_rolelist_cmd = app_commands.ContextMenu(
            name='Generate Rolelist Roles',
            callback=self.generate_rolelist
        )

        self.client.tree.add_command(self.generate_rolelist_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command(self.generate_rolelist_cmd.name, type=self.generate_rolelist_cmd.type)

    @app_commands.guild_only()
    async def generate_rolelist(
            self,
            interaction: discord.Interaction,
            message: discord.Message
    ):
        """Generate rolelist roles"""

        while True:
            if message.author == self.client.user and message.reference:
                message = message.reference.cached_message or message.reference.resolved or await interaction.channel.fetch_message(message.reference.message_id)
            else:
                break

        channel_mentions = message.channel_mentions
        cleaned_content = message.content
        guild_info = utils.get_guild_info(interaction)

        channel_link_regex = (r"https?:\/\/(?:(?:ptb|canary)\.)?discord(?:app)?\.com\/channels\/(?P<guild_id>[0-9]{"
                              r"15,19})\/(?P<channel_id>[0-9]{15,19})?")

        for channel in channel_mentions:
            if isinstance(channel, discord.ForumChannel):
                faction = [f for f in guild_info.factions if f.id == channel.id]
                if not faction:
                    raise SDGException('Channel isn\'t assigned to a faction!')
                cleaned_content = cleaned_content.replace(channel.mention, f'${faction[0].name}')
            else:
                role = [r for r in guild_info.roles if r.id == channel.id]
                if not role:
                    raise SDGException('Thread isn\'t a assigned to a role!')
                cleaned_content = cleaned_content.replace(channel.mention, f'%{role[0].name}')

        for match in re.finditer(channel_link_regex, cleaned_content):
            guild_id = int(match.group('guild_id'))
            channel_id = int(match.group('channel_id'))

            match_str = match.group()

            if guild_id != interaction.guild_id:
                continue

            faction = [f for f in guild_info.factions if f.id == channel_id]

            if faction:
                cleaned_content = cleaned_content.replace(match_str, f'${faction[0].name}')
                continue

            role = [r for r in guild_info.roles if r.id == channel_id]

            if role:
                cleaned_content = cleaned_content.replace(match_str, f'%{role[0].name}')

        rolelist_info = utils.get_rolelist(cleaned_content, all_roles=guild_info.roles)

        if len(rolelist_info.slots) > 30:
            raise SDGException('Too many slots! Max number of slots is 30')

        roles = generate_rolelist_roles(rolelist_info, guild_info.roles)

        roles_str_list = []

        for role in roles:
            faction_channel = self.client.get_channel(role.faction.id)
            sub_tag = faction_channel.get_tag(role.subalignment.id)
            roles_str_list.append(f'{sub_tag.emoji} {role.name} (<#{role.id}>)')

        roles_str = '\n'.join(roles_str_list)

        if not roles_str:
            raise SDGException('No slots specified in message!')

        await interaction.response.send_message(roles_str)


async def setup(bot):
    await bot.add_cog(ContextMenuCog(bot))

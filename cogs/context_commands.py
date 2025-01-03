import re
import time

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button

import utils
from utils import SDGException, generate_rolelist_roles


class RegenerateView(utils.CustomView):
    def __init__(self, owner: discord.User, rolelist, roles: list[utils.Role]):
        self.rolelist = rolelist
        self.roles = roles
        self.message = None
        super().__init__(owner)

    @discord.ui.button(label='Regenerate Roles', style=discord.ButtonStyle.blurple)
    async def regenerate(self, interaction: discord.Interaction, _: Button):
        start_time = time.time()
        roles = generate_rolelist_roles(self.rolelist, self.roles)
        end_time = time.time()
        elapsed_time = end_time - start_time
        elapsed_time_str = f'\n\nGenerated roles in {elapsed_time:4f} seconds'

        roles_str_list = []

        for role in roles:
            faction_channel = interaction.client.get_channel(role.faction.id)
            sub_tag = faction_channel.get_tag(role.subalignment.id)
            roles_str_list.append(f'{sub_tag.emoji} {role.name} (<#{role.id}>)')

        roles_str = '\n'.join(roles_str_list)

        await interaction.response.send_message(content=roles_str + elapsed_time_str)


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
                cached_message = message.reference.cached_message or message.reference.resolved
                message = cached_message or await interaction.channel.fetch_message(message.reference.message_id)
            else:
                break

        channel_mentions = message.channel_mentions
        cleaned_content = message.content
        guild_info = utils.get_guild_info(interaction)

        await interaction.response.defer()

        channel_link_regex = (r"https?:\/\/(?:(?:ptb|canary)\.)?discord(?:app)?\.com\/channels\/(?P<guild_id>[0-9]{"
                              r"15,19})\/(?P<channel_id>[0-9]{15,19})?")

        for channel in channel_mentions:
            if isinstance(channel, discord.ForumChannel):
                faction = guild_info.get_faction(channel.id)
                if not faction:
                    raise SDGException('Channel isn\'t assigned to a faction!')
                cleaned_content = cleaned_content.replace(channel.mention, f'${faction.name}')
            else:
                role = guild_info.get_role(channel.id)
                if not role:
                    raise SDGException('Thread isn\'t a assigned to a role!')
                cleaned_content = cleaned_content.replace(channel.mention, f'%{role.name}')

        for match in re.finditer(channel_link_regex, cleaned_content):
            guild_id = int(match.group('guild_id'))
            channel_id = int(match.group('channel_id'))

            match_str = match.group()

            if guild_id != interaction.guild_id:
                continue

            faction = guild_info.get_faction(channel_id)

            if faction:
                cleaned_content = cleaned_content.replace(match_str, f'${faction.name}')
                continue

            role = guild_info.get_role(channel_id)

            if role:
                cleaned_content = cleaned_content.replace(match_str, f'%{role.name}')

        rolelist_info = utils.get_rolelist(cleaned_content, all_roles=guild_info.roles)

        if len(rolelist_info.slots) > 30:
            raise SDGException('Too many slots! Max number of slots is 30')

        start_time = time.time()
        roles = generate_rolelist_roles(rolelist_info, guild_info.roles)
        end_time = time.time()
        elapsed_time = end_time - start_time
        elapsed_time_str = f'\n\nGenerated roles in {elapsed_time:4f} seconds'

        roles_str_list = []

        for role in roles:
            faction_channel = self.client.get_channel(role.faction.id)
            sub_tag = faction_channel.get_tag(role.subalignment.id)
            roles_str_list.append(f'{sub_tag.emoji} {role.name} (<#{role.id}>)')

        roles_str = '\n'.join(roles_str_list)

        if not roles_str:
            raise SDGException('No slots specified in message!')

        view = RegenerateView(interaction.user, rolelist_info, guild_info.roles)

        await interaction.edit_original_response(content=roles_str + elapsed_time_str, view=view)


async def setup(bot):
    await bot.add_cog(ContextMenuCog(bot))

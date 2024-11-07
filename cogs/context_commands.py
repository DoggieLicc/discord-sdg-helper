import discord

from discord import app_commands
from discord.ext import commands
from utils import SDGException, generate_rolelist_roles

import utils


class ContextMenuCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.generate_rolelist_cmd = app_commands.ContextMenu(
            name='Generate Rolelist Roles',
            callback=self.generate_rolelist
        )
        self.generate_mod_threads_cmd = app_commands.ContextMenu(
            name='Generate Threads with Mentions',
            callback=self.generate_mod_threads
        )

        self.client.tree.add_command(self.generate_rolelist_cmd)
        self.client.tree.add_command(self.generate_mod_threads_cmd)

    async def cog_unload(self) -> None:
        self.client.tree.remove_command(self.generate_rolelist_cmd.name, type=self.generate_rolelist_cmd.type)
        self.client.tree.remove_command(self.generate_mod_threads_cmd.name, type=self.generate_mod_threads_cmd.type)

    @app_commands.guild_only()
    async def generate_rolelist(
            self,
            interaction: discord.Interaction,
            message: discord.Message
    ):
        """Generate rolelist roles"""

        channel_mentions = message.channel_mentions
        cleaned_content = message.content
        guild_info = utils.get_guild_info(interaction)

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

        rolelist_info = utils.get_rolelist(cleaned_content, all_roles=guild_info.roles)
        roles = generate_rolelist_roles(rolelist_info, guild_info.roles)

        roles_str = '\n'.join(f'{r.name} (<#{r.id}>)' for r in roles)

        if not roles_str:
            raise SDGException('No slots specified in message!')

        await interaction.response.send_message(roles_str)

    @app_commands.checks.has_permissions(manage_threads=True, create_private_threads=True)
    @app_commands.checks.bot_has_permissions(manage_threads=True, create_private_threads=True)
    @app_commands.guild_only()
    async def generate_mod_threads(
            self,
            interaction: discord.Interaction,
            message: discord.Message
    ):
        """Generate mod threads using mentions from the provided message"""

        message_mentions = message.mentions
        role_mentions = message.role_mentions

        for role in role_mentions:
            for member in role.members:
                if member not in message_mentions:
                    message_mentions.append(member)

        if not message_mentions:
            raise SDGException('No users or roles are mentioned in that message!')

        if not interaction.channel.type == discord.ChannelType.text:
            raise SDGException('Can\'t use in non-text channels!')

        await interaction.response.defer()

        for member in message_mentions:
            thread = await message.channel.create_thread(
                name=f'{member} Mod Thread',
                auto_archive_duration=10080,
                invitable=False
            )
            await thread.send(member.mention + ' ' + interaction.user.mention)
            await thread.leave()

        embed = utils.create_embed(
            interaction.user,
            title='Threads created!',
            description=f'Generated {len(message_mentions)} private threads'
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ContextMenuCog(bot))

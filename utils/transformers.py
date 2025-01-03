from typing import Any

import discord
from discord import app_commands, Interaction, Message
from discord.app_commands import Choice
from discord.ext.commands import MessageConverter, MemberConverter, RoleConverter, BadArgument, CommandError
from discord.utils import cached_property
from thefuzz import process as thefuzz_process
from thefuzz import fuzz

from utils.classes import *

__all__ = [
    'FakeContext',
    'FakeMessage',
    'ChoiceTransformer',
    'MessageTransformer',
    'GreedyMemberRoleTransformer',
    'FactionTransformer',
    'SubalignmentTransformer',
    'RoleTransformer',
    'InfoCategoryTransformer',
    'InfoTagTransformer',
    'RSFTransformer',
    'ScrollTransformer',
    'ForumTagTransformer',
    'AchievementTransformer'
]


class FakeContext(discord.Object):
    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)
        super().__init__(id=0)


class FakeMessage(discord.Object):
    # pylint: disable=no-member
    def __init__(self, guild: discord.Guild | None, content: str):
        self.content = content
        self.guild = guild
        super().__init__(id=0)

    @cached_property
    def raw_mentions(self) -> list[int]:
        return Message.raw_mentions.function(self)

    @cached_property
    def raw_channel_mentions(self) -> list[int]:
        return Message.raw_channel_mentions.function(self)

    @cached_property
    def raw_role_mentions(self) -> list[int]:
        return Message.raw_role_mentions.function(self)

    @cached_property
    def channel_mentions(self) -> list[discord.abc.GuildChannel | discord.Thread]:
        return Message.channel_mentions.function(self)

    @cached_property
    def mentions(self) -> list[discord.Member]:
        mentions = []
        if self.guild:
            for mention in self.raw_mentions:
                member = self.guild.get_member(mention)
                if member:
                    mentions.append(member)
        return mentions

    @cached_property
    def role_mentions(self) -> list[discord.Role]:
        role_mentions = []
        if self.guild:
            for mention in self.raw_role_mentions:
                role = self.guild.get_role(mention)
                if role:
                    role_mentions.append(role)

        return role_mentions

    @cached_property
    def clean_content(self) -> str:
        return Message.clean_content.function(self)


class MessageTransformer(app_commands.Transformer):
    # pylint: disable=abstract-method
    async def transform(self, interaction: Interaction, value: str, /) -> Any:
        if value.isnumeric():  # MessageConverter does not fetch message for an id, so we handle it here
            state_msg = interaction.client._connection._get_message(int(value))
            message = state_msg or await interaction.channel.fetch_message(int(value))
            return message

        fake_ctx = FakeContext(bot=interaction.client, guild=interaction.guild)
        message_converter = MessageConverter()
        return await message_converter.convert(fake_ctx, value)  # type: ignore


class GreedyMemberRoleTransformer(app_commands.Transformer):
    # pylint: disable=abstract-method
    async def transform(self, interaction: Interaction, value: str, /) -> list[discord.Role | discord.Member]:
        cleaned_value = value.replace('><', '> <').strip()
        arguments = cleaned_value.split()

        fake_ctx = FakeContext(bot=interaction.client, guild=interaction.guild)
        member_converter = MemberConverter()
        role_converter = RoleConverter()
        items = []
        for argument in arguments:
            converted = None
            try:
                converted = await member_converter.convert(fake_ctx, argument)
            except (CommandError, BadArgument):
                try:
                    converted = await role_converter.convert(fake_ctx, argument)
                except (CommandError, BadArgument):
                    pass

            if converted is not None and converted not in items:
                items.append(converted)

        if not items:
            raise SDGException()

        return items

class ChoiceTransformer(app_commands.Transformer):
    async def transform(self, interaction: Interaction, value: Any, /) -> Any:
        return self.get_value(interaction, value)

    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        raise NotImplementedError('Derived classes need to implement this method')

    def get_value(self, interaction: Interaction, value: Any) -> Any:
        raise NotImplementedError('Derived classes need to implement this method')

    async def autocomplete(
            self, interaction: Interaction, value: int | float | str, /
    ) -> list[Choice[int | float | str]]:
        choices = self.get_choices(interaction)
        if not value:
            return choices[:25]

        choices_dict = {c.value: c.name for c in choices}
        matches = thefuzz_process.extract(str(value), choices_dict, limit=25, scorer=fuzz.UQRatio)
        choice_matches = {m[2]: m[0] for m in matches}
        choices = [Choice(name=v, value=k) for k, v in choice_matches.items()]
        return choices


class FactionTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        choice_list = []
        for faction in guild_info.factions:
            choice_list.append(app_commands.Choice(name=faction.name, value=str(faction.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Faction:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        faction = guild_info.get_faction(int(value))
        if faction is None:
            raise SDGException('Invalid value')
        return faction


class SubalignmentTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        choice_list = []
        for subalignment in guild_info.subalignments:
            choice_list.append(app_commands.Choice(name=subalignment.name, value=str(subalignment.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Subalignment:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        subalignment = guild_info.get_subalignment(int(value))
        if subalignment is None:
            raise SDGException('Invalid value')
        return subalignment


class InfoCategoryTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        choice_list = []
        for information_category in guild_info.info_categories:
            choice_list.append(app_commands.Choice(name=information_category.name, value=str(information_category.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> InfoCategory:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        info_category = guild_info.get_info_category(int(value))
        if info_category is None:
            raise SDGException('Invalid value')
        return info_category


class InfoTagTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)

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
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        info_tag = guild_info.get_info_tag(int(value))
        if info_tag is None:
            raise SDGException('Invalid value')
        return info_tag


class RoleTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        choice_list = []
        for role in guild_info.roles:
            choice_list.append(app_commands.Choice(name=role.name, value=str(role.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Role:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        role = guild_info.get_role(int(value))
        if role is None:
            raise SDGException('Invalid value')
        return role


class RSFTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        choice_list = []
        for item in guild_info.roles + guild_info.subalignments + guild_info.factions:
            if isinstance(item, Role):
                rsf_type = 'Role'
            elif isinstance(item, Subalignment):
                rsf_type = 'Subalignment'
            else:
                rsf_type = 'Faction'
            choice_list.append(app_commands.Choice(name=f'{item.name} ({rsf_type})', value=str(item.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Role | Subalignment | Faction:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        role = guild_info.get_role(int(value))
        subalignment = guild_info.get_subalignment(int(value))
        faction = guild_info.get_faction(int(value))
        rsf = role or subalignment or faction
        if rsf is None:
            raise SDGException('Invalid value')

        return rsf


class ScrollTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        account = guild_info.get_account(interaction.user.id)
        if not account:
            return [app_commands.Choice(name='You don\'t have an account!', value=0)]

        choice_list = []
        for item in account.blessed_scrolls:
            name = f'Blessed - {item.name}'
            choice_list.append(app_commands.Choice(name=name, value=str(item.id)))

        for item in account.cursed_scrolls:
            name = f'Cursed - {item.name}'
            choice_list.append(app_commands.Choice(name=name, value=str(item.id)))

        if not choice_list:
            return [app_commands.Choice(name='You don\'t have any scrolls equipped!', value=0)]

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Role | Subalignment | Faction:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        account = guild_info.get_account(interaction.user.id)
        if not account:
            raise SDGException('You don\'t have an account!')

        all_scrolls = account.blessed_scrolls + account.cursed_scrolls
        scroll = [s for s in all_scrolls if s.id == int(value)]

        if not scroll:
            raise SDGException('Invalid scroll!')

        return scroll[0]


class ForumTagTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
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

        if faction_channel is None:
            raise SDGException('Invalid value')

        forum_tag = faction_channel.get_tag(int(value))

        if forum_tag is None:
            raise SDGException('Invalid value')

        return forum_tag


class AchievementTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        choice_list = []
        for achievement in guild_info.achievements:
            choice_list.append(app_commands.Choice(name=achievement.name, value=str(achievement.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Achievement:
        guild_info: GuildInfo = interaction.client.get_guild_info(interaction.guild.id)
        achievement = guild_info.get_achievement(int(value))

        if achievement is None:
            raise SDGException('Invalid value')

        return achievement

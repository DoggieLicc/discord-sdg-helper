import re
import discord

from typing import Any
from thefuzz import process as thefuzz_process
from discord import app_commands, Interaction
from discord.app_commands import Choice

import utils
from utils.classes import *
from utils.funcs import get_guild_info

__all__ = [
    'MessageTransformer',
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


class MessageTransformer(app_commands.Transformer):
    async def transform(self, interaction: Interaction, value: str, /) -> Any:
        try:
            if value.isnumeric():
                state_msg = interaction.client._connection._get_message(int(value))
                message = state_msg or await interaction.channel.fetch_message(int(value))
                return message
            else:
                link_regex = re.compile(
                    r"https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com"
                    r"/channels/[0-9]{15,19}/(?P<channel_id>"
                    r"[0-9]{15,19})/(?P<message_id>[0-9]{15,19})/?"
                )

                match = re.search(link_regex, value)
                if match:
                    channel_id = int(match.group('channel_id'))
                    message_id = int(match.group('message_id'))

                    state_msg = interaction.client._connection._get_message(message_id)

                    if state_msg:
                        return state_msg

                    channel = (interaction.guild.get_channel_or_thread(channel_id) or
                               await interaction.guild.fetch_channel(channel_id))

                    message = await channel.fetch_message(message_id)
                    return message
        except discord.DiscordException:
            raise SDGException('Invalid message ID! Message must be in the same channel as this one')


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
        matches = thefuzz_process.extract(str(value), choices_dict, limit=25)
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
        faction = guild_info.get_faction(int(value))
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
        subalignment = guild_info.get_subalignment(int(value))
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
        info_category = guild_info.get_info_category(int(value))
        return info_category


class InfoTagTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)

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
        guild_info: GuildInfo = get_guild_info(interaction)
        info_tag = guild_info.get_info_tag(int(value))

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
        role = guild_info.get_role(int(value))
        return role


class RSFTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)
        choice_list = []
        for item in guild_info.roles + guild_info.subalignments + guild_info.factions:
            if isinstance(item, utils.Role):
                rsf_type = 'Role'
            elif isinstance(item, utils.Subalignment):
                rsf_type = 'Subalignment'
            else:
                rsf_type = 'Faction'
            choice_list.append(app_commands.Choice(name=f'{item.name} ({rsf_type})', value=str(item.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Role | Subalignment | Faction:
        guild_info: GuildInfo = get_guild_info(interaction)
        role = guild_info.get_role(int(value))
        subalignment = guild_info.get_subalignment(int(value))
        faction = guild_info.get_faction(int(value))
        return role or subalignment or faction


class ScrollTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)
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
        guild_info: GuildInfo = get_guild_info(interaction)
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


class AchievementTransformer(ChoiceTransformer):
    def get_choices(self, interaction: Interaction) -> list[app_commands.Choice]:
        guild_info: GuildInfo = get_guild_info(interaction)
        choice_list = []
        for achievement in guild_info.achievements:
            choice_list.append(app_commands.Choice(name=achievement.name, value=str(achievement.id)))

        return choice_list

    def get_value(self, interaction: Interaction, value: Any) -> Achievement:
        guild_info: GuildInfo = get_guild_info(interaction)
        achievement = guild_info.get_achievement(int(value))
        return achievement

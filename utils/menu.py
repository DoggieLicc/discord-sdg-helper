from typing import Any
from collections.abc import Iterable
from collections import Counter

import discord
from discord import Interaction
from discord.ui import View, Button, Item
from discord.ext.commands import Paginator

from utils.funcs import create_embed, generate_gamestate_csv, get_valid_emoji


__all__ = [
    'PaginatedMenu',
    'PollSelect',
    'PollSelectButton',
    'CustomView',
    'GenerateCSVView'
]


class CustomView(View):
    def __init__(self, owner: discord.User):
        self.owner = owner
        self.message = None
        super().__init__(timeout=360)

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        self.message = interaction.message

        if interaction.user != self.owner:
            await interaction.response.send_message(content='You didn\'t use this command!', ephemeral=True)
            return False

        return True

    async def on_timeout(self) -> None:
        self.disable_children()

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    def disable_children(self) -> None:
        for child in self._children:
            child.disabled = True

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[Any], /) -> None:
        await interaction.client.tree.on_error(interaction, error)


class PaginatedMenu(CustomView):
    def __init__(self, owner: discord.User, items: Iterable):
        super().__init__(owner)

        self.paginator = self.get_paginator(items)

        self.items = items
        self.current_page = 1
        self.max_page = len(self.paginator.pages)

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        check = await super().interaction_check(interaction)
        if check:
            await interaction.response.defer()
        return check

    def format_line(self, item) -> str:
        return str(item)

    def get_paginator(self, items) -> Paginator:
        paginator = Paginator(prefix=None, suffix=None, max_size=750)

        for item in items:
            paginator.add_line(self.format_line(item))

        return paginator

    async def get_page_contents(self) -> dict:
        ...

    async def update_page(self, interaction: discord.Interaction):
        contents = await self.get_page_contents()
        await interaction.edit_original_response(view=self, **contents)

    @discord.ui.button(emoji='\U000023EA', style=discord.ButtonStyle.blurple)
    async def far_left(self, interaction: discord.Interaction, _: Button):
        self.current_page = 1
        await self.update_page(interaction)

    @discord.ui.button(emoji='\U000025C0', style=discord.ButtonStyle.blurple)
    async def left(self, interaction: discord.Interaction, _: Button):
        self.current_page -= 1
        self.current_page = max(self.current_page, 1)

        await self.update_page(interaction)

    @discord.ui.button(emoji='\U000023F9', style=discord.ButtonStyle.red)
    async def stop_button(self, interaction: discord.Interaction, _: Button):
        children = self.children
        for child in children:
            child.disabled = True
        self._children = children

        await interaction.edit_original_response(view=self)

    @discord.ui.button(emoji='\U000025B6', style=discord.ButtonStyle.blurple)
    async def right(self, interaction: discord.Interaction, _: Button):
        self.current_page += 1
        self.current_page = min(self.current_page, self.max_page)

        await self.update_page(interaction)

    @discord.ui.button(emoji='\U000023E9', style=discord.ButtonStyle.blurple)
    async def far_right(self, interaction: discord.Interaction, _: Button):
        self.current_page = self.max_page
        await self.update_page(interaction)


class PollSelect(discord.ui.Select):
    def __init__(self, thread: discord.Thread, whitelist, blacklist, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_options: dict[int, str] = {}

        self.whitelist: list[discord.Role | discord.Member] = whitelist
        self.blacklist: list[discord.Role | discord.Member] = blacklist
        self.thread = thread

    async def callback(self, interaction: discord.Interaction):
        valid_user = not self.whitelist

        if self.whitelist:
            for mention in self.whitelist:
                if isinstance(mention, discord.Role):
                    if interaction.user in mention.members:
                        valid_user = True
                        continue
                if interaction.user == mention:
                    valid_user = True
                    continue

        if self.blacklist:
            for mention in self.blacklist:
                if isinstance(mention, discord.Role):
                    if interaction.user in mention.members:
                        await interaction.response.send_message('You are in the excluded roles list!', ephemeral=True)
                        return
                if interaction.user == mention:
                    await interaction.response.send_message('You are in the excluded members list!', ephemeral=True)
                    return

        if not valid_user:
            await interaction.response.send_message('You aren\'t in the whitelist!', ephemeral=True)
            return

        option_str = format_option_value(self.values[0], self.options, interaction.client)

        last_selected = self.selected_options.get(interaction.user.id, None)
        if last_selected is not None:
            await self.thread.send(f'{interaction.user} switched from {last_selected} to {option_str}')
        else:
            await self.thread.send(f'{interaction.user} selected {option_str}')

        self.selected_options[interaction.user.id] = self.values[0]
        await interaction.response.send_message(f'Your vote for {option_str} has been counted.', ephemeral=True)


class PollSelectButton(discord.ui.Button):
    def __init__(self, allowed_user: discord.Member, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_user = allowed_user
        self.style = discord.ButtonStyle.danger
        self.label = 'Stop poll'

    async def callback(self, interaction: discord.Interaction):
        if interaction.user == self.allowed_user:
            await interaction.response.defer()
            self.disabled = True
            self.view.children[0].disabled = True
            thread = self.view.children[0].thread
            selected_options = self.view.children[0].selected_options
            all_options = self.view.children[0].options

            counts = Counter(selected_options.values())

            for option in all_options:
                if option.value not in counts.keys():
                    counts[option.value] = 0

            counts_msg = ''
            for value, count in counts.most_common():
                option_str = format_option_value(value, all_options, interaction.client)
                counts_msg += f'**"{option_str}"** got {count} votes!\n'

            counts_msg = counts_msg.strip()

            selected_msg = ''
            for user, value in selected_options.items():
                option_str = format_option_value(value, all_options, interaction.client)
                selected_msg += f'<@{user}> voted {option_str}\n'

            selected_msg = selected_msg.strip()

            full_msg = counts_msg + '\n\n' + selected_msg if selected_options else 'No one voted!'

            embed = create_embed(
                user=self.allowed_user,
                title='Poll ended!',
                description=full_msg
            )

            await interaction.edit_original_response(view=self.view)
            await thread.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            self.view.stop()
        else:
            await interaction.response.send_message(content='Not your button!', ephemeral=True)


class GenerateCSVView(CustomView):
    def __init__(
            self,
            owner: discord.User,
            players: list[discord.User],
            roles: list[discord.Role],
            ephemeral: bool = True
    ):
        super().__init__(owner=owner)
        self.players = players
        self.roles = roles
        self.ephemeral = ephemeral

    @discord.ui.button(label='Generate Gamestate CSV', style=discord.ButtonStyle.blurple)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        csv_file = generate_gamestate_csv(self.players, self.roles)
        await interaction.response.send_message(file=csv_file, ephemeral=self.ephemeral)
        await self.on_timeout()


def format_option_value(value: str, all_options: list[discord.SelectOption], client: discord.Client) -> str:
    option = [o for o in all_options if o.value == value][0]
    option_label = discord.utils.escape_markdown(option.label)
    full_emoji = get_valid_emoji(option.emoji, client)
    return f'{option.emoji} {option_label}' if full_emoji else option_label

from typing import Any
from collections.abc import Iterable
from collections import Counter

import discord
from discord import Interaction
from discord.ui import View, Button, Item
from discord.ext.commands import Paginator

from utils.funcs import create_embed, generate_gamestate_csv


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
        await interaction.response.defer()
        self.message = interaction.message

        if interaction.user != self.owner:
            await interaction.followup.send('You didn\'t use this command!', ephemeral=True)
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
        children = self.children
        for child in children:
            child.disabled = True
        self._children = children

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[Any], /) -> None:
        print(type(error), error)


class PaginatedMenu(CustomView):
    def __init__(self, owner: discord.User, items: Iterable):
        super().__init__(owner)

        self.paginator = self.get_paginator(items)

        self.items = items
        self.current_page = 1
        self.max_page = len(self.paginator.pages)

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
    def __init__(self, thread: discord.Thread, included_roles, excluded_roles, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_options: dict[int, str] = {}
        self.included_roles: list[discord.Role] = included_roles
        self.excluded_roles: list[discord.Role] = excluded_roles
        self.thread = thread

    async def callback(self, interaction: discord.Interaction):
        valid_user = not self.included_roles

        if self.included_roles:
            for role in self.included_roles:
                if interaction.user in role.members:
                    valid_user = True
                    continue

        if self.excluded_roles:
            for role in self.excluded_roles:
                if interaction.user in role.members:
                    await interaction.response.send_message('You are in the excluded roles list!', ephemeral=True)
                    return None

        if not valid_user:
            await interaction.response.send_message('You aren\'t in the included roles list', ephemeral=True)
            return None

        await self.thread.send(f'{interaction.user} selected {self.values[0]}')

        self.selected_options[interaction.user.id] = self.values[0]
        await interaction.response.defer()


class PollSelectButton(discord.ui.Button):
    def __init__(self, allowed_user: discord.Member, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_user = allowed_user
        self.style = discord.ButtonStyle.danger
        self.label = 'Stop poll'

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if interaction.user == self.allowed_user:
            self.disabled = True
            self.view.children[0].disabled = True
            thread = self.view.children[0].thread
            selected_options = self.view.children[0].selected_options

            counts = Counter(selected_options.values())
            counts_msg = '\n'.join(f'**"{discord.utils.escape_markdown(c[0])}"** got {c[1]} votes!' for c in
                                   counts.most_common())

            selected_msg = '\n'.join(f'<@{k}> voted {v}' for k, v in selected_options.items())

            full_msg = counts_msg + '\n\n' + selected_msg if selected_options else 'No one voted!'

            embed = create_embed(
                user=self.allowed_user,
                title='Poll ended!',
                description=full_msg
            )

            await interaction.message.edit(view=self.view)
            await thread.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            self.view.stop()
        else:
            await interaction.followup.send('Not your button!', ephemeral=True)


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
        await interaction.followup.send(file=csv_file, ephemeral=self.ephemeral)
        self.disable_children()

        try:
            await interaction.edit_original_response(view=self)
        except discord.NotFound:
            pass

        self.stop()

from typing import Any

import discord
from discord import Interaction

from discord.ui import View, Button, Item
from discord.ext.commands import Paginator
from collections.abc import Iterable

from utils.funcs import create_embed


class PaginatedMenu(View):
    def __init__(self, owner: discord.User, items: Iterable):
        super().__init__(timeout=360)

        self.paginator = self.get_paginator(items)

        self.current_page = 1
        self.max_page = len(self.paginator.pages)
        self.owner = owner
        self.message = None

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
    async def far_left(self, interaction: discord.Interaction, button: Button):
        self.current_page = 1
        await self.update_page(interaction)

    @discord.ui.button(emoji='\U000025C0', style=discord.ButtonStyle.blurple)
    async def left(self, interaction: discord.Interaction, button: Button):
        self.current_page -= 1
        if self.current_page < 1:
            self.current_page = 1

        await self.update_page(interaction)

    @discord.ui.button(emoji='\U000023F9', style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: Button):
        children = self.children
        for child in children:
            child.disabled = True
        self._children = children

        await interaction.edit_original_response(view=self)

    @discord.ui.button(emoji='\U000025B6', style=discord.ButtonStyle.blurple)
    async def right(self, interaction: discord.Interaction, button: Button):
        self.current_page += 1
        if self.current_page > self.max_page:
            self.current_page = self.max_page

        await self.update_page(interaction)

    @discord.ui.button(emoji='\U000023E9', style=discord.ButtonStyle.blurple)
    async def far_right(self, interaction: discord.Interaction, button: Button):
        self.current_page = self.max_page
        await self.update_page(interaction)

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        await interaction.response.defer()
        self.message = interaction.message

        if interaction.user != self.owner:
            await interaction.followup.send('You didn\'t use this command!', ephemeral=True)
            return False

        return True

    async def on_timeout(self) -> None:
        children = self.children
        for child in children:
            child.disabled = True
        self._children = children

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[Any], /) -> None:
        print(type(error), error)


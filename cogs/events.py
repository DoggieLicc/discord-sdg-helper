import asyncio

import discord

from discord import app_commands
from discord.ext import commands
from utils import GuildInfo


class EventsCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    async def sync_all(self):
        for guild in self.client.guilds:
            await self.client.sync_guild(guild)

        print('ALL GUILDS SYNCED!')

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Logged in as {self.client.user} (ID: {self.client.user.id})')
        print('------')

        if not self.client.first_sync:
            while not self.client.db_loaded:
                await asyncio.sleep(1)

            await self.sync_all()
            self.client.first_sync = True

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        guild_info = [i for i in self.client.guild_info if i.guild_id == thread.guild.id]
        if not guild_info:
            return

        faction = [f for f in guild_info[0].factions if f.id == thread.parent_id]

        if faction:
            await self.client.sync_faction(faction[0])
            return

        infotag = [t for t in guild_info[0].info_categories if t.id == thread.parent_id]

        if infotag:
            await self.client.sync_infotags(infotag[0])
            return

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        guild_info = [i for i in self.client.guild_info if i.guild_id == guild.id]
        if guild_info:
            return

        self.client.guild_info.append(GuildInfo(
            guild.id,
            list(),
            list(),
            list(),
            list(),
            list(),
            list()
        ))

    @commands.Cog.listener()
    async def on_raw_thread_update(self, payload: discord.RawThreadUpdateEvent):
        guild_info = [i for i in self.client.guild_info if i.guild_id == payload.guild_id]
        if not guild_info:
            return

        guild_info = guild_info[0]

        guild = self.client.get_guild(payload.guild_id)
        thread = payload.thread or await guild.fetch_channel(payload.thread_id)

        if thread not in guild._threads.values():
            print(f'Adding {thread.name} ({thread.id}) to cache')
            guild._threads[thread.id] = thread

        faction = [f for f in guild_info.factions if f.id == payload.parent_id]

        if faction:
            roles = [r for r in self.client.get_faction_roles(faction[0]) if r.id != payload.thread_id]
            guild_info.roles = roles

        infotag = [t for t in guild_info.info_categories if t.id == payload.parent_id]

        if infotag:
            infotags = [t for t in guild_info.info_tags if t.id != payload.thread_id]
            guild_info.info_tags = infotags

        if faction or infotag:
            self.client.guild_info.remove([gi for gi in self.client.guild_info if gi.guild_id == payload.guild_id][0])
            self.client.guild_info.append(guild_info)
            await self.client.sync_guild(guild)

    @commands.Cog.listener()
    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent):
        guild_info = [i for i in self.client.guild_info if i.guild_id == payload.guild_id]
        if not guild_info:
            return

        guild_info = guild_info[0]

        faction = [f for f in guild_info.factions if f.id == payload.parent_id]

        if faction:
            guild_info.roles = [r for r in guild_info.roles if r.id != payload.thread_id]

        infotag = [t for t in guild_info.info_categories if t.id == payload.parent_id]

        if infotag:
            guild_info.info_tags = [t for t in guild_info.info_tags if t.id != payload.thread_id]

        if infotag or faction:
            self.client.guild_info.remove([gi for gi in self.client.guild_info if gi.guild_id == payload.guild_id][0])
            self.client.guild_info.append(guild_info)


async def setup(bot):
    await bot.add_cog(EventsCog(bot))

import asyncio

import discord

from discord import app_commands
from discord.ext import commands, tasks

import utils
from utils import GuildInfo


class EventsCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.last_activity = None
        self.update_custom_activity.start()

    @tasks.loop(hours=1)
    async def update_custom_activity(self):
        len_roles = sum(len(gi.roles) for gi in self.client.guild_info)
        len_guilds = len(self.client.guilds)
        activity = discord.CustomActivity(f'Handling {len_roles} roles in {len_guilds} servers')

        if activity != self.last_activity:
            await self.client.change_presence(activity=activity)
            self.last_activity = activity

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

            await self.update_custom_activity()

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        guild_info = self.client.get_guild_info(thread.guild.id)
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
        guild_info = self.client.get_guild_info(guild.id)
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
        guild_info = self.client.get_guild_info(payload.guild_id)
        if not guild_info:
            return

        guild_info = guild_info[0]

        guild = self.client.get_guild(payload.guild_id)
        thread = payload.thread or await guild.fetch_channel(payload.thread_id)

        if thread not in guild._threads.values():
            print(f'Adding {thread.name} ({thread.id}) to cache')
            guild._add_thread(thread)

        faction = [f for f in guild_info.factions if f.id == payload.parent_id]

        if faction:
            roles = [r for r in self.client.get_faction_roles(faction[0]) if r.id != payload.thread_id]
            guild_info.roles = roles

        infotag = [t for t in guild_info.info_categories if t.id == payload.parent_id]

        if infotag:
            infotags = [t for t in guild_info.info_tags if t.id != payload.thread_id]
            guild_info.info_tags = infotags

        if faction or infotag:
            self.client.replace_guild_info(guild_info)
            await self.client.sync_guild(guild)

    @commands.Cog.listener()
    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent):
        guild_info = self.client.get_guild_info(payload.guild_id)
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
            self.client.replace_guild_info(guild_info)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if not isinstance(before, discord.ForumChannel):
            return

        guild_info = self.client.get_guild_info(before.guild.id)

        faction = [f for f in guild_info.factions if f.id == before.id]

        if not faction:
            return

        faction = faction[0]

        before_tags = before.available_tags
        after_tags = after.available_tags

        missing_tags = []
        for tag in before_tags:
            if tag not in after_tags:
                missing_tags.append(tag)

        for missing_tag in missing_tags:
            subalignment = [s for s in guild_info.subalignments if s.id == missing_tag.id]
            if subalignment:
                subalignment = subalignment[0]
                for role in self.client.get_subalignment_roles(subalignment):
                    guild_info.roles.remove(role)

                guild_info.subalignments.remove(subalignment)
                self.client.replace_guild_info(guild_info)

                await self.client.delete_item_from_db(subalignment, 'subalignments')

                print(f'Deleted {subalignment.name} automatically')

        await self.client.sync_faction(faction)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild_info: utils.GuildInfo = self.client.get_guild_info(channel.guild.id)

        faction = [f for f in guild_info.factions if f.id == channel.id]

        if faction:
            faction = faction[0]
            guild_info.factions.remove(faction)
            for role in self.client.get_faction_roles(faction):
                guild_info.roles.remove(role)
            await self.client.delete_item_from_db(faction)

        info_category = [t for t in guild_info.info_categories if t.id == channel.id]

        if info_category:
            info_category = info_category[0]
            guild_info.info_categories.remove(info_category)
            info_tags = [it for it in guild_info.info_tags if it.info_category == info_category]
            for info_tag in info_tags:
                guild_info.info_tags.remove(info_tag)
            await self.client.delete_item_from_db(info_category)

        if faction or info_category:
            self.client.replace_guild_info(guild_info)
            await self.client.sync_guild(channel.guild)


async def setup(bot):
    await bot.add_cog(EventsCog(bot))

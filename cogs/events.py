import asyncio

import discord

from discord.ext import commands, tasks

import utils
from utils import GuildInfo


class EventsCog(commands.Cog):
    def __init__(self, client):
        self.client: utils.DiscordClient = client
        self.last_activity = None
        self.update_custom_activity.start()

    @tasks.loop(hours=1)
    async def update_custom_activity(self):
        len_roles = sum(len(gi.roles) for gi in self.client.guild_info)
        len_guilds = len(self.client.guilds)
        activity = discord.CustomActivity(f'Handling {len_roles} roles in {len_guilds} servers')

        if self.client and activity != self.last_activity:
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

            await asyncio.sleep(1)
            await self.sync_all()
            await self.client.post_guild_info_load()
            self.client.first_sync = True

            await self.update_custom_activity()

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        guild_info: GuildInfo = self.client.get_guild_info(thread.guild.id)
        if not guild_info:
            return

        faction = guild_info.get_faction(thread.parent_id)

        if faction:
            await self.client.sync_faction(faction)
            return

        info_category = guild_info.get_info_category(thread.parent_id)

        if info_category:
            await self.client.sync_infotags(info_category)
            return

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        guild_info = self.client.get_guild_info(guild.id)
        if guild_info:
            return

        default_settings = utils.GuildSettings(
            max_scrolls=5,
            roles_are_scrollable=True,
            subalignments_are_scrollable=True,
            factions_are_scrollable=True,
            role_scroll_multiplier=10,
            subalignment_scroll_multiplier=10,
            faction_scroll_multiplier=10,
            accounts_creatable=True
        )

        self.client.guild_info.append(
            GuildInfo(
                guild.id,
                [],
                [],
                [],
                [],
                [],
                [],
                [],
                [],
                default_settings
            )
        )

        await self.client.add_settings_to_db(default_settings, guild.id)

    @commands.Cog.listener()
    async def on_raw_thread_update(self, payload: discord.RawThreadUpdateEvent):
        guild_info: GuildInfo = self.client.get_guild_info(payload.guild_id)
        if not guild_info:
            return

        guild = self.client.get_guild(payload.guild_id)
        thread = payload.thread or await guild.fetch_channel(payload.thread_id)

        if thread not in guild._threads.values():
            print(f'Adding {thread.name} ({thread.id}) to cache')
            guild._add_thread(thread)

        faction = guild_info.get_faction(payload.parent_id)

        if faction:
            roles = [r for r in self.client.get_faction_roles(faction) if r.id != payload.thread_id]
            guild_info.roles = roles

        info_category = guild_info.get_info_category(payload.parent_id)

        if info_category:
            infotags = [t for t in guild_info.info_tags if t.id != payload.thread_id]
            guild_info.info_tags = infotags

        if faction or info_category:
            self.client.replace_guild_info(guild_info)
            await self.client.sync_guild(guild)

    @commands.Cog.listener()
    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent):
        guild_info: GuildInfo = self.client.get_guild_info(payload.guild_id)
        if not guild_info:
            return

        faction = guild_info.get_faction(payload.parent_id)

        if faction:
            guild_info.roles = [r for r in guild_info.roles if r.id != payload.thread_id]

        info_category = guild_info.get_info_category(payload.parent_id)

        if info_category:
            guild_info.info_tags = [t for t in guild_info.info_tags if t.id != payload.thread_id]

        if info_category or faction:
            self.client.replace_guild_info(guild_info)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if not isinstance(before, discord.ForumChannel) and not isinstance(after, discord.ForumChannel):
            return

        guild_info: GuildInfo = self.client.get_guild_info(before.guild.id)

        faction = guild_info.get_faction(before.id)

        if not faction:
            return

        before_tags = before.available_tags
        after_tags = after.available_tags

        missing_tags = []
        for tag in before_tags:
            if tag not in after_tags:
                missing_tags.append(tag)

        for missing_tag in missing_tags:
            subalignment = guild_info.get_subalignment(missing_tag.id)
            if subalignment:
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

        faction = guild_info.get_faction(channel.id)

        if faction:
            guild_info.factions.remove(faction)
            for role in self.client.get_faction_roles(faction):
                guild_info.roles.remove(role)
            await self.client.delete_item_from_db(faction, 'factions')

        info_category = guild_info.get_info_category(channel.id)

        if info_category:
            guild_info.info_categories.remove(info_category)
            info_tags = [it for it in guild_info.info_tags if it.info_category == info_category]
            for info_tag in info_tags:
                guild_info.info_tags.remove(info_tag)
            await self.client.delete_item_from_db(info_category, 'infotags')

        if faction or info_category:
            self.client.replace_guild_info(guild_info)
            await self.client.sync_guild(channel.guild)


async def setup(bot):
    await bot.add_cog(EventsCog(bot))

import asyncio

import discord
import os
import random
import copy

from dotenv import load_dotenv
from discord import app_commands

import utils.classes
from utils import DiscordClient
from utils import get_guild_info

load_dotenv()

DISCORD_TOKEN = os.getenv('BOT_TOKEN')

DEV_GUILD_ID = os.getenv('DEVELOPMENT_GUILD')
DEV = os.getenv('DEV_ID')

DEV = int(DEV) if DEV else None
MY_GUILD = discord.Object(id=int(DEV_GUILD_ID)) if DEV_GUILD_ID else None

intents = discord.Intents.default()
intents.message_content = True

client = DiscordClient(intents=intents, test_guild=MY_GUILD)


faction_cmds = app_commands.Group(name='faction', description='Commands to manage and view factions')
subalignment_cmds = app_commands.Group(name='subalignment', description='Commands to manage and view subalignments')
infotag_cmds = app_commands.Group(name='infotag', description='Commands to manage and view infotags')

faction_cmds.guild_only = True
subalignment_cmds.guild_only = True
infotag_cmds.guild_only = True


def mod_check(interaction: discord.Interaction) -> bool:
    if interaction.user.id == DEV:
        return True

    if interaction.user.guild_permissions.manage_channels:
        return True

    return False


async def sync_faction(faction: utils.Faction):
    forum_channel = client.get_channel(faction.id)
    guild_info = [g for g in client.guild_info if g.guild_id == forum_channel.guild.id][0]
    subalignments = guild_info.subalignments

    failed_roles = []
    roles = []

    guild_info_roles = [r for r in guild_info.roles if r.faction.id != faction.id]

    await add_archived_threads(forum_channel)

    for thread in forum_channel.threads:
        subalignment = None

        if thread.flags.pinned:
            continue

        for tag in thread.applied_tags:
            for subalign in subalignments:
                if subalign.id == tag.id:
                    subalignment = subalign
                    break
            if subalignment:
                break

        if subalignment:
            forum_tags = [str(t).lower() for t in thread.applied_tags if t.id != subalignment.id]
            roles.append(utils.Role(thread.name, thread.id, faction, subalignment, set(forum_tags)))

        if not subalignment:
            failed_roles.append(thread)

    guild_info_roles += roles
    guild_info.roles = guild_info_roles

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == guild_info.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    return roles, failed_roles


async def sync_infotags(info_category: utils.InfoCategory):
    forum_channel = client.get_channel(info_category.id)
    guild_info = [g for g in client.guild_info if g.guild_id == forum_channel.guild.id][0]

    failed_tags = []
    tags = []

    guild_info_tags = [r for r in guild_info.info_tags if r.id != info_category.id]

    await add_archived_threads(forum_channel)

    for thread in forum_channel.threads:
        if thread.flags.pinned:
            continue

        tags.append(utils.InfoTag(name=thread.name, id=thread.id))

    guild_info_tags += tags
    guild_info.info_tags = guild_info_tags

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == guild_info.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    return tags, failed_tags


async def sync_guild(guild: discord.Guild):
    guild_info = [g for g in client.guild_info if g.guild_id == guild.id]
    if not guild_info:
        return

    for faction in copy.deepcopy(guild_info[0].factions):
        await sync_faction(faction)

    for info_cat in guild_info[0].info_categories:
        await sync_infotags(info_cat)


def get_faction_roles(faction: utils.Faction) -> list[utils.Role]:
    forum_channel = client.get_channel(faction.id)
    guild_info = [g for g in client.guild_info if g.guild_id == forum_channel.guild.id][0]
    roles = []

    for role in guild_info.roles:
        if role.faction.id == faction.id:
            roles.append(role)

    return roles


def get_faction_subalignments(faction: utils.Faction) -> list[utils.Subalignment]:
    forum_channel = client.get_channel(faction.id)
    guild_info = [g for g in client.guild_info if g.guild_id == forum_channel.guild.id][0]

    subalignments = []
    for tag in forum_channel.available_tags:
        for subalignment in guild_info.subalignments:
            if tag.id == subalignment.id:
                subalignments.append(subalignment)

    return subalignments


def get_subalignment_roles(subalignment: utils.Subalignment) -> list[utils.Role]:
    for channel in client.get_all_channels():
        if isinstance(channel, discord.ForumChannel):
            for tag in channel.available_tags:
                if tag.id == subalignment.id:
                    guild = channel.guild

    guild_info = [g for g in client.guild_info if g.guild_id == guild.id][0]
    roles = []

    for role in guild_info.roles:
        if role.subalignment.id == subalignment.id:
            roles.append(role)

    return roles


def get_subalignment_faction(subalignment: utils.Subalignment) -> utils.Faction:
    for channel in client.get_all_channels():
        if isinstance(channel, discord.ForumChannel):
            for tag in channel.available_tags:
                if tag.id == subalignment.id:
                    guild = channel.guild
                    guild_info = [g for g in client.guild_info if g.guild_id == guild.id][0]
                    faction = [f for f in guild_info.factions if f.id == channel.id][0]

                    return faction


async def add_archived_threads(forum_channel: discord.ForumChannel):
    if forum_channel.id in client.populated_forum_ids:
        return

    async for thread in forum_channel.archived_threads(limit=None):
        # Add to dpy's internal cache lol
        thread.guild._threads[thread.id] = thread

    client.populated_forum_ids.append(forum_channel.id)


async def sync_all():
    for guild in client.guilds:
        await sync_guild(guild)


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')

    if not client.first_sync:
        while not client.db_loaded:
            await asyncio.sleep(1)

        await sync_all()
        client.first_sync = True


@client.event
async def on_thread_create(thread: discord.Thread):
    guild_info = [i for i in client.guild_info if i.guild_id == thread.guild.id]
    if not guild_info:
        return

    faction = [f for f in guild_info[0].factions if f.id == thread.parent_id]

    if faction:
        await sync_faction(faction[0])
        return

    infotag = [t for t in guild_info[0].info_categories if t.id == thread.parent_id]

    if infotag:
        await sync_infotags(infotag[0])
        return


@client.event
async def on_guild_join(guild: discord.Guild):
    guild_info = [i for i in client.guild_info if i.guild_id == guild.id]
    if guild_info:
        return

    client.guild_info.append(utils.GuildInfo(
        guild.id,
        list(),
        list(),
        list(),
        list(),
        list()
    ))


@client.event
async def on_raw_thread_update(payload: discord.RawThreadUpdateEvent):
    guild_info = [i for i in client.guild_info if i.guild_id == payload.guild_id]
    if not guild_info:
        return

    faction = [f for f in guild_info[0].factions if f.id == payload.parent_id]

    if faction:
        await sync_faction(faction[0])
        return

    infotag = [t for t in guild_info[0].info_categories if t.id == payload.parent_id]

    if infotag:
        await sync_infotags(infotag[0])
        return


@client.event
async def on_raw_thread_delete(payload: discord.RawThreadDeleteEvent):
    guild_info = [i for i in client.guild_info if i.guild_id == payload.guild_id]
    if not guild_info:
        return

    faction = [f for f in guild_info[0].factions if f.id == payload.parent_id]

    if faction:
        await sync_faction(faction[0])
        return

    infotag = [t for t in guild_info[0].info_categories if t.id == payload.parent_id]

    if infotag:
        ...
        return


@client.tree.error
async def error_handler(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error_message = str(error)

    if isinstance(error, app_commands.CommandInvokeError):
        original = error.original

        if isinstance(original, app_commands.TransformerError):
            error_message = 'Invalid option'

    embed = utils.create_embed(
        interaction.user,
        title='Error while running command!',
        description=error_message,
        color=discord.Color.brand_red()
    )

    await interaction.response.send_message(embed=embed)


@faction_cmds.command(name='add')
@app_commands.describe(forum_channel='The forum channel to assign the faction to')
@app_commands.describe(name='The name to give the faction')
@app_commands.check(mod_check)
async def faction_add(interaction: discord.Interaction, forum_channel: discord.ForumChannel, name: str):
    """Adds a faction to your server"""

    name = name.title()

    faction_info = utils.classes.Faction(id=forum_channel.id, name=name)
    guild_info = get_guild_info(interaction)

    duplicates = [d for d in guild_info.factions if d.id == forum_channel.id or d.name == name]

    if duplicates:
        raise app_commands.AppCommandError('Duplicate faction')

    guild_info.factions.append(faction_info)

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == interaction.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    embed = utils.create_embed(
        interaction.user,
        title='Faction added',
        description=f'Added {name} from {forum_channel.mention}'
    )

    await client.add_item_to_db(faction_info, 'factions')

    await interaction.response.send_message(embed=embed)


@faction_cmds.command(name='view')
@app_commands.describe(faction='The faction to view')
async def faction_view(
        interaction: discord.Interaction,
        faction: app_commands.Transform[utils.Faction, utils.FactionTransformer]
):
    """Get faction info"""
    roles = get_faction_roles(faction)
    subalignments = get_faction_subalignments(faction)

    embed = utils.create_embed(
        interaction.user,
        title='Faction info',
        description=f'{faction.name}: <#{faction.id}>\n\n'
                    f'**Amount of roles:** {len(roles)}\n'
                    f'**Amount of subalignments:** {len(subalignments)}'

    )

    await interaction.response.send_message(embed=embed)


@faction_cmds.command(name='remove')
@app_commands.describe(faction='The faction to remove from the bot database')
@app_commands.check(mod_check)
async def faction_remove(
        interaction: discord.Interaction,
        faction: app_commands.Transform[utils.Faction, utils.FactionTransformer]
):
    """Removes a faction"""
    guild_info: utils.GuildInfo = get_guild_info(interaction)
    faction_roles = get_faction_roles(faction)

    guild_info.factions.remove(faction)

    for role in faction_roles:
        guild_info.roles.remove(role)

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == interaction.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    embed = utils.create_embed(
        user=interaction.user,
        title='Faction Removed',
        description=f'Removed <#{faction.id}>'
    )

    await client.delete_item_from_db(faction, 'factions')

    await interaction.response.send_message(embed=embed)


@faction_cmds.command(name='sync')
@app_commands.describe(faction='The faction to sync')
@app_commands.check(mod_check)
async def faction_sync(
        interaction: discord.Interaction,
        faction: app_commands.Transform[utils.Faction, utils.FactionTransformer]
):
    """Sync faction's roles and subalignments manually"""
    roles, failed_roles = await sync_faction(faction)

    failed_str = '\n'.join(r.mention for r in failed_roles)
    if failed_str:
        failed_str = f'\n\nThreads unable to be synced due to lack of subalignment tag or duplicate name:\n' + failed_str

    embed = utils.create_embed(
        interaction.user,
        title='Faction Synced',
        description=f'Faction {faction.name} synced {len(roles)} roles' + failed_str
    )

    await interaction.response.send_message(embed=embed)


@subalignment_cmds.command(name='add')
@app_commands.describe(faction='The faction to add the subalignment to')
@app_commands.describe(forum_tag='The forum tag to associate with the subalignment, you need to select faction before this one')
@app_commands.check(mod_check)
async def subalignment_add(
        interaction: discord.Interaction,
        faction: app_commands.Transform[utils.Faction, utils.FactionTransformer],
        forum_tag: app_commands.Transform[discord.ForumTag, utils.ForumTagTransformer]
):
    """Add a subalignment to a faction"""
    guild_info = get_guild_info(interaction)
    subalignment = utils.Subalignment(forum_tag.name, forum_tag.id)
    guild_info.subalignments.append(subalignment)

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == interaction.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    embed = utils.create_embed(
        interaction.user,
        title='Subalignment added',
        description=f'Added {forum_tag.emoji} {forum_tag} to <#{faction.id}>'
    )

    await sync_faction(faction)
    await client.add_item_to_db(subalignment, 'subalignments')

    await interaction.response.send_message(embed=embed)


@subalignment_cmds.command(name='view')
@app_commands.describe(subalignment='The subalignment to view')
async def subalignment_view(
        interaction: discord.Interaction,
        subalignment: app_commands.Transform[utils.Subalignment, utils.SubalignmentTransformer]
):
    """Get info for a subalignment"""
    roles = get_subalignment_roles(subalignment)
    faction = get_subalignment_faction(subalignment)
    faction_channel = client.get_channel(faction.id)

    for tag in faction_channel.available_tags:
        if tag.id == subalignment.id:
            forum_tag = tag

    embed = utils.create_embed(
        interaction.user,
        title='Subalignment info',
        description=f'**Name:** {forum_tag.emoji} {subalignment.name.title()}\n'
                    f'**Main faction:** {faction}\n'
                    f'**Amount of roles:** {len(roles)}'
    )

    await interaction.response.send_message(embed=embed)


@subalignment_cmds.command(name='remove')
@app_commands.check(mod_check)
@app_commands.describe(subalignment='The subalignment to remove')
async def subalignment_remove(
        interaction: discord.Interaction,
        subalignment: app_commands.Transform[utils.Subalignment, utils.SubalignmentTransformer]
):
    """Removes a subalignment from the bot"""
    faction = get_subalignment_faction(subalignment)

    guild_info = get_guild_info(interaction)

    for role in get_subalignment_roles(subalignment):
        guild_info.roles.remove(role)

    guild_info.subalignments.remove(subalignment)

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == interaction.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    embed = utils.create_embed(
        interaction.user,
        title='Removed subalignment',
        description=f'Removed {subalignment.name} from <#{faction.id}>'
    )

    await sync_faction(faction)
    await client.delete_item_from_db(subalignment, 'subalignments')

    await interaction.response.send_message(embed=embed)


@client.tree.command(name='role')
@app_commands.guild_only()
@app_commands.describe(role='The role to view')
async def get_role(interaction: discord.Interaction, role: app_commands.Transform[utils.Role, utils.RoleTransformer]):
    """Get info on a role"""
    thread_channel = interaction.guild.get_channel_or_thread(role.id)
    starter_message = thread_channel.starter_message or await thread_channel.fetch_message(thread_channel.id)
    role_str = starter_message.content

    embed = utils.create_embed(
        interaction.user,
        title=f'{role.name}',
        description=f'Post: {thread_channel.mention}\n\n'
                    f'{role_str[:4000]}'
    )

    await interaction.response.send_message(embed=embed)


@client.tree.command(name='random')
@app_commands.describe(faction='Only get roles from this faction')
@app_commands.describe(amount='Amount of roles to generate, defaults to 1')
@app_commands.describe(subalignment='Only get roles from this subalignment')
@app_commands.describe(individuality='Whether to generate unique roles, defaults to false')
@app_commands.describe(include_tags='Only include roles containing atleast one of the provided comma-seperated list of forum tags')
@app_commands.describe(exclude_tags='Exclude roles that contain atleast one of the provided comma-seperated list of forum tags')
@app_commands.guild_only()
async def random_roles(
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 1,
        faction: app_commands.Transform[utils.Faction, utils.FactionTransformer] | None = None,
        subalignment: app_commands.Transform[utils.Subalignment, utils.SubalignmentTransformer] | None = None,
        individuality: bool = False,
        include_tags: str | None = '',
        exclude_tags: str | None = ''
):
    """Get random roles!"""
    guild_info = get_guild_info(interaction)
    split_include_tags = include_tags.split(',')
    split_exclude_tags = exclude_tags.split(',')

    valid_roles = []
    for role in guild_info.roles:
        if faction and role.faction.id != faction.id:
            continue

        if subalignment and role.subalignment.id != subalignment.id:
            continue

        role_thread = interaction.guild.get_channel_or_thread(role.id)
        role_thread_tags = [t.name.lower().strip() for t in role_thread.applied_tags]
        has_included_tag = not bool(include_tags)
        has_excluded_tag = False

        for exclude_tag in split_exclude_tags:
            normalized_e_tag = exclude_tag.lower().strip()
            if normalized_e_tag in role_thread_tags:
                has_excluded_tag = True

        for include_tag in split_include_tags:
            normalized_i_tag = include_tag.lower().strip()
            if normalized_i_tag in role_thread_tags:
                has_included_tag = True

        if has_excluded_tag or not has_included_tag:
            continue

        valid_roles.append(role)

    len_valid_roles = len(valid_roles)
    chosen_roles = []
    for _ in range(amount):
        if len(valid_roles) <= 0:
            raise app_commands.AppCommandError('Not enough valid roles')

        chosen_role = random.choice(valid_roles)
        chosen_roles.append(chosen_role)
        if individuality:
            valid_roles.remove(chosen_role)

    chosen_roles_str = '\n'.join([f'<#{r.id}>' for r in chosen_roles])

    embed = utils.create_embed(
        interaction.user,
        title=f'Generated {len(chosen_roles)} roles out of {len_valid_roles} possible roles!',
        description=chosen_roles_str
    )

    await interaction.response.send_message(embed=embed)


@client.tree.context_menu(name='Generate Threads With Mentions')
@app_commands.checks.has_permissions(manage_threads=True, create_private_threads=True)
@app_commands.checks.bot_has_permissions(manage_threads=True, create_private_threads=True)
@app_commands.guild_only()
async def generate_mod_threads(
        interaction: discord.Interaction,
        message: discord.Message
):
    """Generate mod threads using mentions from the provided message"""

    message_mentions = message.mentions

    if not interaction.channel.type == discord.ChannelType.text:
        raise app_commands.AppCommandError('Can\'t use in non-text channels!')

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


@infotag_cmds.command(name='add')
@app_commands.describe(forum_channel='The forum channel to associate with the infotag category')
@app_commands.describe(name='The name to give the category')
@app_commands.check(mod_check)
async def infotag_add(interaction: discord.Interaction, forum_channel: discord.ForumChannel, name: str):
    """Adds an infotag category"""

    guild_info = get_guild_info(interaction)
    infotag_category = utils.InfoCategory(name, forum_channel.id)
    guild_info.info_categories.append(infotag_category)

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == interaction.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    embed = utils.create_embed(
        interaction.user,
        title='Infotag Category added',
        description=f'Added {name} to {forum_channel.mention}'
    )

    await sync_infotags(infotag_category)
    await client.add_item_to_db(infotag_category, 'infotags')

    await interaction.response.send_message(embed=embed)


@infotag_cmds.command(name='remove')
@app_commands.describe(info_category='The infotag category to remove')
@app_commands.check(mod_check)
async def infotag_remove(
        interaction: discord.Interaction,
        info_category: app_commands.Transform[utils.InfoCategory, utils.InfoCategoryTransformer],
):
    """Removes an infotag"""
    guild_info = get_guild_info(interaction)
    guild_info.info_categories.remove(info_category)

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == interaction.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    embed = utils.create_embed(
        interaction.user,
        title='Removed subalignment',
        description=f'Removed {info_category.name}'
    )

    await sync_guild(interaction.guild)
    await client.delete_item_from_db(info_category, 'infotags')

    await interaction.response.send_message(embed=embed)


@infotag_cmds.command(name='view')
@app_commands.describe(info_category='The infotag category to get the tag of')
@app_commands.describe(info_tag='The infotag to view')
async def infotag_view(
        interaction: discord.Interaction,
        info_category: app_commands.Transform[utils.InfoCategory, utils.InfoCategoryTransformer],
        info_tag: app_commands.Transform[utils.InfoTag, utils.InfoTagTransformer]
):
    """View an infotag"""
    info_cat_channel = interaction.guild.get_channel_or_thread(info_category.id)
    info_tag_thread = info_cat_channel.get_thread(info_tag.id)
    info_tag_msg = info_tag_thread.starter_message or await info_tag_thread.fetch_message(info_tag_thread.id)

    embed = utils.create_embed(
        interaction.user,
        title=f'Infotag {info_category.name}:{info_tag.name}',
        description=f'{info_tag_thread.mention}\n\n' + info_tag_msg.content
    )

    await interaction.response.send_message(embed=embed)


@client.tree.command(name='syncall')
@app_commands.guild_only()
@app_commands.check(mod_check)
async def syncall(
        interaction: discord.Interaction,
        no_sync: bool = False
):
    """Manually sync everything in the server!"""

    await interaction.response.defer()

    if not no_sync:
        await sync_guild(interaction.guild)
        await asyncio.sleep(3)

    guild_info: utils.GuildInfo = get_guild_info(interaction)

    len_factions = len(guild_info.factions)
    len_subalignments = len(guild_info.subalignments)
    len_infocategories = len(guild_info.info_categories)
    len_roles = len(guild_info.roles)
    len_infotags = len(guild_info.info_tags)

    embed = utils.create_embed(
        interaction.user,
        title='Guild synced',
        description=f'Synced!\n\n'
                    f'**Factions:** {len_factions}\n'
                    f'**Subalignments:** {len_subalignments}\n'
                    f'**Info Categories:** {len_infocategories}\n\n'
                    f'**Roles:** {len_roles}\n'
                    f'**Info tags:** {len_infotags}'
    )

    await interaction.followup.send(embed=embed)


@client.tree.command(name='eval')
@app_commands.check(lambda i: i.user.id == DEV)
async def dev_eval(interaction: discord.Interaction):
    """Dev only"""
    await interaction.response.send_modal(utils.DevEval())

if __name__ == '__main__':
    client.tree.add_command(faction_cmds)
    client.tree.add_command(subalignment_cmds)
    client.tree.add_command(infotag_cmds)

    client.run(DISCORD_TOKEN)

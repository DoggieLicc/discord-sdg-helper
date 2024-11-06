import asyncio
import discord
import os
import random
import copy
import traceback

from dotenv import load_dotenv
from discord import app_commands

import utils.classes

from utils import DiscordClient, Role, Faction, Subalignment, InfoCategory, InfoTag, GuildInfo, PaginatedMenu, SDGException
from utils import get_guild_info, get_rolelist, generate_rolelist_roles

load_dotenv()

DISCORD_TOKEN = os.getenv('BOT_TOKEN')

DEV_GUILD_ID = os.getenv('DEVELOPMENT_GUILD')
DEV = os.getenv('DEV_ID')

DEV = int(DEV) if DEV else None
MY_GUILD = discord.Object(id=int(DEV_GUILD_ID)) if DEV_GUILD_ID else None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = DiscordClient(intents=intents, test_guild=MY_GUILD)


faction_cmds = app_commands.Group(name='faction', description='Commands to manage and view factions')
subalignment_cmds = app_commands.Group(name='subalignment', description='Commands to manage and view subalignments')
infotag_cmds = app_commands.Group(name='infotag', description='Commands to manage and view infotags')
random_cmds = app_commands.Group(name='random', description='Randomization commands')
trust_cmds = app_commands.Group(name='trust', description='Commands to manage trust of roles/members')

faction_cmds.guild_only = True
subalignment_cmds.guild_only = True
infotag_cmds.guild_only = True
random_cmds.guild_only = True
trust_cmds.guild_only = True

admin_perms = discord.Permissions.none()
admin_perms.manage_guild = True

trust_cmds.default_permissions = admin_perms


client.allowed_mentions = discord.AllowedMentions(users=True, replied_user=True, everyone=False, roles=False)


def mod_check(interaction: discord.Interaction) -> bool:
    guild_info = get_guild_info(interaction)

    if interaction.user.id == DEV:
        return True

    if interaction.user.guild_permissions.manage_channels:
        return True

    if interaction.user.id in guild_info.trusted_ids:
        return True

    for role in interaction.user.roles:
        if role.id in guild_info.trusted_ids:
            return True

    return False


async def sync_faction(faction: Faction):
    forum_channel = client.get_channel(faction.id)
    guild_info = [g for g in client.guild_info if g.guild_id == forum_channel.guild.id][0]
    subalignments = guild_info.subalignments

    failed_roles = []
    roles = []

    guild_info_roles = [r for r in guild_info.roles if r.faction.id != faction.id]
    pre_faction_roles = [r for r in guild_info.roles if r.faction.id == faction.id]
    pre_faction_roles_ids = [r.id for r in pre_faction_roles]

    roles += pre_faction_roles

    await add_archived_threads(forum_channel)

    for thread in forum_channel.threads:
        subalignment = None

        if thread.flags.pinned:
            continue

        if thread.id in pre_faction_roles_ids:
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
            roles.append(Role(thread.name, thread.id, faction, subalignment, set(forum_tags)))

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


async def sync_infotags(info_category: InfoCategory):
    forum_channel = client.get_channel(info_category.id)
    guild_info = [g for g in client.guild_info if g.guild_id == forum_channel.guild.id][0]

    failed_tags = []
    tags = []

    guild_info_tags = [r for r in guild_info.info_tags if r.id != info_category.id]
    guild_info_tags_ids = [t.id for t in guild_info_tags]

    await add_archived_threads(forum_channel)

    for thread in forum_channel.threads:
        if thread.flags.pinned:
            continue

        if thread.id in guild_info_tags_ids:
            continue

        tags.append(InfoTag(name=thread.name, id=thread.id))

    guild_info_tags += tags
    guild_info.info_tags = guild_info_tags

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == guild_info.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    return tags, failed_tags


async def sync_guild(guild: discord.Guild) -> dict[int, list[discord.Thread]]:
    guild_info = [g for g in client.guild_info if g.guild_id == guild.id]
    if not guild_info:
        return

    failed_factions = {}

    for faction in copy.deepcopy(guild_info[0].factions):
        _, failed_roles = await sync_faction(faction)
        failed_factions[faction.id] = failed_roles

    for info_cat in guild_info[0].info_categories:
        await sync_infotags(info_cat)

    return failed_factions


def get_faction_roles(faction: Faction) -> list[Role]:
    forum_channel = client.get_channel(faction.id)
    guild_info = [g for g in client.guild_info if g.guild_id == forum_channel.guild.id][0]
    roles = []

    for role in guild_info.roles:
        if role.faction.id == faction.id:
            roles.append(role)

    return roles


def get_faction_subalignments(faction: Faction) -> list[Subalignment]:
    forum_channel = client.get_channel(faction.id)
    guild_info = [g for g in client.guild_info if g.guild_id == forum_channel.guild.id][0]

    subalignments = []
    for tag in forum_channel.available_tags:
        for subalignment in guild_info.subalignments:
            if tag.id == subalignment.id:
                subalignments.append(subalignment)

    return subalignments


def get_subalignment_roles(subalignment: Subalignment) -> list[Role]:
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


def get_subalignment_faction(subalignment: Subalignment) -> Faction:
    for channel in client.get_all_channels():
        if isinstance(channel, discord.ForumChannel):
            for tag in channel.available_tags:
                if tag.id == subalignment.id:
                    guild = channel.guild
                    guild_info = [g for g in client.guild_info if g.guild_id == guild.id][0]
                    faction = [f for f in guild_info.factions if f.id == channel.id][0]

                    return faction


async def add_archived_threads(forum_channel: discord.ForumChannel, force: bool = False):
    if forum_channel.id in client.populated_forum_ids and not force:
        return

    async for thread in forum_channel.archived_threads(limit=None):
        # Add to dpy's internal cache lol
        thread.guild._threads[thread.id] = thread

    if not force:
        client.populated_forum_ids.append(forum_channel.id)


async def sync_all():
    for guild in client.guilds:
        await sync_guild(guild)

    print('ALL GUILDS SYNCED!')


class RoleFactionMenu(PaginatedMenu):
    def format_line(self, item: Role) -> str:
        faction_channel = client.get_channel(item.faction.id)
        sub_tag = faction_channel.get_tag(item.subalignment.id)
        return f'{sub_tag.emoji} {item.name} (<#{item.id}>)'

    async def get_page_contents(self) -> dict:
        page = self.paginator.pages[self.current_page-1]
        embed = utils.create_embed(
            self.owner,
            title=f'Listing roles ({self.current_page}/{self.max_page})',
            description=page
        )
        return {'embed': embed}


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

    client.guild_info.append(GuildInfo(
        guild.id,
        list(),
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

    guild_info = guild_info[0]

    guild = client.get_guild(payload.guild_id)
    thread = payload.thread or await guild.fetch_channel(payload.thread_id)

    if thread not in guild._threads.values():
        print(f'Adding {thread.name} ({thread.id}) to cache')
        guild._threads[thread.id] = thread

    faction = [f for f in guild_info.factions if f.id == payload.parent_id]

    if faction:
        roles = [r for r in get_faction_roles(faction[0]) if r.id != payload.thread_id]
        guild_info.roles = roles

    infotag = [t for t in guild_info.info_categories if t.id == payload.parent_id]

    if infotag:
        infotags = [t for t in guild_info.info_tags if t.id != payload.thread_id]
        guild_info.info_tags = infotags

    if faction or infotag:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == payload.guild_id][0])
        client.guild_info.append(guild_info)
        await sync_guild(guild)


@client.event
async def on_raw_thread_delete(payload: discord.RawThreadDeleteEvent):
    guild_info = [i for i in client.guild_info if i.guild_id == payload.guild_id]
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
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == payload.guild_id][0])
        client.guild_info.append(guild_info)


@client.tree.error
async def error_handler(interaction: discord.Interaction, error: app_commands.AppCommandError):
    error_message = None

    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original

    if isinstance(error, app_commands.TransformerError):
        error_message = f'Invalid option "{error.value}" for {error.type}'

    if isinstance(error, app_commands.CheckFailure):
        error_message = 'You aren\'t allowed to use that command!'

    if isinstance(error, app_commands.MissingPermissions):
        error_message = f'You are missing the following permissions: {error.missing_permissions}'

    if isinstance(error, app_commands.BotMissingPermissions):
        error_message = f'The bot is missing the following permissions: {error.missing_permissions}'

    if isinstance(error, SDGException):
        error_message = str(error)

    if not error_message:
        error_message = f'An unknown error occurred: {error}\n\nError info will be sent to owner'

        etype = type(error)
        trace = error.__traceback__
        lines = traceback.format_exception(etype, error, trace)
        traceback_t: str = ''.join(lines)

        print(traceback_t)
        file = utils.str_to_file(traceback_t, filename='traceback.py')

        owner: discord.User = client.get_user(DEV)

        if owner:
            owner_embed = utils.create_embed(
                interaction.user,
                title='Unhandled error occurred!',
                color=discord.Color.red()
            )

            owner_embed.add_field(name='Unhandled Error!:', value=f"Error {error}", inline=False)
            owner_embed.add_field(name='Command:', value=str(interaction.data)[:1000], inline=False)

            owner_embed.add_field(
                name='Extra Info:',
                value=f'Guild: {interaction.guild}: {getattr(interaction.guild, "id", "None")}\n'
                      f'Channel: {interaction.channel.mention}:{interaction.channel.id}', inline=False
            )

            await owner.send(embed=owner_embed, files=[file])

    embed = utils.create_embed(
        interaction.user,
        title='Error while running command!',
        description=error_message,
        color=discord.Color.brand_red()
    )

    try:
        await interaction.response.send_message(embed=embed)
    except discord.InteractionResponded:
        try:
            await interaction.channel.send(embed=embed)
        except discord.DiscordException:
            print(f'Unable to respond to exception in {interaction.channel.name} ({interaction.channel.id})')


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
        faction: app_commands.Transform[Faction, utils.FactionTransformer]
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
        faction: app_commands.Transform[Faction, utils.FactionTransformer]
):
    """Removes a faction"""
    guild_info: GuildInfo = get_guild_info(interaction)
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
        faction: app_commands.Transform[Faction, utils.FactionTransformer]
):
    """Sync faction's roles and subalignments manually"""
    roles, failed_roles = await sync_faction(faction)

    failed_str = '\n'.join(r.mention for r in failed_roles)
    if failed_str:
        failed_str = f'\n\nThreads unable to be synced due to lack of subalignment tag:\n' + failed_str

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
        faction: app_commands.Transform[Faction, utils.FactionTransformer],
        forum_tag: app_commands.Transform[discord.ForumTag, utils.ForumTagTransformer]
):
    """Add a subalignment to a faction"""
    guild_info = get_guild_info(interaction)
    subalignment = Subalignment(forum_tag.name, forum_tag.id)
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
        subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer]
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
                    f'**Main faction:** <#{faction.id}>\n'
                    f'**Amount of roles:** {len(roles)}'
    )

    await interaction.response.send_message(embed=embed)


@subalignment_cmds.command(name='remove')
@app_commands.check(mod_check)
@app_commands.describe(subalignment='The subalignment to remove')
async def subalignment_remove(
        interaction: discord.Interaction,
        subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer]
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
async def get_role(interaction: discord.Interaction, role: app_commands.Transform[Role, utils.RoleTransformer]):
    """Get info on a role"""
    thread_channel = interaction.guild.get_channel_or_thread(role.id)
    starter_message = thread_channel.starter_message or await thread_channel.fetch_message(thread_channel.id)
    role_str = starter_message.content
    message_image = starter_message.attachments[0] if starter_message.attachments else None

    embed = utils.create_embed(
        interaction.user,
        title=f'{role.name}',
        thumbnail=message_image,
        description=f'Post: {thread_channel.mention}\n\n'
                    f'{role_str[:4000]}'
    )

    await interaction.response.send_message(embed=embed)


@random_cmds.command(name='roles')
@app_commands.describe(faction='Only get roles from this faction')
@app_commands.describe(amount='Amount of roles to generate, defaults to 1')
@app_commands.describe(subalignment='Only get roles from this subalignment')
@app_commands.describe(individuality='Whether to generate unique roles, defaults to false')
@app_commands.describe(include_tags='Only include roles containing atleast one of the provided comma-seperated list of forum tags')
@app_commands.describe(exclude_tags='Exclude roles that contain atleast one of the provided comma-seperated list of forum tags')
async def random_roles(
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 1,
        faction: app_commands.Transform[Faction, utils.FactionTransformer] | None = None,
        subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer] | None = None,
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

    chosen_roles_str = '\n'.join([f'{r.name} (<#{r.id}>)' for r in chosen_roles])

    embed = utils.create_embed(
        interaction.user,
        title=f'Generated {len(chosen_roles)} roles out of {len_valid_roles} possible roles!',
        description=chosen_roles_str
    )

    await interaction.response.send_message(embed=embed)


@random_cmds.command(name='faction')
@app_commands.describe(amount='Amount of factions to generate, defaults to 1')
@app_commands.describe(individuality='Whether to generate unique factions, defaults to false')
async def random_faction(
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 1,
        individuality: bool = False,
):
    """Generate random factions"""
    guild_info = get_guild_info(interaction)

    valid_factions = copy.deepcopy(guild_info.factions)
    len_valid_factions = len(valid_factions)
    chosen_factions = []
    for _ in range(amount):
        if len(valid_factions) <= 0:
            raise app_commands.AppCommandError('Not enough valid factions')

        chosen_faction = random.choice(valid_factions)
        chosen_factions.append(chosen_faction)
        if individuality:
            valid_factions.remove(chosen_faction)

    chosen_factions_str = '\n'.join([f'<#{r.id}>' for r in chosen_factions])

    embed = utils.create_embed(
        interaction.user,
        title=f'Generated {len(chosen_factions)} factions out of {len_valid_factions} possible factions!',
        description=chosen_factions_str
    )

    await interaction.response.send_message(embed=embed)


@random_cmds.command(name='members')
@app_commands.describe(amount='Amount of members to generate, defaults to 1')
@app_commands.describe(individuality='Whether to generate unique members, defaults to true')
@app_commands.describe(role='Only get members from this role')
async def random_members(
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 1,
        individuality: bool = True,
        role: discord.Role | None = None
):
    """Get random server members!"""
    valid_members = role.members if role else list(interaction.guild.members)
    len_valid_members = len(valid_members)
    chosen_members = []
    for _ in range(amount):
        if len(valid_members) <= 0:
            raise app_commands.AppCommandError('Not enough valid members')

        chosen_member = random.choice(valid_members)
        chosen_members.append(chosen_member)
        if individuality:
            valid_members.remove(chosen_member)

    chosen_members_str = '\n'.join([m.mention for m in chosen_members])

    embed = utils.create_embed(
        interaction.user,
        title=f'Generated {len(chosen_members)} members out of {len_valid_members} possible members!',
        description=chosen_members_str
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
        info_category: app_commands.Transform[InfoCategory, utils.InfoCategoryTransformer],
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
        info_category: app_commands.Transform[InfoCategory, utils.InfoCategoryTransformer],
        info_tag: app_commands.Transform[InfoTag, utils.InfoTagTransformer]
):
    """View an infotag"""
    info_cat_channel = interaction.guild.get_channel_or_thread(info_category.id)
    info_tag_thread = info_cat_channel.get_thread(info_tag.id)

    if not info_tag_thread:
        await add_archived_threads(info_cat_channel, force=True)
        info_tag_thread = info_cat_channel.get_thread(info_tag.id)

    info_tag_msg = info_tag_thread.starter_message or await info_tag_thread.fetch_message(info_tag_thread.id)
    message_image = info_tag_msg.attachments[0] if info_tag_msg.attachments else None

    embed = utils.create_embed(
        interaction.user,
        title=f'Infotag {info_category.name}:{info_tag.name}',
        thumbnail=message_image,
        description=f'{info_tag_thread.mention}\n\n' + info_tag_msg.content
    )

    await interaction.response.send_message(embed=embed)


@client.tree.command(name='maintenance')
@app_commands.guild_only()
@app_commands.check(mod_check)
async def maintenance(
        interaction: discord.Interaction,
):
    """Get maintenance info for this server"""

    await interaction.response.defer()

    failed_factions = await sync_guild(interaction.guild)

    guild_info: GuildInfo = get_guild_info(interaction)

    len_factions = len(guild_info.factions)
    len_subalignments = len(guild_info.subalignments)
    len_infocategories = len(guild_info.info_categories)
    len_roles = len(guild_info.roles)
    len_infotags = len(guild_info.info_tags)

    embed = utils.create_embed(
        interaction.user,
        title='Maintenance info!',
        description=f'If there are failed roles, make sure your subalignments are set up properly!\n\n'
                    f'**Factions:** {len_factions}\n'
                    f'**Subalignments:** {len_subalignments}\n'
                    f'**Info Categories:** {len_infocategories}\n\n'
                    f'**Roles:** {len_roles}\n'
                    f'**Info tags:** {len_infotags}'
    )

    for k, v in failed_factions.items():
        if not v:
            continue

        faction = [f for f in guild_info.factions if f.id == k][0]
        failed_str = '\n'.join(r.mention for r in v)
        embed.add_field(
            name=f'Failed roles in {faction.name}',
            value=failed_str[:1000],
            inline=False
        )
        embed.colour = discord.Color.yellow()

    await interaction.followup.send(embed=embed)


@client.tree.command(name='eval')
@app_commands.check(lambda i: i.user.id == DEV)
async def dev_eval(interaction: discord.Interaction):
    """Dev only"""
    await interaction.response.send_modal(utils.DevEval())


@client.tree.context_menu(name='Generate Rolelist Roles')
@app_commands.guild_only()
async def generate_rolelist(
        interaction: discord.Interaction,
        message: discord.Message
):
    """Generate rolelist roles"""

    channel_mentions = message.channel_mentions
    cleaned_content = message.content
    guild_info = get_guild_info(interaction)

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

    rolelist_info = get_rolelist(cleaned_content, all_roles=guild_info.roles)
    roles = generate_rolelist_roles(rolelist_info, guild_info.roles)

    roles_str = '\n'.join(f'{r.name} (<#{r.id}>)' for r in roles)

    await interaction.response.send_message(roles_str)


@client.tree.command(name='anonpoll')
@app_commands.describe(poll_question='The question to ask')
@app_commands.describe(poll_options='The comma-seperated list of options, defaults to "INNOCENT, GUILTY, ABSTAIN"')
@app_commands.describe(include_role_1='If included roles are set, only members with those roles can vote')
@app_commands.describe(exclude_role_1='Players with excluded roles can\'t vote')
@app_commands.guild_only()
async def start_anonpoll(
        interaction: discord.Interaction,
        poll_question: str,
        poll_options: str = 'INNOCENT, GUILTY, ABSTAIN',
        include_role_1: discord.Role | None = None,
        include_role_2: discord.Role | None = None,
        include_role_3: discord.Role | None = None,
        exclude_role_1: discord.Role | None = None,
        exclude_role_2: discord.Role | None = None,
        exclude_role_3: discord.Role | None = None
):
    """Starts a hidden poll that sends votes to a private thread"""

    include_role_1 = [include_role_1] if include_role_1 else list()
    include_role_2 = [include_role_2] if include_role_2 else list()
    include_role_3 = [include_role_3] if include_role_3 else list()
    exclude_role_1 = [exclude_role_1] if exclude_role_1 else list()
    exclude_role_2 = [exclude_role_2] if exclude_role_2 else list()
    exclude_role_3 = [exclude_role_3] if exclude_role_3 else list()

    included_roles = include_role_1 + include_role_2 + include_role_3
    excluded_roles = exclude_role_1 + exclude_role_2 + exclude_role_3

    poll_options = poll_options.split(',')
    poll_options = [o.strip() for o in poll_options]

    if not poll_options:
        raise SDGException('No poll options!')

    private_thread = await interaction.channel.create_thread(name=f'Poll results: {poll_question}', invitable=False)
    await private_thread.send(interaction.user.mention)

    view = discord.ui.View(timeout=None)
    select = utils.PollSelect(
        thread=private_thread,
        included_roles=included_roles,
        excluded_roles=excluded_roles,
        placeholder=poll_question
    )
    button = utils.PollSelectButton(allowed_user=interaction.user, custom_id=f'button:stop:{private_thread.id}')

    view.add_item(select)
    view.add_item(button)

    for option in poll_options[:25]:
        select.add_option(label=option[:100])

    await interaction.response.send_message(poll_question, view=view)


@trust_cmds.command(name='add')
@app_commands.describe(trustee='The member or role you want to give trust to')
async def trust_add(interaction: discord.Interaction, trustee: discord.Member | discord.Role):
    """Allow a role/member access to special commands"""
    guild_info = get_guild_info(interaction)

    if trustee.id in guild_info.trusted_ids:
        embed = utils.create_embed(
            interaction.user,
            title='Role/member already trusted!',
            description='The provided role/member is already trusted',
            color=discord.Color.red()
        )

        return await interaction.response.send_message(embed=embed)

    guild_info.trusted_ids.append(trustee.id)

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == interaction.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    await client.add_trusted_id_in_db(trustee.id, interaction.guild_id)

    embed = utils.create_embed(
        interaction.user,
        title='Added trustee!',
        description=f'Added trust to {trustee.mention}'
    )

    await interaction.response.send_message(embed=embed)


@trust_cmds.command(name='remove')
@app_commands.describe(trustee='The trusted member or role you want remove')
async def trust_remove(interaction: discord.Interaction, trustee: discord.Member | discord.Role):
    """Removes trust from role or member"""
    guild_info = get_guild_info(interaction)

    try:
        guild_info.trusted_ids.remove(trustee.id)
    except ValueError:
        embed = utils.create_embed(
            interaction.user,
            title='Role/member not in list!',
            description='The provided role/member isn\'t in the trustee list',
            color=discord.Color.red()
        )

        return await interaction.response.send_message(embed=embed)

    try:
        client.guild_info.remove([gi for gi in client.guild_info if gi.guild_id == interaction.guild_id][0])
    except ValueError:
        pass

    client.guild_info.append(guild_info)

    await client.delete_trusted_id_in_db(trustee.id)

    embed = utils.create_embed(
        interaction.user,
        title='Deleted trustee!',
        description=f'Deleted trust from {trustee.mention}'
    )

    await interaction.response.send_message(embed=embed)


@trust_cmds.command(name='list')
async def trust_view(interaction: discord.Interaction):
    """List all members/roles that are trusted"""
    guild_info = get_guild_info(interaction)

    trusted_strs = []

    for trusted in guild_info.trusted_ids:
        role = interaction.guild.get_role(trusted)
        if role:
            trusted_strs.append(role.mention)
            continue

        trusted_strs.append(f'<@{trusted}>')

    trusted_str = '\n'.join(trusted_strs) or 'No roles or members are trusted yet! (/trust add)'

    embed = utils.create_embed(
        interaction.user,
        title='List of trusted members/roles:',
        description=trusted_str
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@client.tree.command(name='listroles')
@app_commands.describe(faction='List roles part of this faction')
@app_commands.describe(subalignment='List roles part of this subalignment')
@app_commands.describe(include_tags='List roles that has atleast one of these comma-seperated forum tags')
@app_commands.describe(exclude_tags='Don\'t list roles that have any of these comma-seperated forum tags')
async def list_roles(
    interaction: discord.Interaction,
    faction: app_commands.Transform[Faction, utils.FactionTransformer] | None = None,
    subalignment: app_commands.Transform[Subalignment, utils.SubalignmentTransformer] | None = None,
    include_tags: str | None = '',
    exclude_tags: str | None = ''
):
    """Lists all roles that fit the filters"""
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

    valid_roles.sort(key=lambda r: r.subalignment.name)

    if not valid_roles:
        raise SDGException('No valid roles fit those filters!')

    view = RoleFactionMenu(
        owner=interaction.user,
        items=valid_roles
    )

    contents = await view.get_page_contents()

    if view.max_page == 1:
        view = discord.utils.MISSING

    await interaction.response.send_message(view=view, **contents)


if __name__ == '__main__':
    client.tree.add_command(faction_cmds)
    client.tree.add_command(subalignment_cmds)
    client.tree.add_command(infotag_cmds)
    client.tree.add_command(random_cmds)
    client.tree.add_command(trust_cmds)

    client.run(DISCORD_TOKEN)

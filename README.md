# SDG Helper

A helper for social-deduction games hosted on Discord

This bot runs on [discord.py](https://github.com/Rapptz/discord.py)

## Invite this bot:
[Invite Link](https://discord.com/oauth2/authorize?client_id=1299302394299158538), it's recommended to not remove any permissions, as some or all commands may stop working

## Self-hosting guide:

1. Create a bot account in the Discord Dev portal and invite it to your server. - [Guide](https://discordpy.readthedocs.io/en/latest/discord.html)

2. Enable member and message intents - [Example](https://discordpy.readthedocs.io/en/latest/intents.html#privileged-intents)

3. Install the latest version of python if you don't have it already. - [Download](https://www.python.org/downloads/)

4. Download the source code either by using the "Download ZIP" option or running

```git clone https://github.com/DoggieLicc/discord-sdg-helper```

5. Open a terminal/command prompt in the `discord-sdg-helper` folder
6. Create a virtual environment: `python -m venv .venv`
7. Activate the virtual environment: `.venv\Scripts\activate` (command prompt) or `source ./.venv/bin/activate` (linux)
8. Install requirements: `pip install -r requirements.txt`
9. Create a file named `.env`
10. Edit it and add `BOT_TOKEN=<token>` where `<token>` is the bot's token you got from step 1, then save
11. Run the main script: `python main.py`

## How to use this bot:
This bot uses the slash commands system provided by Discord. Type `/` to see the available commands

# Rolelist Generation

To use this function, right-click/tap on a message, and click "Generate Rolelist Roles" under Apps
Before using this, make sure all your factions and subalignments are defined properly

## Symbols:
### Filters:
% - Role

$ - Faction (You can also use #forum)

(no symbol is for forum tags)

ANY - No filter (dont combine with ! ...)

### Logic: 
& - Seperator

| - Union (Roles only have to be part of atleast one of the unioned filters)

! - Negation (Will negate the next filter's roles)

### Global Filters:
Lines starting with + will apply to all slots, except slots starting with -

Examples:

`%Jailor` - Gets Jailor role

`Town Killing` - Gets role with the Town Killing forum tag

`$Town` - Gets role from the Town faction

`!Dogflummery` - Gets any role that doesnt have Dogflummery forum tag

`$Coven&Balanced` - Gets any Coven role with Balanced tag

`Town Power|Town Killing!Dogflummery&Reworked` - Get any role that has either the Town Power or Town Killing tag, and doesn't have Dogflummery tag, and has the Reworked tag

`+!Dogflummery|!Cursed` - Global filter that makes all slots generate roles that dont have the Doglummery or Cursed tag

`-ANY` - Get any role, without applying global filters

### Modifiers

Modifiers change how all slots generate in unique ways.

Modifiers start with `?` and can have arguments seperated by `:`

* limit:**filters**:*amount*

Limits the amount of the filtered roles that can generate. If the filters correspond to multiple roles, the limit will be shared between them. If no amount is provided, it will be one by default

Examples:

`?limit:$Coven:4` - Caps spawning of coven faction roles at 4

`?limit:%Mayor` - Caps spawning of Mayor at 1, the default. Essentially makes it unique

* individuality:*filters*

Makes it so that all filtered roles will only spawn a maximum of 1. If no filters are supplied, all roles become unique 

Examples:

`?individuality:Town Power` - Makes all roles with Town Power tag unique

`?individuality:$Mafia!%Consort` - Makes all roles part of Mafia faction unique, except Consort

* exclusive:**filters**

Makes all filtered roles mutually exclusive to each other, meaning if one generates, the rest of them cant.

Examples:

`?exclusive:%Warlock|%Soul Collector` - Makes Warlock and Soul Collector mutually exclusive 

`?exclusive:Town Power|Town Killing` - Makes all roles with either Town Power tag or Town Killing tag mutually exclusive to eachother

### Weights

You can change the weight of roles to make them more or less likely to spawn

For example, multiplying the weight of Sheriff by 10 will give it 10 times the chance to spawn in all slots it can generate in

The default weight for all roles is `10`

Format: `=filter:weight`

Examples:

`=%Sheriff:x10` - Multiply weight of sheriff by 10 (100)

`=$Town:/2` - Divide weight of all town roles by 2 (5)

`=Cursed:-9` - Subtracts the weight of all roles with Cursed tag by 9 (1)

`=Town Power:+40` - Adds the weight of all roles with Town Power tag by 40 (50)

`=%Cleric:1000` - Sets weight of cleric spawning to 1000

If the filter matches no roles, or if the weight of a role <= 0, generation will fail.
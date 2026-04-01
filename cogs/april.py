import random

import discord

from discord import app_commands, Interaction
from discord.ext import commands

import utils


class AprilCog(commands.Cog):
    def __init__(self, client):
        self.client: utils.DiscordClient = client
        self.data_channel_ids = [1279223636141801522, 1302039731856740374, 1290128336902946877, 1279867650939293828, 1302052417289850940, 1283183863048441928, 1302333888068190338, 1305990115432206398, 1306323545097244863, 1279223581733290106, 1306658816506466399, 1279223556286316597]
        self.thread_mgs = []

    async def cog_load(self):
        await self.client.wait_until_ready()
        guild = self.client.get_guild(1279220317826580510)
        for d_c_i in self.data_channel_ids:
            forum_channel = guild.get_channel(d_c_i)
            async for t in forum_channel.archived_threads(limit=None):
                try:
                    self.thread_mgs.append(t.starter_message or await t.fetch_message(t.id))
                except discord.DiscordException:
                    pass

    @app_commands.command(name='airole')
    @app_commands.describe(ephemeral='Whether to only show the response to you. Defaults to False')
    async def generate_role(
            self,
            interaction: Interaction,
            ephemeral: bool = False
    ):
        """Use the latest and most modern models to generate a new role! ...Might be slow..."""

        await interaction.response.defer(ephemeral=ephemeral)

        msg_l = []
        for _ in range(random.randint(15, 20)):
            tok_l = []
            while len(tok_l) < random.randint(5, 15):
                msg = random.choice(self.thread_mgs)
                toks_l = [l for l in msg.content.splitlines() if l]
                toks = random.choice(toks_l).split(' ')
                for __ in range(random.randint(5,10)):
                    r_tok = random.choice(toks)
                    if r_tok not in tok_l:
                        tok_l.append(r_tok)

            msg_l.append(' '.join(tok_l))

        embed = utils.create_embed(interaction.user, title='AI Generated Role', description='\n\n'.join(msg_l)[:4000])

        await interaction.edit_original_response(embed=embed)


async def setup(bot):
    await bot.add_cog(AprilCog(bot))

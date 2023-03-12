from contextlib import suppress
from io import BytesIO
from typing import Optional

import discord
from redbot.core import commands

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import FMMixin

command_fm = FMMixin.command_fm
command_fm_server = FMMixin.command_fm_server

with suppress(Exception):
    from wordcloud import WordCloud


async def wordcloud_available(ctx):
    return "WordCloud" in globals().keys()


class WordCloudMixin(MixinMeta):
    """WordCloud Commands"""

    def wordcloud_create(self):
        if "WordCloud" in globals().keys():
            self.wc = WordCloud(width=1920, height=1080, mode="RGBA", background_color=None)

    @command_fm.group(name="wordcloud", aliases=["cloud", "wc"])
    @commands.check(wordcloud_available)
    @commands.bot_has_permissions(attach_files=True)
    async def command_wordcloud(self, ctx):
        """WordCloud Commands

        Original idea: http://lastfm.dontdrinkandroot.net"""

    @command_wordcloud.command(name="artists", aliases=["artist"])
    @commands.max_concurrency(1, commands.BucketType.user)
    async def command_wordcloud_artists(self, ctx, user: Optional[discord.Member] = None):
        """Get a picture with the most listened to artists."""
        user = user or ctx.author
        async with ctx.typing():
            conf = await self.config.user(user).all()
            self.check_if_logged_in(conf, user == ctx.author)
            name = conf["lastfm_username"]
            data = await self.api_request(
                ctx, {"user": name, "method": "user.gettopartists", "period": "overall"}
            )
            artists = data["topartists"]["artist"]
            if not artists:
                return await ctx.send(f"{name} has not listened to any artists yet!")
            data = {a["name"]: int(a["playcount"]) for a in artists}
            wc = await self.bot.loop.run_in_executor(None, self.wc.generate_from_frequencies, data)
            pic = BytesIO()
            pic.name = f"{name}_artists.png"
            wc.to_file(pic)
            pic.seek(0)
            await ctx.send(f"{name}'s artist cloud:", file=discord.File(pic))
        pic.close()

    @command_wordcloud.command(name="tracks", aliases=["track"])
    @commands.max_concurrency(1, commands.BucketType.user)
    async def command_wordcloud_tracks(self, ctx, user: Optional[discord.Member] = None):
        """Get a picture with the most listened to tracks."""
        user = user or ctx.author
        async with ctx.typing():
            conf = await self.config.user(user).all()
            self.check_if_logged_in(conf, user == ctx.author)
            name = conf["lastfm_username"]
            data = await self.api_request(
                ctx, {"user": name, "method": "user.gettoptracks", "period": "overall"}
            )
            tracks = data["toptracks"]["track"]
            if not tracks:
                return await ctx.send(f"{name} has not listened to any tracks yet!")
            data = {a["name"]: int(a["playcount"]) for a in tracks}
            wc = await self.bot.loop.run_in_executor(None, self.wc.generate_from_frequencies, data)
            pic = BytesIO()
            pic.name = f"{name}_tracks.png"
            wc.to_file(pic)
            pic.seek(0)
            await ctx.send(f"{name}'s track cloud:", file=discord.File(pic))
        pic.close()

    @command_wordcloud.command(name="albums", aliases=["album"])
    @commands.max_concurrency(1, commands.BucketType.user)
    async def command_wordcloud_albums(self, ctx, user: Optional[discord.Member] = None):
        """Get a picture with the most listened to albums."""
        user = user or ctx.author
        async with ctx.typing():
            conf = await self.config.user(user).all()
            self.check_if_logged_in(conf, user == ctx.author)
            name = conf["lastfm_username"]
            data = await self.api_request(
                ctx, {"user": name, "method": "user.gettopalbums", "period": "overall"}
            )
            albums = data["topalbums"]["album"]
            if not albums:
                return await ctx.send(f"{name} has not listened to any albums yet!")
            data = {a["name"]: int(a["playcount"]) for a in albums}
            wc = await self.bot.loop.run_in_executor(None, self.wc.generate_from_frequencies, data)
            pic = BytesIO()
            pic.name = f"{name}_albums.png"
            wc.to_file(pic)
            pic.seek(0)
            await ctx.send(f"{name}'s albums cloud:", file=discord.File(pic))
        pic.close()

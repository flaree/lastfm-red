from contextlib import suppress
from typing import Optional

import discord
from redbot.core import commands

from .abc import MixinMeta
from .fmmixin import fm
from .utils import *

with suppress(Exception):
    from wordcloud import WordCloud


async def wordcloud_available(ctx):
    return "WordCloud" in globals().keys()


class WordCloudMixin(MixinMeta):
    """WordCloud Commands"""

    def wordcloud_create(self):
        if "WordCloud" in globals().keys():
            self.wc = WordCloud(width=1920, height=1080, mode="RGBA", background_color=None)

    @fm.group(aliases=["cloud", "wc"])
    @commands.check(wordcloud_available)
    async def wordcloud(self, ctx):
        """WordCloud Commands

        Original idea: http://lastfm.dontdrinkandroot.net"""

    @wordcloud.command(aliases=["artist"])
    @commands.max_concurrency(1, commands.BucketType.user)
    async def artists(self, ctx, user: Optional[discord.Member] = None):
        """Get a picture with the most listened to artists."""
        author = user or ctx.author
        async with ctx.typing():
            name = await self.config.user(author).lastfm_username()
            if name is None:
                return await ctx.send(f"{author} does not have a LastFM account set.")
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

    @wordcloud.command()
    @commands.max_concurrency(1, commands.BucketType.user)
    async def tracks(self, ctx, user: Optional[discord.Member] = None):
        """Get a picture with the most listened to tracks."""
        author = user or ctx.author
        async with ctx.typing():
            name = await self.config.user(author).lastfm_username()
            if name is None:
                return await ctx.send(f"{author} does not have a LastFM account set.")
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

    @wordcloud.command()
    @commands.max_concurrency(1, commands.BucketType.user)
    async def albums(self, ctx, user: Optional[discord.Member] = None):
        """Get a picture with the most listened to albums."""
        author = user or ctx.author
        async with ctx.typing():
            name = await self.config.user(author).lastfm_username()
            if name is None:
                return await ctx.send(f"{author} does not have a LastFM account set.")
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

import contextlib
from io import BytesIO

import discord
import tabulate
from PIL import Image, ImageDraw, ImageFont
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_number

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import command_fm


class CompareMixin(MixinMeta):
    """Commands for comparing two users"""

    def make_table_into_image(self, text):

        color = (150, 123, 182)

        lines = 0
        keep_going = True
        width = 0
        for line in text:
            if keep_going:
                width += 6.5
            if line == "\n":
                lines += 16.5
                keep_going = False

        img = Image.new("RGBA", (int(width), int(lines)), color=(255, 0, 0, 0))

        d = ImageDraw.Draw(img)
        fnt_file = f"{self.data_loc}/fonts/NotoSansMono-Regular.ttf"
        font = ImageFont.truetype(fnt_file, 11, encoding="utf-8")
        d.text((0, 0), text, fill=color, font=font)

        final = BytesIO()
        img.save(final, "webp")
        final.seek(0)
        return discord.File(final, "result.webp")

    @command_fm.group(name="compare")
    async def command_compare(self, ctx):
        """Compare two users music tastes"""

    @command_compare.command(name="artists", aliases=["artist"])
    async def compare_artists(self, ctx, user: discord.Member, period: str = "1month"):
        """
        Compare your top artists with someone else.

        `[period]` can be one of: overall, 7day, 1month, 3month, 6month, 12month
        The default is 1 month.
        """
        if user == ctx.author:
            await ctx.send("You need to compare with someone else.")
            return

        period, displayperiod = self.get_period(period)
        if not period:
            await ctx.send(
                "Invalid period. Valid periods are: overall, 7day, 1month, 3month, 6month, 12month"
            )
            return

        author_conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in(author_conf)
        user_conf = await self.config.user(user).all()
        self.check_if_logged_in(user_conf, True)
        async with ctx.typing():
            author_data = await self.api_request(
                ctx,
                {
                    "user": author_conf["lastfm_username"],
                    "method": "user.gettopartists",
                    "period": period,
                    "limit": "10",
                },
            )
            author_artists = author_data["topartists"]["artist"]
            if not author_artists:
                if period == "overall":
                    await ctx.send("You haven't listened to any artists yet.")
                else:
                    await ctx.send(
                        "You haven't listened to any artists in the last {}s.".format(period)
                    )
                return

            g = await ctx.send("Gathering data... This might take a while.")

            author_plays = []
            artist_names = []
            for artist in author_artists:
                if artist["playcount"] == 1:
                    author_plays.append(f"{artist['playcount']} Play")
                else:
                    author_plays.append(f"{humanize_number(artist['playcount'])} Plays")
                artist_names.append(artist["name"])

            user_plays = []
            async for artist in AsyncIter(author_artists):
                plays = await self.get_playcount(
                    ctx, user_conf["lastfm_username"], artist["name"], period
                )
                if plays == 1:
                    user_plays.append(f"{plays} Play")
                else:
                    user_plays.append(f"{humanize_number(plays)} Plays")

            data = {"Artist": artist_names, ctx.author: author_plays, user: user_plays}
            table = tabulate.tabulate(data, headers="keys", tablefmt="fancy_grid")
            color = await ctx.embed_colour()
            img = await self.bot.loop.run_in_executor(None, self.make_table_into_image, table)
            embed = discord.Embed(color=color, title=f"{ctx.author} vs {user} ({displayperiod})")
            embed.set_image(url="attachment://result.webp")

            with contextlib.suppress(discord.NotFound):
                await g.delete()

            await ctx.send(file=img, embed=embed)

    @command_compare.command(name="tracks", aliases=["track"])
    async def compare_tracks(self, ctx, user: discord.Member, period: str = "1month"):
        """
        Compare your top tracks with someone else.

        `[period]` can be one of: overall, 7day, 1month, 3month, 6month, 12month
        The default is 1 month.
        """
        if user == ctx.author:
            await ctx.send("You need to compare with someone else.")
            return

        period, displayperiod = self.get_period(period)
        if not period:
            await ctx.send(
                "Invalid period. Valid periods are: overall, 7day, 1month, 3month, 6month, 12month"
            )
            return

        author_conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in(author_conf)
        user_conf = await self.config.user(user).all()
        self.check_if_logged_in(user_conf, True)
        async with ctx.typing():
            author_data = await self.api_request(
                ctx,
                {
                    "user": author_conf["lastfm_username"],
                    "method": "user.gettoptracks",
                    "period": period,
                    "limit": "10",
                },
            )
            author_tracks = author_data["toptracks"]["track"]
            if not author_tracks:
                if period == "overall":
                    await ctx.send("You haven't listened to any tracks yet.")
                else:
                    await ctx.send("You haven't listened to any tracks in that time period.")
                return

            g = await ctx.send("Gathering data... This might take a while.")

            author_plays = []
            artist_names = []
            track_names = []
            for track in author_tracks:
                if track["playcount"] == 1:
                    author_plays.append(f"{track['playcount']} Play")
                else:
                    author_plays.append(f"{humanize_number(track['playcount'])} Plays")
                artist_names.append(track["artist"]["name"])
                track_names.append(track["name"])

            user_plays = []
            async for track in AsyncIter(author_tracks):
                plays = await self.get_playcount_track(
                    ctx,
                    user_conf["lastfm_username"],
                    track["artist"]["name"],
                    track["name"],
                    period,
                )
                if plays == 1:
                    user_plays.append(f"{plays} Play")
                else:
                    user_plays.append(f"{humanize_number(plays)} Plays")

            data = {
                "Artist": artist_names,
                "Track": track_names,
                ctx.author: author_plays,
                user: user_plays,
            }
            table = tabulate.tabulate(data, headers="keys", tablefmt="fancy_grid")
            color = await ctx.embed_colour()
            img = await self.bot.loop.run_in_executor(None, self.make_table_into_image, table)
            embed = discord.Embed(color=color, title=f"{ctx.author} vs {user} ({displayperiod})")
            embed.set_image(url="attachment://result.webp")

            with contextlib.suppress(discord.NotFound):
                await g.delete()

            await ctx.send(file=img, embed=embed)

    @command_compare.command(name="albums", aliases=["album"])
    async def compare_albums(self, ctx, user: discord.Member, period: str = "1month"):
        """
        Compare your top albums with someone else.

        `[period]` can be one of: overall, 7day, 1month, 3month, 6month, 12month
        The default is 1 month.
        """
        if user == ctx.author:
            await ctx.send("You need to compare with someone else.")
            return

        period, displayperiod = self.get_period(period)
        if not period:
            await ctx.send(
                "Invalid period. Valid periods are: overall, 7day, 1month, 3month, 6month, 12month"
            )
            return

        author_conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in(author_conf)
        user_conf = await self.config.user(user).all()
        self.check_if_logged_in(user_conf, True)
        async with ctx.typing():
            author_data = await self.api_request(
                ctx,
                {
                    "user": author_conf["lastfm_username"],
                    "method": "user.gettopalbums",
                    "period": period,
                    "limit": "10",
                },
            )
            author_albums = author_data["topalbums"]["album"]
            if not author_albums:
                if period == "overall":
                    await ctx.send("You haven't listened to any albums yet.")
                else:
                    await ctx.send("You haven't listened to any albums in that time period.")
                return

            g = await ctx.send("Gathering data... This might take a while.")

            author_plays = []
            artist_names = []
            album_names = []
            for album in author_albums:
                if album["playcount"] == 1:
                    author_plays.append(f"{album['playcount']} Play")
                else:
                    author_plays.append(f"{humanize_number(album['playcount'])} Plays")
                artist_names.append(album["artist"]["name"])
                album_names.append(album["name"])

            user_plays = []
            async for album in AsyncIter(author_albums):
                plays = await self.get_playcount_album(
                    ctx,
                    user_conf["lastfm_username"],
                    album["artist"]["name"],
                    album["name"],
                    period,
                )
                if plays == 1:
                    user_plays.append(f"{plays} Play")
                else:
                    user_plays.append(f"{humanize_number(plays)} Plays")

            data = {
                "Artist": artist_names,
                "Album": album_names,
                ctx.author: author_plays,
                user: user_plays,
            }
            table = tabulate.tabulate(data, headers="keys", tablefmt="fancy_grid")
            color = await ctx.embed_colour()
            img = await self.bot.loop.run_in_executor(None, self.make_table_into_image, table)
            embed = discord.Embed(color=color, title=f"{ctx.author} vs {user} ({displayperiod})")
            embed.set_image(url="attachment://result.webp")

            with contextlib.suppress(discord.NotFound):
                await g.delete()

            await ctx.send(file=img, embed=embed)

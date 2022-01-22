from io import BytesIO

import discord
import tabulate
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import humanize_number

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import fm


class CompareMixin(MixinMeta):
    """Commands for comparing two users"""

    def make_table_into_image(self, text, color):
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
        fnt_file = f"{self.data_loc}/fonts/JetBrainsMonoNL-SemiBold.ttf"
        font = ImageFont.truetype(fnt_file, 11, encoding="utf-8")
        d.text((0, 0), text, fill=color.to_rgb(), font=font)

        final = BytesIO()
        img.save(final, "webp")
        final.seek(0)
        return discord.File(final, "result.webp")

    @fm.group(name="compare")
    async def compare_command(self, ctx):
        """Compare two users music tastes"""

    @compare_command.command(name="artists", aliases=["artist"])
    async def compare_artists(self, ctx, user: discord.Member, period: str = "overall"):
        """
        Compare your Artist taste with someone else.

        `[period]` can be one of: overall, 7day, 1month, 3month, 6month, 12month
        """
        if user == ctx.author:
            await ctx.send("You need to compare with someone else.")
            return

        period = self.get_period(period)
        if not period:
            await ctx.send(
                "Invalid period. Valid periods are: overall, 7day, 1month, 3month, 6month, 12month"
            )
            return

        author_conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in(author_conf)
        user_conf = await self.config.user(user).all()
        self.check_if_logged_in(user_conf, False)
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
            author_plays = []
            author_names = []
            for artist in author_artists:

                if artist["playcount"] == 1:
                    author_plays.append(f"{artist['playcount']} Play")
                else:
                    author_plays.append(f"{humanize_number(artist['playcount'])} Plays")
                author_names.append(artist["name"])

            user_plays = []
            async for artist in AsyncIter(author_artists):
                url = (
                    f"https://last.fm/user/{user_conf['lastfm_username']}/library/music/{artist['name']}"
                    f"?date_preset={self.period_http_format(period)}"
                )
                data = await self.fetch(self, ctx, url, handling="text")
                soup = BeautifulSoup(data, "html.parser")
                divs = soup.findAll(class_="metadata-display")
                if not divs:
                    user_plays.append("0 Plays")
                    continue
                div = divs[0]
                plays = div.get_text()
                if plays == "1":
                    user_plays.append(f"{plays} Play")
                else:
                    user_plays.append(f"{plays} Plays")

            data = {"Artist": author_names, ctx.author: author_plays, user: user_plays}
            table = tabulate.tabulate(data, headers="keys", tablefmt="fancy_grid")
            color = await ctx.embed_colour()
            img = await self.bot.loop.run_in_executor(
                None, self.make_table_into_image, table, color
            )
            embed = discord.Embed(color=color, title=f"{ctx.author} vs {user}")
            embed.set_image(url="attachment://result.webp")
            await ctx.send(file=img, embed=embed)

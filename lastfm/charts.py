from io import BytesIO

import discord
from PIL import Image, ImageDraw, ImageFont
from redbot.core import commands
from redbot.core.utils import AsyncIter

from .abc import MixinMeta
from .fmmixin import fm
from .utils import *

NO_IMAGE_PLACEHOLDER = (
    "https://lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png"
)


class ChartMixin(MixinMeta):
    """Chart Commands"""

    async def get_img(self, url):
        async with self.session.get(url or NO_IMAGE_PLACEHOLDER) as resp:
            if resp.status == 200:
                img = await resp.read()
                return img
            async with self.session.get(NO_IMAGE_PLACEHOLDER) as resp:
                img = await resp.read()
                return img

    @fm.command(usage="[album | artist | recent] [timeframe] [width]x[height]")
    @commands.max_concurrency(1, commands.BucketType.user)
    async def chart(self, ctx, *args):
        """Visual chart of your top albums or artists."""
        username = await self.config.user(ctx.author).lastfm_username()
        if username is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.clean_prefix
                )
            )
        arguments = parse_chart_arguments(args)
        if arguments["width"] + arguments["height"] > 31:  # TODO: Figure out a reasonable value.
            return await ctx.send(
                "Size is too big! Chart `width` + `height` total must not exceed `31`"
            )
        msg = await ctx.send("Gathering images and data, this may take some time.")
        try:
            data = await self.api_request(
                ctx,
                {
                    "user": username,
                    "method": arguments["method"],
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                },
            )
        except LastFMError as e:
            return await ctx.send(str(e))
        chart = []
        chart_type = "ERROR"
        async with ctx.typing():
            if arguments["method"] == "user.gettopalbums":
                chart_type = "top album"
                albums = data["topalbums"]["album"]
                async for album in AsyncIter(albums[: arguments["width"] * arguments["height"]]):
                    name = album["name"]
                    artist = album["artist"]["name"]
                    plays = album["playcount"]
                    if album["image"][3]["#text"] in self.chart_data:
                        chart_img = self.chart_data[album["image"][3]["#text"]]
                    else:
                        chart_img = await self.get_img(album["image"][3]["#text"])
                        self.chart_data[album["image"][3]["#text"]] = chart_img
                    chart.append((f"{plays} {format_plays(plays)}\n{name} - {artist}", chart_img,))
                img = await self.bot.loop.run_in_executor(
                    None, charts, chart, arguments["width"], arguments["height"], self.data_loc,
                )

            elif arguments["method"] == "user.gettopartists":
                chart_type = "top artist"
                artists = data["topartists"]["artist"]
                scraped_images = await self.scrape_artists_for_chart(
                    ctx, username, arguments["period"], arguments["amount"]
                )
                iterator = AsyncIter(artists[: arguments["width"] * arguments["height"]])
                async for i, artist in iterator.enumerate():
                    name = artist["name"]
                    plays = artist["playcount"]
                    if scraped_images[i] in self.chart_data:
                        chart_img = self.chart_data[scraped_images[i]]
                    else:
                        chart_img = await self.get_img(scraped_images[i])
                        self.chart_data[scraped_images[i]] = chart_img
                    chart.append((f"{plays} {format_plays(plays)}\n{name}", chart_img,))
                img = await self.bot.loop.run_in_executor(
                    None, charts, chart, arguments["width"], arguments["height"], self.data_loc,
                )

            elif arguments["method"] == "user.getrecenttracks":
                chart_type = "recent tracks"
                tracks = data["recenttracks"]["track"]
                async for track in AsyncIter(tracks[: arguments["width"] * arguments["height"]]):
                    name = track["name"]
                    artist = track["artist"]["#text"]
                    if track["image"][3]["#text"] in self.chart_data:
                        chart_img = self.chart_data[track["image"][3]["#text"]]
                    else:
                        chart_img = await self.get_img(track["image"][3]["#text"])
                        self.chart_data[track["image"][3]["#text"]] = chart_img
                    chart.append((f"{name} - {artist}", chart_img,))
                img = await self.bot.loop.run_in_executor(
                    None,
                    track_chart,
                    chart,
                    arguments["width"],
                    arguments["height"],
                    self.data_loc,
                )
        await msg.delete()
        try:
            await ctx.send(
                f"`{username} - {humanized_period(arguments['period'])} - {arguments['width']}x{arguments['height']} {chart_type} chart`",
                file=img,
            )
        except discord.HTTPException:
            await ctx.send("File is to big to send, try lowering the size.")


def charts(data, w, h, loc):
    fnt_file = f"{loc}/fonts/HelveticaNeueLTStd-Md.otf"
    fnt = ImageFont.truetype(fnt_file, 18, encoding="utf-8")
    imgs = []
    for item in data:
        img = BytesIO(item[1])
        image = Image.open(img).convert("RGBA")
        draw = ImageDraw.Draw(image)
        texts = item[0].split("\n")
        if len(texts[1]) > 30:
            height = 237
            text = f"{texts[0]}\n{texts[1][:30]}\n{texts[1][30:]}"
        else:
            height = 257
            text = item[0]
        draw.text(
            (5, height),
            text,
            fill=(255, 255, 255, 255),
            font=fnt,
            stroke_width=1,
            stroke_fill=(255, 255, 255, 0),
        )
        _file = BytesIO()
        image.save(_file, "png")
        _file.name = f"{item[0]}.png"
        _file.seek(0)
        imgs.append(_file)
    return create_graph(imgs, w, h)


def track_chart(data, w, h, loc):
    fnt_file = f"{loc}/fonts/HelveticaNeueLTStd-Md.otf"
    fnt = ImageFont.truetype(fnt_file, 18, encoding="utf-8")
    imgs = []
    for item in data:
        img = BytesIO(item[1])
        image = Image.open(img).convert("RGBA")
        draw = ImageDraw.Draw(image)
        if len(item[0]) > 30:
            height = 257
            text = f"{item[0][:30]}\n{item[0][30:]}"
        else:
            height = 277
            text = item[0]
        draw.text(
            (5, height),
            text,
            fill=(255, 255, 255, 255),
            font=fnt,
            stroke_width=1,
            stroke_fill=(255, 255, 255, 0),
        )
        _file = BytesIO()
        image.save(_file, "png")
        _file.name = f"{item[0]}.png"
        _file.seek(0)
        imgs.append(_file)
    return create_graph(imgs, w, h)


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i : i + n]


def create_graph(data, w, h):
    dimensions = (300 * w, 300 * h)
    final = Image.new("RGBA", dimensions)
    images = chunks(data, w)
    y = 0
    for chunked in images:
        x = 0
        for img in chunked:
            new = Image.open(img)
            w, h = new.size
            final.paste(new, (x, y, x + w, y + h))
            x += 300
        y += 300
    w, h = final.size
    if w > 2100 and h > 2100:
        final = final.resize(
            (2100, 2100), resample=Image.ANTIALIAS
        )  # Resize cause a 6x6k image is blocking when being sent
    file = BytesIO()
    final.save(file, "webp")
    file.name = f"chart.webp"
    file.seek(0)
    image = discord.File(file)
    return image

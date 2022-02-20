import asyncio
from io import BytesIO

import discord
from PIL import Image, ImageDraw, ImageFile, ImageFont
from redbot.core import commands
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import escape

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import command_fm, command_fm_server

NO_IMAGE_PLACEHOLDER = (
    "https://lastfm.freetls.fastly.net/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png"
)
ImageFile.LOAD_TRUNCATED_IMAGES = True


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

    @command_fm.command(
        name="chart", usage="[album | artist | recent] [timeframe] [width]x[height]"
    )
    @commands.max_concurrency(1, commands.BucketType.user)
    async def command_chart(self, ctx, *args):
        """Visual chart of your top albums, tracks or artists."""
        conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in(conf)
        arguments = self.parse_chart_arguments(args)
        if arguments["width"] + arguments["height"] > 31:  # TODO: Figure out a reasonable value.
            return await ctx.send(
                "Size is too big! Chart `width` + `height` total must not exceed `31`"
            )
        msg = await ctx.send("Gathering images and data, this may take some time.")
        data = await self.api_request(
            ctx,
            {
                "user": conf["lastfm_username"],
                "method": arguments["method"],
                "period": arguments["period"],
                "limit": arguments["amount"],
            },
        )
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
                    chart.append(
                        (
                            f"{plays} {self.format_plays(plays)}\n{name} - {artist}",
                            chart_img,
                        )
                    )
                img = await self.bot.loop.run_in_executor(
                    None,
                    charts,
                    chart,
                    arguments["width"],
                    arguments["height"],
                    self.data_loc,
                )

            elif arguments["method"] == "user.gettopartists":
                chart_type = "top artist"
                artists = data["topartists"]["artist"]
                scraped_images = await self.scrape_artists_for_chart(
                    ctx, conf["lastfm_username"], arguments["period"], arguments["amount"]
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
                    chart.append(
                        (
                            f"{plays} {self.format_plays(plays)}\n{name}",
                            chart_img,
                        )
                    )
                img = await self.bot.loop.run_in_executor(
                    None,
                    charts,
                    chart,
                    arguments["width"],
                    arguments["height"],
                    self.data_loc,
                )

            elif arguments["method"] == "user.getrecenttracks":
                chart_type = "recent tracks"
                tracks = data["recenttracks"]["track"]
                if isinstance(tracks, dict):
                    tracks = [tracks]
                async for track in AsyncIter(tracks[: arguments["width"] * arguments["height"]]):
                    name = track["name"]
                    artist = track["artist"]["#text"]
                    if track["image"][3]["#text"] in self.chart_data:
                        chart_img = self.chart_data[track["image"][3]["#text"]]
                    else:
                        chart_img = await self.get_img(track["image"][3]["#text"])
                        self.chart_data[track["image"][3]["#text"]] = chart_img
                    chart.append(
                        (
                            f"{name} - {artist}",
                            chart_img,
                        )
                    )
                img = await self.bot.loop.run_in_executor(
                    None,
                    track_chart,
                    chart,
                    arguments["width"],
                    arguments["height"],
                    self.data_loc,
                )
        await msg.delete()
        u = conf["lastfm_username"]
        try:
            await ctx.send(
                f"`{u} - {self.humanized_period(arguments['period'])} - {arguments['width']}x{arguments['height']} {chart_type} chart`",
                file=img,
            )
        except discord.HTTPException:
            await ctx.send("File is to big to send, try lowering the size.")

    @command_fm_server.command(
        name="chart", usage="[album | artist | tracks] [timeframe] [width]x[height]"
    )
    @commands.max_concurrency(1, commands.BucketType.user)
    async def server_chart(self, ctx, *args):
        """Visual chart of the servers albums, artists or tracks."""
        arguments = self.parse_chart_arguments(args)
        if arguments["width"] + arguments["height"] > 31:  # TODO: Figure out a reasonable value.
            return await ctx.send(
                "Size is too big! Chart `width` + `height` total must not exceed `31`"
            )
        if arguments["method"] not in [
            "user.gettopalbums",
            "user.gettopartists",
            "user.gettoptracks",
        ]:
            return await ctx.send("Only albums, artists and tracks are supported.")
        chart_total = arguments["width"] * arguments["height"]
        msg = await ctx.send("Gathering images and data, this may take some time.")
        tasks = []
        userlist = await self.config.all_users()
        guildusers = [x.id for x in ctx.guild.members]
        userslist = [user for user in userlist if user in guildusers]
        datatype = {
            "user.gettopalbums": "album",
            "user.gettopartists": "artist",
            "user.gettoptracks": "track",
        }
        for user in userslist:
            lastfm_username = userlist[user]["lastfm_username"]
            if lastfm_username is None:
                continue
            member = ctx.guild.get_member(user)
            if member is None:
                continue

            tasks.append(
                self.get_server_top(
                    ctx,
                    lastfm_username,
                    datatype.get(arguments["method"]),
                    arguments["period"],
                    arguments["amount"],
                )
            )
        chart = []
        chart_type = "ERROR"
        if not tasks:
            return await ctx.send("No users have set their last.fm username yet.")
        content_map = {}
        async with ctx.typing():
            data = await asyncio.gather(*tasks)
            if arguments["method"] == "user.gettopalbums":
                chart_type = "top album"
                for user_data in data:
                    if user_data is None:
                        continue
                    for album in user_data:
                        album_name = album["name"]
                        artist = album["artist"]["name"]
                        name = f"{album_name} — {artist}"
                        plays = int(album["playcount"])
                        if name in content_map:
                            content_map[name]["plays"] += plays
                        else:
                            content_map[name] = {
                                "plays": plays,
                                "link": album["image"][3]["#text"],
                            }
            elif arguments["method"] == "user.gettopartists":
                chart_type = "top artist"
                for user_data in data:
                    if user_data is None:
                        continue
                    for artist in user_data:
                        name = artist["name"]
                        plays = int(artist["playcount"])
                        if name in content_map:
                            content_map[name]["plays"] += plays
                        else:
                            content_map[name] = {"plays": plays}
            elif arguments["method"] == "user.gettoptracks":
                chart_type = "top tracks"
                for user in data:
                    if user is None:
                        continue
                    for user_data in user:
                        name = f'{escape(user_data["artist"]["name"])} — *{escape(user_data["name"])}*'
                        plays = int(user_data["playcount"])
                        if name in content_map:
                            content_map[name]["plays"] += plays
                        else:
                            content_map[name] = {
                                "plays": plays,
                                "link": user_data["artist"]["name"],
                            }
        cached_images = {}
        for i, (name, content_data) in enumerate(
            sorted(content_map.items(), key=lambda x: x[1]["plays"], reverse=True), start=1
        ):
            if arguments["method"] == "user.gettopartists":
                image = await self.get_img(await self.scrape_artist_image(name, ctx))
            elif arguments["method"] == "user.gettoptracks":
                if content_data["link"] in cached_images:
                    image = cached_images[content_data["link"]]
                else:
                    image = await self.get_img(
                        await self.scrape_artist_image(content_data["link"], ctx)
                    )
                    cached_images[content_data["link"]] = image
            else:
                image = await self.get_img(content_data["link"])
            chart.append(
                (
                    f"{content_data['plays']} {self.format_plays(content_data['plays'])}\n{name}",
                    image,
                )
            )
            if i >= chart_total:
                break
        img = await self.bot.loop.run_in_executor(
            None,
            charts,
            chart,
            arguments["width"],
            arguments["height"],
            self.data_loc,
        )
        await msg.delete()
        try:
            await ctx.send(
                f"`{ctx.guild} - {self.humanized_period(arguments['period'])} - {arguments['width']}x{arguments['height']} {chart_type} chart`",
                file=img,
            )
        except discord.HTTPException:
            await ctx.send("File is to big to send, try lowering the size.")


def charts(data, w, h, loc):
    fnt_file = f"{loc}/fonts/Arial Unicode.ttf"
    fnt = ImageFont.truetype(fnt_file, 18, encoding="utf-8")
    imgs = []
    for item in data:
        img = BytesIO(item[1])
        image = Image.open(img).convert("RGBA")
        draw = ImageDraw.Draw(image)
        texts = item[0].split("\n")
        if len(texts[1]) > 30:
            height = 227
            text = f"{texts[0]}\n{texts[1][:30]}\n{texts[1][30:]}"
        else:
            height = 247
            text = item[0]
        draw.text(
            (5, height),
            text,
            fill=(255, 255, 255, 255),
            font=fnt,
            stroke_width=1,
            stroke_fill=(0, 0, 0),
        )
        _file = BytesIO()
        image.save(_file, "png")
        _file.name = f"{item[0]}.png"
        _file.seek(0)
        imgs.append(_file)
    return create_graph(imgs, w, h)


def track_chart(data, w, h, loc):
    fnt_file = f"{loc}/fonts/Arial Unicode.ttf"
    fnt = ImageFont.truetype(fnt_file, 18, encoding="utf-8")
    imgs = []
    for item in data:
        img = BytesIO(item[1])
        image = Image.open(img).convert("RGBA")
        draw = ImageDraw.Draw(image)
        if len(item[0]) > 30:
            height = 247
            text = f"{item[0][:30]}\n{item[0][30:]}"
        else:
            height = 267
            text = item[0]
        draw.text(
            (5, height),
            text,
            fill=(255, 255, 255, 255),
            font=fnt,
            stroke_width=1,
            stroke_fill=(0, 0, 0),
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

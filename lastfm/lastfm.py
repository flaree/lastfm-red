import asyncio
import urllib.parse
from abc import ABC
from contextlib import suppress
from io import BytesIO
from operator import itemgetter
from typing import Optional

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.data_manager import bundled_data_path
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import escape, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .charts import charts, track_chart
from .utils import *
from .whoknows import WhoKnowsMixin

with suppress(Exception):
    from wordcloud import WordCloud


async def wordcloud_available(ctx):
    return "WordCloud" in globals().keys()


async def tokencheck(ctx):
    token = await ctx.bot.get_shared_api_tokens("lastfm")
    return bool(token.get("appid"))


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """This allows the metaclass used for proper type detection to coexist with discord.py's
    metaclass."""


class LastFM(
    UtilsMixin, WhoKnowsMixin, commands.Cog, metaclass=CompositeMetaClass,
):
    # noinspection PyMissingConstructor
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=95932766180343808, force_registration=True)
        defaults = {"lastfm_username": None}
        self.config.register_global(version=1)
        self.config.register_user(**defaults)
        self.config.register_guild(crowns={})
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Arch Linux; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0"
            },
            loop=self.bot.loop,
        )
        self.token = None
        self.wc = None
        if "WordCloud" in globals().keys():
            self.wc = WordCloud(width=1920, height=1080, mode="RGBA", background_color=None)
        self.data_loc = bundled_data_path(self)

    async def initialize(self):
        token = await self.bot.get_shared_api_tokens("lastfm")
        self.token = token.get("appid")
        await self.migrate_config()

    async def migrate_config(self):
        if await self.config.version() == 1:
            a = {}
            conf = await self.config.all_guilds()
            for guild in conf:
                a[guild] = {"crowns": {}}
                for artist in conf[guild]["crowns"]:
                    a[guild]["crowns"][artist.lower()] = conf[guild]["crowns"][artist]
            group = self.config._get_base_group(self.config.GUILD)
            async with group.all() as new_data:
                for guild in a:
                    new_data[guild] = a[guild]
            await self.config.version.set(2)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, api_tokens):
        if service_name == "lastfm":
            self.token = api_tokens.get("appid")

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.is_owner()
    @commands.command(aliases=["fmset"])
    async def lastfmset(self, ctx):
        """Instructions on how to set the api key."""
        message = (
            "1. Vist the [LastFM](https://www.last.fm/api/) site and click on 'Get an API Account'.\n"
            "2. Fill in the application. Once completed do not exit the page. - "
            "Copy all information on the page and save it.\n"
            f"3. Enter the key via `{ctx.clean_prefix}set api lastfm appid <appid_here>`"
        )
        await ctx.maybe_send_embed(message)

    @commands.check(tokencheck)
    @commands.group(case_insensitive=True)
    async def fm(self, ctx):
        """Last.fm commands"""

    @fm.command()
    async def set(self, ctx, username):
        """Save your last.fm username."""
        try:
            content = await self.get_userinfo_embed(ctx, username)
        except LastFMError as e:
            return await ctx.send(str(e))
        if content is None:
            return await ctx.send(f"\N{WARNING SIGN} Invalid Last.fm username `{username}`")

        await self.config.user(ctx.author).lastfm_username.set(username)
        await ctx.send(
            f"{ctx.message.author.mention} Username saved as `{username}`", embed=content,
        )

    @fm.command()
    async def unset(self, ctx):
        """Unlink your last.fm."""
        await self.config.user(ctx.author).lastfm_username.set(None)
        await ctx.send("\N{BROKEN HEART} Removed your last.fm username from the database")
        async with self.config.guild(ctx.guild).crowns() as crowns:
            crownlist = []
            for crown in crowns:
                if crowns[crown]["user"] == ctx.author.id:
                    crownlist.append(crown)
            for crown in crownlist:
                del crowns[crown]

    @fm.command()
    async def profile(self, ctx, user: Optional[discord.Member] = None):
        """Lastfm profile."""
        author = user or ctx.author
        name = await self.config.user(author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.clean_prefix
                )
            )
        try:
            await ctx.send(embed=await self.get_userinfo_embed(ctx, name))
        except LastFMError as e:
            return await ctx.send(str(e))

    @commands.command(aliases=["np"],)
    async def nowplaying(self, ctx, user: Optional[discord.Member] = None):
        """Currently playing song or most recent song."""
        author = user or ctx.author
        async with ctx.typing():
            name = await self.config.user(author).lastfm_username()
            if name is None:
                return await ctx.send(
                    "You do not have a LastFM account set. Please set one with {}fm set".format(
                        ctx.clean_prefix
                    )
                )
            try:
                data = await self.api_request(
                    ctx, {"user": name, "method": "user.getrecenttracks", "limit": 1}
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            user_attr = data["recenttracks"]["@attr"]
            tracks = data["recenttracks"]["track"]

            if not tracks:
                return await ctx.send("You have not listened to anything yet!")
            try:
                artist = tracks[0]["artist"]["#text"]
                album = tracks[0]["album"]["#text"]
                track = tracks[0]["name"]
                image_url = tracks[0]["image"][-1]["#text"]
                url = tracks[0]["url"]
                # image_url_small = tracks[0]['image'][1]['#text']
                # image_colour = await color_from_image_url(image_url_small)
            except KeyError:
                artist = tracks["artist"]["#text"]
                album = tracks["album"]["#text"]
                track = tracks["name"]
                image_url = tracks["image"][-1]["#text"]
                url = tracks["url"]

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel), url=url)
            # content.colour = int(image_colour, 16)
            content.description = f"**{escape(album, formatting=True)}**"
            content.title = (
                f"**{escape(artist, formatting=True)}** — ***{escape(track, formatting=True)} ***"
            )
            content.set_thumbnail(url=image_url)

            # tags and playcount
            try:
                trackdata = await self.api_request(
                    ctx,
                    {"user": name, "method": "track.getInfo", "artist": artist, "track": track,},
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            if trackdata is not None:
                tags = []
                try:
                    trackdata = trackdata["track"]
                    playcount = int(trackdata["userplaycount"])
                    if playcount > 0:
                        content.description += f"\n> {playcount} {format_plays(playcount)}"
                    for tag in trackdata["toptags"]["tag"]:
                        tags.append(tag["name"])
                    content.set_footer(text=", ".join(tags))
                except KeyError:
                    pass

            # play state
            state = "— Most recent track"
            try:
                if "@attr" in tracks[0]:
                    if "nowplaying" in tracks[0]["@attr"]:
                        state = "— Now Playing"
            except KeyError:
                if "@attr" in tracks:
                    if "nowplaying" in tracks["@attr"]:
                        state = "— Now Playing"

            content.set_author(
                name=f"{user_attr['user']} {state}", icon_url=ctx.message.author.avatar_url,
            )
            if state == "— Most recent track":
                msg = "You aren't currently listening to anything, here is the most recent song found."
            else:
                msg = None
            await ctx.send(msg if msg is not None else None, embed=content)

    @fm.command(aliases=["snp"])
    async def servernp(self, ctx):
        """What people on this server are listening to at the moment."""
        listeners = []
        tasks = []
        userlist = await self.config.all_users()
        guildusers = [x.id for x in ctx.guild.members]
        userslist = [user for user in userlist if user in guildusers]
        for user in userslist:
            lastfm_username = userlist[user]["lastfm_username"]
            if lastfm_username is None:
                continue
            member = ctx.guild.get_member(user)
            if member is None:
                continue

            tasks.append(self.get_np(ctx, lastfm_username, member))

        total_linked = len(tasks)
        if tasks:
            data = await asyncio.gather(*tasks)
            for song, member_ref in data:
                if song is not None:
                    listeners.append((song, member_ref))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        if not listeners:
            return await ctx.send("Nobody on this server is listening to anything at the moment!")

        total_listening = len(listeners)
        rows = []
        for song, member in listeners:
            rows.append(f"{member.mention} **{song.get('artist')}** — ***{song.get('name')}***")

        content = discord.Embed()
        content.set_author(
            name=f"What is {ctx.guild.name} listening to?",
            icon_url=ctx.guild.icon_url_as(size=64),
        )
        content.set_footer(text=f"{total_listening} / {total_linked} Members")
        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @commands.command()
    @commands.guild_only()
    async def crowns(self, ctx, user: discord.Member = None):
        """Check yourself or another users crowns."""
        user = user or ctx.author
        crowns = await self.config.guild(ctx.guild).crowns()
        crownartists = []
        for key in crowns:
            if crowns[key]["user"] == user.id:
                crownartists.append((key, crowns[key]["playcount"]))
        if crownartists is None:
            return await ctx.send(
                "You haven't acquired any crowns yet! "
                f"Use the `{ctx.clean_prefix}whoknows` command to claim crowns \N{CROWN}"
            )

        rows = []
        for artist, playcount in sorted(crownartists, key=itemgetter(1), reverse=True):
            rows.append(f"**{artist}** with **{playcount}** {format_plays(playcount)}")

        content = discord.Embed(
            title=f"Artist crowns for {user.name} — Total {len(crownartists)} crowns",
            color=user.color,
        )
        content.set_footer(text="Playcounts are updated on the whoknows command.")
        if not rows:
            return await ctx.send("You do not have any crowns.")
        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @fm.command(aliases=["ta"], usage="[timeframe] [amount]")
    async def topartists(self, ctx, *args):
        """Most listened artists."""
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.clean_prefix
                )
            )
        async with ctx.typing():
            arguments = parse_arguments(args)
            try:
                data = await self.api_request(
                    ctx,
                    {
                        "user": name,
                        "method": "user.gettopartists",
                        "period": arguments["period"],
                        "limit": arguments["amount"],
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            user_attr = data["topartists"]["@attr"]
            artists = data["topartists"]["artist"]

            if not artists:
                return await ctx.send("You have not listened to any artists yet!")

            rows = []
            for i, artist in enumerate(artists, start=1):
                name = escape(artist["name"], formatting=True)
                plays = artist["playcount"]
                rows.append(f"`#{i:2}` **{plays}** {format_plays(plays)} — **{name}**")

            image_url = await self.scrape_artist_image(artists[0]["name"], ctx)
            # image_colour = await color_from_image_url(image_url)

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            # content.colour = int(image_colour, 16)
            content.set_thumbnail(url=image_url)
            content.set_footer(text=f"Total unique artists: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top artists",
                icon_url=ctx.message.author.avatar_url,
            )

        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @fm.command(aliases=["talb"], usage="[timeframe] [amount]")
    async def topalbums(self, ctx, *args):
        """Most listened albums."""
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.clean_prefix
                )
            )
        arguments = parse_arguments(args)
        try:
            data = await self.api_request(
                ctx,
                {
                    "user": name,
                    "method": "user.gettopalbums",
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                },
            )
        except LastFMError as e:
            return await ctx.send(str(e))
        user_attr = data["topalbums"]["@attr"]
        albums = data["topalbums"]["album"]

        if not albums:
            return await ctx.send("You have not listened to any albums yet!")

        rows = []
        for i, album in enumerate(albums, start=1):
            name = escape(album["name"], formatting=True)
            artist_name = escape(album["artist"]["name"], formatting=True)
            plays = album["playcount"]
            rows.append(
                f"`#{i:2}` **{plays}** {format_plays(plays)} — **{artist_name}** — ***{name}***"
            )

        image_url = albums[0]["image"][-1]["#text"]
        # image_url_small = albums[0]['image'][1]['#text']
        # image_colour = await color_from_image_url(image_url_small)

        content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
        # content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique albums: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top albums",
            icon_url=ctx.message.author.avatar_url,
        )

        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @fm.command(aliases=["tt"], usage="[timeframe] [amount]")
    async def toptracks(self, ctx, *args):
        """Most listened tracks."""
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.clean_prefix
                )
            )
        async with ctx.typing():
            arguments = parse_arguments(args)
            try:
                data = await self.api_request(
                    ctx,
                    {
                        "user": name,
                        "method": "user.gettoptracks",
                        "period": arguments["period"],
                        "limit": arguments["amount"],
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            user_attr = data["toptracks"]["@attr"]
            tracks = data["toptracks"]["track"]

            if not tracks:
                return await ctx.send("You have not listened to anything yet!")

            rows = []
            for i, track in enumerate(tracks, start=1):
                name = escape(track["name"], formatting=True)
                artist_name = escape(track["artist"]["name"], formatting=True)
                plays = track["playcount"]
                rows.append(
                    f"`#{i:2}` **{plays}** {format_plays(plays)} — **{artist_name}** — ***{name}***"
                )
            try:
                trackdata = await self.api_request(
                    ctx,
                    {
                        "user": name,
                        "method": "track.getInfo",
                        "artist": tracks[0]["artist"]["name"],
                        "track": tracks[0]["name"],
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            try:
                if trackdata is None:
                    raise KeyError
                image_url = trackdata["track"]["album"]["image"][-1]["#text"]
                # image_url_small = trackdata['track']['album']['image'][1]['#text']
                # image_colour = await color_from_image_url(image_url_small)
            except KeyError:
                image_url = await self.scrape_artist_image(tracks[0]["artist"]["name"], ctx)
                # image_colour = await color_from_image_url(image_url)

            content.set_thumbnail(url=image_url)

            content.set_footer(text=f"Total unique tracks: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top tracks",
                icon_url=ctx.message.author.avatar_url,
            )

            pages = await create_pages(content, rows)
            if len(pages) > 1:
                await menu(ctx, pages[:15], DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=pages[0])

    @fm.command(aliases=["recents", "re"], usage="[amount]")
    async def recent(self, ctx, size: int = 15):
        """Recently listened tracks."""
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.clean_prefix
                )
            )
        async with ctx.typing():
            try:
                data = await self.api_request(
                    ctx, {"user": name, "method": "user.getrecenttracks", "limit": size}
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            user_attr = data["recenttracks"]["@attr"]
            tracks = data["recenttracks"]["track"]

            if not tracks:
                return await ctx.send("You have not listened to anything yet!")

            rows = []
            for i, track in enumerate(tracks):
                if i >= size:
                    break
                name = escape(track["name"], formatting=True)
                track_url = track["url"]
                artist_name = escape(track["artist"]["#text"], formatting=True)
                rows.append(f"[**{artist_name}** — ***{name}***]({track_url})")

            image_url = tracks[0]["image"][-1]["#text"]
            # image_url_small = tracks[0]['image'][1]['#text']
            # image_colour = await color_from_image_url(image_url_small)

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            # content.colour = int(image_colour, 16)
            content.set_thumbnail(url=image_url)
            content.set_footer(text=f"Total scrobbles: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — Recent tracks",
                icon_url=ctx.message.author.avatar_url,
            )

            pages = await create_pages(content, rows)
            if len(pages) > 1:
                await menu(ctx, pages[:15], DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=pages[0])

    @fm.command(usage="[timeframe] <toptracks|topalbums|overview> <artist name>")
    async def artist(self, ctx, timeframe, datatype, *, artistname=""):
        """Your top tracks or albums for specific artist."""
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.clean_prefix
                )
            )
        period = get_period(timeframe)
        if period is None:
            artistname = " ".join([datatype, artistname]).strip()
            datatype = timeframe
            period = "overall"

        if artistname == "":
            return await ctx.send("Missing artist name!")

        if datatype in ["toptracks", "tt", "tracks", "track"]:
            datatype = "tracks"
        elif datatype in ["topalbums", "talb", "albums", "album"]:
            datatype = "albums"
        elif datatype in ["overview", "stats", "ov"]:
            return await self.artist_overview(ctx, period, artistname, name)
        else:
            return

        artist, data = await self.artist_top(ctx, period, artistname, datatype, name)
        if artist is None or not data:
            if period == "overall":
                return await ctx.send(f"You have never listened to **{artistname}**!")
            return await ctx.send(
                f"You have not listened to **{artistname}** in the past {period}s!"
            )
        rows = []
        for i, (aname, playcount) in enumerate(data, start=1):
            rows.append(f"`#{i:2}` **{playcount}** {format_plays(playcount)} — **{aname}**")

        # image_colour = await color_from_image_url(image_url)

        content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
        content.set_author(
            name=f"{ctx.author.name} — "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + f"Top 50 {datatype} for {artist['formatted_name']}",
            icon_url=ctx.author.avatar_url,
            url=f"https://last.fm/user/{name}/library/music/{urllib.parse.quote_plus(artistname)}/+{datatype}?date_preset={period_http_format(period)}",
        )
        content.set_thumbnail(url=artist["image_url"])
        # content.colour = int(image_colour, 16)

        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

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
                    chart.append(
                        (
                            f"{plays} {format_plays(plays)}\n{name} - {artist}",
                            await self.get_img(album["image"][3]["#text"]),
                        )
                    )
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
                    chart.append(
                        (
                            f"{plays} {format_plays(plays)}\n{name}",
                            await self.get_img(scraped_images[i]),
                        )
                    )
                img = await self.bot.loop.run_in_executor(
                    None, charts, chart, arguments["width"], arguments["height"], self.data_loc,
                )

            elif arguments["method"] == "user.getrecenttracks":
                chart_type = "recent tracks"
                tracks = data["recenttracks"]["track"]
                async for track in AsyncIter(tracks[: arguments["width"] * arguments["height"]]):
                    name = track["name"]
                    artist = track["artist"]["#text"]
                    chart.append(
                        (f"{name} - {artist}", await self.get_img(track["image"][3]["#text"]),)
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
        try:
            await ctx.send(
                f"`{username} - {humanized_period(arguments['period'])} - {arguments['width']}x{arguments['height']} {chart_type} chart`",
                file=img,
            )
        except discord.HTTPException:
            await ctx.send("File is to big to send, try lowering the size.")

    @fm.command(aliases=["lyr"])
    async def lyrics(self, ctx, *, track: str = None):
        """Currently playing song or most recent song."""
        if track is None:
            name = await self.config.user(ctx.author).lastfm_username()
            if name is None:
                return await ctx.send(
                    "You do not have a LastFM account set. Please set one with `{}fm set`.".format(
                        ctx.clean_prefix
                    )
                )
            try:
                data = await self.api_request(
                    ctx, {"user": name, "method": "user.getrecenttracks", "limit": 1}
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            tracks = data["recenttracks"]["track"]

            if not tracks:
                return await ctx.send("You have not listened to anything yet!")

            artist = tracks[0]["artist"]["#text"]
            track = tracks[0]["name"]
            image_url = tracks[0]["image"][-1]["#text"]
            # image_url_small = tracks[0]['image'][1]['#text']
            # image_colour = await color_from_image_url(image_url_small)

            # content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            # content.colour = int(image_colour, 16)
            title = (
                f"**{escape(artist, formatting=True)}** — ***{escape(track, formatting=True)} ***"
            )

            # tags and playcount
            if "@attr" in tracks[0]:
                if "nowplaying" in tracks[0]["@attr"]:
                    results, songtitle = await self.lyrics_musixmatch(f"{artist} {track}")
                    if results is None:
                        return await ctx.send(f'No lyrics for "{artist} {track}" found.')
                    embeds = []
                    results = list(pagify(results, page_length=2048))
                    for i, page in enumerate(results, 1):
                        content = discord.Embed(
                            color=await self.bot.get_embed_color(ctx.channel),
                            description=page,
                            title=title,
                        )
                        content.set_thumbnail(url=image_url)
                        content.set_footer(text=f"Page {i}/{len(results)}")

                        embeds.append(content)
                    if len(embeds) > 1:
                        await menu(ctx, embeds, DEFAULT_CONTROLS)
                    else:
                        await ctx.send(embed=embeds[0])
            else:
                await ctx.send("You're not currently playing a song.")
        else:
            # content.colour = int(image_colour, 16)

            results, songtitle = await self.lyrics_musixmatch(track)
            if results is None:
                return await ctx.send(f'No lyrics for "{track}" found.')
            embeds = []
            results = list(pagify(results, page_length=2048))
            for i, page in enumerate(results, 1):
                content = discord.Embed(
                    color=await self.bot.get_embed_color(ctx.channel),
                    title=f"***{escape(songtitle, formatting=True)} ***",
                    description=page,
                )
                content.set_footer(text=f"Page {i}/{len(results)}")
                embeds.append(content)
            if len(embeds) > 1:
                await menu(ctx, embeds, DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=embeds[0])

    @fm.group(aliases=["cloud", "wc"])
    @commands.check(wordcloud_available)
    async def wordcloud(self, ctx):
        """WordCloud Commands

        Original idea: http://lastfm.dontdrinkandroot.net"""

    @wordcloud.command(aliases=["artist"])
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

    @wordcloud.command()
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

    @wordcloud.command()
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

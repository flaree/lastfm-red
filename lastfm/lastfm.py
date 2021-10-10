import asyncio
import urllib.parse
from abc import ABC
from operator import itemgetter

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.data_manager import bundled_data_path
from redbot.core.utils.chat_formatting import escape, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .charts import ChartMixin
from .fmmixin import FMMixin, fm
from .nowplaying import NowPlayingMixin
from .profile import ProfileMixin
from .scrobbler import ScrobblerMixin
from .top import TopMixin
from .utils import *
from .whoknows import WhoKnowsMixin
from .wordcloud import WordCloudMixin


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """This allows the metaclass used for proper type detection to coexist with discord.py's
    metaclass."""


class LastFM(
    ChartMixin,
    FMMixin,
    ProfileMixin,
    ScrobblerMixin,
    NowPlayingMixin,
    TopMixin,
    WordCloudMixin,
    UtilsMixin,
    WhoKnowsMixin,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    # noinspection PyMissingConstructor
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=95932766180343808, force_registration=True)
        defaults = {"lastfm_username": None, "session_key": None, "scrobbles": 0}
        self.config.register_global(version=1, sent_secret_key_dm=False)
        self.config.register_user(**defaults)
        self.config.register_guild(crowns={})
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Arch Linux; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0"
            },
        )
        self.token = None
        self.wc = None
        self.wordcloud_create()
        self.data_loc = bundled_data_path(self)
        self.chart_data = {}
        self.chart_data_loop = self.bot.loop.create_task(self.chart_clear_loop())

    async def chart_clear_loop(self):
        await self.bot.wait_until_ready()
        while True:
            self.chart_data = {}
            await asyncio.sleep(1800)

    async def initialize(self):
        token = await self.bot.get_shared_api_tokens("lastfm")
        self.token = token.get("appid")
        self.secret = token.get("secret")
        await self.send_secret_key_dm()
        await self.migrate_config()

    async def is_this_first_load(self):
        v = await self.config.version()
        if v == 1:
            return True
        return False

    async def send_secret_key_dm(self):
        if await self.config.sent_secret_key_dm():
            return
        first_load = await self.is_this_first_load()
        if not first_load:
            message = (
                "Hello!\n\n"
                "The last.fm cog has been updated and now requires a new API key.\n"
                "If you do not set this, everything except the `fm set` command "
                "(now called `fm login`) and the new scrobbler feature will continue to function.\n\n"
                "If you already have a last.fm application, you can view https://www.last.fm/api/accounts"
                " to get your `shared secret`.\nSet this with `[p]set api lastfm secret <shared_secret>` and "
                "you'll be all set!"
            )
            await self.bot.send_to_owners(message)
            await self.config.sent_secret_key_dm.set(True)

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
            await self.config.sent_secret_key_dm.set(True)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, api_tokens):
        if service_name == "lastfm":
            self.token = api_tokens.get("appid")
            self.secret = api_tokens.get("secret")

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
        if self.chart_data_loop:
            self.chart_data_loop.cancel()

    @commands.is_owner()
    @commands.command(aliases=["fmset"])
    async def lastfmset(self, ctx):
        """Instructions on how to set the api key."""
        message = (
            "1. Vist the [LastFM](https://www.last.fm/api/) site and click on 'Get an API Account'.\n"
            "2. Fill in the application. Once completed do not exit the page. - "
            "Copy all information on the page and save it.\n"
            f"3. Enter the key via `{ctx.clean_prefix}set api lastfm appid <appid_here>`\n"
            f"4. Enter the secret via `{ctx.clean_prefix}set api lastfm secret <secret_here>`"
        )
        await ctx.maybe_send_embed(message)

    @commands.command()
    @commands.check(tokencheck)
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

    @fm.command(aliases=["recents", "re"], usage="[amount]")
    async def recent(self, ctx, size: int = 15):
        """Recently listened tracks."""
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a last.fm account set. Please set one with {}fm login".format(
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
        """Your top tracks or albums for specific artist.

        Usage:
            [p]fm artist [timeframe] toptracks <artist name>
            [p]fm artist [timeframe] topalbums <artist name>
            [p]fm artist [timeframe] overview  <artist name>"""
        username = await self.config.user(ctx.author).lastfm_username()
        if username is None:
            return await ctx.send(
                "You do not have a last.fm account set. Please set one with {}fm login".format(
                    ctx.clean_prefix
                )
            )

        period = get_period(timeframe)
        if period in [None, "today"]:
            artistname = " ".join([datatype, artistname]).strip()
            datatype = timeframe
            period = "overall"

        artistname = self.remove_mentions(artistname)

        if artistname == "":
            return await ctx.send("Missing artist name!")

        if datatype in ["toptracks", "tt", "tracks", "track"]:
            datatype = "tracks"

        elif datatype in ["topalbums", "talb", "albums", "album"]:
            datatype = "albums"

        elif datatype in ["overview", "stats", "ov"]:
            return await self.artist_overview(ctx, period, artistname, username)

        else:
            return await ctx.send_help()

        artist, data = await self.artist_top(ctx, period, artistname, datatype, username)
        if artist is None or not data:
            artistname = escape(artistname)
            if period == "overall":
                return await ctx.send(f"You have never listened to **{artistname}**!")
            else:
                return await ctx.send(
                    f"You have not listened to **{artistname}** in the past {period}s!"
                )

        total = 0
        rows = []
        for i, (name, playcount) in enumerate(data, start=1):
            rows.append(f"`#{i:2}` **{playcount}** {format_plays(playcount)} — **{escape(name)}**")
            total += playcount

        artistname = urllib.parse.quote_plus(artistname)
        content = discord.Embed(color=await ctx.embed_color())
        content.set_thumbnail(url=artist["image_url"])
        # content.colour = await self.cached_image_color(artist["image_url"])
        content.set_author(
            name=f"{ctx.author.display_name} — "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + f"Top {datatype} by {artist['formatted_name']}",
            icon_url=ctx.author.avatar_url,
            url=f"https://last.fm/user/{username}/library/music/{artistname}/"
            f"+{datatype}?date_preset={period_http_format(period)}",
        )
        content.set_footer(
            text=f"Total {total} {format_plays(total)} across {len(rows)} {datatype}"
        )

        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @fm.command()
    async def last(self, ctx):
        """
        Your weekly listening overview.
        """
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a last.fm account set. Please set one with {}fm login".format(
                    ctx.clean_prefix
                )
            )
        await self.listening_report(ctx, "week", name)

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

import asyncio
import urllib.parse
from operator import itemgetter

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.data_manager import bundled_data_path
from redbot.core.utils.chat_formatting import escape, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import *
from .charts import ChartMixin
from .compare import CompareMixin
from .exceptions import *
from .fmmixin import FMMixin, command_fm
from .love import LoveMixin
from .nowplaying import NowPlayingMixin
from .profile import ProfileMixin
from .recent import RecentMixin
from .scrobbler import ScrobblerMixin
from .tags import TagsMixin
from .top import TopMixin
from .utils.base import UtilsMixin
from .utils.tokencheck import *
from .whoknows import WhoKnowsMixin
from .wordcloud import WordCloudMixin


class LastFM(
    ChartMixin,
    CompareMixin,
    FMMixin,
    LoveMixin,
    NowPlayingMixin,
    ProfileMixin,
    RecentMixin,
    ScrobblerMixin,
    TagsMixin,
    TopMixin,
    UtilsMixin,
    WhoKnowsMixin,
    WordCloudMixin,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Interacts with the last.fm API.
    """

    __version__ = "1.6.9"

    # noinspection PyMissingConstructor
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=95932766180343808, force_registration=True)
        defaults = {"lastfm_username": None, "session_key": None, "scrobbles": 0, "scrobble": True}
        self.config.register_global(version=1)
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

    def format_help_for_context(self, ctx):
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, *, requester, user_id):
        await self.config.user_from_id(user_id).clear()

    async def chart_clear_loop(self):
        await self.bot.wait_until_ready()
        while True:
            self.chart_data = {}
            await asyncio.sleep(1800)

    async def initialize(self):
        token = await self.bot.get_shared_api_tokens("lastfm")
        self.token = token.get("appid")
        self.secret = token.get("secret")
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

    @commands.Cog.listener(name="on_red_api_tokens_update")
    async def listener_update_class_tokens(self, service_name, api_tokens):
        if service_name == "lastfm":
            self.token = api_tokens.get("appid")
            self.secret = api_tokens.get("secret")

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
        if self.chart_data_loop:
            self.chart_data_loop.cancel()

    @commands.is_owner()
    @commands.command(name="lastfmset", aliases=["fmset"])
    async def command_lastfmset(self, ctx):
        """Instructions on how to set the api key."""
        message = (
            "1. Visit the [LastFM](https://www.last.fm/api/) website and click on 'Get an API Account'.\n"
            "2. Fill in the application. Once completed do not exit the page. - "
            "Copy all information on the page and save it.\n"
            f"3. Enter the api key via `{ctx.clean_prefix}set api lastfm appid <appid_here>`\n"
            f"4. Enter the api secret via `{ctx.clean_prefix}set api lastfm secret <secret_here>`"
        )
        await ctx.maybe_send_embed(message)

    @commands.command(name="crowns")
    @commands.check(tokencheck)
    @commands.guild_only()
    async def command_crowns(self, ctx, user: discord.Member = None):
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
            rows.append(f"**{artist}** with **{playcount}** {self.format_plays(playcount)}")

        content = discord.Embed(
            title=f"Artist crowns for {user.name} — Total {len(crownartists)} crowns",
            color=user.color,
        )
        content.set_footer(text="Playcounts are updated on the whoknows command.")
        if not rows:
            return await ctx.send("You do not have any crowns.")
        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @command_fm.command(
        name="artist", usage="[timeframe] <toptracks|topalbums|overview> <artist name>"
    )
    async def command_artist(self, ctx, timeframe, datatype, *, artistname=""):
        """Your top tracks or albums for specific artist.

        Usage:
            [p]fm artist [timeframe] toptracks <artist name>
            [p]fm artist [timeframe] topalbums <artist name>
            [p]fm artist [timeframe] overview  <artist name>"""
        conf = await self.config.user(ctx.author).all()
        username = conf["lastfm_username"]

        period, _ = self.get_period(timeframe)
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
            rows.append(
                f"`#{i:2}` **{playcount}** {self.format_plays(playcount)} — **{escape(name)}**"
            )
            total += playcount

        artistname = urllib.parse.quote_plus(artistname)
        content = discord.Embed(color=await ctx.embed_color())
        content.set_thumbnail(url=artist["image_url"])
        content.set_author(
            name=f"{ctx.author.display_name} — "
            + (f"{self.humanized_period(period)} " if period != "overall" else "")
            + f"Top {datatype} by {artist['formatted_name']}",
            icon_url=ctx.author.avatar_url,
            url=f"https://last.fm/user/{username}/library/music/{artistname}/"
            f"+{datatype}?date_preset={self.period_http_format(period)}",
        )
        content.set_footer(
            text=f"Total {total} {self.format_plays(total)} across {len(rows)} {datatype}"
        )

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @command_fm.command(name="last")
    async def command_last(self, ctx):
        """
        Your weekly listening overview.
        """
        conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in(conf)
        await self.listening_report(ctx, "week", conf["lastfm_username"])

    @command_fm.command(name="lyrics", aliases=["lyr"])
    async def command_lyrics(self, ctx, *, track: str = None):
        """Currently playing song or most recent song."""
        if track is None:
            conf = await self.config.user(ctx.author).all()
            self.check_if_logged_in(conf)
            track, artist, albumname, image_url = await self.get_current_track(
                ctx, conf["lastfm_username"]
            )

            title = (
                f"**{escape(artist, formatting=True)}** — ***{escape(track, formatting=True)} ***"
            )

            results, songtitle = await self.lyrics_musixmatch(f"{artist} {track}")
            if results is None:
                return await ctx.send(f'No lyrics for "{artist} {track}" found.')
            embeds = []
            results = list(pagify(results, page_length=2048))
            for i, page in enumerate(results, 1):
                content = discord.Embed(
                    color=await ctx.embed_color(),
                    description=page,
                    title=title,
                )
                content.set_thumbnail(url=image_url)
                if len(results) > 1:
                    content.set_footer(text=f"Page {i}/{len(results)}")

                embeds.append(content)
            if len(embeds) > 1:
                await menu(ctx, embeds, DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=embeds[0])
        else:

            results, songtitle = await self.lyrics_musixmatch(track)
            if results is None:
                return await ctx.send(f'No lyrics for "{track}" found.')
            embeds = []
            results = list(pagify(results, page_length=2048))
            for i, page in enumerate(results, 1):
                content = discord.Embed(
                    color=await ctx.embed_color(),
                    title=f"***{escape(songtitle, formatting=True)} ***",
                    description=page,
                )
                if len(results) > 1:
                    content.set_footer(text=f"Page {i}/{len(results)}")
                embeds.append(content)
            if len(embeds) > 1:
                await menu(ctx, embeds, DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=embeds[0])

    @command_fm.command(name="streak")
    async def command_streak(self, ctx, user: discord.User = None):
        """
        View how many times you've listened to something in a row

        Only the most 200 recent plays are tracked
        """
        if not user:
            user = ctx.author
        conf = await self.config.user(user).all()
        self.check_if_logged_in(conf, user == ctx.author)
        data = await self.api_request(
            ctx,
            {"user": conf["lastfm_username"], "method": "user.getrecenttracks", "limit": 200},
        )
        tracks = data["recenttracks"]["track"]
        if not tracks or not isinstance(tracks, list):
            return await ctx.send("You have not listened to anything yet!")
        track_streak = [tracks[0]["name"], 1, True]
        artist_streak = [tracks[0]["artist"]["#text"], 1, True]
        album_streak = [tracks[0]["album"]["#text"], 1, True]
        ignore = True
        for x in tracks:
            if ignore:
                ignore = False
                continue
            if track_streak[2]:
                if x["name"] == track_streak[0]:
                    track_streak[1] += 1
                else:
                    track_streak[2] = False
            if artist_streak[2]:
                if x["artist"]["#text"] == artist_streak[0]:
                    artist_streak[1] += 1
                else:
                    artist_streak[2] = False
            if album_streak[2]:
                if x["album"]["#text"] == album_streak[0]:
                    album_streak[1] += 1
                else:
                    album_streak[2] = False

            if not track_streak[2] and not artist_streak[2] and not album_streak[2]:
                break

        if track_streak[1] == 1 and artist_streak[1] == 1 and album_streak[1] == 1:
            return await ctx.send("You have not listened to anything in a row.")
        embed = discord.Embed(color=await ctx.embed_color(), title=f"{user.name}'s streaks")
        embed.set_thumbnail(url=tracks[0]["image"][3]["#text"])
        if track_streak[1] > 1:
            embed.add_field(
                name="Track", value=f"{track_streak[1]} times in a row \n({track_streak[0][:50]})"
            )
        if artist_streak[1] > 1:
            embed.add_field(
                name="Artist",
                value=f"{artist_streak[1]} times in a row \n({artist_streak[0][:50]})",
            )
        if album_streak[1] > 1:
            embed.add_field(
                name="Album", value=f"{album_streak[1]} times in a row \n({album_streak[0][:50]})"
            )

        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx, error):
        if hasattr(error, "original"):
            if isinstance(error.original, SilentDeAuthorizedError):
                return
            if isinstance(error.original, LastFMError):
                await ctx.send(str(error.original))
                return
        await ctx.bot.on_command_error(ctx, error, unhandled_by_cog=True)

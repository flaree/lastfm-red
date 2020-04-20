import asyncio
import math
import os
import re
import urllib.parse
from operator import itemgetter
from typing import Optional
from copy import deepcopy
import regex

import aiohttp
import arrow
import discord
from bs4 import BeautifulSoup
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
from requests_futures.sessions import FuturesSession  # from wyns cog


class LastFMError(Exception):
    pass


async def tokencheck(ctx):
    token = await ctx.bot.get_shared_api_tokens("lastfm")
    return bool(token.get("appid"))


class LastFm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=95932766180343808, force_registration=True)
        defaults = {"lastfm_username": None}

        self.config.register_member(**defaults)
        self.config.register_guild(crowns={})
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Arch Linux; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0"
            },
            loop=self.bot.loop,
        )
        self.token = None

    async def initalize(self):
        token = await self.bot.get_shared_api_tokens("lastfm")
        self.token = token.get("appid")

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, api_tokens):
        if service_name == "lastfm":
            self.token = api_tokens.get("appid")

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.check(tokencheck)
    @commands.group(case_insensitive=True)
    async def fm(self, ctx):
        """Last.fm commands"""
        pass

    @fm.command()
    async def set(self, ctx, username):
        """Save your last.fm username."""
        try:
            content = await self.get_userinfo_embed(ctx, username)
        except LastFMError as e:
            return await ctx.send(str(e))
        if content is None:
            return await ctx.send(f":warning: Invalid Last.fm username `{username}`")

        await self.config.member(ctx.author).lastfm_username.set(username)
        await ctx.send(
            f"{ctx.message.author.mention} Username saved as `{username}`", embed=content
        )

    @fm.command()
    async def unset(self, ctx):
        """Unlink your last.fm."""
        await self.config.member(ctx.author).lastfm_username.set(None)
        await ctx.send(":broken_heart: Removed your last.fm username from the database")
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
        name = await self.config.member(author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.prefix
                )
            )
        try:
            await ctx.send(embed=await self.get_userinfo_embed(ctx, name))
        except LastFMError as e:
            return await ctx.send(str(e))

    @commands.command()
    @commands.guild_only()
    @commands.cooldown(2, 10, type=commands.BucketType.user)
    async def whoknows(self, ctx, *, artistname):
        """Check who has listened to a given artist the most.
        Usage:
            >whoknows <artist name>
        """
        listeners = []
        tasks = []
        async with ctx.typing():
            userslist = await self.config.all_members(guild=ctx.guild)
            for user in userslist:
                lastfm_username = userslist[user]["lastfm_username"]
                if lastfm_username is None:
                    continue
                member = ctx.guild.get_member(user)
                if member is None:
                    continue

                tasks.append(self.get_playcount(ctx, artistname, lastfm_username, member))
            if tasks:
                try:
                    data = await asyncio.gather(*tasks)
                except LastFMError as e:
                    return await ctx.send(str(e))
                for playcount, user, name in data:
                    if playcount > 0:
                        artistname = name
                        listeners.append((playcount, user))
            else:
                return await ctx.send(
                    "Nobody on this server has connected their last.fm account yet!"
                )
            rows = []
            total = 0
            for i, (playcount, user) in enumerate(
                sorted(listeners, key=lambda p: p[0], reverse=True), start=1
            ):
                if i == 1:
                    rank = ":crown:"
                    old_kingdata = await self.config.guild(ctx.guild).crowns()
                    old_kingartist = old_kingdata.get(artistname)
                    if old_kingartist is not None:
                        old_king = old_kingartist["user"]
                        old_king = ctx.guild.get_member(old_king)
                    else:
                        old_king = None
                    new_king = user
                    play = playcount
                else:
                    rank = f"`#{i:2}`"
                rows.append(f"{rank} **{user.name}** — **{playcount}** {format_plays(playcount)}")
                total += playcount

            if not rows:
                return await ctx.send(f"Nobody on this server has listened to **{artistname}**")

            content = discord.Embed(
                title=f"Who knows **{artistname}**?",
                color=await self.bot.get_embed_color(ctx.channel),
            )
            image_url = await self.scrape_artist_image(artistname)
            content.set_thumbnail(url=image_url)
            if len(listeners) > 1:
                content.set_footer(text=f"Collective plays: {total}")

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])
        if old_king is None:
            await ctx.send(f"> **{new_king.name}** just earned the **{artistname}** crown.")
            async with self.config.guild(ctx.guild).crowns() as crowns:
                crowns[artistname] = {"user": new_king.id, "playcount": play}
        if isinstance(old_king, discord.Member):
            if not (old_king.id == new_king.id):
                await ctx.send(f"> **{new_king.name}** just earned the **{artistname}** crown.")
                async with self.config.guild(ctx.guild).crowns() as crowns:
                    crowns[artistname] = {"user": new_king.id, "playcount": play}
            if old_king.id == new_king.id:
                async with self.config.guild(ctx.guild).crowns() as crowns:
                    crowns[artistname] = {"user": new_king.id, "playcount": play}

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
                "You haven't acquired any crowns yet! Use the `>whoknows` command to claim crowns :crown:"
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
        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @fm.command(aliases=["np"])
    async def nowplaying(self, ctx, user: Optional[discord.Member] = None):
        """Currently playing song or most recent song."""
        author = user or ctx.author
        async with ctx.typing():
            name = await self.config.member(author).lastfm_username()
            if name is None:
                return await ctx.send(
                    "You do not have a LastFM account set. Please set one with {}fm set".format(
                        ctx.prefix
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
                # image_url_small = tracks[0]['image'][1]['#text']
                # image_colour = await color_from_image_url(image_url_small)
            except KeyError:
                artist = tracks["artist"]["#text"]
                album = tracks["album"]["#text"]
                track = tracks["name"]
                image_url = tracks["image"][-1]["#text"]

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            # content.colour = int(image_colour, 16)
            content.description = f"**{escape_md(album)}**"
            content.title = f"**{escape_md(artist)}** — ***{escape_md(track)} ***"
            content.set_thumbnail(url=image_url)

            # tags and playcount
            try:
                trackdata = await self.api_request(
                    ctx,
                    {"user": name, "method": "track.getInfo", "artist": artist, "track": track},
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
                name=f"{user_attr['user']} {state}", icon_url=ctx.message.author.avatar_url
            )
            if state == "— Most recent track":
                msg = "You aren't currently listening to anything, here is the most recent song found."
            else:
                msg = None
            await ctx.send(msg if msg is not None else None, embed=content)

    @fm.command(aliases=["ta"])
    async def topartists(self, ctx, *args):
        """Most listened artists.

        Usage:
            [p]fm topartists [timeframe] [amount]
        """
        name = await self.config.member(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.prefix
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
                name = escape_md(artist["name"])
                plays = artist["playcount"]
                rows.append(f"`#{i:2}` **{plays}** {format_plays(plays)} — **{name}**")

            image_url = await self.scrape_artist_image(artists[0]["name"])
            # image_colour = await color_from_image_url(image_url)

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            # content.colour = int(image_colour, 16)
            content.set_thumbnail(url=image_url)
            content.set_footer(text=f"Total unique artists: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top artists",
                icon_url=ctx.message.author.avatar_url,
            )

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @fm.command(aliases=["talb"])
    async def topalbums(self, ctx, *args):
        """Most listened albums.

        Usage:
            [p]fm topalbums [timeframe] [amount]    
        """
        name = await self.config.member(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.prefix
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
            name = escape_md(album["name"])
            artist_name = escape_md(album["artist"]["name"])
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

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @fm.command(aliases=["tt"])
    async def toptracks(self, ctx, *args):
        """Most listened tracks.

        Usage:
            [p]fm toptracks [timeframe] [amount]
        """
        name = await self.config.member(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.prefix
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
                name = escape_md(track["name"])
                artist_name = escape_md(track["artist"]["name"])
                plays = track["playcount"]
                rows.append(
                    f"`#{i:2}` **{plays}** {format_plays(plays)} — **{artist_name}** — ***{name}***"
                )
            try:
                trackdata = await self.api_request(
                    ctx,
                    {
                        "user": await self.config.member(ctx.author).lastfm_username(),
                        "method": "track.getInfo",
                        "artist": tracks[0]["artist"]["name"],
                        "track": tracks[0]["name"],
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            try:
                image_url = trackdata["track"]["album"]["image"][-1]["#text"]
                # image_url_small = trackdata['track']['album']['image'][1]['#text']
                # image_colour = await color_from_image_url(image_url_small)
            except KeyError:
                image_url = await self.scrape_artist_image(tracks[0]["artist"]["name"])
                # image_colour = await color_from_image_url(image_url)

            content.set_thumbnail(url=image_url)

            content.set_footer(text=f"Total unique tracks: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top tracks",
                icon_url=ctx.message.author.avatar_url,
            )

            pages = await self.create_pages(content, rows)
            if len(pages) > 1:
                await menu(ctx, pages[:15], DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=pages[0])

    @fm.command(aliases=["recents", "re"])
    async def recent(self, ctx, size: int = 15):
        """Recently listened tracks.

        Usage:
            [p]fm recent [amount]
        """
        name = await self.config.member(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.prefix
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
                name = escape_md(track["name"])
                artist_name = escape_md(track["artist"]["#text"])
                rows.append(f"**{artist_name}** — ***{name}***")

            image_url = tracks[0]["image"][-1]["#text"]
            # image_url_small = tracks[0]['image'][1]['#text']
            # image_colour = await color_from_image_url(image_url_small)

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            # content.colour = int(image_colour, 16)
            content.set_thumbnail(url=image_url)
            content.set_footer(text=f"Total scrobbles: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — Recent tracks", icon_url=ctx.message.author.avatar_url
            )

            pages = await self.create_pages(content, rows)
            if len(pages) > 1:
                await menu(ctx, pages[:15], DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=pages[0])

    @fm.command()
    async def artist(self, ctx, timeframe, datatype, *, artistname=""):
        """Your top tracks or albums for specific artist.
        
        Usage:
            [p]fm artist [timeframe] toptracks <artist name>
            [p]fm artist [timeframe] topalbums <artist name>
            [p]fm artist [timeframe] overview  <artist name>
        """
        name = await self.config.member(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.prefix
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
            method = "user.gettoptracks"
            path = ["toptracks", "track"]
        elif datatype in ["topalbums", "talb", "albums", "album"]:
            method = "user.gettopalbums"
            path = ["topalbums", "album"]
        elif datatype in ["overview", "stats", "ov"]:
            return await self.artist_overview(ctx, period, artistname, name)
        else:
            return

        async def extract_songs(items):
            songs = []
            for item in items:
                item_artist = item["artist"]["name"]
                if item_artist.casefold() == artistname.casefold():
                    songs.append((item["name"], int(item["playcount"])))
            return songs

        try:
            data = await self.api_request(
                ctx, {"method": method, "user": name, "limit": 200, "period": period}
            )
        except LastFMError as e:
            return await ctx.send(str(e))
        total_pages = int(data[path[0]]["@attr"]["totalPages"])
        artist_data = await extract_songs(data[path[0]][path[1]])
        username = data[path[0]]["@attr"]["user"]

        if total_pages > 1:
            tasks = []
            for i in range(2, total_pages + 1):
                params = {
                    "method": method,
                    "user": name,
                    "limit": 200,
                    "period": period,
                    "page": i,
                }
                tasks.append(self.api_request(ctx, params))
            try:
                data = await asyncio.gather(*tasks)
            except LastFMError as e:
                return await ctx.send(str(e))
            extraction_tasks = []
            for datapage in data:
                extraction_tasks.append(extract_songs(datapage[path[0]][path[1]]))

            artist_data += sum(await asyncio.gather(*extraction_tasks), [])

        if not artist_data:
            if period == "overall":
                return await ctx.send(f"You have never listened to **{artistname}**!")
            else:
                return await ctx.send(
                    f"You have not listened to **{artistname}** in the past {period}s!"
                )
        try:
            artist_info = await self.api_request(
                ctx, {"method": "artist.getinfo", "artist": artistname}
            )
        except LastFMError as e:
            return await ctx.send(str(e))
        artist_info = artist_info.get("artist")
        image_url = await self.scrape_artist_image(artistname)
        formatted_name = artist_info["name"]

        # image_colour = await color_from_image_url(image_url)

        content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
        content.set_thumbnail(url=image_url)
        # content.colour = int(image_colour, 16)

        rows = []
        total_plays = 0
        for i, (name, playcount) in enumerate(artist_data, start=1):
            line = f"`#{i:2}` **{playcount}** {format_plays(total_plays)} — **{name}**"
            total_plays += playcount
            rows.append(line)

        content.set_footer(text=f"Total {total_plays} {format_plays(total_plays)}")
        content.title = (
            f"{username} — "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + f"top {'tracks' if method == 'user.gettoptracks' else 'albums'}"
            f" for {formatted_name}"
        )

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @commands.command(aliases=["lyr"])
    async def lyrics(self, ctx, *, track: str = None):
        """Currently playing song or most recent song."""
        if track is None:
            name = await self.config.member(ctx.author).lastfm_username()
            if name is None:
                return await ctx.send(
                    "You do not have a LastFM account set. Please set one with {}fm set".format(
                        ctx.prefix
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

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            # content.colour = int(image_colour, 16)
            content.title = f"**{escape_md(artist)}** — ***{escape_md(track)} ***"
            content.set_thumbnail(url=image_url)

            # tags and playcount
            if "@attr" in tracks[0]:
                if "nowplaying" in tracks[0]["@attr"]:
                    results = lyrics_musixmatch(track)
                    for page in pagify(results):
                        content.description = page
                        await ctx.send(embed=content)
            else:
                await ctx.send("You're not currently playing a song.")
        else:
            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            # content.colour = int(image_colour, 16)
            content.title = f"***{escape_md(track)} ***"

            results = lyrics_musixmatch(track)
            for page in pagify(results):
                content.description = page
                await ctx.send(embed=content)

    async def api_request(self, ctx, params):
        """Get json data from the lastfm api"""
        url = "http://ws.audioscrobbler.com/2.0/"
        params["api_key"] = self.token
        params["format"] = "json"
        async with ctx.typing():
            async with self.session.get(url, params=params) as response:
                try:
                    content = await response.json()
                    if response.status == 200:
                        return content
                    else:
                        raise LastFMError(
                            f"Error {content.get('error')} : {content.get('message')}"
                        )

                except aiohttp.client_exceptions.ContentTypeError:
                    return None

    async def scrape_artist_image(self, artist):
        url = f"https://www.last.fm/music/{urllib.parse.quote_plus(artist)}/+images"
        data = await fetch(self.session, url, handling="text")

        soup = BeautifulSoup(data, "html.parser")
        if soup is None:
            return ""
        image = soup.find("img", {"class": "image-list-image"})
        if image is None:
            try:
                image = soup.find("li", {"class": "image-list-item-wrapper"}).find("a").find("img")
            except AttributeError:
                return ""
        return image["src"].replace("/avatar170s/", "/300x300/") if image else ""

    async def scrape_artists_for_chart(self, username, period, amount):
        period_format_map = {
            "7day": "LAST_7_DAYS",
            "1month": "LAST_30_DAYS",
            "3month": "LAST_90_DAYS",
            "6month": "LAST_180_DAYS",
            "12month": "LAST_365_DAYS",
            "overall": "ALL",
        }
        tasks = []
        url = f"https://www.last.fm/user/{username}/library/artists"
        for i in range(1, math.ceil(amount / 50) + 1):
            params = {"date_preset": period_format_map[period], "page": i}
            task = asyncio.ensure_future(fetch(self.session, url, params, handling="text"))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        images = []
        for data in responses:
            if len(images) >= amount:
                break
            else:
                soup = BeautifulSoup(data, "html.parser")
                imagedivs = soup.findAll("td", {"class": "chartlist-image"})
                images += [
                    div.find("img")["src"].replace("/avatar70s/", "/300x300/") for div in imagedivs
                ]

        return images

    async def get_similar_artists(self, artistname):
        similar = []
        url = f"https://last.fm/music/{artistname}"
        data = await fetch(self.session, url, handling="text")
        soup = BeautifulSoup(data, "html.parser")
        for artist in soup.findAll("h3", {"class": "artist-similar-artists-sidebar-item-name"}):
            similar.append(artist.find("a").text)
        listeners = (
            soup.find("li", {"class": "header-metadata-tnew-item--listeners"}).find("abbr").text
        )
        return similar, listeners

    async def artist_overview(self, ctx, period, artistname, name):
        """Overall artist view"""
        albums = []
        tracks = []
        metadata = [None, None, None]
        url = f"https://last.fm/user/{name}/library/music/{artistname}?date_preset={period_http_format(period)}"
        data = await fetch(self.session, url, handling="text")
        soup = BeautifulSoup(data, "html.parser")
        try:
            albumsdiv, tracksdiv, _ = soup.findAll("tbody", {"data-playlisting-add-entries": ""})
        except ValueError:
            if period == "overall":
                return await ctx.send(f"You have never listened to **{artistname}**!")
            else:
                return await ctx.send(
                    f"You have not listened to **{artistname}** in the past {period}s!"
                )

        for container, destination in zip([albumsdiv, tracksdiv], [albums, tracks]):
            items = container.findAll("tr", {"class": "chartlist-row"})
            for item in items:
                name = item.find("td", {"class": "chartlist-name"}).find("a").get("title")
                playcount = (
                    item.find("span", {"class": "chartlist-count-bar-value"})
                    .text.replace("scrobbles", "")
                    .replace("scrobble", "")
                    .strip()
                )
                destination.append((name, playcount))

        metadata_list = soup.find("ul", {"class": "metadata-list"})
        for i, metadata_item in enumerate(
            metadata_list.findAll("p", {"class": "metadata-display"})
        ):
            metadata[i] = int(metadata_item.text.replace(",", ""))

        artist_info = await self.api_request(
            ctx, {"method": "artist.getinfo", "artist": artistname}
        )
        artist_info = artist_info.get("artist")
        formatted_name = artist_info["name"]
        image_url = (
            soup.find("span", {"class": "library-header-image"})
            .find("img")
            .get("src")
            .replace("avatar70s", "avatar300s")
        )
        # image_colour = await util.color_from_image_url(image_url)

        content = discord.Embed()
        content.set_thumbnail(url=image_url)
        # content.colour = int(image_colour, 16)
        content.set_author(
            name=f"{ctx.author.name} — {formatted_name} "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + "Overview",
            icon_url=ctx.author.avatar_url,
        )
        similar, listeners = await self.get_similar_artists(formatted_name)

        content.set_footer(text=f"{listeners} Listeners | Similar to: {', '.join(similar)}")

        crowns = await self.config.guild(ctx.guild).crowns()
        crown_holder = crowns.get(artistname, None)

        if crown_holder is None or crown_holder["user"] != ctx.author.id:
            crownstate = ""
        else:
            crownstate = ":crown: "

        content.add_field(
            name="Scrobbles | Albums | Tracks",
            value=f"{crownstate}**{metadata[0]}** | **{metadata[1]}** | **{metadata[2]}**",
            inline=False,
        )

        content.add_field(
            name="Top albums",
            value="\n".join(
                f"`#{i:2}` **{item}** ({playcount})"
                for i, (item, playcount) in enumerate(albums, start=1)
            ),
            inline=True,
        )
        content.add_field(
            name="Top tracks",
            value="\n".join(
                f"`#{i:2}` **{item}** ({playcount})"
                for i, (item, playcount) in enumerate(tracks, start=1)
            ),
            inline=True,
        )
        await ctx.send(embed=content)

    async def get_userinfo_embed(self, ctx, username):
        data = await self.api_request(ctx, {"user": username, "method": "user.getinfo"})
        if data is None:
            return None

        username = data["user"]["name"]
        playcount = data["user"]["playcount"]
        profile_url = data["user"]["url"]
        profile_pic_url = data["user"]["image"][3]["#text"]
        timestamp = arrow.get(int(data["user"]["registered"]["unixtime"]))
        # image_colour = await color_from_image_url(profile_pic_url)

        content = discord.Embed(title=f":cd: {username}")
        content.add_field(name="Last.fm profile", value=f"[Link]({profile_url})", inline=True)
        content.add_field(
            name="Registered",
            value=f"{timestamp.humanize()}\n{timestamp.format('DD/MM/YYYY')}",
            inline=True,
        )
        content.set_thumbnail(url=profile_pic_url)
        content.set_footer(text=f"Total plays: {playcount}")
        return content

    async def get_playcount(self, ctx, artist, username, reference=None):
        data = await self.api_request(
            ctx, {"method": "artist.getinfo", "user": username, "artist": artist, "autocorrect": 1}
        )
        try:
            count = int(data["artist"]["stats"]["userplaycount"])
            name = data["artist"]["name"]
        except KeyError:
            count = 0
            name = None

        if reference is None:
            return count
        else:
            return count, reference, name

    async def create_pages(self, content, rows, maxrows=15, maxpages=10):
        pages = []
        content.description = ""
        thisrow = 0
        rowcount = len(rows)
        for row in rows:
            thisrow += 1
            if len(content.description) + len(row) < 2000 and thisrow < maxrows + 1:
                content.description += f"\n{row}"
                rowcount -= 1
            else:
                thisrow = 1
                if len(pages) == maxpages - 1:
                    content.description += f"\n*+ {rowcount} more entries...*"
                    pages.append(content)
                    content = None
                    break

                pages.append(content)
                content = deepcopy(content)
                content.description = f"{row}"
                rowcount -= 1
        if content is not None and not content.description == "":
            pages.append(content)

        return pages


def lyrics_musixmatch(artistsong):
    artistsong = re.sub("[^a-zA-Z0-9 \n.]", "", artistsong)
    artistsong = re.sub(r"\s+", " ", artistsong).strip()
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Arch Linux; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0"
    }
    try:
        session = FuturesSession()
        searchresult = session.get(
            "https://musixmatch.com/search/{}".format(artistsong).replace(" ", "%20"),
            headers=headers,
        )
        soup = BeautifulSoup(searchresult.result().content, "html.parser")
        url = "https://www.musixmatch.com" + soup.find("a", {"class": "title"})["href"]
        soup = BeautifulSoup(session.get(url, headers=headers).result().content, "html.parser")
        lyrics = soup.text.split('"body":"')[1].split('","language"')[0]
        lyrics = lyrics.replace("\\n", "\n")
        lyrics = lyrics.replace("\\", "")
        lyrics = lyrics.replace("&amp;", "&")
        lyrics = lyrics.replace("`", "'")
        lyrics = lyrics.strip()

    except Exception:
        lyrics = "No lyrics Found."

    return lyrics


def format_plays(amount):
    if amount == 1:
        return "play"
    else:
        return "plays"


def get_period(timeframe):
    if timeframe in ["7day", "7days", "weekly", "week", "1week"]:
        period = "7day"
    elif timeframe in ["30day", "30days", "monthly", "month", "1month"]:
        period = "1month"
    elif timeframe in ["90day", "90days", "3months", "3month"]:
        period = "3month"
    elif timeframe in ["180day", "180days", "6months", "6month", "halfyear"]:
        period = "6month"
    elif timeframe in ["365day", "365days", "1year", "year", "12months", "12month"]:
        period = "12month"
    elif timeframe in ["at", "alltime", "overall"]:
        period = "overall"
    else:
        period = None

    return period


def humanized_period(period):
    if period == "7day":
        humanized = "weekly"
    elif period == "1month":
        humanized = "monthly"
    elif period == "3month":
        humanized = "past 3 months"
    elif period == "6month":
        humanized = "past 6 months"
    elif period == "12month":
        humanized = "yearly"
    else:
        humanized = "alltime"

    return humanized


def parse_arguments(args):
    parsed = {"period": None, "amount": None}
    for a in args:
        if parsed["amount"] is None:
            try:
                parsed["amount"] = int(a)
                continue
            except ValueError:
                pass
        if parsed["period"] is None:
            parsed["period"] = get_period(a)

    if parsed["period"] is None:
        parsed["period"] = "overall"
    if parsed["amount"] is None:
        parsed["amount"] = 15
    return parsed


def parse_chart_arguments(args):
    parsed = {
        "period": None,
        "amount": None,
        "width": None,
        "height": None,
        "method": None,
        "path": None,
    }
    for a in args:
        a = a.lower()
        if parsed["amount"] is None:
            try:
                size = a.split("x")
                parsed["width"] = int(size[0])
                if len(size) > 1:
                    parsed["height"] = int(size[1])
                else:
                    parsed["height"] = int(size[0])
                continue
            except ValueError:
                pass

        if parsed["method"] is None:
            if a in ["talb", "topalbums", "albums", "album"]:
                parsed["method"] = "user.gettopalbums"
                continue
            elif a in ["ta", "topartists", "artists", "artist"]:
                parsed["method"] = "user.gettopartists"
                continue
            elif a in ["re", "recent", "recents"]:
                parsed["method"] = "user.getrecenttracks"
                continue

        if parsed["period"] is None:
            parsed["period"] = get_period(a)

    if parsed["period"] is None:
        parsed["period"] = "7day"
    if parsed["width"] is None:
        parsed["width"] = 3
        parsed["height"] = 3
    if parsed["method"] is None:
        parsed["method"] = "user.gettopalbums"
    parsed["amount"] = parsed["width"] * parsed["height"]
    return parsed


async def fetch(session, url, params={}, handling="json"):
    async with session.get(url, params=params) as response:
        if handling == "json":
            return await response.json()
        elif handling == "text":
            return await response.text()
        else:
            return await response


def escape_md(s):

    transformations = {regex.escape(c): "\\" + c for c in ("*", "`", "_", "~", "\\", "||")}

    def replace(obj):
        return transformations.get(regex.escape(obj.group(0)), "")

    pattern = regex.compile("|".join(transformations.keys()))
    return pattern.sub(replace, s)


def period_http_format(period):
    period_format_map = {
        "7day": "LAST_7_DAYS",
        "1month": "LAST_30_DAYS",
        "3month": "LAST_90_DAYS",
        "6month": "LAST_180_DAYS",
        "12month": "LAST_365_DAYS",
        "overall": "ALL",
    }
    return period_format_map.get(period)

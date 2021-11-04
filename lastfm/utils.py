import asyncio
import contextlib
import datetime
import hashlib
import math
import re
import urllib
from copy import deepcopy
from typing import Tuple

import aiohttp
import arrow
import discord
import humanize
import tabulate
from bs4 import BeautifulSoup
from redbot.core.utils.chat_formatting import box

from .abc import MixinMeta
from .utils import *


class UtilsMixin(MixinMeta):
    """Utils"""

    def remove_mentions(self, text):
        """Remove mentions from string."""
        return (re.sub(r"<@\!?[0-9]+>", "", text)).strip()

    async def artist_top(self, ctx, period, artistname, datatype, name):
        """Scrape either top tracks or top albums from lastfm library page."""
        url = (
            f"https://last.fm/user/{name}/library/music/{artistname}/"
            f"+{datatype}?date_preset={period_http_format(period)}"
        )
        data = await fetch(ctx, self.session, url, handling="text")
        soup = BeautifulSoup(data, "html.parser")
        data = []
        try:
            chartlist = soup.find("tbody", {"data-playlisting-add-entries": ""})
        except ValueError:
            return None, []

        artist = {
            "image_url": soup.find("span", {"class": "library-header-image"})
            .find("img")
            .get("src")
            .replace("avatar70s", "avatar300s"),
            "formatted_name": soup.find("a", {"class": "library-header-crumb"}).text.strip(),
        }

        items = chartlist.findAll("tr", {"class": "chartlist-row"})
        for item in items:
            name = item.find("td", {"class": "chartlist-name"}).find("a").get("title")
            playcount = (
                item.find("span", {"class": "chartlist-count-bar-value"})
                .text.replace("scrobbles", "")
                .replace("scrobble", "")
                .strip()
            )
            data.append((name, int(playcount.replace(",", ""))))

        return artist, data

    async def lyrics_musixmatch(self, artistsong) -> Tuple[str, str]:
        artistsong = re.sub("[^a-zA-Z0-9 \n.]", "", artistsong)
        artistsong = re.sub(r"\s+", " ", artistsong).strip()
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Arch Linux; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0"
        }
        async with self.session.get(
            "https://musixmatch.com/search/{}".format(artistsong).replace(" ", "%20"),
            headers=headers,
        ) as resp:
            if resp.status == 200:
                result = await resp.text()
            else:
                return None, None
        soup = BeautifulSoup(result, "html.parser")
        songurl = soup.find("a", {"class": "title"})
        if songurl is None:
            return None, None
        url = "https://www.musixmatch.com" + songurl["href"]
        async with self.session.get(url, headers=headers) as resp:
            result = await resp.text()
        soup = BeautifulSoup(result, "html.parser")
        lyrics = soup.text.split('"body":"')
        lyrics = lyrics[0]
        songname = lyrics.split("|")[0]
        lyrics = lyrics.split('","language"')[0]
        try:
            lyrics = lyrics.split("languages")[1]
        except IndexError:
            return None, None
        lyrics = lyrics.split("Report")[0]
        lyrics = lyrics.replace("\\n", "\n")
        lyrics = lyrics.replace("\\", "")
        lyrics = lyrics.replace("&amp;", "&")
        lyrics = lyrics.replace("`", "'")
        lyrics = lyrics.strip()
        return lyrics, songname.strip()

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
                    raise LastFMError(f"Error {content.get('error')} : {content.get('message')}")

                except aiohttp.ContentTypeError:
                    return None

    async def api_post(self, params):
        """Post data to the lastfm api"""
        url = "http://ws.audioscrobbler.com/2.0/"
        params["format"] = "json"
        async with self.session.post(url, params=params) as response:
            with contextlib.suppress(aiohttp.ContentTypeError):
                content = await response.json()
                return response.status, content

    async def scrape_artist_image(self, artist, ctx):
        url = f"https://www.last.fm/music/{urllib.parse.quote_plus(artist)}/+images"
        data = await fetch(ctx, self.session, url, handling="text")

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

    async def scrape_artists_for_chart(self, ctx, username, period, amount):
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
            task = asyncio.ensure_future(fetch(ctx, self.session, url, params, handling="text"))
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

    async def get_similar_artists(self, artistname, ctx):
        similar = []
        url = f"https://last.fm/music/{artistname}"
        data = await fetch(ctx, self.session, url, handling="text")
        soup = BeautifulSoup(data, "html.parser")
        for artist in soup.findAll("h3", {"class": "artist-similar-artists-sidebar-item-name"}):
            similar.append(artist.find("a").text)
        listeners = (
            soup.find("li", {"class": "header-metadata-tnew-item--listeners"}).find("abbr").text
        )
        return similar, listeners

    async def artist_overview(self, ctx, period, artistname, fmname):
        """Overall artist view"""
        albums = []
        tracks = []
        metadata = [None, None, None]
        artistinfo = await self.api_request(
            ctx, {"method": "artist.getInfo", "artist": artistname}
        )
        url = (
            f"https://last.fm/user/{fmname}/library/music/{artistname}"
            f"?date_preset={period_http_format(period)}"
        )
        data = await fetch(ctx, self.session, url, handling="text")
        soup = BeautifulSoup(data, "html.parser")
        try:
            albumsdiv, tracksdiv, _ = soup.findAll("tbody", {"data-playlisting-add-entries": ""})
        except ValueError:
            if period == "overall":
                return await ctx.send(f"You have never listened to **{artistname}**!")
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

        artist = {
            "image_url": soup.find("span", {"class": "library-header-image"})
            .find("img")
            .get("src")
            .replace("avatar70s", "avatar300s"),
            "formatted_name": soup.find("h2", {"class": "library-header-title"}).text.strip(),
        }

        listeners = artistinfo["artist"]["stats"]["listeners"]
        globalscrobbles = artistinfo["artist"]["stats"]["playcount"]
        similar = [a["name"] for a in artistinfo["artist"]["similar"]["artist"]]
        tags = [t["name"] for t in artistinfo["artist"]["tags"]["tag"]]

        content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
        content.set_thumbnail(url=artist["image_url"])
        # content.colour = int(image_colour, 16)
        content.set_author(
            name=f"{ctx.author.name} — {artist['formatted_name']} "
            + (f"{humanized_period(period)} " if period != "overall" else "")
            + "Overview",
            icon_url=ctx.author.avatar_url,
            url=f"https://last.fm/user/{fmname}/library/music/{urllib.parse.quote_plus(artistname)}?date_preset={period_http_format(period)}",
        )
        # similar, listeners = await self.get_similar_artists(artist["formatted_name"], ctx)
        content.set_footer(text=f"{', '.join(tags)}")
        # content.set_footer(text=f"{listeners} Listeners | Similar to: {', '.join(similar)}")

        crowns = await self.config.guild(ctx.guild).crowns()
        crown_holder = crowns.get(artistname.lower(), None)
        if crown_holder is None or crown_holder["user"] != ctx.author.id:
            crownstate = None
        else:
            crownstate = "👑"
        if crownstate is not None:
            stats = [[crownstate, str(metadata[0]), str(metadata[1]), str(metadata[2])]]
            headers = ["-", "Scrobbles", "Albums", "Tracks"]
        else:
            stats = [[str(metadata[0]), str(metadata[1]), str(metadata[2])]]
            headers = ["Scrobbles", "Albums", "Tracks"]
        content.description = box(tabulate.tabulate(stats, headers=headers), lang="prolog")

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
        if similar:
            content.add_field(name="Similar artists", value=", ".join(similar), inline=False)
        await ctx.send(embed=content)

    async def get_userinfo_embed(self, ctx, user, username):
        data = await self.api_request(ctx, {"user": username, "method": "user.getinfo"})
        if not data:
            raise LastFMError

        username = data["user"]["name"]
        playcount = data["user"]["playcount"]
        profile_url = data["user"]["url"]
        profile_pic_url = data["user"]["image"][3]["#text"]
        vc_scrobbles = await self.config.user(user).scrobbles()
        timestamp = int(data["user"]["registered"]["unixtime"])
        exact_time = f"<t:{timestamp}>"
        relative_time = f"<t:{timestamp}:R>"

        content = discord.Embed(title=f"\N{OPTICAL DISC} {username}", color=await ctx.embed_color())
        content.add_field(name="Last.fm profile", value=f"[Link]({profile_url})", inline=True)
        content.add_field(
            name="Registered",
            value=f"{exact_time}\n{relative_time}",
            inline=True,
        )
        content.set_thumbnail(url=profile_pic_url)

        footer = f"Total plays: {playcount}"

        if vc_scrobbles:
            footer += f" | VC Plays: {vc_scrobbles}"

        content.set_footer(text=footer)
        return content

    async def listening_report(self, ctx, timeframe, name):
        current_day_floor = arrow.utcnow().floor("day")
        week = []
        # for i in range(7, 0, -1):
        for i in range(1, 8):
            dt = current_day_floor.shift(days=-i)
            week.append(
                {
                    "dt": int(dt.timestamp()),
                    "ts": int(dt.timestamp()),
                    "ts_to": int(dt.shift(days=+1, minutes=-1).timestamp()),
                    "day": dt.format("ddd, MMM Do"),
                    "scrobbles": 0,
                }
            )

        params = {
            "method": "user.getrecenttracks",
            "user": name,
            "from": week[-1]["ts"],
            "to": int(current_day_floor.shift(minutes=-1).timestamp()),
            "limit": 1000,
        }
        content = await self.api_request(ctx, params)
        tracks = content["recenttracks"]["track"]
        if not tracks or not isinstance(tracks, list):
            await ctx.send("No data found.")
            return

        # get rid of nowplaying track if user is currently scrobbling.
        # for some reason even with from and to parameters it appears
        if tracks[0].get("@attr") is not None:
            tracks = tracks[1:]

        day_counter = 1
        for trackdata in reversed(tracks):
            scrobble_ts = int(trackdata["date"]["uts"])
            if scrobble_ts > week[-day_counter]["ts_to"]:
                day_counter += 1

            week[day_counter - 1]["scrobbles"] += 1

        scrobbles_total = sum(day["scrobbles"] for day in week)
        scrobbles_average = round(scrobbles_total / len(week))

        rows = []
        for day in week:
            rows.append(f"`{day['day']}`: **{day['scrobbles']}** Scrobbles")

        content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
        content.set_author(
            name=f"{ctx.author.display_name} | Last {timeframe.title()}",
            icon_url=ctx.author.avatar_url,
        )
        content.description = "\n".join(rows)
        content.add_field(
            name="Total scrobbles", value=f"{scrobbles_total} Scrobbles", inline=False
        )
        content.add_field(
            name="Avg. daily scrobbles", value=f"{scrobbles_average} Scrobbles", inline=False
        )
        # content.add_field(name="Listening time", value=listening_time)
        await ctx.send(embed=content)

    async def get_np(self, ctx, username, ref):
        data = await self.api_request(
            ctx,
            {"method": "user.getrecenttracks", "user": username, "limit": 1},
        )
        song = None
        if data is not None:
            tracks = data["recenttracks"]["track"]
            if tracks:
                if "@attr" in tracks[0]:
                    if "nowplaying" in tracks[0]["@attr"]:
                        song = {
                            "artist": tracks[0]["artist"]["#text"],
                            "name": tracks[0]["name"],
                        }

        return song, ref


def format_plays(amount):
    if amount == 1:
        return "play"
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


async def fetch(ctx, session, url, params=None, handling="json"):
    if params is None:
        params = {}
    async with ctx.typing():
        async with session.get(url, params=params) as response:
            if handling == "json":
                return await response.json()
            if handling == "text":
                return await response.text()
            return await response


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


class LastFMError(Exception):
    pass


async def create_pages(content, rows, maxrows=15, maxpages=10):
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


async def tokencheck(ctx):
    token = await ctx.bot.get_shared_api_tokens("lastfm")
    return bool(token.get("appid"))


async def tokencheck_plus_secret(ctx):
    token = await ctx.bot.get_shared_api_tokens("lastfm")
    if token.get("appid") and token.get("secret"):
        return True
    return False


def hashRequest(obj, secretKey):
    """
    This hashing function is courtesy of GitHub user huberf.
    It is licensed under the MIT license.
    Source: https://github.com/huberf/lastfm-scrobbler/blob/master/lastpy/__init__.py#L50-L60
    """
    string = ""
    items = obj.keys()
    sorted(items)
    for i in items:
        string += i
        string += obj[i]
    string += secretKey
    stringToHash = string.encode("utf8")
    requestHash = hashlib.md5(stringToHash).hexdigest()
    return requestHash

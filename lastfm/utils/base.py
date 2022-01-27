import hashlib
import re
import urllib
from copy import deepcopy

import arrow
import discord
import tabulate
from bs4 import BeautifulSoup
from redbot.core.utils.chat_formatting import box

from ..abc import *
from ..exceptions import *
from .api import APIMixin
from .converters import ConvertersMixin
from .scraping import ScrapingMixin


class UtilsMixin(APIMixin, ConvertersMixin, ScrapingMixin):
    """Utils"""

    def remove_mentions(self, text):
        """Remove mentions from string."""
        return (re.sub(r"<@\!?[0-9]+>", "", text)).strip()

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
            f"?date_preset={self.period_http_format(period)}"
        )
        data = await self.fetch(ctx, url, handling="text")
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

        similar = [a["name"] for a in artistinfo["artist"]["similar"]["artist"]]
        tags = [t["name"] for t in artistinfo["artist"]["tags"]["tag"]]

        content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
        content.set_thumbnail(url=artist["image_url"])
        content.set_author(
            name=f"{ctx.author.name} — {artist['formatted_name']} "
            + (f"{self.humanized_period(period)} " if period != "overall" else "")
            + "Overview",
            icon_url=ctx.author.avatar_url,
            url=f"https://last.fm/user/{fmname}/library/music/{urllib.parse.quote_plus(artistname)}?date_preset={self.period_http_format(period)}",
        )
        content.set_footer(text=f"{', '.join(tags)}")

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

        content = discord.Embed(
            title=f"\N{OPTICAL DISC} {username}", color=await ctx.embed_color()
        )
        content.add_field(name="Last.fm profile", value=f"[Link]({profile_url})", inline=True)
        content.add_field(
            name="Registered",
            value=f"{exact_time}\n({relative_time})",
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
        await ctx.send(embed=content)

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

    def hashRequest(self, obj, secretKey):
        """
        This hashing function is courtesy of GitHub user huberf.
        It is licensed under the MIT license.
        Source: https://github.com/huberf/lastfm-scrobbler/blob/master/lastpy/__init__.py#L50-L60
        """
        string = ""
        items = obj.keys()
        items = sorted(items)
        for i in items:
            string += i
            string += obj[i]
        string += secretKey
        stringToHash = string.encode("utf8")
        requestHash = hashlib.md5(stringToHash).hexdigest()
        return requestHash

    def check_if_logged_in(self, conf, another_person=False):
        if not conf["lastfm_username"]:
            if not another_person:
                raise NotLoggedInError(
                    "They need to log into a last.fm account. Please log in with `fm login`."
                )
            raise NotLoggedInError(
                "You need to log into a last.fm account. Please log in with `fm login`."
            )

    def check_if_logged_in_and_sk(self, conf):
        if not conf["session_key"] and not conf["lastfm_username"]:
            raise NotLoggedInError(
                "You need to log into a last.fm account. Please log in with `fm login`."
            )
        if not conf["session_key"] and conf["lastfm_username"]:
            raise NeedToReauthorizeError(
                "You appear to be an old user of this cog. "
                "To use this command you will need to reauthorize with `fm login`."
            )

    async def maybe_send_403_msg(self, ctx, data):
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to add your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            raise SilentDeAuthorizedError

    async def get_playcount_track(self, ctx, artist, track, username, period, reference=None):
        try:
            data = await self.api_request(
                ctx,
                {
                    "method": "track.getinfo",
                    "user": username,
                    "track": track,
                    "artist": artist,
                    "autocorrect": 1,
                },
            )
        except LastFMError:
            data = {}

        try:
            count = int(data["track"]["userplaycount"])
        except KeyError:
            count = 0
        try:
            artistname = data["track"]["artist"]["name"]
            trackname = data["track"]["name"]
        except KeyError:
            artistname = None
            trackname = None

        try:
            image_url = data["track"]["album"]["image"][-1]["#text"]
        except KeyError:
            image_url = None

        if reference is None:
            return count
        else:
            return count, reference, (artistname, trackname, image_url)

    async def get_playcount_album(self, ctx, artist, album, username, period, reference=None):
        try:
            data = await self.api_request(
                ctx,
                {
                    "method": "album.getinfo",
                    "user": username,
                    "album": album,
                    "artist": artist,
                    "autocorrect": 1,
                },
            )
        except LastFMError:
            data = {}
        try:
            count = int(data["album"]["userplaycount"])
        except (KeyError, TypeError):
            count = 0

        try:
            artistname = data["album"]["artist"]
            albumname = data["album"]["name"]
        except KeyError:
            artistname = None
            albumname = None

        try:
            image_url = data["album"]["image"][-1]["#text"]
        except KeyError:
            image_url = None

        if reference is None:
            return count
        else:
            return count, reference, (artistname, albumname, image_url)

    async def get_playcount(self, ctx, artist, username, period, reference=None):
        count = await self.get_playcount_scraper(ctx, artist, username, period)
    
        return count, reference, artist

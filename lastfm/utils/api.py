import contextlib

import aiohttp
import arrow

from ..exceptions import *


class APIMixin:
    async def api_request(self, ctx, params, supress_errors=False):
        """Get json data from the lastfm api"""
        url = "http://ws.audioscrobbler.com/2.0/"
        params["api_key"] = self.token
        params["format"] = "json"
        async with self.session.get(url, params=params) as response:
            with contextlib.suppress(aiohttp.ContentTypeError):
                content = await response.json()
                if "error" in content or response.status != 200:
                    if supress_errors:
                        return
                    raise LastFMError(
                        f"Last.fm returned an error: {content.get('message')} | Error code {content.get('error')}"
                    )
                return content

    async def api_post(self, params):
        """Post data to the lastfm api"""
        url = "http://ws.audioscrobbler.com/2.0/"
        params["api_key"] = self.token
        hashed = self.hashRequest(params, self.secret)
        params["api_sig"] = hashed
        params["format"] = "json"
        async with self.session.post(url, params=params) as response:
            with contextlib.suppress(aiohttp.ContentTypeError):
                content = await response.json()
                return response.status, content

    async def fetch(self, ctx, url, params=None, handling="json"):
        if params is None:
            params = {}
        cookies = {'sessionid': self.login_token}
        async with self.session.get(url, params=params, cookies=cookies) as response:

            if handling == "json":
                return await response.json()
            if handling == "text":
                return await response.text()
            return await response

    async def get_current_track(self, ctx, username, ref=None, supress_errors=False):
        data = await self.api_request(
            ctx, {"method": "user.getrecenttracks", "user": username, "limit": 1}, supress_errors
        )
        if not data:
            return
        tracks = data["recenttracks"]["track"]
        if type(tracks) == list:
            if tracks:
                track = tracks[0]
            else:
                if supress_errors:
                    return
                raise NoScrobblesError("You haven't scrobbled anything yet.")
        else:
            track = tracks

        if "@attr" in track and "nowplaying" in track["@attr"]:

            name = track["name"]
            artist = track["artist"]["#text"]
            image = track["image"][-1]["#text"]
            album = None
            if "#text" in track["album"]:
                album = track["album"]["#text"]
            if ref:
                return name, artist, album, image, ref
            else:
                return name, artist, album, image

        if not ref:
            if supress_errors:
                return
            raise NotScrobblingError("You aren't currently listening to anything.")
        else:
            return None, None, None, None, ref

    async def get_server_top(self, ctx, username, request_type, period, limit=100):
        if request_type == "artist":
            data = await self.api_request(
                ctx,
                {
                    "user": username,
                    "method": "user.gettopartists",
                    "limit": limit,
                    "period": period,
                },
                True,
            )
            return data["topartists"]["artist"] if data is not None else None
        if request_type == "album":
            data = await self.api_request(
                ctx,
                {
                    "user": username,
                    "method": "user.gettopalbums",
                    "limit": limit,
                    "period": period,
                },
                True,
            )
            return data["topalbums"]["album"] if data is not None else None
        if request_type == "track":
            data = await self.api_request(
                ctx,
                {
                    "user": username,
                    "method": "user.gettoptracks",
                    "limit": limit,
                    "period": period,
                },
                True,
            )
            return data["toptracks"]["track"] if data is not None else None

    async def get_lastplayed(self, ctx, username, ref):
        data = await self.api_request(
            ctx,
            {"method": "user.getrecenttracks", "user": username, "limit": 1},
            True,
        )
        song = None
        if data:
            tracks = data["recenttracks"]["track"]
            if type(tracks) == list:
                if tracks:
                    track = tracks[0]
                else:
                    return None, ref
            else:
                track = tracks

            nowplaying = False
            if track.get("@attr") and track["@attr"].get("nowplaying"):
                nowplaying = True

            if track.get("date"):
                date = tracks[0]["date"]["uts"]
            else:
                date = arrow.utcnow().int_timestamp

            song = {
                "name": track["name"],
                "artist": track["artist"]["#text"],
                "nowplaying": nowplaying,
                "date": int(date),
                "url": track["url"],
            }

        return song, ref

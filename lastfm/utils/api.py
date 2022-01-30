import contextlib

import aiohttp

from ..exceptions import *


class APIMixin:
    async def api_request(self, ctx, params):
        """Get json data from the lastfm api"""
        url = "http://ws.audioscrobbler.com/2.0/"
        params["api_key"] = self.token
        params["format"] = "json"
        async with ctx.typing():
            async with self.session.get(url, params=params) as response:
                with contextlib.suppress(aiohttp.ContentTypeError):
                    content = await response.json()
                    if "error" in content or response.status != 200:
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
        async with ctx.typing():
            async with self.session.get(url, params=params) as response:
                if handling == "json":
                    return await response.json()
                if handling == "text":
                    return await response.text()
                return await response

    async def get_current_track(self, ctx, username, ref=None):
        data = await self.api_request(
            ctx,
            {"method": "user.getrecenttracks", "user": username, "limit": 1},
        )
        tracks = data["recenttracks"]["track"]
        if type(tracks) == list:
            if tracks:
                track = tracks[0]
            else:
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
            raise NotScrobblingError("You aren't currently listening to anything.")
        else:
            return None, None, None, None, ref

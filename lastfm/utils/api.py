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

    async def get_np(self, ctx, username, ref=None):
        data = await self.api_request(
            ctx,
            {"method": "user.getrecenttracks", "user": username, "limit": 1},
        )
        song = None
        if data is not None:
            tracks = data["recenttracks"]["track"]
            if tracks:
                if isinstance(tracks, list):
                    if "@attr" in tracks[0]:
                        if "nowplaying" in tracks[0]["@attr"]:
                            song = {
                                "artist": tracks[0]["artist"]["#text"],
                                "name": tracks[0]["name"],
                            }
                            if "#text" in tracks[0]["album"]:
                                song["album"] = tracks[0]["album"]["#text"]
                else:
                    if "@attr" in tracks:
                        if "nowplaying" in tracks["@attr"]:
                            song = {
                                "artist": tracks["artist"]["#text"],
                                "name": tracks["name"],
                            }
                            if "#text" in tracks[0]["album"]:
                                song["album"] = tracks[0]["album"]["#text"]

        return song, ref

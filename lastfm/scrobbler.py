import contextlib
import re
import time

import arrow
import discord
import lavalink
from redbot.core import commands

from .abc import MixinMeta
from .fmmixin import fm
from .utils import *


class ScrobblerMixin(MixinMeta):
    def __init__(self):
        # This regex is from GitHub user TheWyn
        # Source: https://github.com/TheWyn/Wyn-RedV3Cogs/blob/master/lyrics/lyrics.py#L12-13
        self.regex = re.compile(
            (
                r"((\[)|(\()).*(of?ficial|feat\.?|"
                r"ft\.?|audio|video|lyrics?|remix|HD).*(?(2)]|\))"
            ),
            flags=re.I,
        )
        self.started_time = {}

    async def scrobble_song(self, track, artist, duration, user, requester, key):
        fm_tokens = await self.bot.get_shared_api_tokens("lastfm")
        api_key = fm_tokens.get("appid")
        api_secret = fm_tokens.get("secret")
        timestamp = arrow.utcnow().timestamp()
        chosen = 0
        if user == requester:
            chosen = 1
        params = {
            "api_key": api_key,
            "artist": artist,
            "chosenByUser": str(chosen),
            "duration": str(duration / 1000),
            "method": "track.scrobble",
            "sk": key,
            "timestamp": str(timestamp),
            "track": track,
        }
        hashed = hashRequest(params, api_secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 200:
            scrobbles = await self.config.user(user).scrobbles()
            if not scrobbles:
                scrobbles = 0
            scrobbles += 1
            await self.config.user(user).scrobbles.set(scrobbles)

    async def set_nowplaying(self, track, artist, duration, user, key):
        fm_tokens = await self.bot.get_shared_api_tokens("lastfm")
        api_key = fm_tokens.get("appid")
        api_secret = fm_tokens.get("secret")
        timestamp = arrow.utcnow().timestamp()
        params = {
            "api_key": api_key,
            "artist": artist,
            "duration": str(duration / 1000),
            "method": "track.updateNowPlaying",
            "sk": key,
            "timestamp": str(timestamp),
            "track": track,
        }
        hashed = hashRequest(params, api_secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403:
            if data[1]["error"] == 9:
                await self.config.user(user).session_key.clear()
                with contextlib.suppress(discord.HTTPException):
                    message = (
                        "I was unable to scrobble your last song as it seems you have unauthorized me to do so.\n"
                        "You can reauthorize me using the `fm login` command again, but I will still continue"
                        "to show your stats unless you use the `fm logout` command."
                    )
                    embed = discord.Embed(
                        title="Authorization Failed",
                        description=message,
                        color=await self.bot.get_embed_color(),
                    )
                    await user.send(embed=embed)

    @commands.Cog.listener()
    async def on_red_audio_track_start(
        self, guild: discord.Guild, track: lavalink.Track, requester: discord.Member
    ):
        if not (guild and track) or track.length <= 30000 or not guild.me.voice:
            return
        self.started_time[guild.id] = (int(time.time()), track.uri)
        renamed_track = self.regex.sub("", track.title).strip()
        track_array = renamed_track.split("-")
        if len(track_array) == 1:
            return
        track_artist = track_array[0]
        track_title = track_array[1]
        voice_members = guild.me.voice.channel.members
        for member in voice_members:
            if member == guild.me or member.bot is True:
                continue
            key = await self.config.user(member).session_key()
            if key:
                await self.set_nowplaying(track_title, track_artist, track.length, member, key)

    @commands.Cog.listener()
    async def on_red_audio_track_end(
        self, guild: discord.Guild, track: lavalink.Track, requester: discord.Member
    ):
        if not guild:
            return
        try:
            t = self.started_time[guild.id]
            started = t[0]
            uri = t[1]
        except KeyError:
            return
        if not track or track.length <= 30000 or not guild.me.voice or uri != track.uri:
            return
        renamed_track = self.regex.sub("", track.title).strip()
        track_array = renamed_track.split("-")
        if len(track_array) == 1:
            return
        track_artist = track_array[0]
        track_title = track_array[1]
        voice_members = guild.me.voice.channel.members
        how_much_to_subtrack = track.length / 5000
        should_end_song_threshold = ((int(track.length / 1000)) + started) - how_much_to_subtrack
        if int(time.time()) >= should_end_song_threshold:
            for member in voice_members:
                if member == guild.me or member.bot is True:
                    continue
                key = await self.config.user(member).session_key()
                if key:
                    await self.scrobble_song(
                        track_title, track_artist, track.length, member, requester, key
                    )

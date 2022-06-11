import contextlib
import re
import time

import arrow
import discord
import lavalink
from redbot.core import commands

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import command_fm


class ScrobblerMixin(MixinMeta):
    def __init__(self):
        # This regex is from GitHub user TheWyn
        # Source: https://github.com/TheWyn/Wyn-RedV3Cogs/blob/master/lyrics/lyrics.py#L12-13
        self.regex = re.compile(
            (
                r"((\[)|(\()).*(of?ficial|feat\.?|"
                r"ft\.?|audio|video|explicit|clean|lyrics?|remix|HD).*(?(2)]|\))"
            ),
            flags=re.I,
        )
        self.started_time = {}

    def is_valid_scrobble(self, started, track_length):
        """
        A track should only be scrobbled when the following conditions have been met:
        The track has been played for at least half its duration, or for 4 minutes (whichever occurs earlier)
        """
        track_length = track_length / 1000
        started = started - 3
        now = int(time.time())
        four_minutes = 240
        half_track_length = int(track_length / 2)
        listen_time = now - started
        if listen_time >= four_minutes or listen_time >= half_track_length:
            return True
        return False

    @commands.command(name="scrobble", usage="<track name> | <artist name>")
    @commands.cooldown(1, 300, type=commands.BucketType.user)
    async def command_scrobble(self, ctx, *, track):
        """
        Scrobble a song to last.fm.

        Usage:
            [p]scrobble <track name> | <artist name>
        """
        conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in_and_sk(conf)
        try:
            trackname, artistname = [x.strip() for x in track.split("|")]
            if trackname == "" or artistname == "":
                raise ValueError
        except ValueError:
            return await ctx.send("\N{WARNING SIGN} Incorrect format! use `track | artist`")

        result = await self.scrobble_song(
            trackname, artistname, ctx.author, ctx.author, conf["session_key"], False
        )
        await self.maybe_send_403_msg(ctx, result)
        await ctx.tick()

    @command_fm.command(name="scrobbler")
    async def command_scrobbler(self, ctx):
        """
        Toggles automatic scrobbling in VC.

        Note: this also toggles the setting of now playing in VC as well.
        """
        current = await self.config.user(ctx.author).scrobble()
        new = not current
        await self.config.user(ctx.author).scrobble.set(new)
        if new:
            await ctx.send("\N{WHITE HEAVY CHECK MARK} VC scrobbling enabled.")
        else:
            await ctx.send("\N{CROSS MARK} VC scrobbling disabled.")

    async def scrobble_song(self, track, artist, user, requester, key, is_vc):
        timestamp = arrow.utcnow().timestamp()
        chosen = 0
        if user == requester:
            chosen = 1
        params = {
            "api_key": self.token,
            "artist": artist,
            "chosenByUser": str(chosen),
            "method": "track.scrobble",
            "sk": key,
            "timestamp": str(timestamp),
            "track": track,
        }
        data = await self.api_post(params=params)
        if data[0] == 200 and is_vc:
            scrobbles = await self.config.user(user).scrobbles()
            if not scrobbles:
                scrobbles = 0
            scrobbles += 1
            await self.config.user(user).scrobbles.set(scrobbles)
        return data

    async def set_nowplaying(self, track, artist, user, key):
        params = {
            "artist": artist,
            "method": "track.updateNowPlaying",
            "sk": key,
            "timestamp": str(arrow.utcnow().timestamp()),
            "track": track,
        }
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(user).session_key.clear()
            await self.config.user(user).lastfm_username.clear()
            with contextlib.suppress(discord.HTTPException):
                message = (
                    "I was unable to scrobble your last song as it seems you have unauthorized me to do so.\n"
                    "You can reauthorize me using the `fm login` command, but I have logged you out for now."
                )
                embed = discord.Embed(
                    title="Authorization Failed",
                    description=message,
                    color=await self.bot.get_embed_color(user.dm_channel),
                )
                await user.send(embed=embed)

    @commands.Cog.listener(name="on_red_audio_track_start")
    async def listener_scrobbler_track_start(
        self, guild: discord.Guild, track: lavalink.Track, requester: discord.Member
    ):
        if not (guild and track) or int(track.length) <= 30000 or not guild.me or not guild.me.voice:
            return
        track.length = int(track.length)
        self.started_time[guild.id] = (int(time.time()), track.uri)
        renamed_track = self.regex.sub("", track.title).strip()
        track_array = renamed_track.split("-")
        if len(track_array) == 1:
            track_array = (track.author, track_array[0])
        track_artist = track_array[0]
        track_title = track_array[1]
        voice_members = guild.me.voice.channel.members
        for member in voice_members:
            if member == guild.me or member.bot is True:
                continue
            user_settings = await self.config.user(member).all()
            if user_settings["scrobble"] and user_settings["session_key"]:
                await self.set_nowplaying(
                    track_title, track_artist, member, user_settings["session_key"]
                )

    @commands.Cog.listener(name="on_red_audio_track_end")
    async def listener_scrobbler_track_end(
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
        if not track or int(track.length) <= 30000 or not guild.me or not guild.me.voice or uri != track.uri:
            return
        track.length = int(track.length)
        renamed_track = self.regex.sub("", track.title).strip()
        track_array = renamed_track.split("-")
        if len(track_array) == 1:
            track_array = (track.author, track_array[0])
        track_artist = track_array[0]
        track_title = track_array[1]
        voice_members = guild.me.voice.channel.members
        if self.is_valid_scrobble(started, track.length) is True:
            for member in voice_members:
                if member == guild.me or member.bot is True:
                    continue
                user_settings = await self.config.user(member).all()
                if user_settings["scrobble"] and user_settings["session_key"]:
                    await self.scrobble_song(
                        track_title,
                        track_artist,
                        member,
                        requester,
                        user_settings["session_key"],
                        True,
                    )

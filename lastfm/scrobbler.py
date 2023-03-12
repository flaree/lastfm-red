import asyncio
import contextlib
import re

import arrow
import discord
import lavalink
from redbot.core import commands

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import FMMixin

command_fm = FMMixin.command_fm
command_fm_server = FMMixin.command_fm_server


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
        params = {
            "api_key": self.token,
            "artist": artist,
            "method": "track.scrobble",
            "sk": key,
            "timestamp": str(arrow.utcnow().timestamp()),
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

    async def maybe_scrobble_song(
        self,
        user: discord.Member,
        guild: discord.Guild,
        track: lavalink.Track,
        artist_name: str,
        track_name: str,
        session_key: str,
    ):
        four_minutes = 240
        half_track_length = int((track.length / 1000) / 2)

        time_to_sleep = min(four_minutes, half_track_length)
        await asyncio.sleep(time_to_sleep)

        try:
            player = lavalink.get_player(guild.id)
        except:
            return

        if player.current and player.current.uri == track.uri:
            await self.scrobble_song(track_name, artist_name, user, guild.me, session_key, True)

    @commands.Cog.listener(name="on_red_audio_track_start")
    async def listener_scrobbler_track_start(
        self, guild: discord.Guild, track: lavalink.Track, requester: discord.Member
    ):
        if (
            not (guild and track)
            or int(track.length) <= 30000
            or not guild.me
            or not guild.me.voice
        ):
            return

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
                await self.maybe_scrobble_song(
                    member, guild, track, track_artist, track_title, user_settings["session_key"]
                )

import discord
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import MixinMeta
from .errors import *
from .fmmixin import fm
from .utils import *


class LoveMixin(MixinMeta):
    """Love Commands"""

    async def love_or_unlove_song(self, track, artist, love, key):
        if love:
            params = {
                "api_key": self.token,
                "artist": artist,
                "method": "track.love",
                "sk": key,
                "track": track,
            }
        else:
            params = {
                "api_key": self.token,
                "artist": artist,
                "method": "track.unlove",
                "sk": key,
                "track": track,
            }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        return data

    @fm.command(usage="<track name> | <artist name>")
    async def love(self, ctx, *, track=None):
        """
        Love a song on last.fm.

        Usage:
            [p]love
            [p]love <track name> | <artist name>
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        if track:
            try:
                trackname, artistname = [x.strip() for x in track.split("|")]
                if trackname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                return await ctx.send("\N{WARNING SIGN} Incorrect format! use `track | artist`")
        else:
            try:
                data = await self.api_request(
                    ctx,
                    {
                        "user": conf["lastfm_username"],
                        "method": "user.getrecenttracks",
                        "limit": 1,
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            tracks = data["recenttracks"]["track"]
            if not tracks:
                return await ctx.send("You have not listened to anything yet!")
            artistname = tracks[0]["artist"]["#text"]
            trackname = tracks[0]["name"]

        try:
            data = await self.api_request(
                ctx,
                {
                    "username": conf["lastfm_username"],
                    "method": "track.getInfo",
                    "track": trackname,
                    "artist": artistname,
                },
            )
        except LastFMError as e:
            return await ctx.send(str(e))

        if data["track"]["userloved"] == "1":
            return await ctx.send(
                f"This song is already loved. Did you mean to run `{ctx.clean_prefix}fm unlove`?"
            )

        result = await self.love_or_unlove_song(
            data["track"]["name"], data["track"]["artist"]["name"], True, conf["session_key"]
        )
        if result[0] == 403 and result[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to like this as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        await ctx.send(f"Loved **{trackname[:50]}** by **{artistname[:50]}**")

    @fm.command(usage="<track name> | <artist name>")
    async def unlove(self, ctx, *, track=None):
        """
        Unlove a song on last.fm.

        Usage:
            [p]unlove
            [p]unlove <track name> | <artist name>
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        if track:
            try:
                trackname, artistname = [x.strip() for x in track.split("|")]
                if trackname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                return await ctx.send("\N{WARNING SIGN} Incorrect format! use `track | artist`")
        else:
            try:
                data = await self.api_request(
                    ctx,
                    {
                        "user": conf["lastfm_username"],
                        "method": "user.getrecenttracks",
                        "limit": 1,
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            tracks = data["recenttracks"]["track"]
            if not tracks:
                return await ctx.send("You have not listened to anything yet!")
            artistname = tracks[0]["artist"]["#text"]
            trackname = tracks[0]["name"]

        try:
            data = await self.api_request(
                ctx,
                {
                    "username": conf["lastfm_username"],
                    "method": "track.getInfo",
                    "track": trackname,
                    "artist": artistname,
                },
            )
        except LastFMError as e:
            return await ctx.send(str(e))

        if data["track"]["userloved"] == "0":
            return await ctx.send(
                f"This song is not loved. Did you mean to run `{ctx.clean_prefix}fm love`?"
            )

        result = await self.love_or_unlove_song(
            data["track"]["name"], data["track"]["artist"]["name"], False, conf["session_key"]
        )
        if result[0] == 403 and result[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to unlove this as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        await ctx.send(f"Unloved **{trackname[:50]}** by **{artistname[:50]}**")

    @fm.command()
    async def loved(self, ctx, user: discord.User = None):
        """
        Get a list of loved songs for a user.

        Usage:
            [p]loved
            [p]loved <user>
        """
        if not user:
            user = ctx.author
        conf = await self.config.user(user).all()
        await check_if_logged_in_and_sk(conf)
        try:
            data = await self.api_request(
                ctx, {"user": conf["lastfm_username"], "method": "user.getlovedtracks"}
            )
        except LastFMError as e:
            return await ctx.send(str(e))
        tracks = data["lovedtracks"]["track"]
        if not tracks:
            return await ctx.send("You have not loved anything yet!")
        tracks = [f"{x['name']} by {x['artist']['name']}\n" for x in tracks]
        content = discord.Embed(color=await ctx.embed_color(), title=f"{user.name}'s loved tracks")

        pages = await create_pages(content, tracks)
        for i, page in enumerate(pages):
            page.set_footer(text=f"Page {i + 1}/{len(pages)}")
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

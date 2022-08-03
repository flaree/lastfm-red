import discord
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import command_fm


class LoveMixin(MixinMeta):
    """Love Commands"""

    async def love_or_unlove_song(self, track, artist, love, key):
        params = {
            "api_key": self.token,
            "artist": artist,
            "sk": key,
            "track": track,
        }
        if love:
            params["method"] = "track.love"
        else:
            params["method"] = "track.unlove"
        data = await self.api_post(params=params)
        return data

    @command_fm.command(name="love", usage="<track name> | <artist name>")
    async def command_love(self, ctx, *, track=None):
        """
        Love a song on last.fm.

        Usage:
            [p]love
            [p]love <track name> | <artist name>
        """
        conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in_and_sk(conf)
        if track:
            try:
                trackname, artistname = [x.strip() for x in track.split("|")]
                if trackname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                return await ctx.send("\N{WARNING SIGN} Incorrect format! use `track | artist`")
        else:
            trackname, artistname, albumname, imageurl = await self.get_current_track(
                ctx, conf["lastfm_username"]
            )

        data = await self.api_request(
            ctx,
            {
                "username": conf["lastfm_username"],
                "method": "track.getInfo",
                "track": trackname,
                "artist": artistname,
            },
        )

        if data["track"].get("userloved", "0") == "1":
            return await ctx.send(
                f"This song is already loved. Did you mean to run `{ctx.clean_prefix}fm unlove`?"
            )

        result = await self.love_or_unlove_song(
            data["track"]["name"], data["track"]["artist"]["name"], True, conf["session_key"]
        )
        await self.maybe_send_403_msg(ctx, result)
        await ctx.send(f"Loved **{trackname[:50]}** by **{artistname[:50]}**")

    @command_fm.command(name="unlove", usage="<track name> | <artist name>")
    async def command_unlove(self, ctx, *, track=None):
        """
        Unlove a song on last.fm.

        Usage:
            [p]unlove
            [p]unlove <track name> | <artist name>
        """
        conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in_and_sk(conf)
        if track:
            try:
                trackname, artistname = [x.strip() for x in track.split("|")]
                if trackname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                return await ctx.send("\N{WARNING SIGN} Incorrect format! use `track | artist`")
        else:
            trackname, artistname, albumname, imageurl = await self.get_current_track(
                ctx, conf["lastfm_username"]
            )

        data = await self.api_request(
            ctx,
            {
                "username": conf["lastfm_username"],
                "method": "track.getInfo",
                "track": trackname,
                "artist": artistname,
            },
        )

        if data["track"].get("userloved", "0") == "0":
            return await ctx.send(
                f"This song is not loved. Did you mean to run `{ctx.clean_prefix}fm love`?"
            )

        result = await self.love_or_unlove_song(
            data["track"]["name"], data["track"]["artist"]["name"], False, conf["session_key"]
        )
        await self.maybe_send_403_msg(ctx, result)
        await ctx.send(f"Unloved **{trackname[:50]}** by **{artistname[:50]}**")

    @command_fm.command(name="loved")
    async def command_loved(self, ctx, user: discord.User = None):
        """
        Get a list of loved songs for a user.

        Usage:
            [p]loved
            [p]loved <user>
        """
        if not user:
            user = ctx.author
        conf = await self.config.user(user).all()
        self.check_if_logged_in_and_sk(conf)
        data = await self.api_request(
            ctx, {"user": conf["lastfm_username"], "method": "user.getlovedtracks"}
        )
        tracks = data["lovedtracks"]["track"]
        if not tracks:
            return await ctx.send("You have not loved anything yet!")
        tracks = [f"{x['name']} by {x['artist']['name']}\n" for x in tracks]
        content = discord.Embed(color=await ctx.embed_color(), title=f"{user.name}'s loved tracks")

        pages = await self.create_pages(content, tracks)
        for i, page in enumerate(pages):
            page.set_footer(text=f"Page {i + 1}/{len(pages)}")
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

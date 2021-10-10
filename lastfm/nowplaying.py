import asyncio
from typing import Optional

import discord
from redbot.core.utils.chat_formatting import escape
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import MixinMeta
from .fmmixin import fm
from .utils import *


class NowPlayingMixin(MixinMeta):
    """NowPlaying Commands"""

    @fm.command(aliases=["np"])
    async def nowplaying(self, ctx, user: Optional[discord.Member] = None):
        """Currently playing song or most recent song."""
        author = user or ctx.author
        async with ctx.typing():
            name = await self.config.user(author).lastfm_username()
            if name is None:
                return await ctx.send(
                    "You do not have a LastFM account set. Please set one with {}fm set".format(
                        ctx.clean_prefix
                    )
                )
            try:
                data = await self.api_request(
                    ctx, {"user": name, "method": "user.getrecenttracks", "limit": 1}
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            user_attr = data["recenttracks"]["@attr"]
            tracks = data["recenttracks"]["track"]

            if not tracks:
                return await ctx.send("You have not listened to anything yet!")
            try:
                artist = tracks[0]["artist"]["#text"]
                album = tracks[0]["album"]["#text"]
                track = tracks[0]["name"]
                image_url = tracks[0]["image"][-1]["#text"]
                url = tracks[0]["url"]
                # image_url_small = tracks[0]['image'][1]['#text']
                # image_colour = await color_from_image_url(image_url_small)
            except KeyError:
                artist = tracks["artist"]["#text"]
                album = tracks["album"]["#text"]
                track = tracks["name"]
                image_url = tracks["image"][-1]["#text"]
                url = tracks["url"]

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel), url=url)
            # content.colour = int(image_colour, 16)

            content.description = f"**{escape(album, formatting=True)}**" if album else ""
            content.title = (
                f"**{escape(artist, formatting=True)}** — ***{escape(track, formatting=True)} ***"
            )
            content.set_thumbnail(url=image_url)

            # tags and playcount
            try:
                trackdata = await self.api_request(
                    ctx,
                    {
                        "user": name,
                        "method": "track.getInfo",
                        "artist": artist,
                        "track": track,
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            if trackdata is not None:
                tags = []
                try:
                    trackdata = trackdata["track"]
                    playcount = int(trackdata["userplaycount"])
                    if playcount > 0:
                        content.description += f"\n> {playcount} {format_plays(playcount)}"
                    if isinstance(trackdata["toptags"], dict):
                        for tag in trackdata["toptags"]["tag"]:
                            if "name" in tag:
                                tags.append(tag["name"])
                            else:
                                tags.append(tag)
                        if tags:
                            content.set_footer(text=", ".join(tags))
                except KeyError:
                    pass

            # play state
            state = "— Most recent track"
            try:
                if "@attr" in tracks[0]:
                    if "nowplaying" in tracks[0]["@attr"]:
                        state = "— Now Playing"
            except KeyError:
                if "@attr" in tracks:
                    if "nowplaying" in tracks["@attr"]:
                        state = "— Now Playing"

            content.set_author(
                name=f"{user_attr['user']} {state}",
                icon_url=author.avatar_url,
            )
            if state == "— Most recent track":
                msg = "You aren't currently listening to anything, here is the most recent song found."
            else:
                msg = None
            await ctx.send(msg if msg is not None else None, embed=content)

    @fm.command(aliases=["snp"])
    async def servernp(self, ctx):
        """What people on this server are listening to at the moment."""
        listeners = []
        tasks = []
        userlist = await self.config.all_users()
        guildusers = [x.id for x in ctx.guild.members]
        userslist = [user for user in userlist if user in guildusers]
        for user in userslist:
            lastfm_username = userlist[user]["lastfm_username"]
            if lastfm_username is None:
                continue
            member = ctx.guild.get_member(user)
            if member is None:
                continue

            tasks.append(self.get_np(ctx, lastfm_username, member))

        total_linked = len(tasks)
        if tasks:
            data = await asyncio.gather(*tasks)
            data = [i for i in data if i]
            for song, member_ref in data:
                if song is not None:
                    listeners.append((song, member_ref))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        if not listeners:
            return await ctx.send("Nobody on this server is listening to anything at the moment!")

        total_listening = len(listeners)
        rows = []
        for song, member in listeners:
            rows.append(f"{member.mention} **{song.get('artist')}** — ***{song.get('name')}***")

        content = discord.Embed(color=await ctx.embed_color())
        content.set_author(
            name=f"What is {ctx.guild.name} listening to?",
            icon_url=ctx.guild.icon_url_as(size=64),
        )
        content.set_footer(text=f"{total_listening} / {total_linked} Members")
        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

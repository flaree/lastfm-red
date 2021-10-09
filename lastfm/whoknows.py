import asyncio

import discord

from redbot.core import commands
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import MixinMeta
from .utils import *


class WhoKnowsMixin(MixinMeta):
    """WhoKnows Commands"""

    @commands.command(usage="<artist name>", aliases=["wk"])
    @commands.guild_only()
    @commands.cooldown(2, 10, type=commands.BucketType.user)
    async def whoknows(self, ctx, *, artistname=None):
        """Check who has listened to a given artist the most."""
        listeners = []
        tasks = []
        async with ctx.typing():
            userlist = await self.config.all_users()
            guildusers = [x.id for x in ctx.guild.members]
            userslist = [user for user in userlist if user in guildusers]
            if not artistname:
                username = await self.config.user(ctx.author).lastfm_username()
                if username is None:
                    return await ctx.send(
                        "You have not logged into your last.fm account. Please log in with {}fm login".format(
                            ctx.clean_prefix
                        )
                    )
                try:
                    data = await self.api_request(
                        ctx, {"user": username, "method": "user.getrecenttracks", "limit": 1}
                    )
                except LastFMError as e:
                    return await ctx.send(str(e))
                tracks = data["recenttracks"]["track"]
                if not tracks:
                    return await ctx.send("You have not listened to anything yet!")
                artistname = tracks[0]["artist"]["#text"]
            for user in userslist:
                lastfm_username = userlist[user]["lastfm_username"]
                if lastfm_username is None:
                    continue
                member = ctx.guild.get_member(user)
                if member is None:
                    continue

                tasks.append(self.get_playcount(ctx, artistname, lastfm_username, member))
            if tasks:
                try:
                    data = await asyncio.gather(*tasks)
                except LastFMError as e:
                    return await ctx.send(str(e))
                for playcount, user, name in data:
                    artistname = name
                    if playcount > 0:
                        listeners.append((playcount, user))
            else:
                return await ctx.send(
                    "Nobody on this server has connected their last.fm account yet!"
                )
            rows = []
            total = 0
            for i, (playcount, user) in enumerate(
                sorted(listeners, key=lambda p: p[0], reverse=True), start=1
            ):
                if i == 1:
                    rank = "\N{CROWN}"
                    old_kingdata = await self.config.guild(ctx.guild).crowns()
                    old_kingartist = old_kingdata.get(artistname.lower())
                    if old_kingartist is not None:
                        old_king = old_kingartist["user"]
                        old_king = ctx.guild.get_member(old_king)
                    else:
                        old_king = None
                    new_king = user
                    play = playcount
                else:
                    rank = f"`#{i:2}`"
                rows.append(f"{rank} **{user.name}** — **{playcount}** {format_plays(playcount)}")
                total += playcount

            if not rows:
                return await ctx.send(f"Nobody on this server has listened to **{artistname}**")

            content = discord.Embed(
                title=f"Who knows **{artistname}**?",
                color=await self.bot.get_embed_color(ctx.channel),
            )
            image_url = await self.scrape_artist_image(artistname, ctx)
            content.set_thumbnail(url=image_url)
            content.set_footer(text=f"Collective plays: {total}")

        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])
        if old_king is None:
            await ctx.send(f"> **{new_king.name}** just earned the **{artistname}** crown.")
            async with self.config.guild(ctx.guild).crowns() as crowns:
                crowns[artistname.lower()] = {"user": new_king.id, "playcount": play}
        if isinstance(old_king, discord.Member):
            if not (old_king.id == new_king.id):
                await ctx.send(f"> **{new_king.name}** just earned the **{artistname}** crown.")
                async with self.config.guild(ctx.guild).crowns() as crowns:
                    crowns[artistname.lower()] = {"user": new_king.id, "playcount": play}
            if old_king.id == new_king.id:
                async with self.config.guild(ctx.guild).crowns() as crowns:
                    crowns[artistname.lower()] = {"user": new_king.id, "playcount": play}

    @commands.command(usage="<track name> | <artist name>", aliases=["wkt", "whoknowst"])
    @commands.guild_only()
    @commands.cooldown(2, 15, type=commands.BucketType.user)
    async def whoknowstrack(self, ctx, *, track=None):
        """
        Check who has listened to a given song the most.
        """
        if not track:
            username = await self.config.user(ctx.author).lastfm_username()
            if username is None:
                return await ctx.send(
                    "You have not logged into your Last.fm account. Please log in with {}fm login".format(
                        ctx.clean_prefix
                    )
                )
            try:
                data = await self.api_request(
                    ctx, {"user": username, "method": "user.getrecenttracks", "limit": 1}
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            tracks = data["recenttracks"]["track"]
            if not tracks:
                return await ctx.send("You have not listened to anything yet!")
            trackname = tracks[0]["name"]
            artistname = tracks[0]["artist"]["#text"]
        else:
            try:
                trackname, artistname = [x.strip() for x in track.split("|")]
                if trackname == "" or artistname == "":
                    raise ValueError
            except ValueError:
                return await ctx.send("\N{WARNING SIGN} Incorrect format! use `track | artist`")

        listeners = []
        tasks = []
        userlist = await self.config.all_users()
        guildusers = [x.id for x in ctx.guild.members]
        userslist = [user for user in userlist if user in guildusers]
        for user in userslist:
            lastfm_username = userlist[user]["lastfm_username"]
            member = ctx.guild.get_member(user)
            if member is None or lastfm_username is None:
                continue

            tasks.append(
                self.get_playcount_track(ctx, artistname, trackname, lastfm_username, member)
            )

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, user, metadata in data:
                artistname, trackname, image_url = metadata
                if artistname is None or trackname is None:
                    return await ctx.send("Track could not be found on last.fm!")
                if playcount > 0:
                    listeners.append((playcount, user))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        rows = []
        total = 0
        for i, (playcount, user) in enumerate(
            sorted(listeners, key=lambda p: p[0], reverse=True), start=1
        ):
            rows.append(f"`#{i:2}` **{user.name}** — **{playcount}** {format_plays(playcount)}")
            total += playcount

        if not rows:
            return await ctx.send(
                f"Nobody on this server has listened to **{trackname}** by **{artistname}**"
            )
        if image_url is None:
            image_url = await self.scrape_artist_image(artistname, ctx)

        content = discord.Embed(
            title=f"Who knows **{trackname}**\n— by {artistname}",
            color=await self.bot.get_embed_color(ctx.channel),
        )
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Collective plays: {total}")

        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @commands.command(aliases=["wka", "whoknowsa"], usage="<album name> | <artist name>")
    @commands.guild_only()
    @commands.cooldown(2, 15, type=commands.BucketType.user)
    async def whoknowsalbum(self, ctx, *, album=None):
        """
        Check who has listened to a given album the most.
        """
        if not album:
            username = await self.config.user(ctx.author).lastfm_username()
            if username is None:
                return await ctx.send(
                    "You have not logged into your Last.fm account. Please log in with {}fm login".format(
                        ctx.clean_prefix
                    )
                )
            try:
                data = await self.api_request(
                    ctx, {"user": username, "method": "user.getrecenttracks", "limit": 1}
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            tracks = data["recenttracks"]["track"]
            if not tracks:
                return await ctx.send("You have not listened to anything yet!")
            if "#text" in tracks[0]["album"]:
                albumname = tracks[0]["album"]["#text"]
                artistname = tracks[0]["artist"]["#text"]
            else:
                return await ctx.send(
                    "Sorry, the track you're listening to doesn't have the album info provided."
                )
        else:
            try:
                albumname, artistname = [x.strip() for x in album.split("|")]
                if not albumname or not artistname:
                    raise ValueError
            except ValueError:
                return await ctx.send("\N{WARNING SIGN} Incorrect format! use `album | artist`")

        listeners = []
        tasks = []
        userlist = await self.config.all_users()
        guildusers = [x.id for x in ctx.guild.members]
        userslist = [user for user in userlist if user in guildusers]
        for user in userslist:
            lastfm_username = userlist[user]["lastfm_username"]
            member = ctx.guild.get_member(user)
            if member is None or lastfm_username is None:
                continue

            tasks.append(
                self.get_playcount_album(ctx, artistname, albumname, lastfm_username, member)
            )

        if tasks:
            data = await asyncio.gather(*tasks)
            for playcount, user, metadata in data:
                artistname, albumname, image_url = metadata
                if artistname is None or albumname is None:
                    return await ctx.send("Album could not be found on last.fm!")
                if playcount > 0:
                    listeners.append((playcount, user))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        rows = []
        total = 0
        for i, (playcount, user) in enumerate(
            sorted(listeners, key=lambda p: p[0], reverse=True), start=1
        ):
            rows.append(f"`#{i:2}` **{user.name}** — **{playcount}** {format_plays(playcount)}")
            total += playcount

        if not rows:
            return await ctx.send(
                f"Nobody on this server has listened to **{albumname}** by **{artistname}**"
            )

        if image_url is None:
            image_url = await self.scrape_artist_image(artistname, ctx)

        content = discord.Embed(
            title=f"Who knows **{albumname}**\n— by {artistname}",
            color=await self.bot.get_embed_color(ctx.channel),
        )
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Collective plays: {total}")

        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    async def get_playcount_track(self, ctx, artist, track, username, reference=None):
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

    async def get_playcount_album(self, ctx, artist, album, username, reference=None):
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

    async def get_playcount(self, ctx, artist, username, reference=None):
        data = await self.api_request(
            ctx,
            {
                "method": "artist.getinfo",
                "user": username,
                "artist": artist,
                "autocorrect": 1,
            },
        )
        try:
            count = int(data["artist"]["stats"]["userplaycount"])
            name = data["artist"]["name"]
        except (KeyError, TypeError):
            count = 0
            name = None

        if not reference:
            return count
        return count, reference, name

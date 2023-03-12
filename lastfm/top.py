import asyncio

import discord
from redbot.core.utils.chat_formatting import escape
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import FMMixin

command_fm = FMMixin.command_fm
command_fm_server = FMMixin.command_fm_server


class TopMixin(MixinMeta):
    """Top Artist/Album/Track Commands"""

    @command_fm.command(name="topartists", aliases=["ta"], usage="[timeframe] [amount]")
    async def command_topartists(self, ctx, *args):
        """Most listened artists."""
        conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in(conf)
        async with ctx.typing():
            arguments = self.parse_arguments(args)
            data = await self.api_request(
                ctx,
                {
                    "user": conf["lastfm_username"],
                    "method": "user.gettopartists",
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                },
            )
            user_attr = data["topartists"]["@attr"]
            artists = data["topartists"]["artist"]

            if not artists:
                return await ctx.send("You have not listened to any artists yet!")

            rows = []
            for i, artist in enumerate(artists, start=1):
                name = escape(artist["name"], formatting=True)
                plays = artist["playcount"]
                rows.append(f"`#{i:2}` **{plays}** {self.format_plays(plays)} — **{name}**")

            image_url = await self.scrape_artist_image(artists[0]["name"], ctx)

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            content.set_thumbnail(url=image_url)
            content.set_footer(text=f"Total unique artists: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — {self.humanized_period(arguments['period']).capitalize()} top artists",
                icon_url=ctx.message.author.display_avatar.url,
            )

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @command_fm.command(name="topalbums", aliases=["talb"], usage="[timeframe] [amount]")
    async def command_topalbums(self, ctx, *args):
        """Most listened albums."""
        conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in(conf)
        arguments = self.parse_arguments(args)
        data = await self.api_request(
            ctx,
            {
                "user": conf["lastfm_username"],
                "method": "user.gettopalbums",
                "period": arguments["period"],
                "limit": arguments["amount"],
            },
        )
        user_attr = data["topalbums"]["@attr"]
        albums = data["topalbums"]["album"]

        if not albums:
            return await ctx.send("You have not listened to any albums yet!")

        rows = []
        for i, album in enumerate(albums, start=1):
            name = escape(album["name"], formatting=True)
            artist_name = escape(album["artist"]["name"], formatting=True)
            plays = album["playcount"]
            rows.append(
                f"`#{i:2}` **{plays}** {self.format_plays(plays)} — **{artist_name}** — ***{name}***"
            )

        image_url = albums[0]["image"][-1]["#text"]

        content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique albums: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — {self.humanized_period(arguments['period']).capitalize()} top albums",
            icon_url=ctx.message.author.display_avatar.url,
        )

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @command_fm.command(name="toptracks", aliases=["tt"], usage="[timeframe] [amount]")
    async def command_toptracks(self, ctx, *args):
        """Most listened tracks."""
        conf = await self.config.user(ctx.author).all()
        self.check_if_logged_in(conf)
        async with ctx.typing():
            arguments = self.parse_arguments(args)
            data = await self.api_request(
                ctx,
                {
                    "user": conf["lastfm_username"],
                    "method": "user.gettoptracks",
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                },
            )
            user_attr = data["toptracks"]["@attr"]
            tracks = data["toptracks"]["track"]

            if not tracks:
                return await ctx.send("You have not listened to anything yet!")

            rows = []
            for i, track in enumerate(tracks, start=1):
                name = escape(track["name"], formatting=True)
                artist_name = escape(track["artist"]["name"], formatting=True)
                plays = track["playcount"]
                rows.append(
                    f"`#{i:2}` **{plays}** {self.format_plays(plays)} — **{artist_name}** — ***{name}***"
                )
            trackdata = await self.api_request(
                ctx,
                {
                    "user": name,
                    "method": "track.getInfo",
                    "artist": tracks[0]["artist"]["name"],
                    "track": tracks[0]["name"],
                },
            )
            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            try:
                if trackdata is None:
                    raise KeyError
                image_url = trackdata["track"]["album"]["image"][-1]["#text"]
                # image_url_small = trackdata['track']['album']['image'][1]['#text']
                # image_colour = await color_from_image_url(image_url_small)
            except KeyError:
                image_url = await self.scrape_artist_image(tracks[0]["artist"]["name"], ctx)
                # image_colour = await color_from_image_url(image_url)

            content.set_thumbnail(url=image_url)

            content.set_footer(text=f"Total unique tracks: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — {self.humanized_period(arguments['period']).capitalize()} top tracks",
                icon_url=ctx.message.author.display_avatar.url,
            )

            pages = await self.create_pages(content, rows)
            if len(pages) > 1:
                await menu(ctx, pages[:15], DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=pages[0])

    @command_fm_server.command(name="topartists", aliases=["ta"])
    async def command_servertopartists(self, ctx):
        """Most listened artists in the server."""
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

            tasks.append(
                self.get_server_top(
                    ctx,
                    lastfm_username,
                    "artist",
                    "overall",
                    100,
                )
            )
        if not tasks:
            return await ctx.send("No users have logged in to LastFM!")
        async with ctx.typing():
            mapping = {}
            total_users = 0
            total_plays = 0
            data = await asyncio.gather(*tasks)
            for user in data:
                if user is None:
                    continue
                total_users += 1
                for user_data in user:
                    artist_name = user_data["name"]
                    artist_plays = int(user_data["playcount"])
                    total_plays += artist_plays
                    if artist_name in mapping:
                        mapping[artist_name] += artist_plays
                    else:
                        mapping[artist_name] = artist_plays

            rows = []
            for i, (artist, playcount) in enumerate(
                sorted(mapping.items(), key=lambda x: x[1], reverse=True), start=1
            ):
                name = escape(artist, formatting=True)
                plays = playcount
                rows.append(f"`#{i:2}` **{plays}** {self.format_plays(plays)} — **{name}**")

            content = discord.Embed(
                title=f"Most listened to artists in {ctx.guild}",
                color=await self.bot.get_embed_color(ctx.channel),
            )
            content.set_footer(text=f"Top 100 artists of {total_users} users.")

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @command_fm_server.command(name="topalbums", aliases=["talb"])
    async def command_servertopalbums(self, ctx):
        """Most listened albums in the server."""
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

            tasks.append(
                self.get_server_top(
                    ctx,
                    lastfm_username,
                    "album",
                    "overall",
                    100,
                )
            )
        if not tasks:
            return await ctx.send("No users have logged in to LastFM!")
        async with ctx.typing():
            mapping = {}
            total_users = 0
            total_plays = 0
            data = await asyncio.gather(*tasks)
            for user in data:
                if user is None:
                    continue
                total_users += 1
                for user_data in user:
                    name = f'**{escape(user_data["artist"]["name"], formatting=True)}** — **{escape(user_data["name"], formatting=True)}**'
                    plays = int(user_data["playcount"])
                    total_plays += plays
                    if name in mapping:
                        mapping[name] += plays
                    else:
                        mapping[name] = plays

            rows = []
            for i, (album, playcount) in enumerate(
                sorted(mapping.items(), key=lambda x: x[1], reverse=True), start=1
            ):
                plays = playcount
                rows.append(f"`#{i:2}` **{plays}** {self.format_plays(plays)} — {album}")

            content = discord.Embed(
                title=f"Most listened to albums in {ctx.guild}",
                color=await self.bot.get_embed_color(ctx.channel),
            )
            content.set_footer(text=f"Top 100 albums of {total_users} users.")

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @command_fm_server.command(name="toptracks", aliases=["tt"])
    async def command_servertoptracks(self, ctx):
        """Most listened tracks in the server."""
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

            tasks.append(
                self.get_server_top(
                    ctx,
                    lastfm_username,
                    "track",
                    "overall",
                    100,
                )
            )
        if not tasks:
            return await ctx.send("No users have logged in to LastFM!")
        async with ctx.typing():
            mapping = {}
            total_users = 0
            total_plays = 0
            data = await asyncio.gather(*tasks)
            for user in data:
                if user is None:
                    continue
                total_users += 1
                for user_data in user:
                    name = f'**{escape(user_data["artist"]["name"], formatting=True)}** — **{escape(user_data["name"], formatting=True)}**'
                    plays = int(user_data["playcount"])
                    total_plays += plays
                    if name in mapping:
                        mapping[name] += plays
                    else:
                        mapping[name] = plays

            rows = []
            for i, (track, playcount) in enumerate(
                sorted(mapping.items(), key=lambda x: x[1], reverse=True), start=1
            ):
                plays = playcount
                rows.append(f"`#{i:2}` **{plays}** {self.format_plays(plays)} — {track}")

            content = discord.Embed(
                title=f"Most listened to tracks in {ctx.guild}",
                color=await self.bot.get_embed_color(ctx.channel),
            )
            content.set_footer(text=f"Top 100 tracks of {total_users} users.")

        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

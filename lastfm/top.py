import discord
from redbot.core.utils.chat_formatting import escape
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import command_fm


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
                icon_url=ctx.message.author.avatar_url,
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
            icon_url=ctx.message.author.avatar_url,
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
                icon_url=ctx.message.author.avatar_url,
            )

            pages = await self.create_pages(content, rows)
            if len(pages) > 1:
                await menu(ctx, pages[:15], DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=pages[0])

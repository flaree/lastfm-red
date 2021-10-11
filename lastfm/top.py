import discord
from redbot.core.utils.chat_formatting import escape
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import MixinMeta
from .fmmixin import fm
from .utils import *


class TopMixin(MixinMeta):
    """Top Artist/Album/Track Commands"""

    @fm.command(aliases=["ta"], usage="[timeframe] [amount]")
    async def topartists(self, ctx, *args):
        """Most listened artists."""
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You have not logged into your last.fm account. Please log in with {}fm login".format(
                    ctx.clean_prefix
                )
            )
        async with ctx.typing():
            arguments = parse_arguments(args)
            try:
                data = await self.api_request(
                    ctx,
                    {
                        "user": name,
                        "method": "user.gettopartists",
                        "period": arguments["period"],
                        "limit": arguments["amount"],
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
            user_attr = data["topartists"]["@attr"]
            artists = data["topartists"]["artist"]

            if not artists:
                return await ctx.send("You have not listened to any artists yet!")

            rows = []
            for i, artist in enumerate(artists, start=1):
                name = escape(artist["name"], formatting=True)
                plays = artist["playcount"]
                rows.append(f"`#{i:2}` **{plays}** {format_plays(plays)} — **{name}**")

            image_url = await self.scrape_artist_image(artists[0]["name"], ctx)
            # image_colour = await color_from_image_url(image_url)

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            # content.colour = int(image_colour, 16)
            content.set_thumbnail(url=image_url)
            content.set_footer(text=f"Total unique artists: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top artists",
                icon_url=ctx.message.author.avatar_url,
            )

        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @fm.command(aliases=["talb"], usage="[timeframe] [amount]")
    async def topalbums(self, ctx, *args):
        """Most listened albums."""
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You have not logged into your last.fm account. Please log in with {}fm login".format(
                    ctx.clean_prefix
                )
            )
        arguments = parse_arguments(args)
        try:
            data = await self.api_request(
                ctx,
                {
                    "user": name,
                    "method": "user.gettopalbums",
                    "period": arguments["period"],
                    "limit": arguments["amount"],
                },
            )
        except LastFMError as e:
            return await ctx.send(str(e))
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
                f"`#{i:2}` **{plays}** {format_plays(plays)} — **{artist_name}** — ***{name}***"
            )

        image_url = albums[0]["image"][-1]["#text"]
        # image_url_small = albums[0]['image'][1]['#text']
        # image_colour = await color_from_image_url(image_url_small)

        content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
        # content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique albums: {user_attr['total']}")
        content.set_author(
            name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top albums",
            icon_url=ctx.message.author.avatar_url,
        )

        pages = await create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages[:15], DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

    @fm.command(aliases=["tt"], usage="[timeframe] [amount]")
    async def toptracks(self, ctx, *args):
        """Most listened tracks."""
        name = await self.config.user(ctx.author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You have not logged into your last.fm account. Please log in with {}fm login".format(
                    ctx.clean_prefix
                )
            )
        async with ctx.typing():
            arguments = parse_arguments(args)
            try:
                data = await self.api_request(
                    ctx,
                    {
                        "user": name,
                        "method": "user.gettoptracks",
                        "period": arguments["period"],
                        "limit": arguments["amount"],
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
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
                    f"`#{i:2}` **{plays}** {format_plays(plays)} — **{artist_name}** — ***{name}***"
                )
            try:
                trackdata = await self.api_request(
                    ctx,
                    {
                        "user": name,
                        "method": "track.getInfo",
                        "artist": tracks[0]["artist"]["name"],
                        "track": tracks[0]["name"],
                    },
                )
            except LastFMError as e:
                return await ctx.send(str(e))
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
                name=f"{user_attr['user']} — {humanized_period(arguments['period']).capitalize()} top tracks",
                icon_url=ctx.message.author.avatar_url,
            )

            pages = await create_pages(content, rows)
            if len(pages) > 1:
                await menu(ctx, pages[:15], DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=pages[0])

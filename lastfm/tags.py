import discord
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import MixinMeta
from .errors import *
from .fmmixin import fm
from .utils import *


class TagsMixin(MixinMeta):
    """Tag Commands"""

    @fm.group(name="tag")
    async def tag_group(self, ctx):
        """Commands to tag things"""

    @tag_group.group(name="track", aliases=["tracks", "song"])
    async def track_group(self, ctx):
        """Commands to tag tracks"""

    @track_group.command(name="add", usage="<tag>,[tag] | [track name] | [artist name]")
    async def track_add_command(self, ctx, *, args):
        """
        Add tags to a track

        Tags are inputted as a comma separated list in the first group
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        split_args = [x.strip() for x in args.split("|")]
        list_of_tags = [x.strip() for x in split_args[0].split(",")]
        list_of_tags = [x for x in list_of_tags if x][:10]
        if len(split_args) not in [1, 3] or not list_of_tags:
            return await ctx.send(
                "\N{WARNING SIGN} Incorrect format! use `<tag>,[tag] | [track] | [artist]`"
            )

        if len(split_args) == 1:
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
            trackname = tracks[0]["name"]
            artistname = tracks[0]["artist"]["#text"]
        else:
            trackname = split_args[1]
            artistname = split_args[2]
        params = {
            "artist": artistname,
            "api_key": self.token,
            "method": "track.addtags",
            "sk": conf["session_key"],
            "tags": ",".join(list_of_tags),
            "track": trackname,
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to add your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        await ctx.send(
            f"Added **{len(list_of_tags)}** {'tag' if len(list_of_tags) == 1 else 'tags'}."
        )

    @track_group.command(name="remove", usage="<tag>,[tag] | [track name] | [artist name]")
    async def track_remove_command(self, ctx, *, args):
        """
        Remove tags from a track

        Tags are inputted as a comma separated list in the first group
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        split_args = [x.strip() for x in args.split("|")]
        list_of_tags = [x.strip() for x in split_args[0].split(",")]
        list_of_tags = [x for x in list_of_tags if x][:10]
        if len(split_args) not in [1, 3] or not list_of_tags:
            return await ctx.send(
                "\N{WARNING SIGN} Incorrect format! use `<tag>,[tag] | [track] | [artist]`"
            )

        if len(split_args) == 1:
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
            trackname = tracks[0]["name"]
            artistname = tracks[0]["artist"]["#text"]
        else:
            trackname = split_args[1]
            artistname = split_args[2]
        params = {
            "artist": artistname,
            "api_key": self.token,
            "method": "track.removetags",
            "sk": conf["session_key"],
            "tags": ",".join(list_of_tags),
            "track": trackname,
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to remove your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        await ctx.send(
            f"Removed **{len(list_of_tags)}** {'tag' if len(list_of_tags) == 1 else 'tags'}."
        )

    @track_group.command(name="list", usage="[track name] | [artist name]")
    async def track_list_command(self, ctx, *, args=None):
        """
        List tags for a track

        If no arguments are given, the tags for the last track you listened to will be listed
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        if args:
            try:
                trackname, artistname = [x.strip() for x in args.split("|")]
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
            trackname = tracks[0]["name"]
            artistname = tracks[0]["artist"]["#text"]

        params = {
            "artist": artistname,
            "api_key": self.token,
            "method": "track.gettags",
            "sk": conf["session_key"],
            "track": trackname,
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to list your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        if "tag" not in data[1]["tags"]:
            return await ctx.send("This track has no tags.")
        trackname = data[1]["tags"]["@attr"]["track"]
        artistname = data[1]["tags"]["@attr"]["artist"]
        embed = discord.Embed(
            title=f"Your tags for {trackname} by {artistname}",
            color=await ctx.embed_color(),
        )
        nicelooking = []
        for tag in data[1]["tags"]["tag"]:
            nicelooking.append(f"[{tag['name']}]({tag['url']})")
        message = humanize_list(nicelooking)
        pages = []
        for page in pagify(message, delims=[","]):
            pages.append(page)
        embeds = []
        for num, page in enumerate(pages):
            embed.description = page
            embeds.append(embed)
            if len(pages) > 1:
                embed.set_footer(text=f"Page {num + 1}/{len(pages)}")
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await menu(ctx, embeds, DEFAULT_CONTROLS)

    @tag_group.group(name="album", aliases=["albums"])
    async def album_group(self, ctx):
        """Commands to tag albums"""

    @album_group.command(name="add", usage="<tag>,[tag] | [album name] | [artist name]")
    async def album_add_command(self, ctx, *, args):
        """
        Add tags to an album

        Tags are inputted as a comma separated list in the first group
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        split_args = [x.strip() for x in args.split("|")]
        list_of_tags = [x.strip() for x in split_args[0].split(",")]
        list_of_tags = [x for x in list_of_tags if x][:10]
        if len(split_args) not in [1, 3] or not list_of_tags:
            return await ctx.send(
                "\N{WARNING SIGN} Incorrect format! use `<tag>,[tag] | [album] | [artist]`"
            )

        if len(split_args) == 1:
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
            albumname = tracks[0]["album"]["#text"]
            artistname = tracks[0]["artist"]["#text"]
        else:
            albumname = split_args[1]
            artistname = split_args[2]
        params = {
            "artist": artistname,
            "api_key": self.token,
            "method": "album.addtags",
            "sk": conf["session_key"],
            "tags": ",".join(list_of_tags),
            "album": albumname,
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to add your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        await ctx.send(
            f"Added **{len(list_of_tags)}** {'tag' if len(list_of_tags) == 1 else 'tags'}."
        )

    @album_group.command(name="remove", usage="<tag>,[tag] | [album name] | [artist name]")
    async def album_remove_command(self, ctx, *, args):
        """
        Remove tags from an album

        Tags are inputted as a comma separated list in the first group
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        split_args = [x.strip() for x in args.split("|")]
        list_of_tags = [x.strip() for x in split_args[0].split(",")]
        list_of_tags = [x for x in list_of_tags if x][:10]
        if len(split_args) not in [1, 3] or not list_of_tags:
            return await ctx.send(
                "\N{WARNING SIGN} Incorrect format! use `<tag>,[tag] | [album] | [artist]`"
            )

        if len(split_args) == 1:
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
            albumname = tracks[0]["album"]["#text"]
            artistname = tracks[0]["artist"]["#text"]
        else:
            albumname = split_args[1]
            artistname = split_args[2]
        params = {
            "artist": artistname,
            "api_key": self.token,
            "method": "album.removetags",
            "sk": conf["session_key"],
            "tags": ",".join(list_of_tags),
            "album": albumname,
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to remove your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        await ctx.send(
            f"Removed **{len(list_of_tags)}** {'tag' if len(list_of_tags) == 1 else 'tags'}."
        )

    @album_group.command(name="list", usage="[album name] | [artist name]")
    async def album_list_command(self, ctx, *, args=None):
        """
        List tags for an album

        If no arguments are given, the tags for the last album you listened to will be listed
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        if args:
            try:
                albumname, artistname = [x.strip() for x in args.split("|")]
                if albumname == "" or artistname == "":
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
            albumname = tracks[0]["album"]["#text"]
            artistname = tracks[0]["artist"]["#text"]
        if albumname == "":
            return await ctx.send("Your current track doesn't have an album.")
        params = {
            "artist": artistname,
            "api_key": self.token,
            "method": "album.gettags",
            "sk": conf["session_key"],
            "album": albumname,
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to list your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        if "tag" not in data[1]["tags"]:
            return await ctx.send("This album has no tags.")
        albumname = data[1]["tags"]["@attr"]["album"]
        artistname = data[1]["tags"]["@attr"]["artist"]
        embed = discord.Embed(
            title=f"Your tags for {albumname} by {artistname}",
            color=await ctx.embed_color(),
        )
        nicelooking = []
        for tag in data[1]["tags"]["tag"]:
            nicelooking.append(f"[{tag['name']}]({tag['url']})")
        message = humanize_list(nicelooking)
        pages = []
        for page in pagify(message, delims=[","]):
            pages.append(page)
        embeds = []
        for num, page in enumerate(pages):
            embed.description = page
            embeds.append(embed)
            if len(pages) > 1:
                embed.set_footer(text=f"Page {num + 1}/{len(pages)}")
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await menu(ctx, embeds, DEFAULT_CONTROLS)

    @tag_group.group(name="artist")
    async def artist_group(self, ctx):
        """Commands to tag tracks"""

    @artist_group.command(name="add", usage="<tag>,[tag] | [artist name]")
    async def artist_add_command(self, ctx, *, args):
        """
        Add tags to an artist

        Tags are inputted as a comma separated list in the first group
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        split_args = [x.strip() for x in args.split("|")]
        list_of_tags = [x.strip() for x in split_args[0].split(",")]
        list_of_tags = [x for x in list_of_tags if x][:10]
        if len(split_args) not in [1, 2] or not list_of_tags:
            return await ctx.send(
                "\N{WARNING SIGN} Incorrect format! use `<tag>,[tag] | [artist]`"
            )

        if len(split_args) == 1:
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
        else:
            artistname = split_args[1]
        params = {
            "artist": artistname,
            "api_key": self.token,
            "method": "artist.addtags",
            "sk": conf["session_key"],
            "tags": ",".join(list_of_tags),
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to add your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        await ctx.send(
            f"Added **{len(list_of_tags)}** {'tag' if len(list_of_tags) == 1 else 'tags'}."
        )

    @artist_group.command(name="remove", usage="<tag>,[tag] | [artist name]")
    async def artist_remove_command(self, ctx, *, args):
        """
        Remove tags from an artist

        Tags are inputted as a comma separated list in the first group
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        split_args = [x.strip() for x in args.split("|")]
        list_of_tags = [x.strip() for x in split_args[0].split(",")]
        list_of_tags = [x for x in list_of_tags if x][:10]
        if len(split_args) not in [1, 2] or not list_of_tags:
            return await ctx.send(
                "\N{WARNING SIGN} Incorrect format! use `<tag>,[tag] | [artist]`"
            )

        if len(split_args) == 1:
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
        else:
            artistname = split_args[1]
        params = {
            "artist": artistname,
            "api_key": self.token,
            "method": "artist.removetags",
            "sk": conf["session_key"],
            "tags": ",".join(list_of_tags),
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to remove your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        await ctx.send(
            f"Removed **{len(list_of_tags)}** {'tag' if len(list_of_tags) == 1 else 'tags'}."
        )

    @artist_group.command(name="list", usage="[artist name]")
    async def artist_list_command(self, ctx, *, artist=None):
        """
        List tags for an artist

        If no arguments are given, the tags for the last track you listened to will be listed
        """
        conf = await self.config.user(ctx.author).all()
        await check_if_logged_in_and_sk(conf)
        if not artist:
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
            artist = tracks[0]["artist"]["#text"]

        params = {
            "artist": artist,
            "api_key": self.token,
            "method": "artist.gettags",
            "sk": conf["session_key"],
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        data = await self.api_post(params=params)
        if data[0] == 403 and data[1]["error"] == 9:
            await self.config.user(ctx.author).session_key.clear()
            await self.config.user(ctx.author).lastfm_username.clear()
            message = (
                "I was unable to list your tags as it seems you have unauthorized me to do so.\n"
                "You can reauthorize me using the `fm login` command, but I have logged you out for now."
            )
            embed = discord.Embed(
                title="Authorization Failed",
                description=message,
                color=await ctx.embed_color(),
            )
            await ctx.send(embed=embed)
            return
        if "tag" not in data[1]["tags"]:
            return await ctx.send("This track has no tags.")
        artistname = data[1]["tags"]["@attr"]["artist"]
        embed = discord.Embed(
            title=f"Your tags for {artistname}",
            color=await ctx.embed_color(),
        )
        nicelooking = []
        for tag in data[1]["tags"]["tag"]:
            nicelooking.append(f"[{tag['name']}]({tag['url']})")
        message = humanize_list(nicelooking)
        pages = []
        for page in pagify(message, delims=[","]):
            pages.append(page)
        embeds = []
        for num, page in enumerate(pages):
            embed.description = page
            embeds.append(embed)
            if len(pages) > 1:
                embed.set_footer(text=f"Page {num + 1}/{len(pages)}")
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await menu(ctx, embeds, DEFAULT_CONTROLS)

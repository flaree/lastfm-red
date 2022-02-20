import asyncio

import discord
from redbot.core.utils.chat_formatting import escape
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import command_fm, command_fm_server


class RecentMixin(MixinMeta):
    """Recent Commands"""

    @command_fm.command(name="recent", aliases=["recents", "re"], usage="[amount]")
    async def command_recent(self, ctx, size: int = 15):
        """Tracks you have recently listened to."""
        conf = await self.config.user(ctx.author).all()
        name = conf["lastfm_username"]
        self.check_if_logged_in(conf)
        async with ctx.typing():
            data = await self.api_request(
                ctx, {"user": name, "method": "user.getrecenttracks", "limit": size}
            )
            user_attr = data["recenttracks"]["@attr"]
            tracks = data["recenttracks"]["track"]

            if not tracks or not isinstance(tracks, list):
                return await ctx.send("You have not listened to anything yet!")

            rows = []
            for i, track in enumerate(tracks):
                if i >= size:
                    break
                name = escape(track["name"], formatting=True)
                track_url = track["url"]
                artist_name = escape(track["artist"]["#text"], formatting=True)
                if track.get("@attr") and track["@attr"].get("nowplaying"):
                    extra = ":musical_note:"
                else:
                    extra = f"(<t:{track['date']['uts']}:R>)"
                rows.append(f"[**{artist_name}** — **{name}**]({track_url}) {extra}")

            image_url = tracks[0]["image"][-1]["#text"]

            content = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            content.set_thumbnail(url=image_url)
            content.set_footer(text=f"Total scrobbles: {user_attr['total']}")
            content.set_author(
                name=f"{user_attr['user']} — Recent tracks",
                icon_url=ctx.message.author.avatar_url,
            )

            pages = await self.create_pages(content, rows)
            if len(pages) > 1:
                await menu(ctx, pages[:15], DEFAULT_CONTROLS)
            else:
                await ctx.send(embed=pages[0])

    @command_fm_server.command(name="recent", aliases=["recents", "re"], usage="[amount]")
    async def command_recent_server(self, ctx, size: int = 15):
        """Tracks recently listened to in this server."""
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

            tasks.append(self.get_lastplayed(ctx, lastfm_username, member))

        total_linked = len(tasks)
        total_listening = 0
        if tasks:
            data = await asyncio.gather(*tasks)
            for song, member_ref in data:
                if song is not None:
                    if song.get("nowplaying"):
                        total_listening += 1
                    listeners.append((song, member_ref))
        else:
            return await ctx.send("Nobody on this server has connected their last.fm account yet!")

        if not listeners:
            return await ctx.send("Nobody on this server is listening to anything at the moment!")

        listeners = sorted(listeners, key=lambda l: l[0].get("date"), reverse=True)
        rows = []
        for song, member in listeners:
            suffix = ""
            if song.get("nowplaying"):
                suffix = ":musical_note: "
            else:
                suffix = f"(<t:{song.get('date')}:R>)"
            rows.append(
                f"{member.mention} [**{escape(song.get('artist'), formatting=True)}** — **{escape(song.get('name'), formatting=True)}**]({song.get('url')}) {suffix}"
            )

        content = discord.Embed(color=await ctx.embed_color())
        content.set_author(
            name=f"What has {ctx.guild.name} been listening to?",
            icon_url=ctx.guild.icon_url,
        )
        content.set_footer(
            text=f"{total_listening} / {total_linked} Members are listening to music right now"
        )
        pages = await self.create_pages(content, rows)
        if len(pages) > 1:
            await menu(ctx, pages, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=pages[0])

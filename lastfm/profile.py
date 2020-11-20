import discord

from .abc import MixinMeta
from .fmmixin import fm
from .utils import *


class ProfileMixin(MixinMeta):
    """Profile Commands"""

    @fm.command()
    async def set(self, ctx, username):
        """Save your last.fm username."""
        try:
            content = await self.get_userinfo_embed(ctx, username)
        except LastFMError as e:
            return await ctx.send(str(e))
        if content is None:
            return await ctx.send(f"\N{WARNING SIGN} Invalid Last.fm username `{username}`")

        await self.config.user(ctx.author).lastfm_username.set(username)
        await ctx.send(
            f"{ctx.message.author.mention} Username saved as `{username}`",
            embed=content,
        )

    @fm.command()
    async def unset(self, ctx):
        """Unlink your last.fm."""
        await self.config.user(ctx.author).lastfm_username.set(None)
        await ctx.send("\N{BROKEN HEART} Removed your last.fm username from the database")
        async with self.config.guild(ctx.guild).crowns() as crowns:
            crownlist = []
            for crown in crowns:
                if crowns[crown]["user"] == ctx.author.id:
                    crownlist.append(crown)
            for crown in crownlist:
                del crowns[crown]

    @fm.command()
    async def profile(self, ctx, user: Optional[discord.Member] = None):
        """Lastfm profile."""
        author = user or ctx.author
        name = await self.config.user(author).lastfm_username()
        if name is None:
            return await ctx.send(
                "You do not have a LastFM account set. Please set one with {}fm set".format(
                    ctx.clean_prefix
                )
            )
        try:
            await ctx.send(embed=await self.get_userinfo_embed(ctx, name))
        except LastFMError as e:
            return await ctx.send(str(e))

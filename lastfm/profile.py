import asyncio
from typing import Optional

import discord
from redbot.core import commands
from redbot.core.utils.predicates import MessagePredicate

from .abc import MixinMeta
from .fmmixin import fm
from .utils import *


class ProfileMixin(MixinMeta):
    """Profile Commands"""

    @fm.command(aliases=["set"])
    @commands.check(tokencheck_plus_secret)
    async def login(self, ctx):
        """Authenticates your last.fm account."""
        params = {
            "api_key": self.token,
            "method": "auth.getToken",
        }
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        try:
            response = await self.api_request(ctx, params=params)
        except LastFMError as e:
            await ctx.send(str(e))
            return

        token = response["token"]
        link = f"https://www.last.fm/api/auth/?api_key={self.token}&token={token}"
        message = (
            f"Please click [here]({link}) to authorize me to access your account.\n\n"
            "You have 120 seconds to successfully authenticate."
        )
        embed = discord.Embed(
            title="Authorization", description=message, color=await ctx.embed_color()
        )

        try:
            await ctx.author.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I can't DM you.")
            return

        if ctx.guild:
            await ctx.send("Check your Direct Messages for instructions on how to log in.")

        params = {"api_key": self.token, "method": "auth.getSession", "token": token}
        hashed = hashRequest(params, self.secret)
        params["api_sig"] = hashed
        for x in range(12):
            try:
                data = await self.api_request(ctx, params=params)
                break
            except LastFMError as e:
                if x == 19:
                    message = "You took to long to log in. Rerun the command to try again."
                    embed = discord.Embed(
                        title="Authorization Timeout",
                        description=message,
                        color=await ctx.embed_color(),
                    )
                    await ctx.author.send(embed=embed)
                    return
            await asyncio.sleep(10)

        await self.config.user(ctx.author).lastfm_username.set(data["session"]["name"])
        await self.config.user(ctx.author).session_key.set(data["session"]["key"])
        message = f"Your username is now set as: `{data['session']['name']}`"
        embed = discord.Embed(title="Success!", description=message, color=await ctx.embed_color())
        await ctx.author.send(embed=embed)

    @fm.command(aliases=["unset"])
    async def logout(self, ctx):
        """
        Deauthenticates your last.fm account.
        """
        await ctx.send("Are you sure you want to log out? (yes/no)")
        try:
            pred = MessagePredicate.yes_or_no(ctx, user=ctx.message.author)
            await ctx.bot.wait_for("message", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send(
                "You took too long! Use the command again if you still want to log out."
            )
            return
        if pred.result:
            await self.config.user(ctx.author).clear()
            await ctx.send("Ok, I've logged you out.")
            if ctx.guild:
                async with self.config.guild(ctx.guild).crowns() as crowns:
                    crownlist = []
                for crown in crowns:
                    if crowns[crown]["user"] == ctx.author.id:
                        crownlist.append(crown)
                for crown in crownlist:
                    del crowns[crown]
        else:
            await ctx.send("Ok, I won't log you out.")

    @fm.command()
    async def profile(self, ctx, user: Optional[discord.Member] = None):
        """Lastfm profile."""
        author = user or ctx.author
        name = await self.config.user(author).lastfm_username()
        if not name:
            await ctx.send(
                "You are not logged into your last.fm account. Please log in with`{}fm login`.".format(
                    ctx.clean_prefix
                )
            )
            return

        try:
            await ctx.send(embed=await self.get_userinfo_embed(ctx, author, name))
        except LastFMError as e:
            return await ctx.send(str(e))

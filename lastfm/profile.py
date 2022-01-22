import asyncio
from typing import Optional

import discord
from redbot.core import commands
from redbot.core.utils.predicates import MessagePredicate

from .abc import MixinMeta
from .exceptions import *
from .fmmixin import command_fm
from .utils.tokencheck import tokencheck_plus_secret


class ProfileMixin(MixinMeta):
    """Profile Commands"""

    @command_fm.command(name="login", aliases=["set"])
    @commands.check(tokencheck_plus_secret)
    async def command_login(self, ctx):
        """Authenticates your last.fm account."""
        params = {
            "api_key": self.token,
            "method": "auth.getToken",
        }
        hashed = self.hashRequest(params, self.secret)
        params["api_sig"] = hashed
        response = await self.api_request(ctx, params=params)

        token = response["token"]
        link = f"https://www.last.fm/api/auth/?api_key={self.token}&token={token}"
        message = (
            f"Please click [here]({link}) to authorize me to access your account.\n\n"
            "You have 90 seconds to successfully authenticate."
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
        hashed = self.hashRequest(params, self.secret)
        params["api_sig"] = hashed
        for x in range(6):
            try:
                data = await self.api_request(ctx, params=params)
                break
            except LastFMError as e:
                if x == 5:
                    message = "You took to long to log in. Rerun the command to try again."
                    embed = discord.Embed(
                        title="Authorization Timeout",
                        description=message,
                        color=await ctx.embed_color(),
                    )
                    await ctx.author.send(embed=embed)
                    return
            await asyncio.sleep(15)

        await self.config.user(ctx.author).lastfm_username.set(data["session"]["name"])
        await self.config.user(ctx.author).session_key.set(data["session"]["key"])
        message = f"Your username is now set as: `{data['session']['name']}`"
        embed = discord.Embed(title="Success!", description=message, color=await ctx.embed_color())
        await ctx.author.send(embed=embed)

    @command_fm.command(name="logout", aliases=["unset"])
    async def command_logout(self, ctx):
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

    @command_fm.command(name="profile")
    async def command_profile(self, ctx, user: Optional[discord.Member] = None):
        """Lastfm profile."""
        author = user or ctx.author
        conf = await self.config.user(author).all()
        self.check_if_logged_in(conf, author == ctx.author)
        await ctx.send(embed=await self.get_userinfo_embed(ctx, author, conf["lastfm_username"]))

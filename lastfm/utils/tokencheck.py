async def tokencheck(ctx):
    token = await ctx.bot.get_shared_api_tokens("lastfm")
    return bool(token.get("appid"))


async def tokencheck_plus_secret(ctx):
    token = await ctx.bot.get_shared_api_tokens("lastfm")
    if token.get("appid") and token.get("secret"):
        return True
    return False

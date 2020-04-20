from .lastfm import LastFm


async def setup(bot):
    cog = LastFm(bot)
    bot.add_cog(cog)
    await cog.initalize()

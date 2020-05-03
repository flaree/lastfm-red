from .lastfm import LastFM


async def setup(bot):
    cog = LastFM(bot)
    bot.add_cog(cog)
    await cog.initialize()

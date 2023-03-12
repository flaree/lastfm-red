from .lastfm import LastFM

__red_end_user_data_statement__ = "This cog stores a user's last.fm username, their amount of VC scrobbles, and a last.fm session key to scrobble for them. It also stores the user's crowns. This is all data that can be cleared."


async def setup(bot):
    cog = LastFM(bot)
    await bot.add_cog(cog)
    await cog.initialize()

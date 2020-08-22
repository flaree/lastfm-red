from redbot.core import commands

@commands.group(name="fm")
async def fm(self, ctx: commands.Context):
    """
    LastFM commands
    """
    pass

class FMMixin:
    """ This is mostly here to easily mess with things... """

    c = fm
from redbot.core import commands

from .utils import tokencheck


@commands.check(tokencheck)
@commands.group(name="fm")
async def fm(self, ctx: commands.Context):
    """
    LastFM commands
    """


class FMMixin:
    """ This is mostly here to easily mess with things... """

    c = fm

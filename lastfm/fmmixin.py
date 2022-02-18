from redbot.core import commands

from .utils.tokencheck import tokencheck


@commands.check(tokencheck)
@commands.group(name="fm")
async def command_fm(self, ctx: commands.Context):
    """
    LastFM commands
    """


@command_fm.group(name="server")
async def command_fm_server(self, ctx: commands.Context):
    """
    LastFM Server Commands
    """


class FMMixin:
    """This is mostly here to easily mess with things..."""

    c = command_fm
    d = command_fm_server

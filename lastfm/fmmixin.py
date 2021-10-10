from redbot.core import commands

from .utils import tokencheck


@commands.check(tokencheck)
@commands.group(name="fm")
async def fm(self, ctx: commands.Context):
    """
    LastFM commands
    """


class FMMixin:
    """This is mostly here to easily mess with things..."""

    c = fm

async def red_delete_data_for_user(self, *, requester, user_id):
    await self.config.user_from_id(user_id).clear()

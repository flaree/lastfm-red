class LastFMError(Exception):
    pass

class NotLoggedInError(LastFMError):
    pass

class NeedToReauthorizeError(LastFMError):
    pass

class UnauthorizedError(LastFMError):
    pass

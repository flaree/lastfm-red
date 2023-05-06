class ConvertersMixin:
    def format_plays(self, amount):
        if amount == 1:
            return "play"
        return "plays"

    def get_period(self, timeframe):
        if timeframe in ["7day", "7days", "weekly", "week", "1week", "7d"]:
            period = "7day", "past week"
        elif timeframe in ["30day", "30days", "monthly", "month", "1month", "1m"]:
            period = "1month", "past month"
        elif timeframe in ["90day", "90days", "3months", "3month", "3m"]:
            period = "3month", "past 3 months"
        elif timeframe in ["180day", "180days", "6months", "6month", "halfyear", "hy", "6m"]:
            period = "6month", "past 6 months"
        elif timeframe in [
            "365day",
            "365days",
            "1year",
            "year",
            "12months",
            "12month",
            "y",
            "1y",
            "12m",
        ]:
            period = "12month", "past year"
        elif timeframe in ["at", "alltime", "overall"]:
            period = "overall", "overall"
        else:
            period = None, None

        return period

    def humanized_period(self, period):
        if period == "7day":
            humanized = "weekly"
        elif period == "1month":
            humanized = "monthly"
        elif period == "3month":
            humanized = "past 3 months"
        elif period == "6month":
            humanized = "past 6 months"
        elif period == "12month":
            humanized = "yearly"
        else:
            humanized = "alltime"

        return humanized

    def period_http_format(self, period):
        period_format_map = {
            "7day": "LAST_7_DAYS",
            "1month": "LAST_30_DAYS",
            "3month": "LAST_90_DAYS",
            "6month": "LAST_180_DAYS",
            "12month": "LAST_365_DAYS",
            "overall": "ALL",
        }
        return period_format_map.get(period)

    def parse_arguments(self, args):
        parsed = {"period": None, "amount": None}
        for a in args:
            if parsed["amount"] is None:
                try:
                    parsed["amount"] = int(a)
                    continue
                except ValueError:
                    pass
            if parsed["period"] is None:
                parsed["period"], _ = self.get_period(a)

        if parsed["period"] is None:
            parsed["period"] = "overall"
        if parsed["amount"] is None:
            parsed["amount"] = 15
        return parsed

    def parse_chart_arguments(self, args):
        parsed = {
            "period": None,
            "amount": None,
            "width": None,
            "height": None,
            "method": None,
            "path": None,
        }
        for a in args:
            a = a.lower()
            if parsed["amount"] is None:
                try:
                    size = a.split("x")
                    parsed["width"] = int(size[0])
                    if len(size) > 1:
                        parsed["height"] = int(size[1])
                    else:
                        parsed["height"] = int(size[0])
                    continue
                except ValueError:
                    pass

            if parsed["method"] is None:
                if a in ["talb", "topalbums", "albums", "album"]:
                    parsed["method"] = "user.gettopalbums"
                    continue
                elif a in ["ta", "topartists", "artists", "artist"]:
                    parsed["method"] = "user.gettopartists"
                    continue
                elif a in ["re", "recent", "recents"]:
                    parsed["method"] = "user.getrecenttracks"
                    continue
                elif a in ["tracks", "track"]:
                    parsed["method"] = "user.gettoptracks"

            if parsed["period"] is None:
                parsed["period"], _ = self.get_period(a)

        if parsed["period"] is None:
            parsed["period"] = "7day"
        if parsed["width"] is None:
            parsed["width"] = 3
            parsed["height"] = 3
        if parsed["method"] is None:
            parsed["method"] = "user.gettopalbums"
        parsed["amount"] = parsed["width"] * parsed["height"]
        return parsed

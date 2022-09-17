from custom_mwclient.wiki_client import WikiClient


class WikiggClient(WikiClient):
    """Extension of `WikiClient` for wiki.gg-specific stuff.

    >>> site = WikiggClient("terraria", "de", WikiggAuth.from_file())
    """

    def __init__(self, wikiname: str, lang: str = "en", **kwargs):
        url = f"https://{wikiname}.wiki.gg"
        if lang != "en":
            url += '/' + lang
        super().__init__(url, **kwargs)

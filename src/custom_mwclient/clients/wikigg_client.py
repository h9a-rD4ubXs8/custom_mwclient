from custom_mwclient.wiki_client import WikiClient


class WikiggClient(WikiClient):
    """Extension of `WikiClient` for wiki.gg-specific stuff.

    >>> site = WikiggClient("terraria", "de", WikiggAuth.from_file())

    Wiki requests time out after 30 seconds by default when using the normal
    `WikiClient`. This `WikiggClient` has a `timeout` argument that is set to
    180 seconds (3 minutes) by default, in order to adapt to the slower servers.
    """

    def __init__(self, wikiname: str, lang: str = "en", timeout: int = 180, **kwargs):
        url = f"https://{wikiname}.wiki.gg"
        if lang != "en":
            url += '/' + lang
        # the timeout arg is just a nice interface (the same functionality can
        # be achieved by setting kwargs["reqs"]["timeout"]), which is why we have
        # to merge the two (merge the timeout arg into the kwargs["reqs"] dict)
        kwargs.setdefault("reqs", {}).setdefault("timeout", timeout)
        super().__init__(url, **kwargs)


    def get_current_wiki_name(self) -> str:
        """Return the name of the current host.

        The `.wiki.gg` part is omitted and `/<lang>` is appended, if the
        language is not English.
        """

        api_result = self.api('query', meta='siteinfo', siprop='general')
        api_result = api_result.get('query', {}).get('general', {})

        sitename = api_result.get('servername', '')
        sitename = sitename.replace('.wiki.gg', '')

        sitelang = api_result.get('lang')
        if sitelang and sitelang != "en":
            sitename += '/' + sitelang

        return sitename

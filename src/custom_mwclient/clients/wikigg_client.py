from mwclient.page import Page

from custom_mwclient.wiki_client import WikiClient


class WikiggClient(WikiClient):
    """Extension of `WikiClient` for wiki.gg-specific stuff.

    >>> site = WikiggClient("terraria", "de", WikiggAuth.from_file())
    """

    def __init__(self, wikiname: str, lang: str = "en", **kwargs):
        url = f"https://{wikiname}.wiki.gg"
        if lang != "en":
            url += '/' + lang
        if not "max_retries" in kwargs:
            kwargs["max_retries"] = 10
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


    def save(self, page: Page, text, summary='', minor=False, bot=True, section=None, **kwargs):
        """Call the `save` method of the `page`, retrying if necessary."""
        sleeper = self.sleepers.make()
        while True:
            try:
                page.edit(text, summary, minor, bot, section, **kwargs)
            except self.write_errors:
                sleeper.sleep()
            else:
                break

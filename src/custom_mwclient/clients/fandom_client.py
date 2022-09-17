from custom_mwclient.wiki_client import WikiClient


class FandomClient(WikiClient):
    """Extension of `WikiClient` for Fandom-specific stuff."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def get_current_wiki_name(self) -> str:
        """Return the name of the current host.

        The `.fandom.com` part is omitted and `/<lang>` is appended, if the
        language is not English.
        """

        api_result = self.api('query', meta='siteinfo', siprop='general')
        api_result = api_result.get('query', {}).get('general', {})

        sitename = api_result.get('servername', '')
        sitename = sitename.replace('.fandom.com', '')

        sitelang = api_result.get('lang')
        if sitelang and sitelang != "en":
            sitename += '/' + sitelang

        return sitename

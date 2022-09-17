from custom_mwclient.wiki_client import WikiClient


class FandomClient(WikiClient):
    """Extension of `WikiClient` for Fandom-specific stuff."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

import importlib.util
import json
import os
from pathlib import Path
from typing import Literal


class WikiAuth():
    """Holds username and password for a wiki.

    There are three ways to initialize an object:
    >>> auth1 = WikiAuth('myusername', 'mystrongpassword')
    >>> auth2 = WikiAuth.from_file('creds.txt', 'plaintext')
    >>> auth3 = WikiAuth.from_env('WIKI_CREDS_USERNAME', 'WIKI_CREDS_PASSWORD')

    In all three cases, the returned object has `.username` and `.password` attributes.
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    @classmethod
    def from_file(cls, filename, filetype: Literal['plaintext', 'json']):
        """Return an auth object with credentials loaded from a file."""
        with open(filename, encoding='utf-8') as f:
            if filetype == 'plaintext':
                username = f.readline().strip()
                password = f.readline().strip()
            elif filetype == 'json':
                jsonfile_contents = json.load(f)
                username = jsonfile_contents['username']
                password = jsonfile_contents['password']
            else:
                raise ValueError('invalid filetype')
            return cls(username, password)

    @classmethod
    def from_env(cls, username_env, password_env):
        """Return an auth object with credentials loaded from environment variables."""
        username = os.getenv(username_env)
        password = os.getenv(password_env)
        return cls(username, password)


class WikiggAuth(WikiAuth):
    """Authentication for a wiki.gg wiki.

    The credentials can be loaded from file or environment variables. As
    there is currently only one account active on wiki.gg, the functions take
    no arguments.
    >>> auth1 = WikiggAuth.from_file()
    >>> auth2 = WikiggAuth.from_env()
    """

    def __init__(self, *args):
        super().__init__(*args)

    @classmethod
    def from_file(cls):
        """Return an auth object with credentials loaded from a file."""
        key = "ryebot"
        file = (  # "credentials" directory in the root directory
            Path(importlib.util.find_spec(__package__).origin).parents[2]
            / "credentials" / f"wikigg_{key}.txt"
        )
        return super().from_file(file.resolve(), filetype="plaintext")

    @classmethod
    def from_env(cls):
        """Return an auth object with credentials loaded from environment variables."""
        key = "RYEBOT"
        return super().from_env(f"WIKIGG_USERNAME_{key}", f"WIKIGG_PASSWORD_{key}")


class FandomAuth():
    pass

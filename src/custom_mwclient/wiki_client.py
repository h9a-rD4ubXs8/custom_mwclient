import urllib.parse

from mwclient import Site
from mwclient.page import Page
from mwclient.errors import AssertUserFailedError, APIError
from requests.exceptions import ReadTimeout

from custom_mwclient.errors import ApiContinueError
from custom_mwclient.namespace import Namespace
from custom_mwclient.wiki_authentication import WikiAuth


class WikiClient(Site):
    """Extension of mwclient's `Site`.

    >>> site = WikiClient(url, path, credentials)
    """
    write_errors = (AssertUserFailedError, ReadTimeout, APIError)

    def __init__(self,
        url: str,
        path: str = '/',
        credentials: WikiAuth = None,
        max_retries: int = 3,
        **kwargs
    ):
        # always let kwargs["scheme"] override the scheme in "url"
        # (also, Site.__init__ requires the raw URL, without scheme)
        if url.startswith('https://'):
            url = url[8:]
            kwargs.setdefault('scheme', 'https')
        elif url.startswith('http://'):
            url = url[7:]
        super().__init__(url, path=path, max_retries=max_retries, **kwargs)
        self.login(credentials)


    def login(self, credentials: WikiAuth):
        """Login to the wiki."""
        if credentials is None:
            return
        super().login(username=credentials.username, password=credentials.password)


    @property
    def namespaces__(self):
        if self._namespaces is not None:
            return self._namespaces
        result = self.client.api('query', meta='siteinfo', siprop="namespaces|namespacealiases")
        ns_aliases = {}
        for alias in result['query']['namespacealiases']:
            alias_key = str(alias['id'])
            if alias_key not in ns_aliases:
                ns_aliases[alias_key] = []
            ns_aliases[alias_key].append(alias['*'])
        ret = []
        for ns_str, ns_data in result['query']['namespaces'].items():
            ns = int(ns_str)
            ret.append(Namespace(id_number=ns, name=ns_data['*'], canonical_name=ns_data.get('canonical'), aliases=ns_aliases.get(ns_str)))
        self._namespaces = ret
        return ret


    def save(self, page: Page, text, summary='', minor=False, bot=True, section=None, **kwargs):
        """Call the `save` method of the `page`."""
        # this function is mainly intended to be overridden in subclasses
        return page.edit(text, summary, minor, bot, section, **kwargs)


    def move(self, page: Page, new_title, reason='', move_talk=True, no_redirect=False):
        """Call the `move` method of the `page`."""
        # this function is mainly intended to be overridden in subclasses
        return page.move(new_title, reason, move_talk, no_redirect)


    def delete(self, page: Page, reason='', watch=False, unwatch=False, oldimage=False):
        """Call the `delete` method of the `page`."""
        # this function is mainly intended to be overridden in subclasses
        return page.delete(reason, watch, unwatch, oldimage)


    def target(self, name: str):
        """Return the name of a page's redirect target.

        Parameters
        ----------
        1. name : str
            - The name of the redirect page.

        Returns
        -------
        - The name of the target page of the redirect.
        """

        return self.pages[name].resolve_redirect().name


    def fullurl(self, **kwargs):
        """Return the full URL to a page on the wiki.

        The keyword arguments are the parameters to index.php
        (https://www.mediawiki.org/wiki/Manual:Parameters_to_index.php), e.g.:
        >>> site.fullurl(title='Project:Sandbox', action='edit')
        >>> site.fullurl(diff=177126)

        For the reserved parameter `from`, pass it as follows:
        >>> site.fullurl(**{'from': 123})
        """

        return urllib.parse.urlunsplit((
            self.scheme,
            self.host,
            self.path + 'index' + self.ext,
            urllib.parse.urlencode(kwargs, quote_via=urllib.parse.quote),
            ''
        ))


    def get_last_rev(self, page: Page, log, query='revid'):
        """Get the latest revision (rev) id or timestamp for a given page.

        Parameters
        ----------
        1. page : mwclient.Page
            - The name of the page to get the revision for.
        """
        try:
            api_result = self.api('query', prop='revisions', titles=page.name, rvlimit=1) # https://terraria.gamepedia.com/api.php?action=query&prop=revisions&titles=User:Rye_Greenwood/Sandbox&rvlimit=1
        except KeyboardInterrupt:
            raise
        except:
            log('\n***ERROR*** while getting last revision!')
            log(exc_info=True, s='Error message:\n')
            return None
        page_ids = api_result['query']['pages']
        page_id = -1
        for id in page_ids:
            page_id = id
        try:
            rev = page_ids[page_id]['revisions'][0][query]
        except KeyError: # specified key doesn't exist, either because of invalid "query" arg or nonexistent page
            rev = None

        # rev = [revision for revision in page.revisions(limit=1, prop='ids')][0]['revid'] # this is a shorter alternative, but much much slower, since the limit=1 isn't recognized for some reason, and instead all revs are gathered
        return rev


    def find_summary_in_revs(self, page: Page, summary: str, log, user='Ryebot', limit=5, for_undo=False):
        """Get the revision ID of a revision with a specified summary from the specified user in a specified number of last revisions.

        Parameters
        ----------
        1. page : Page
            - The name of the page to operate on.
        2. summary : str
    	    - The edit summary to find.
        3. limit : int
            - The maximum number of revisions to search, starting from the latest
        4. for_undo : bool
            - Whether this method is called for an undo of that revision.

        Returns
        -------
        Without ``for_undo``:
            Revision ID.
        With ``for_undo``:
            (revid, prev_revid)
        """

        try:
            api_result = self.client.api('query', prop='revisions', titles=page.name, rvlimit=limit)
        except KeyboardInterrupt:
            raise
        except:
            log('\n***ERROR*** while getting list of revisions!')
            log(exc_info=True, s='Error message:\n')
            return None

        page_id = None
        page_ids = api_result['query']['pages']
        for p_id in page_ids:
            page_id = p_id

        if not page_id:
            return None

        revisions_to_search = page_ids[page_id]['revisions']
        revid = ''
        prev_revid = ''
        for rev in revisions_to_search:
            if rev['comment'] == summary and rev['user'] == user:
                revid = rev['revid']
                prev_revid = rev['parentid']
                break

        if for_undo:
            return (revid, prev_revid)

        return revid


    def namespace_names_to_ids(self, namespaces: list, log):
        """Convert a list of namespace names to their respective IDs.

        Parameters
        ----------
        1. namespaces : list[str]
            - The input list of namespace names.

        Returns
        -------
        The list of IDs as strings each.
        """

        result_namespaces = []
        try:
            api_result = self.client.api('query', meta='siteinfo', siprop='namespaces') # https://terraria.gamepedia.com/api.php?action=query&meta=siteinfo&siprop=namespaces
        except KeyboardInterrupt:
            raise
        except:
            log('\n***ERROR*** while list of all namespaces!')
            log(exc_info=True, s='Error message:\n')
            return None

        all_namespaces = api_result['query']['namespaces']
        for ns in all_namespaces:
            if all_namespaces[ns]['*'] in namespaces:
                result_namespaces.append(ns)

        return result_namespaces


    def get_current_servername(self):
        """Return the server name of the current wiki."""
        api_result = self.api('query', meta='siteinfo', siprop='general')
        return api_result.get('query', {}).get('general', {}).get('servername', '')


    def get_current_wiki_name(self):
        """Return the name of the current host."""
        # this function is mainly intended to be overridden in subclasses
        return self.get_current_servername()


    def get_current_wiki_user(self):
        """Return the name of the currently logged in user."""
        api_result = self.api('query', meta='userinfo')
        wiki_user = api_result.get('query', {}).get('userinfo', {}).get('name', '')
        return wiki_user


    def get_csrf_token(self, log):
        """Get a CSRF token for a POST request."""

        try:
            api_result = self.client.api('query', meta='tokens')
        except KeyboardInterrupt:
            raise
        except:
            log('\n***ERROR*** while getting CSRF token!')
            log(exc_info=True, s='Error message:\n')
            return None
        token = api_result['query']['tokens']['csrftoken']
        return token


    def api_continue__recursive(self, action: str, continue_name: str='', i: int=0, **kwargs):
        """
        Provides an API call with recursive, thus unlimited "continue" capability (e.g. for when the number of category members may exceed the bot limit (5000) but we want to get all >5000 of them).
        Returns an array with the contents of each "action" (e.g. "query") call.

        Parameters
        ----------
        1. action : str
            - API action module (e.g. ``query``).
        2. continue_name: str
            - Name of the ``continue`` attribute for the specified action (e.g. ``cmcontinue``). Defaults to first element in the ``continue`` array of the API result.
        3. i: int
            - Internally used by the recursion for debug. Do not use from outside!

        Raises
        ------
        - ``ApiContinueError`` (with ``__cause__`` set to the actual exception)
        """

        i += 1
        try:
            api_result = self.api(action, **kwargs)
        except Exception as exc:
            raise ApiContinueError(i, action, kwargs) from exc

        if 'continue' not in api_result:  # reached top of the stack
            if i == 1:  # still in the first call, no continues were necessary at all
                return [api_result[action]]
            else:
                return api_result[action]
        else:
            if not continue_name:
                continue_name = list(api_result['continue'].keys())[0]
            if continue_name not in api_result['continue']:
                raise RuntimeError(
                    f'The "continue_name" of "{continue_name}" was not in the API call!'
                )
            # add the continue parameter to the next API call
            kwargs[continue_name] = api_result['continue'][continue_name]
            # do recursion
            next_api_result = self.api_continue(action, continue_name, i, **kwargs)
            if next_api_result:
                if type(next_api_result) != list:
                    next_api_result = [next_api_result]
                result = next_api_result
                result.append(api_result[action])
                return result
            else:  # error during API call
                return


    def api_continue(self, action: str, continue_name: str='', **kwargs):
        """
        Provides an API call with unlimited "continue" capability (e.g. for when the number of category members may exceed the bot limit (5000) but we want to get all >5000 of them).
        Returns an array with the contents of each "action" (e.g. "query") call.

        Parameters
        ----------
        1. action : str
            - API action module (e.g. ``query``).
        2. continue_name: str
            - Name of the ``continue`` attribute for the specified action (e.g. ``cmcontinue``). Defaults to first element in the ``continue`` array of the API result.

        Raises
        ------
        - ``ApiContinueError`` (with ``__cause__`` set to the actual exception)
        """

        user_input_continue_name = continue_name
        api_results = []
        i = -1
        while True:
            i += 1

            # do API query
            try:
                api_result = self.api(action, **kwargs)
            except Exception as exc:
                raise ApiContinueError(i, action, kwargs) from exc
            api_results.append(api_result[action])

            if 'continue' not in api_result:
                break

            # determine the "continue" key for the next API call
            if not continue_name:
                continue_name = list(api_result['continue'].keys())[0]

            # invalid "continue_name" parameter passed to this function?
            if user_input_continue_name and user_input_continue_name not in api_result['continue']:
                error_str = f'"{user_input_continue_name}" not found'
                if continue_name:
                    error_str += f', did you mean "{continue_name}"?'
                raise RuntimeError(error_str)

            # add the "continue" parameter to the next API call
            kwargs[continue_name] = api_result['continue'][continue_name]

        return api_results


    def redirects_to_inclfragment(self, pagename: str):
        """Similar to ``mwclient.Site.redirects_to()``, but also returns the fragment of the redirect target."""

        api_result = self.client.api('query', prop='pageprops', titles=pagename, redirects='')
        if 'redirects' in api_result['query']:
            for page in api_result['query']['redirects']:
                if page['from'] == pagename:
                    if 'tofragment' in page:
                        return (page['to'], page['tofragment'])
                    else:
                        return (page['to'], None)

        return (None, None)


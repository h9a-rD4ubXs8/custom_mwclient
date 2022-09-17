import collections
import datetime
import time
import logging

from mwclient import Site
from mwclient.page import Page
from mwclient.errors import AssertUserFailedError
from mwclient.errors import APIError
from mwclient.errors import ProtectedPageError
from requests.exceptions import ReadTimeout

from custom_mwclient.wiki_authentication import WikiAuth
from custom_mwclient.wiki_content_error import WikiContentError
from custom_mwclient.namespace import Namespace
from custom_mwclient.errors import RetriedLoginAndStillFailed


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


    def pages_using(self, template: str, **kwargs):
        """Return a list of ``mwclient.page`` objects that are transcluding the specified page."""

        if ':' not in template:
            title = 'Template:' + template
        elif template.startswith(':'):
            title = template[1:]
        else:
            title = template
        return self.client.pages[title].embeddedin(**kwargs)


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

        return self.client.pages[name].resolve_redirect().name


    def save_(self, page: Page, text, summary=u'', minor=False, bot=True, section=None, log=None, **kwargs):
        """Performs a page edit, retrying the login once if the edit fails due to the user being logged out.

        This function hopefully makes it easy to workaround the lag and frequent login timeouts
        experienced on the Fandom UCP platform compared to Gamepedia Hydra.

        Parameters
        ----------
        1. page : Page
            - The page object of the page to save.
        2.–8.
            - As in mwclient.Page.save().
        """
        try:
            page.save(text, summary=summary, minor=minor, bot=bot, section=section, **kwargs)
        except ProtectedPageError:
            if log:
                log(exc_info=True, s='Error while saving page {}: Page is protected!'.format(page.name))
            else:
                raise
        except self.write_errors:
            self._retry_login_action(self._retry_save, 'edit', page=page, text=text, summary=summary, minor=minor,
                                     bot=bot, section=section, log=log, **kwargs)

    def _retry_save(self, **kwargs):
        old_page: Page = kwargs.pop('page')
        # recreate the page object so that we're using the new site object, post-relog
        page = self.client.pages[old_page.name]
        text = kwargs.pop('text')
        log = kwargs.pop('log')
        try:
            page.save(text, **kwargs)
        except ProtectedPageError:
            if log:
                log(exc_info=True, s='Error while saving page {}: Page is protected!'.format(page.name))
            else:
                raise


    def move_(self, page: Page, new_title, reason='', move_talk=True, no_redirect=False, move_subpages=False, ignore_warnings=False):
        try:
            page.move(new_title, reason=reason, move_talk=move_talk, no_redirect=no_redirect, move_subpages=move_subpages, ignore_warnings=ignore_warnings)
        except APIError as e:
            if e.code == 'badtoken':
                self._retry_login_action(self._retry_move, 'move', page=page, new_title=new_title, reason=reason, move_talk=move_talk, no_redirect=no_redirect, move_subpages=move_subpages, ignore_warnings=ignore_warnings)
            else:
                raise e

    def _retry_move(self, **kwargs):
        old_page: Page = kwargs.pop('page')
        page = self.client.pages[old_page.name]
        new_title = kwargs.pop('new_title')
        page.move(new_title, **kwargs)


    def delete_(self, page: Page, reason='', watch=False, unwatch=False, oldimage=False):
        try:
            page.delete(reason=reason, watch=watch, unwatch=unwatch, oldimage=oldimage)
        except APIError as e:
            if e.code == 'badtoken':
                self._retry_login_action(self._retry_delete, 'delete', page=page, reason=reason,
                                         watch=watch, unwatch=unwatch, oldimage=oldimage)
            else:
                raise e

    def _retry_delete(self, **kwargs):
        old_page: Page = kwargs.pop('page')
        page = self.client.pages[old_page.name]
        page.delete(**kwargs)


    def _retry_login_action(self, f, failure_type, **kwargs):
        was_successful = False
        for retry in range(self.max_retries):
            self.relog()
            # don't sleep at all the first retry, and then increment in retry_interval intervals
            # default interval is 10, default retries is 3
            time.sleep((2 ** retry - 1) * self.retry_interval)
            try:
                f(**kwargs)
                was_successful = True
                break
            except self.write_errors:
                continue
        if not was_successful:
            raise RetriedLoginAndStillFailed(failure_type)


    def api_(self, action, http_method='POST', *args, **kwargs):
        try:
            return self.client.api(action, http_method=http_method, *args, **kwargs)
        except self.write_errors:
            for retry in range(self.max_retries):
                self.relog()
                # don't sleep at all the first retry, and then increment in retry_interval intervals
                # default interval is 10, default retries is 3
                time.sleep((2 ** retry - 1) * self.retry_interval)
                try:
                    return self.client.api(action, http_method=http_method, *args, **kwargs)
                except self.write_errors:
                    continue
            raise RetriedLoginAndStillFailed('api')


    def get_last_rev(self, page: Page, log, query='revid'):
        """Get the latest revision (rev) id or timestamp for a given page.

        Parameters
        ----------
        1. page : mwclient.Page
            - The name of the page to get the revision for.
        """
        try:
            api_result = self.client.api('query', prop='revisions', titles=page.name, rvlimit=1) # https://terraria.gamepedia.com/api.php?action=query&prop=revisions&titles=User:Rye_Greenwood/Sandbox&rvlimit=1
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


    def get_last_section(self, page: Page, log, output_as_Wikicode=False, strip=True, anchor=False):
        """Get the heading and wikitext of the last section of the given page.

        Parameters
        ----------
        1. page : mwclient.Page
            - The name of the page to get the section from.
        2. output_as_Wikicode : bool
            - Whether to return the output as a Wikicode object instead of a string.
        3. strip : bool
            - Whether to trim the output (only valid if not output_as_Wikicode).
        4. anchor : bool
            - Whether to include the anchor of the heading in the output.

        Returns
        -------
        Without anchor:
            - (heading, content)
        With anchor:
            - ((headingtitle, headinganchor), content)
        """

        result = None
        try:
            wikitext = mwparserfromhell.parse(page.text())
        except KeyboardInterrupt:
            raise
        except:
            log('\n***ERROR*** while getting last section!')
            log(exc_info=True, s='Error message:\n')
            return None

        # Get heading:
        secs_whead = wikitext.get_sections(include_lead=False)
        if secs_whead: # if there are no sections, just return None
            lastsec = secs_whead[len(secs_whead) - 1]
            heading = None
            anchor_str = None
            for head in lastsec.ifilter_headings():
                heading = head
            if anchor:
                try:
                    api_result = self.client.api('parse', page=page.name, prop='sections')
                except KeyboardInterrupt:
                    raise
                except:
                    log('\n***ERROR*** while getting last section!')
                    log(exc_info=True, s='Error message:\n')
                    return None
                secs = api_result['parse']['sections']
                if len(secs) == 0:
                    return None
                anchor_str = secs[len(secs) - 1]['anchor']

            # Get content:
            secs_nohead = wikitext.get_sections(include_headings=False)
            lastsec = secs_nohead[len(secs_nohead) - 1]
            content = lastsec

            # Format:
            if not output_as_Wikicode:
                content = str(content)
                heading = str(heading)
                if strip:
                    content = content.strip()
                    heading = heading.strip()
            if anchor:
                result = ((heading, anchor_str), content)
            else:
                result = (heading, content)

        return result


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


    def page_exists(self, pagename: str, log):
        """Check whether a page with the specified name exists on the wiki."""
        try:
            api_result = self.client.api('query', prop='info', titles=pagename)
        except KeyboardInterrupt:
            raise
        except:
            log('\n***ERROR*** while checking whether the page "{}" exists!'.format(pagename))
            log(exc_info=True, s='Error message:\n')
            return False
        try:
            if not '-1' in api_result['query']['pages']:
                return True
        except KeyError: # api_result doesn't contain "pages"
            pass

        return False


    def get_current_wiki_name(self):
        """Return the name of the current host, without ``.gamepedia.com`` and ``.fandom.com``, and with ``/<lang>`` appended, if not English."""

        api_result = self.client.api('query', meta='siteinfo', siprop='general')

        sitename = api_result['query']['general']['servername']
        sitename = sitename.replace('.gamepedia.com', '').replace('.fandom.com', '').replace('.wiki.gg', '')

        sitelang = api_result['query']['general']['lang']
        if sitelang != "en" and sitelang != '':
            sitename += '/' + sitelang

        return sitename


    def get_current_wiki_user(self):
        """Returns the name of the currently logged in user."""

        api_result = self.client.api('query', meta='userinfo')
        wiki_user = api_result['query']['userinfo']['name']
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


    def api_continue(self, log, action: str, continue_name: str='', i: int=0, **kwargs):
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
        """

        i += 1
        #log('\n[%s] Enter api_continue().' % i)
        try:
            api_result = self.client.api(action, **kwargs)
            #log('[{}] API result: {}'.format(i, api_result))
        except:
            log('\n[{}] ***ERROR*** while executing continued API call (parameters: action=\'{}\', {})'.format(i, action, kwargs))
            log(exc_info=True, s='[{}] Error message:\n'.format(i))
            log('[{}] Aborted API call.'.format(i))
            return

        flag = True
        try:
            _ = api_result['continue']
        except KeyError: # continue doesn't exist
            flag = False
        if flag:
            if not continue_name:
                #log(list(api_result['continue'].keys()))
                continue_name = list(api_result['continue'].keys())[0]
            if api_result['continue'][continue_name]:
                #log('[{}] continue = {}'.format(i, api_result['continue'][continue_name]))
                kwargs.__setitem__(continue_name, api_result['continue'][continue_name]) # add the continue parameter to the next API call
                #log('[{}] Fetching new api result with the following parameters: action=\'{}\', {}'.format(i, action, kwargs))
                next_api_result = self.api_continue(log, action, continue_name, i, **kwargs) # do recursion
                #log('[{}] Received api result from previous call: {}'.format(i, next_api_result))
                if next_api_result:
                    #log('- Append this previous api result to api result from this call:')
                    #log('--- This api result: %s' % [api_result[action]])
                    #log('--- Previous api result that will be appended to above: %s' % next_api_result)

                    if type(next_api_result) == collections.OrderedDict:
                        next_api_result = [next_api_result]
                    result = next_api_result
                    result.append(api_result[action])
                    #log('- Appended.')
                    #log('[{}] Return:'.format(i))
                    #log('-- %s' % result)
                    #for x in result:
                    #    log('---- %s' % x)
                    return result
                else: # error during API call
                    #log('[%s] Return nothing.\n' % i)
                    return
        else: # reached top of the stack
            #log('[{}] Return {}.\n'.format(i, api_result[action]))
            if i == 1: # still in the first call, no continues were necessary at all
                return [api_result[action]]
            else:
                return api_result[action]


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


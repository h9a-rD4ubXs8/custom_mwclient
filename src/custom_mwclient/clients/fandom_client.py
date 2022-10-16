import time

from mwclient.page import Page
from mwclient.errors import AssertUserFailedError, APIError, ProtectedPageError

from custom_mwclient.wiki_client import WikiClient


class FandomClient(WikiClient):
    """Extension of `WikiClient` for Fandom-specific stuff."""

    def __init__(self, wikiname: str, lang: str = "en", max_retries: int = 3,
                 retry_interval: int = 10, **kwargs):
        url = f"https://{wikiname}.fandom.com"
        if lang != "en":
            url += '/' + lang
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        super().__init__(url, **kwargs)


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


    def save(self, page: Page, text, summary=u'', minor=False, bot=True, section=None, log=None, **kwargs):
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
        page = self.pages[old_page.name]
        text = kwargs.pop('text')
        log = kwargs.pop('log')
        try:
            page.save(text, **kwargs)
        except ProtectedPageError:
            if log:
                log(exc_info=True, s='Error while saving page {}: Page is protected!'.format(page.name))
            else:
                raise


    def move(self, page: Page, new_title, reason='', move_talk=True, no_redirect=False, move_subpages=False, ignore_warnings=False):
        try:
            page.move(new_title, reason=reason, move_talk=move_talk, no_redirect=no_redirect, move_subpages=move_subpages, ignore_warnings=ignore_warnings)
        except APIError as e:
            if e.code == 'badtoken':
                self._retry_login_action(self._retry_move, 'move', page=page, new_title=new_title, reason=reason, move_talk=move_talk, no_redirect=no_redirect, move_subpages=move_subpages, ignore_warnings=ignore_warnings)
            else:
                raise e


    def _retry_move(self, **kwargs):
        old_page: Page = kwargs.pop('page')
        page = self.pages[old_page.name]
        new_title = kwargs.pop('new_title')
        page.move(new_title, **kwargs)


    def delete(self, page: Page, reason='', watch=False, unwatch=False, oldimage=False):
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
        page = self.pages[old_page.name]
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


    def api(self, action, http_method='POST', *args, **kwargs):
        try:
            return super().api(action, http_method=http_method, *args, **kwargs)
        except self.write_errors:
            for retry in range(self.max_retries):
                self.relog()
                # don't sleep at all the first retry, and then increment in retry_interval intervals
                # default interval is 10, default retries is 3
                time.sleep((2 ** retry - 1) * self.retry_interval)
                try:
                    return super().api(action, http_method=http_method, *args, **kwargs)
                except self.write_errors:
                    continue
            raise RetriedLoginAndStillFailed('api')


    def relog(self):
        raise NotImplementedError


class RetriedLoginAndStillFailed(AssertUserFailedError):
    def __init__(self, action):
        self.action = action

    def __str__(self):
        return "Tried to re-login but still failed. Attempted action: {}".format(self.action)

"""Two independently configured Apps use the same production approval scope."""
from test_google_access_ui import ADMIN, USER, app, runtime


def test_two_sites_share_approval_and_revocation_with_separate_login_settings(runtime):
    store, _ = runtime
    first = app()
    second = app()
    first.secrets['auth']['redirect_uri'] = 'https://synthetic-first.example/oauth2callback'
    second.secrets['auth']['redirect_uri'] = 'https://synthetic-second.example/oauth2callback'
    first.secrets['auth']['cookie_secret'] = 'synthetic-first-cookie-' + 'x' * 32
    second.secrets['auth']['cookie_secret'] = 'synthetic-second-cookie-' + 'y' * 32
    store.request(USER, 'production')
    for site in (first, second):
        site.run()
        assert not site.exception and len(site.get('file_uploader')) == 0
    store.review(ADMIN, USER.subject, 'production', 'approved', 1)
    for site in (first, second):
        site.run()
        assert not site.exception and len(site.get('file_uploader')) == 1
        site.session_state['parsed_upload'] = {'digest': 'synthetic', 'report': {}}
    store.review(ADMIN, USER.subject, 'production', 'revoked', 2)
    for site in (first, second):
        site.run()
        assert not site.exception and len(site.get('file_uploader')) == 0
        assert 'parsed_upload' not in site.session_state

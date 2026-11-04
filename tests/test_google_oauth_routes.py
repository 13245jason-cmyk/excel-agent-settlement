"""Exercise Streamlit's real login routes; only upstream Google HTTP is mocked."""
from urllib.parse import parse_qs, urlparse
import asyncio
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware

from streamlit import auth_util
from streamlit.runtime.secrets import AttrDict
from streamlit.web.server.starlette import starlette_auth_routes as routes

METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
CALLBACK = "https://test.example/oauth2callback"
CLIENT_ID = "synthetic.apps.googleusercontent.com"


@pytest.fixture
def native_oauth(monkeypatch):
    requests = []
    state = {"metadata_status": 200}

    def google_http(request):
        requests.append(str(request.url))
        assert str(request.url) == METADATA_URL, "Unexpected upstream request"
        if state["metadata_status"] != 200:
            return httpx.Response(state["metadata_status"], text="synthetic private upstream detail")
        return httpx.Response(200, json={
            "issuer": "https://accounts.google.com",
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "code_challenge_methods_supported": ["S256"],
        })

    config = AttrDict({
        "redirect_uri": CALLBACK,
        "cookie_secret": "synthetic-cookie-signing-secret-at-least-32-characters",
        "google": {
            "client_id": CLIENT_ID,
            "client_secret": "synthetic-client-secret",
            "server_metadata_url": METADATA_URL,
            "client_kwargs": {
                "scope": "openid email profile", "prompt": "select_account",
                "transport": httpx.MockTransport(google_http),
                "trust_env": False,  # Mock-only HTTP must not use runtime proxies.
            },
        },
    })
    monkeypatch.setattr(routes, "get_secrets_auth_section", lambda: config)
    monkeypatch.setattr(auth_util, "get_signing_secret", lambda: config["cookie_secret"])
    monkeypatch.setattr(routes, "get_cookie_secret", lambda: config["cookie_secret"])
    # Callback origin resolution delegates to auth_util rather than the route alias.
    monkeypatch.setattr(auth_util, "get_secrets_auth_section", lambda: config)
    app = Starlette(routes=routes.create_auth_routes(""))
    app.add_middleware(SessionMiddleware, secret_key=config["cookie_secret"], https_only=True)
    loop = asyncio.new_event_loop()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test.example",
                               follow_redirects=False, trust_env=False)
    try:
        def get(*args, **kwargs):
            return loop.run_until_complete(client.get(*args, **kwargs))
        yield SimpleNamespace(get=get, cookies=client.cookies), auth_util.encode_provider_token("google"), requests, state
    finally:
        loop.run_until_complete(client.aclose())
        loop.close()


def test_native_login_reaches_google_with_state_nonce_and_pkce(native_oauth):
    client, provider, requests, _ = native_oauth
    response = client.get("/auth/login", params={"provider": provider})
    assert response.status_code in (302, 307)
    target = urlparse(response.headers["location"])
    query = parse_qs(target.query)
    assert target.netloc == "accounts.google.com"
    assert target.path == "/o/oauth2/v2/auth"
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [CALLBACK]
    assert set(query["scope"][0].split()) == {"openid", "email", "profile"}
    assert query["response_type"] == ["code"]
    assert query["state"][0] and query["nonce"][0]
    assert query["code_challenge"][0]
    assert query["code_challenge_method"] == ["S256"]
    assert requests == [METADATA_URL]
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie


def test_invalid_provider_token_does_not_contact_google(native_oauth):
    client, _, requests, _ = native_oauth
    response = client.get("/auth/login", params={"provider": "not-a-valid-signed-token"})
    assert response.status_code == 302 and response.headers["location"] == "/"
    assert requests == []
    assert "_streamlit_user" not in client.cookies


def test_unknown_callback_state_cannot_exchange_tokens_or_create_user(native_oauth):
    client, provider, requests, _ = native_oauth
    client.get("/auth/login", params={"provider": provider})
    response = client.get("/oauth2callback", params={"state": "forged", "code": "synthetic-code"})
    assert response.status_code == 302 and response.headers["location"] == "/"
    assert requests == [METADATA_URL]
    assert "_streamlit_user" not in client.cookies


def test_upstream_discovery_error_is_denied_without_exposing_details(native_oauth):
    client, provider, _, state = native_oauth
    state["metadata_status"] = 503
    response = client.get("/auth/login", params={"provider": provider})
    assert response.status_code == 400
    assert response.text == "Authentication error"
    assert "synthetic-client-secret" not in response.text
    assert "private upstream detail" not in response.text
    assert "_streamlit_user" not in client.cookies

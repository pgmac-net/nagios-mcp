"""Tests for the SSE transport's HTTP routing.

The SSE transport advertises a POST endpoint to clients in the ``endpoint``
event, and separately mounts a route to receive those POSTs. If the two
disagree, Starlette answers every POST with a 307 redirect, which breaks
clients that do not replay the request body on redirect.
"""

from starlette.routing import Mount
from starlette.testclient import TestClient

from nagios_mcp.server import MESSAGES_PATH, build_sse_app


def _mounted_paths(app):
    return [route.path for route in app.routes if isinstance(route, Mount)]


def test_advertised_path_is_served_by_the_mount():
    """The path clients are told to POST to must be the path we listen on.

    Starlette strips the trailing slash when storing ``Mount.path``, so the
    comparison is made against the normalised form.
    """
    assert MESSAGES_PATH.rstrip("/") in _mounted_paths(build_sse_app())


def test_post_to_advertised_endpoint_is_not_redirected():
    """POSTing to the advertised endpoint must not produce a 307."""
    client = TestClient(build_sse_app())

    response = client.post(
        f"{MESSAGES_PATH}?session_id=00000000000000000000000000000000",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        follow_redirects=False,
    )

    assert response.status_code != 307, (
        f"advertised endpoint {MESSAGES_PATH!r} redirected to "
        f"{response.headers.get('location')!r}; clients that drop the body on "
        f"redirect never complete the initialize handshake"
    )


def test_sse_endpoint_is_registered():
    """The SSE stream endpoint stays reachable at /sse."""
    assert "/sse" in [route.path for route in build_sse_app().routes]

"""Tests for the stateless streamable HTTP transport at /mcp.

The SSE transport hands out a new server-side session on every GET /sse, and a
client that reconnects does not re-run ``initialize`` on it, so every call then
fails with -32602. The streamable HTTP endpoint is stateless: any request is
valid on its own, including after the server restarts.
"""

from starlette.testclient import TestClient

from nagios_mcp.server import MCP_PATH, build_http_app

HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _rpc(client, method, params=None, request_id=1):
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post(MCP_PATH, json=body, headers=HEADERS, follow_redirects=False)


def test_mcp_and_sse_routes_are_registered():
    """The new endpoint is added without removing the legacy ones."""
    paths = [route.path for route in build_http_app().routes]
    assert MCP_PATH in paths
    assert "/sse" in paths
    assert any(path.startswith("/messages") for path in paths)


def test_initialize_works_without_a_session():
    """The handshake succeeds and no session id is issued."""
    with TestClient(build_http_app()) as client:
        response = _rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )

    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "nagios-mcp-server"
    assert "mcp-session-id" not in {key.lower() for key in response.headers}


def test_tools_list_without_prior_initialize():
    """A request needs no earlier handshake: this is what -32602 broke on SSE."""
    with TestClient(build_http_app()) as client:
        response = _rpc(client, "tools/list")

    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert "get_alerts" in names


def test_requests_survive_a_server_restart():
    """A brand-new app (a restarted pod) serves the same client without a reconnect."""
    with TestClient(build_http_app()) as first:
        assert _rpc(first, "tools/list").status_code == 200
    with TestClient(build_http_app()) as restarted:
        response = _rpc(restarted, "tools/list")

    assert response.status_code == 200
    assert "result" in response.json()


def test_mcp_is_not_redirected():
    """/mcp must answer directly, never 307 to /mcp/."""
    with TestClient(build_http_app()) as client:
        response = _rpc(client, "ping")

    assert response.status_code != 307

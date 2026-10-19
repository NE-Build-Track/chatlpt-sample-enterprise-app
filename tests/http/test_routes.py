"""Routes: health, accounts, CSRF, conversations, the SSE reply, usage and admin."""

import json

import httpx

from chatlpt.testing import ScriptedBackend
from tests.http.conftest import signup


async def test_health_without_engine_is_honest(client: httpx.AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    ready = await client.get("/readyz")
    assert ready.status_code == 200
    body = ready.json()
    assert body["ready"] and body["engine_configured"] and body["chat_available"]


async def test_signup_login_me_logout(client: httpx.AsyncClient) -> None:
    me = await signup(client, "alice@example.com")
    assert (await client.get("/api/auth/me")).json()["id"] == me["id"]
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401
    login = await client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "correct horse"}
    )
    assert login.status_code == 200 and login.json()["email"] == "alice@example.com"
    bad = await client.post("/api/auth/login", json={"email": "alice@example.com", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["error"]


async def test_state_changes_need_the_csrf_header(client: httpx.AsyncClient) -> None:
    await signup(client, "alice@example.com")
    response = await client.post("/api/conversations", headers={"x-chatlpt": ""})
    assert response.status_code == 401
    assert (await client.get("/api/conversations", headers={"x-chatlpt": ""})).status_code == 200


async def test_conversation_lifecycle_and_sse_reply(
    client: httpx.AsyncClient, backend: ScriptedBackend
) -> None:
    await signup(client, "alice@example.com")
    created = await client.post("/api/conversations")
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    async with client.stream(
        "POST", f"/api/conversations/{conversation_id}/messages", json={"content": "Hello"}
    ) as stream:
        assert stream.status_code == 200 and stream.headers["content-type"].startswith("text/event-stream")
        frames = (await stream.aread()).decode().strip().split("\n\n")
    events = [json.loads(frame.split("\ndata: ", 1)[1]) for frame in frames]
    assert [e["type"] for e in events] == ["start", "content", "done"]
    assert events[-1]["message"]["retail"]["amount"].startswith("0.0000")
    assert events[-1]["message"]["wholesale"]["status"] == "pending"
    detail = await client.get(f"/api/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert [m["role"] for m in detail.json()["messages"]] == ["user", "assistant"]
    assert detail.json()["conversation"]["title"] == "Hello" and detail.json()["totals"]["replies"] == 1
    renamed = await client.patch(f"/api/conversations/{conversation_id}", json={"title": "Greeting"})
    assert renamed.json()["title"] == "Greeting"
    usage = await client.get("/api/usage/me")
    assert usage.json()["replies"] == 1 and usage.json()["wholesale_pending"] == 1
    assert (await client.delete(f"/api/conversations/{conversation_id}")).status_code == 204
    assert (await client.get(f"/api/conversations/{conversation_id}")).status_code == 404
    assert len(backend.calls) == 1


async def test_users_cannot_see_each_others_conversations(client: httpx.AsyncClient) -> None:
    await signup(client, "alice@example.com")
    conversation_id = (await client.post("/api/conversations")).json()["id"]
    await client.post("/api/auth/logout")
    await signup(client, "bob@example.com")
    assert (await client.get(f"/api/conversations/{conversation_id}")).status_code == 404
    assert (
        await client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "x"})
    ).status_code == 404


async def test_model_endpoint_reports_availability_and_prices(
    client: httpx.AsyncClient, backend: ScriptedBackend
) -> None:
    await signup(client, "alice@example.com")
    model = await client.get("/api/model")
    assert model.json()["chat_available"] and model.json()["prices"]["output_per_m"] == "3.00"
    backend.available = (False, "stale discovery")
    assert (await client.get("/api/model")).json()["reason"] == "stale discovery"


async def test_admin_routes_require_an_admin(client: httpx.AsyncClient) -> None:
    await signup(client, "alice@example.com")
    assert (await client.get("/api/admin/users")).status_code == 403
    await client.post("/api/auth/logout")
    admin = await signup(client, "admin@example.com")
    rows = await client.get("/api/admin/users")
    assert rows.status_code == 200 and {r["user"]["email"] for r in rows.json()} == {
        "alice@example.com",
        "admin@example.com",
    }
    alice_id = next(r["user"]["id"] for r in rows.json() if r["user"]["email"] == "alice@example.com")
    disabled = await client.post(f"/api/admin/users/{alice_id}/disabled", json={"disabled": True})
    assert disabled.json()["disabled"] is True
    assert (
        await client.post(f"/api/admin/users/{admin['id']}/disabled", json={"disabled": True})
    ).status_code == 403


async def test_providers_lists_nothing_when_unconfigured(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/auth/providers")).json() == {"providers": [], "allow_signup": True}
    assert (await client.get("/api/auth/oauth/google/start")).status_code == 404


async def test_patch_thinking_and_continue_route(client: httpx.AsyncClient, backend: ScriptedBackend) -> None:
    from chatlpt.contracts import ReplyChunk, TokenUsage

    await signup(client, "alice@example.com")
    conversation_id = (await client.post("/api/conversations")).json()["id"]
    assert (await client.patch(f"/api/conversations/{conversation_id}", json={})).status_code == 400
    updated = await client.patch(
        f"/api/conversations/{conversation_id}", json={"thinking": "high", "title": "Deep"}
    )
    assert updated.json()["thinking"] == "high" and updated.json()["title"] == "Deep"
    assert (
        await client.patch(f"/api/conversations/{conversation_id}", json={"thinking": "huge"})
    ).status_code == 422

    backend.script = [
        ReplyChunk(kind="content", text="half"),
        ReplyChunk(kind="usage", usage=TokenUsage(prompt_tokens=1, completion_tokens=2)),
        ReplyChunk(kind="done", finish_reason="length"),
    ]
    async with client.stream(
        "POST", f"/api/conversations/{conversation_id}/messages", json={"content": "go"}
    ) as stream:
        frames = (await stream.aread()).decode().strip().split("\n\n")
    first_id = json.loads(frames[-1].split("\ndata: ", 1)[1])["message"]["id"]
    backend.script = [
        ReplyChunk(kind="content", text=" and rest"),
        ReplyChunk(kind="done", finish_reason="stop"),
    ]
    async with client.stream(
        "POST", f"/api/conversations/{conversation_id}/messages/{first_id}/continue"
    ) as stream:
        assert stream.status_code == 200
        frames = (await stream.aread()).decode().strip().split("\n\n")
    events = [json.loads(f.split("\ndata: ", 1)[1]) for f in frames]
    assert [e["type"] for e in events] == ["start", "content", "done"]
    assert events[-1]["message"]["continues_message_id"] == first_id
    detail = await client.get(f"/api/conversations/{conversation_id}")
    assert [m["role"] for m in detail.json()["messages"]] == ["user", "assistant", "assistant"]

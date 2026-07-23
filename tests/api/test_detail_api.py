"""GET/POST /api/detail tests (headless): the dashboard's live detail-provider toggle."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

from kdence.api.server import serve


@contextmanager
def running_server(store_path: str, detail_path: str) -> Iterator[str]:
    server = serve(str(store_path), host="127.0.0.1", port=0, detail_path=str(detail_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(base: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base + path, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(base: str, path: str, body: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(base + path, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_get_defaults_to_off_and_lists_available_providers(tmp_path) -> None:
    store = tmp_path / "kdence.db"
    detail = tmp_path / "detail.json"  # absent
    with running_server(store, detail) as base:
        status, payload = _get(base, "/api/detail")
    assert status == 200
    assert payload["providers"] == []  # nothing enabled yet
    assert payload["available"] == ["caption", "mpris"]
    assert "caption" in payload["labels"] and "mpris" in payload["labels"]


def test_post_enables_a_provider_and_persists(tmp_path) -> None:
    store = tmp_path / "kdence.db"
    detail = tmp_path / "detail.json"
    with running_server(store, detail) as base:
        body = json.dumps({"providers": ["caption"], "denylist": ["org.keepassxc.KeePassXC"]})
        status, saved = _post(base, "/api/detail", body.encode())
        assert status == 200
        assert saved["providers"] == ["caption"]
        assert saved["denylist"] == ["org.keepassxc.KeePassXC"]
        # A subsequent GET reflects the persisted toggle.
        _, got = _get(base, "/api/detail")
        assert got["providers"] == ["caption"]
    # The file the collector reads was actually written.
    assert json.loads(detail.read_text())["providers"] == ["caption"]


def test_post_rejects_unknown_provider_without_writing(tmp_path) -> None:
    store = tmp_path / "kdence.db"
    detail = tmp_path / "detail.json"
    with running_server(store, detail) as base:
        status, err = _post(base, "/api/detail", json.dumps({"providers": ["telepathy"]}).encode())
        assert status == 400
        assert "unknown provider" in err["error"]
    assert not detail.exists()  # nothing written on a bad request


def test_post_toggle_off_writes_empty(tmp_path) -> None:
    store = tmp_path / "kdence.db"
    detail = tmp_path / "detail.json"
    with running_server(store, detail) as base:
        _post(base, "/api/detail", json.dumps({"providers": ["mpris"]}).encode())
        status, saved = _post(base, "/api/detail", json.dumps({"providers": []}).encode())
        assert status == 200
        assert saved["providers"] == []

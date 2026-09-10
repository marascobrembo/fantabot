"""`fantabot auth fantalab-login`, with a fake browser.

No Chromium launches and no socket opens — the autouse guard would fail these
outright. What is pinned is the posture: the page is navigated once and never
interacted with, no credential reaches the output, and no session file is
written.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from fantabot.application.fantalab_login import FantalabLoginResult, run
from fantabot.interface.app import app
from fantabot.interface.console import console

ANSI = re.compile(r"\x1b\[[0-9;]*m")
runner = CliRunner()

REFRESH = "refresh-CanaryValue777"
STORAGE = {
    "origins": [
        {
            "origin": "https://app.fantalab.it",
            "localStorage": [
                {"name": "refresh_token", "value": REFRESH},
                {"name": "id_token", "value": "id-CanaryValue777"},
                {"name": "access_token", "value": "access-CanaryValue777"},
                {"name": "user_id", "value": "user-uuid"},
            ],
        }
    ]
}


class _FakePage:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def goto(self, url: str) -> None:
        self.calls.append("goto")

    def __getattr__(self, name: str) -> Any:
        def record(*_a: Any, **_k: Any) -> None:
            self.calls.append(name)

        return record


class _FakeContext:
    def __init__(self, storage: dict[str, Any]) -> None:
        self.page = _FakePage()
        self._storage = storage

    def new_page(self) -> _FakePage:
        return self.page

    def storage_state(self) -> dict[str, Any]:
        return self._storage

    def __enter__(self) -> _FakeContext:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


@pytest.fixture
def _clean_session(db_session: Any) -> None:  # pragma: no cover - db tier only
    return None


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ctx: _FakeContext) -> Any:
    """Run the flow with the database and cipher stubbed out."""
    import fantabot.application.fantalab_login as module

    saved: list[Any] = []

    class _Cipher:
        fingerprint = "abcd1234"

        def encrypt(self, plaintext: str) -> bytes:
            return plaintext.encode()

    class _Store:
        def __init__(self, *_a: Any) -> None: ...

        def describe(self) -> list[Any]:
            return []

        def save(self, captured: Any, **_k: Any) -> None:
            saved.append(captured)

    class _Session:
        def __enter__(self) -> _Session:
            return self

        def __exit__(self, *_e: object) -> None: ...

        def commit(self) -> None: ...

    monkeypatch.setattr(module, "_preflight_key", lambda: _Cipher())
    monkeypatch.setattr(module, "_preflight_database", lambda: None)
    monkeypatch.setitem(
        __import__("sys").modules, "fantabot.adapters.tokens.fantalab_store",
        type("m", (), {"FantalabStore": _Store})(),
    )
    import fantabot.adapters.persistence as db_module

    monkeypatch.setattr(db_module.database_manager, "get_session", lambda: _Session())
    result = run(report=console, browser_factory=lambda: ctx, prompt=lambda _m: "",
                 now=datetime(2026, 8, 27, tzinfo=UTC))
    return result, saved


def test_the_page_is_navigated_once_and_never_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A scripted sign-in is what gets accounts flagged. The recorded call list
    is asserted exactly, so any future click fails this rather than shipping."""
    ctx = _FakeContext(STORAGE)
    _run(tmp_path, monkeypatch, ctx)
    assert ctx.page.calls == ["goto"], f"the page was interacted with: {ctx.page.calls}"


def test_no_credential_reaches_the_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cron captures stdout, so anything printed outlives the run in a log."""
    _run(tmp_path, monkeypatch, _FakeContext(STORAGE))
    output = ANSI.sub("", capsys.readouterr().out)
    assert "CanaryValue777" not in output
    assert "user-uuid" in output, "the account id is not a secret and is worth reporting"


def test_the_session_is_captured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, saved = _run(tmp_path, monkeypatch, _FakeContext(STORAGE))
    assert isinstance(result, FantalabLoginResult)
    assert result.stored and result.browser_opened
    assert saved[0].refresh_token == REFRESH


def test_no_session_file_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A storage_state.json would hold three credentials in the clear — the very
    thing the token-store phase exists to prevent."""
    monkeypatch.chdir(tmp_path)
    _run(tmp_path, monkeypatch, _FakeContext(STORAGE))
    assert list(tmp_path.rglob("*.json")) == []


def _stub_store_and_db(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Same stubbing `_run` does for `run`, reused for `fantalab-import` — no
    browser factory this time, since the whole point is that one is never opened."""
    import fantabot.application.fantalab_login as module

    saved: list[Any] = []

    class _Cipher:
        fingerprint = "abcd1234"

        def encrypt(self, plaintext: str) -> bytes:
            return plaintext.encode()

    class _Store:
        def __init__(self, *_a: Any) -> None: ...

        def save(self, captured: Any, **_k: Any) -> None:
            saved.append(captured)

    class _Session:
        def __enter__(self) -> _Session:
            return self

        def __exit__(self, *_e: object) -> None: ...

        def commit(self) -> None: ...

    monkeypatch.setattr(module, "_preflight_key", lambda: _Cipher())
    monkeypatch.setattr(module, "_preflight_database", lambda: None)
    monkeypatch.setitem(
        __import__("sys").modules, "fantabot.adapters.tokens.fantalab_store",
        type("m", (), {"FantalabStore": _Store})(),
    )
    import fantabot.adapters.persistence as db_module

    monkeypatch.setattr(db_module.database_manager, "get_session", lambda: _Session())
    return saved


def test_fantalab_import_stores_a_session_with_no_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command a headless host uses instead: a human captured the session by hand,
    elsewhere, in an ordinary browser — this only has to store it."""
    saved = _stub_store_and_db(monkeypatch)

    result = runner.invoke(
        app,
        ["auth", "fantalab-import", "--user-id", "user-uuid"],
        input="refresh-CanaryValue777\nid-CanaryValue777\naccess-CanaryValue777\n",
    )

    assert result.exit_code == 0, result.output
    assert len(saved) == 1
    assert saved[0].user_id == "user-uuid"
    assert saved[0].refresh_token == "refresh-CanaryValue777"
    assert saved[0].id_token == "id-CanaryValue777"
    assert saved[0].access_token == "access-CanaryValue777"


def test_fantalab_import_hides_the_tokens_from_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cron captures stdout, and a terminal's scrollback outlives the session too."""
    _stub_store_and_db(monkeypatch)

    result = runner.invoke(
        app,
        ["auth", "fantalab-import", "--user-id", "user-uuid"],
        input="refresh-CanaryValue777\nid-CanaryValue777\naccess-CanaryValue777\n",
    )

    output = ANSI.sub("", result.output)
    assert "CanaryValue777" not in output
    assert "user-uuid" in output, "the account id is not a secret and is worth reporting"


def test_fantalab_import_accepts_blank_id_and_access_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A human who only copied `refresh_token` — the durable credential — is not stuck:
    the app re-derives the other two on its next `/sign-in`."""
    saved = _stub_store_and_db(monkeypatch)

    result = runner.invoke(
        app,
        ["auth", "fantalab-import", "--user-id", "user-uuid"],
        input="refresh-CanaryValue777\n\n\n",
    )

    assert result.exit_code == 0, result.output
    assert saved[0].id_token is None
    assert saved[0].access_token is None

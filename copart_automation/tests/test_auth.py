"""Tests for authentication and session reauthentication logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from copart_automation.app import auth as auth_module
from copart_automation.app.auth import AuthManager
from copart_automation.app.browser import BrowserManager


class DummyPage:
    url = "https://www.copart.com/"

    async def goto(self, *args, **kwargs) -> None:
        return None

    async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
        return None

    async def close(self) -> None:
        return None


class DummyContext:
    async def new_page(self) -> DummyPage:
        return DummyPage()

    async def close(self) -> None:
        return None


class DummyBrowser:
    async def new_context(self, **kwargs) -> DummyContext:
        return DummyContext()


class DummyBrowserManager(BrowserManager):
    def __init__(self) -> None:
        super().__init__()
        self.started = False

    async def start(self) -> None:
        self.started = True
        self._browser = DummyBrowser()
        self._context = None


@pytest.mark.asyncio
async def test_auth_manager_load_existing_session_starts_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(auth_module.settings, "storage_state_path", state_file)

    manager = DummyBrowserManager()
    auth = AuthManager(manager)

    loaded = await auth.load_existing_session()
    assert loaded is True
    assert manager.started is True

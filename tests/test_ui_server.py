"""UI server path helpers."""

from __future__ import annotations

from pathlib import Path

from rcopilot.ui_server import resolve_web_dir, repo_root


def test_resolve_web_dir_finds_checkout() -> None:
    web = resolve_web_dir()
    assert web is not None
    assert (web / "package.json").is_file()
    assert web == (repo_root() / "web").resolve() or web == (Path.cwd() / "web").resolve()

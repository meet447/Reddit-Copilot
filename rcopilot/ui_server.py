"""Helpers to launch the Next.js review UI alongside the API."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def repo_root() -> Path:
    """Repo root when running from a checkout / editable install."""
    return Path(__file__).resolve().parent.parent


def resolve_web_dir() -> Path | None:
    """Locate web/package.json from cwd or the package checkout."""
    candidates = [
        Path.cwd() / "web",
        repo_root() / "web",
    ]
    for path in candidates:
        if (path / "package.json").is_file():
            return path.resolve()
    return None


def ensure_node_available() -> None:
    if shutil.which("node") is None or shutil.which("npm") is None:
        raise RuntimeError(
            "Node.js and npm are required to run the UI. "
            "Install Node 20+ from https://nodejs.org/ or use "
            "`rcopilot serve --api-only` and run the UI yourself."
        )


def ensure_web_deps(web_dir: Path, *, skip_install: bool = False) -> None:
    node_modules = web_dir / "node_modules"
    if node_modules.is_dir():
        return
    if skip_install:
        raise RuntimeError(
            f"UI dependencies missing at {node_modules}. "
            "Run `npm install` in web/ or omit --no-install."
        )
    print(f"Installing UI dependencies in {web_dir} …")
    result = subprocess.run(
        ["npm", "install"],
        cwd=web_dir,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"`npm install` failed in {web_dir} (exit {result.returncode})."
        )


def start_ui(
    web_dir: Path,
    *,
    api_host: str,
    api_port: int,
    ui_port: int = 3000,
) -> subprocess.Popen[bytes]:
    """Start `next dev` and return the process handle."""
    ensure_node_available()
    env = os.environ.copy()
    env["API_PROXY_TARGET"] = f"http://{api_host}:{api_port}"
    # Bind localhost only; matches default frontend_url.
    cmd = [
        "npm",
        "run",
        "dev",
        "--",
        "--port",
        str(ui_port),
        "--hostname",
        "127.0.0.1",
    ]
    print(f"Starting UI on http://127.0.0.1:{ui_port} (proxy → {env['API_PROXY_TARGET']})")
    return subprocess.Popen(
        cmd,
        cwd=web_dir,
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def stop_ui(proc: subprocess.Popen[bytes] | None, *, timeout: float = 8.0) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)

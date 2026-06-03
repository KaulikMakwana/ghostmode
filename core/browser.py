import asyncio
import json
import os
import signal
import subprocess
import time
import requests
import websockets
from pathlib import Path
from config import (CDP_PORT, CDP_HOST, CHROMIUM_BIN, PROFILES_DIR, STATE_FILE,
                    WS_PING_INTERVAL, WS_PING_TIMEOUT, WS_MAX_SIZE,
                    RECONNECT_WAIT)


# ── Active-browser marker ──────────────────────────────────────────────────────
# A fresh `python main.py ...` process has no memory of which profile is loaded in
# the Chromium that already owns CDP_PORT. We persist that on disk so an account
# switch can detect a mismatch and kill+relaunch instead of silently reusing the
# wrong profile.

def _write_marker(profile_dir: Path, pid: int):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            "profile_dir": str(Path(profile_dir).resolve()),
            "pid": pid,
        }))
    except Exception:
        pass


def read_marker() -> dict | None:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return None


def running_profile_dir() -> str | None:
    """Resolved profile_dir of the Chromium currently on CDP_PORT, or None."""
    m = read_marker()
    return m.get("profile_dir") if m else None


def _port_free(timeout: float = 0.0) -> bool:
    """True once nothing answers on CDP_PORT (optionally wait up to `timeout`)."""
    start = time.time()
    while True:
        try:
            requests.get(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=1)
            up = True
        except Exception:
            up = False
        if not up:
            return True
        if time.time() - start >= timeout:
            return False
        time.sleep(0.3)


def kill_running_browser(timeout: float = 10.0) -> bool:
    """Kill the Chromium that owns CDP_PORT (via the marker pid). Returns True once
    the port is free. Escalates SIGTERM → SIGKILL."""
    m = read_marker()
    pid = m.get("pid") if m else None
    if pid:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                break
            except Exception:
                break
            if _port_free(timeout=timeout / 2):
                break
    freed = _port_free(timeout=timeout)
    if freed:
        try:
            STATE_FILE.unlink()
        except Exception:
            pass
    return freed


class Browser:
    """Manages a Chromium process with CDP and provides a JS execution interface."""

    def __init__(self, profile: str = "google", profile_dir: str = None):
        self.profile = profile
        # Accept an explicit absolute path (from DB) or fall back to default location
        self.profile_dir = Path(profile_dir) if profile_dir else PROFILES_DIR / profile
        self._proc: subprocess.Popen | None = None
        self._ws = None
        self._mid = 0

    # ── Process management ──────────────────────────────────────────────────

    def launch(self, headless: bool = False, extra_args: list = None):
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            CHROMIUM_BIN,
            f"--remote-debugging-port={CDP_PORT}",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--test-type",  # suppresses the "--no-sandbox is unsupported" infobar
            "--disable-infobars",
        ]
        if headless:
            # Pin a desktop viewport — IG's layout (and the CDP coordinate-clicks the
            # deleters rely on) is verified against a wide window; a tiny headless
            # default would shift the bloks buttons and break the clicks.
            cmd.append("--headless=new")
            cmd.append("--window-size=1920,1080")
        if extra_args:
            cmd.extend(extra_args)
        cmd.append("about:blank")
        self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._wait_for_cdp()
        _write_marker(self.profile_dir, self._proc.pid)

    def _wait_for_cdp(self, timeout: int = 15):
        start = time.time()
        while time.time() - start < timeout:
            try:
                requests.get(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=1)
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("Chromium CDP did not start in time")

    def is_running(self) -> bool:
        try:
            requests.get(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=1)
            return True
        except Exception:
            return False

    def kill(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None
        try:
            STATE_FILE.unlink()
        except Exception:
            pass

    # ── WebSocket connection ─────────────────────────────────────────────────

    def _get_ws_url(self) -> str:
        tabs = requests.get(f"http://{CDP_HOST}:{CDP_PORT}/json").json()
        for t in tabs:
            if t.get("type") == "page":
                return t["webSocketDebuggerUrl"]
        raise RuntimeError("No page tab found in CDP")

    async def connect(self) -> "BrowserSession":
        ws_url = self._get_ws_url()
        ws = await websockets.connect(
            ws_url,
            max_size=WS_MAX_SIZE,
            ping_interval=WS_PING_INTERVAL,
            ping_timeout=WS_PING_TIMEOUT,
        )
        return BrowserSession(ws)


class BrowserSession:
    """Thin async wrapper around a CDP WebSocket connection."""

    def __init__(self, ws):
        self._ws = ws
        self._mid = 0

    async def cdp(self, method: str, params: dict = None, timeout: int = 60) -> dict:
        self._mid += 1
        m = self._mid
        await self._ws.send(json.dumps({"id": m, "method": method, "params": params or {}}))
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            data = json.loads(raw)
            if data.get("id") == m:
                if "error" in data:
                    raise RuntimeError(f"CDP [{method}]: {data['error']}")
                return data.get("result", {})

    async def js(self, code: str, await_promise: bool = False, timeout: int = 60):
        r = await self.cdp("Runtime.evaluate", {
            "expression": code,
            "awaitPromise": await_promise,
            "returnByValue": True,
            "timeout": int((timeout - 2) * 1000),
        }, timeout=timeout)
        return r.get("result", {}).get("value")

    async def navigate(self, url: str, wait: float = 5.0):
        await self.cdp("Page.navigate", {"url": url})
        await asyncio.sleep(wait)

    async def current_url(self) -> str:
        return str(await self.js("window.location.href") or "")

    async def screenshot(self, path: str):
        r = await self.cdp("Page.captureScreenshot", {"format": "png"})
        import base64
        Path(path).write_bytes(base64.b64decode(r["data"]))

    async def close(self):
        await self._ws.close()


async def connect_with_retry(browser: Browser, max_tries: int = 10) -> BrowserSession:
    """Keep trying to connect, useful after Chromium restarts."""
    for attempt in range(max_tries):
        try:
            return await browser.connect()
        except Exception:
            if attempt < max_tries - 1:
                await asyncio.sleep(RECONNECT_WAIT)
    raise RuntimeError("Could not connect to Chromium CDP after multiple attempts")

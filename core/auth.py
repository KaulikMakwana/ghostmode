import asyncio
import json
import time
from pathlib import Path
from rich.console import Console
from config import AUTH_COOLDOWN, AUTH_2FA_TIMEOUT, PASSWORD_FILE

console = Console()
_last_auth_time: float = 0


async def handle_auth(session, password_file: Path = PASSWORD_FILE) -> bool:
    """
    Detect and handle Google auth walls.
    - Password prompt  → fill silently from file, click Next, wait for natural redirect.
    - 2FA / challenge  → pause, notify user, wait up to AUTH_2FA_TIMEOUT seconds.
    Returns True if an auth wall was handled, False if not on an auth page.
    """
    global _last_auth_time

    url = await session.current_url()
    if "accounts.google" not in url and "ServiceLogin" not in url:
        return False

    now = time.time()
    if now - _last_auth_time < AUTH_COOLDOWN:
        await asyncio.sleep(3)
        return True

    _last_auth_time = now

    # Check what kind of auth wall this is
    has_pw = await session.js("!!document.querySelector('input[type=\"password\"]')")
    has_otp = await session.js("""
        !!document.querySelector('input[name="totpPin"], input[name="idvPin"],
        [data-challengetype="6"], [data-challengetype="12"]')
    """)

    if has_pw and not has_otp:
        # Simple password prompt — fill silently
        pw = _read_password(password_file)
        if pw:
            await _fill_password(session, pw)
            await _click_next(session)
            await _wait_for_redirect(session, timeout=30)
            console.print("[dim]  ↳ Password prompt handled automatically[/dim]")
        return True

    # 2FA / phone / OTP — user must act
    console.print()
    console.print("[bold yellow]⚠  Google requires verification[/bold yellow]")
    console.print("[yellow]   Complete it in the Chromium window. GhostMode will resume automatically.[/yellow]")
    await _wait_for_redirect(session, timeout=AUTH_2FA_TIMEOUT)
    console.print("[bold green]✓  Verification complete — resuming[/bold green]")
    return True


def _read_password(path: Path) -> str:
    try:
        return path.read_text().strip()
    except Exception:
        return ""


async def _fill_password(session, password: str):
    escaped = json.dumps(password)
    await session.js(f"""
    (function(p){{
        var i = document.querySelector('input[type="password"]');
        if (!i) return;
        var s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        s.call(i, p);
        i.dispatchEvent(new Event('input', {{bubbles: true}}));
        i.dispatchEvent(new Event('change', {{bubbles: true}}));
    }})({escaped})
    """)
    await asyncio.sleep(0.4)


async def _click_next(session):
    await session.js("""
    (function(){
        var b = Array.from(document.querySelectorAll('button'))
            .find(b => ['next','sign in','continue'].includes(b.innerText.trim().toLowerCase()));
        if (b) b.click();
    })()
    """)


async def _wait_for_redirect(session, timeout: int = 30):
    start = time.time()
    while time.time() - start < timeout:
        url = await session.current_url()
        if "accounts.google" not in url and "ServiceLogin" not in url:
            return
        await asyncio.sleep(1)

"""YouTube Watch/Search history — wipe all history in one operation."""
import asyncio
from core.auth import handle_auth
from services.google.deleters.common import page_is_empty


async def delete_tab_history(session, url: str) -> bool:
    """
    YouTube Watch/Search History — wipe ALL history in one operation.
    Flow: DELETE button → menu "Delete all time" → confirm dialog "Delete".

    The DELETE button opens a time-range MENU (not a dialog). After picking
    "Delete all time", a confirm dialog loads behind a SPINNER for ~1-2s before
    its "Delete" button renders — so we poll for that button up to ~12s rather
    than assuming it is present immediately.
    """
    await session.navigate(url, wait=6.0)
    if await handle_auth(session):
        await session.navigate(url, wait=6.0)

    if await page_is_empty(session):
        return False

    # 1. Open the DELETE time-range menu
    opened = await session.js("""
    (function(){
        const b = Array.from(document.querySelectorAll('button, [role="button"]'))
            .find(b => (b.innerText || '').trim().toUpperCase() === 'DELETE');
        if (b) { b.click(); return true; }
        return false;
    })()
    """)
    if not opened:
        return False
    await asyncio.sleep(1.5)

    # 2. Pick "Delete all time"
    picked = await session.js("""
    (function(){
        const m = Array.from(document.querySelectorAll('[role="menuitem"], li, span, div'))
            .find(x => (x.innerText || '').trim().toLowerCase() === 'delete all time');
        if (m) { m.click(); return true; }
        return false;
    })()
    """)
    if not picked:
        return False

    # 3. Poll up to ~12s for the confirm dialog's "Delete" button (loads after
    #    a spinner), then click it. Must NOT click Cancel/Preview more.
    confirmed = False
    for _ in range(24):
        await asyncio.sleep(0.5)
        clicked = await session.js("""
        (function(){
            const d = document.querySelector('[role="dialog"]');
            if (!d) return 0;
            const btns = Array.from(d.querySelectorAll('button, [role="button"]'))
                .filter(b => ['DELETE','GOT IT','OK','CONFIRM']
                    .includes((b.innerText || '').trim().toUpperCase()));
            if (btns.length) { btns[btns.length - 1].click(); return 1; }
            return 0;
        })()
        """)
        if int(clicked or 0) > 0:
            confirmed = True
            break
    if not confirmed:
        return False

    # 4. Wait for the history items to disappear. After "Delete all time" the
    #    list shows a "Loading…" spinner rather than "No activity", so detect
    #    success by the per-item X buttons dropping to 0 (or an empty page).
    cleared = False
    for _ in range(20):
        await asyncio.sleep(0.5)
        xb = int(await session.js(
            "document.querySelectorAll('button[aria-label^=\"Delete activity item\"]').length"
        ) or 0)
        if xb == 0 or await page_is_empty(session):
            cleared = True
            break

    # Dismiss any result dialog with a Close button.
    await session.js("""
    (function(){
        const d = document.querySelector('[role="dialog"]');
        if (!d) return;
        const c = Array.from(d.querySelectorAll('button, [role="button"]'))
            .find(b => (b.innerText || '').trim().toUpperCase() === 'CLOSE');
        if (c) c.click();
    })()
    """)
    return cleared

"""Handles pages with a single 'Delete All' button."""
import asyncio
from core.auth import handle_auth
from services.google.deleters.common import confirm_dialog, page_is_empty


async def _click_dialog_button(session, targets: list) -> bool:
    """Click a button matching one of `targets` (exact, upper) inside any open dialog."""
    return bool(await session.js("""
    (function(targets){
        const dlgs = Array.from(document.querySelectorAll('[role="dialog"]'));
        for (const d of dlgs) {
            const btns = Array.from(d.querySelectorAll('button, [role="button"]'))
                .filter(b => targets.includes((b.innerText || '').trim().toUpperCase()));
            if (btns.length) { btns[btns.length - 1].click(); return true; }
        }
        return false;
    })(%s)
    """ % __import__("json").dumps([t.upper() for t in targets])))


async def click_delete_all(session, url: str, button_text: str = "Delete All") -> bool:
    """Navigate to page and click a bulk Delete button, then confirm.

    Matches the button by case-insensitive PREFIX (startsWith) so locale spelling
    variants are caught — e.g. button_text "Delete all enrol" matches both
    "Delete all enrolments" (UK) and "Delete all enrollments" (US). Verified live:
    the confirm is a simple [Cancel, Delete] dialog handled by confirm_dialog.
    """
    await session.navigate(url, wait=6.0)
    if await handle_auth(session):
        await session.navigate(url, wait=6.0)

    if await page_is_empty(session):
        return False  # nothing to delete

    result = await session.js("""
    (function(target){
        const btn = Array.from(document.querySelectorAll('button, a[role="button"], [role="button"]'))
            .find(b => (b.innerText || '').trim().toUpperCase().startsWith(target));
        if (btn) { btn.click(); return true; }
        return false;
    })(%r)
    """ % button_text.upper())

    if result:
        await confirm_dialog(session)
    return bool(result)


async def delete_all_time(session) -> bool:
    """
    Delete all activity on the CURRENTLY-LOADED page via the time-range flow:
    Delete button → menu "All time" → "Delete Activity" dialog → "Next" →
    final "Delete Activity" dialog → "Delete".

    Used by BOTH the global nuclear delete (/myactivity) and per-product
    service_delete pages (e.g. /product/workspace, /product/home) — verified live
    to share this exact flow. The menu item is "All time" (NOT "Always"), and it is
    a TWO-step dialog (Next, then Delete). Assumes the page is already navigated +
    authed. Returns True only if the final Delete was clicked.
    """
    if await page_is_empty(session):
        return False  # nothing to delete

    # 1. Open the Delete time-range menu
    await session.js("""
    (function(){
        const b = Array.from(document.querySelectorAll('button, [role="button"]'))
            .find(b => (b.innerText || '').trim().toUpperCase() === 'DELETE');
        if (b) b.click();
    })()
    """)
    await asyncio.sleep(1.5)

    # 2. Pick "All time" (fallback "Always" for older UI)
    picked = await session.js("""
    (function(){
        const m = Array.from(document.querySelectorAll('[role="menuitem"], li, span, div'))
            .find(x => {
                const t = (x.innerText || '').trim().toLowerCase();
                return t === 'all time' || t === 'always';
            });
        if (m) { m.click(); return true; }
        return false;
    })()
    """)
    if not picked:
        return False
    await asyncio.sleep(2.5)

    # 3. Step 1 dialog "Delete Activity" → Next (poll up to ~8s; some pages skip it)
    for _ in range(16):
        await asyncio.sleep(0.5)
        if await _click_dialog_button(session, ["NEXT"]):
            break

    # 4. Step 2 dialog "Delete Activity" → Delete (poll up to ~10s; the button
    #    renders behind a brief spinner). NOTE: the final affirmative Delete sits
    #    alongside "Preview more"/"Cancel" — _click_dialog_button matches "DELETE"
    #    only, so it can't hit those.
    confirmed = False
    for _ in range(20):
        await asyncio.sleep(0.5)
        if await _click_dialog_button(session, ["DELETE"]):
            confirmed = True
            break

    await asyncio.sleep(3)
    return confirmed


async def nuclear_delete(session) -> bool:
    """Wipe ALL Google activity via the main /myactivity page."""
    await session.navigate("https://myactivity.google.com/myactivity", wait=6.0)
    if await handle_auth(session):
        await session.navigate("https://myactivity.google.com/myactivity", wait=6.0)
    return await delete_all_time(session)

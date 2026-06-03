"""Handles pages with per-item X buttons (infinite scroll or Load More)."""
import asyncio
from config import CLICK_DELAY, BATCH_SETTLE, SCROLL_STEPS, SCROLL_STEP_PX, LOAD_MORE_WAIT
from core.auth import handle_auth
from services.google.deleters.common import page_is_empty

# Some per-item pages (e.g. YouTube Liked Videos) pop a confirmation dialog
# whose "Delete" button is a <div role="button"> — NOT a <button>. We must
# match both and, if a dialog is open, wait for it to close before continuing
# (it's modal and blocks further clicks).
_SWEEP_JS = """
(async function() {
    const DELAY = %d;

    // Clear any leftover modal from a previous interrupted run before starting.
    const stuck = document.querySelector('[role="dialog"]');
    if (stuck) {
        const c = Array.from(stuck.querySelectorAll('button, [role="button"]'))
            .filter(b => ['DELETE','OK','REMOVE','YES','CONFIRM']
                .includes((b.innerText || '').trim().toUpperCase()));
        if (c.length) c[c.length - 1].click();
        await new Promise(r => setTimeout(r, 600));
    }

    const confirmDialog = () => {
        const dlg = document.querySelector('[role="dialog"]');
        if (!dlg) return false;
        const cands = Array.from(dlg.querySelectorAll('button, [role="button"]'))
            .filter(b => ['DELETE','OK','REMOVE','YES','CONFIRM']
                .includes((b.innerText || '').trim().toUpperCase()));
        if (cands.length) { cands[cands.length - 1].click(); return true; }
        return false;
    };
    const waitClose = async () => {
        for (let i = 0; i < 12; i++) {
            await new Promise(r => setTimeout(r, 200));
            if (!document.querySelector('[role="dialog"]')) return;
        }
    };

    const btns = Array.from(document.querySelectorAll('button[aria-label^="Delete activity item"]'));
    if (!btns.length) return 0;

    // Most pages delete instantly; some (e.g. Liked Videos) show a confirm dialog
    // on the FIRST delete only ("won't show again"). Poll longer until we know
    // which kind this is, then use the fast path.
    let pollForDialog = true;
    let n = 0;
    for (const btn of btns) {
        btn.click();
        if (pollForDialog) {
            let handled = false;
            for (let i = 0; i < 7; i++) {            // poll up to ~1.4s
                await new Promise(r => setTimeout(r, 200));
                if (document.querySelector('[role="dialog"]')) {
                    confirmDialog();
                    await waitClose();
                    handled = true;
                    break;
                }
            }
            if (!handled) pollForDialog = false;     // instant-delete page
        } else {
            await new Promise(r => setTimeout(r, DELAY));
            if (document.querySelector('[role="dialog"]')) { confirmDialog(); await waitClose(); }
        }
        n++;
    }
    await new Promise(r => setTimeout(r, 400));
    return n;
})()
""" % int(CLICK_DELAY * 1000)


async def delete_per_item(session, url: str, use_load_more: bool = False,
                          progress_task=None, progress=None) -> int:
    """Delete all items on a per-item X page. Returns total deleted."""
    await session.navigate(url, wait=6.0)
    total = 0
    no_growth_rounds = 0

    while True:
        if await handle_auth(session):
            no_growth_rounds = 0
            continue

        count = int(await session.js(
            "document.querySelectorAll('button[aria-label^=\"Delete activity item\"]').length"
        ) or 0)

        if count > 0:
            no_growth_rounds = 0
            deleted = int(await session.js(_SWEEP_JS, await_promise=True, timeout=300) or 0)
            total += deleted
            if progress and progress_task is not None:
                progress.advance(progress_task, deleted)
            continue  # re-check immediately for more items

        # No delete buttons visible — are we genuinely done?
        if await page_is_empty(session):
            break  # "No activity" / "No results" / reached the end

        # Try to load more (Load More button or infinite scroll)
        if use_load_more and await _click_load_more(session):
            await asyncio.sleep(LOAD_MORE_WAIT)
            no_growth_rounds = 0
            continue

        grew = await _scroll_grew(session)
        if grew:
            no_growth_rounds = 0
        else:
            # Nothing new loaded and no buttons — we've hit the end.
            no_growth_rounds += 1
            if no_growth_rounds >= 2:
                break

    return total


async def _click_load_more(session) -> bool:
    result = await session.js("""
    (function(){
        const btn = Array.from(document.querySelectorAll('button'))
            .find(b => b.innerText.trim().toLowerCase() === 'load more');
        if (btn) { btn.click(); return true; }
        return false;
    })()
    """)
    return bool(result)


async def _scroll_grew(session) -> bool:
    """Scroll down; return True if the page grew (more content loaded)."""
    old_h = int(await session.js("document.body.scrollHeight") or 0)
    for _ in range(SCROLL_STEPS):
        await session.js(f"window.scrollBy(0, {SCROLL_STEP_PX})")
        await asyncio.sleep(0.5)
    await asyncio.sleep(1.5)
    new_h = int(await session.js("document.body.scrollHeight") or 0)
    return new_h > old_h

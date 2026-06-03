"""Shared deleter helpers — confirm-dialog handling and empty-page detection."""
import asyncio

# The confirm button inside Google's delete dialog is a <div role="button">,
# NOT a <button>. Match both, and click the LAST matching action (Cancel comes
# first, Delete/confirm comes after).
# CRITICAL: Google keeps STALE hidden [role="dialog"] elements in the DOM, so a
# plain querySelector('[role="dialog"]') can land on an invisible one with no
# Delete button. Scope to the VISIBLE dialog(s) first (offsetParent !== null).
CONFIRM_DIALOG_JS = """
(function(){
    const all = Array.from(document.querySelectorAll('[role="dialog"], tp-yt-paper-dialog'));
    const visible = all.filter(d => d.offsetParent !== null);
    const pool = visible.length ? visible : all;
    for (const dlg of pool) {
        const btns = Array.from(dlg.querySelectorAll('button, [role="button"]'))
            .filter(b => ['DELETE','OK','REMOVE','YES','CONFIRM','DELETE ALL']
                .includes((b.innerText || '').trim().toUpperCase()));
        if (btns.length) { btns[btns.length - 1].click(); return 1; }
    }
    return 0;
})()
"""

# Text patterns that indicate a service page is empty (no data to delete).
# NB: do NOT add "Looks like you" — the real string "Looks like you've reached the
# end" is the END-OF-LIST marker on a fully-loaded page WITH data, so it would
# false-flag populated pages as empty and make every bulk deleter skip them.
EMPTY_TEXTS = [
    "No activity",
    "No history",
    "No results",
    "no activity to delete",
    "You have no activity",
]

EMPTY_CHECK_JS = "(function(){{ const t = document.body.innerText; return {expr}; }})()".format(
    expr=" || ".join(f"t.includes({p!r})" for p in EMPTY_TEXTS)
)


async def confirm_dialog(session, tries: int = 3, wait: float = 0.6) -> bool:
    """Wait for the confirm dialog and click its confirm action. Returns True if clicked."""
    for _ in range(tries):
        await asyncio.sleep(wait)
        clicked = await session.js(CONFIRM_DIALOG_JS)
        if int(clicked or 0) > 0:
            await asyncio.sleep(wait)
            return True
    return False


async def page_is_empty(session) -> bool:
    return bool(await session.js(EMPTY_CHECK_JS))

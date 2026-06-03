"""
Instagram "Your Activity" bulk deleter — the per_item analog for IG.

Flow (verified working community pattern, Jan 2026):
  enter Select mode -> tick a small batch of checkboxes -> click the action
  (Delete / Unlike) -> confirm in the popup -> dismiss any rate-limit modal -> wait
  -> repeat until no checkboxes remain.

IG is a React app with obfuscated class names, so EVERYTHING is matched by visible
TEXT / aria-label, and every confirm is scoped to the VISIBLE dialog (IG, like
Google, keeps stale hidden dialogs around). Pacing is deliberately slow and the run
HARD-STOPS on repeated rate-limit modals — the account must survive.
"""
import asyncio
from core.tui import print_event
from config import (IG_BATCH_SIZE, IG_TICK_DELAY, IG_ACTION_DELAY,
                    IG_POST_DELETE_WAIT, IG_SELECT_RETRIES, IG_RELOAD_RETRIES,
                    IG_RELOAD_WAIT, IG_SETTLE_POLLS, IG_SETTLE_WAIT,
                    IG_RATELIMIT_BACKOFF, IG_RATELIMIT_MAX_HITS, IG_MAX_ACTIONS)

_CB = '[aria-label="Toggle checkbox"]'

# Read-only page-state classifier for the dashboard scan. Returns one of:
#   'data'    — a populated list: the 'Select' control / 'Sort & filter' / 'Newest to
#               oldest' controls render ONLY when there is content (verified live on
#               Likes). This is the authoritative has-data signal.
#   'empty'   — IG's empty-state copy (verified live 2026-06-03 on cleared Comments &
#               Story Replies): "…it'll show up here" + "You haven't <verb>…". A cleared
#               page STILL carries 1 image (the empty-state illustration), so the old
#               `imgs > 0` test was a false-positive — never trust the image count.
#   'pending' — neither yet (React still cold-loading); caller keeps polling.
_PAGE_STATE_JS = """
(function(){
    const main = document.querySelector('main,[role="main"]') || document.body;
    const txt = (main.innerText || '').toLowerCase();
    const hasSelect = Array.from(document.querySelectorAll('span,div,button,[role="button"]'))
        .some(e => (e.innerText || '').trim() === 'Select' && e.offsetParent !== null);
    const hasSort = txt.includes('sort & filter') || txt.includes('newest to oldest');
    if (hasSelect || hasSort) return 'data';
    // Empty-state copy. Apostrophe-agnostic ("show up here" has none) + a "you haven…"
    // backstop covering every category's wording (commented/responded/liked/shared/…).
    const empty = txt.includes('show up here')
        || /you haven[’']?t /.test(txt)
        || txt.includes('no activity') || txt.includes('no results');
    if (empty) return 'empty';
    return 'pending';
})()
"""


async def _checkbox_count(session) -> int:
    return int(await session.js(f"document.querySelectorAll('{_CB}').length") or 0)


async def _unselected_count(session) -> int:
    """Visible tiles NOT yet selected (icon still circle__outline). This is what the
    engine can still act on — distinct from total checkboxes."""
    return int(await session.js(f"""
    (function(){{
        return Array.from(document.querySelectorAll('{_CB}'))
            .filter(b => {{
                if (b.offsetParent === null) return false;
                const ic = b.querySelector('[data-bloks-name="ig.components.Icon"]');
                return !(ic && /circle-check/.test(ic.getAttribute('style') || ''));
            }}).length;
    }})()
    """) or 0)


async def _wait_for_items(session, url: str) -> bool:
    """Patiently wait for actionable items to render, then confirm done only when the
    page is genuinely empty.

    IG paginates the Likes/Comments list and loads the NEXT page only after the
    current one is deleted — and that reload can lag many seconds. The old loop gave
    up after two short waits and falsely reported 'Done'. This polls, and if IG is
    stuck, HARD-REFRESHES the page (mirroring the manual fix) before concluding.
    Returns True if there are unselected items to act on, False if truly empty."""
    for _ in range(IG_RELOAD_RETRIES):
        # A stray "Something went wrong" modal can pop HERE, not just post-confirm.
        # Undismissed it overlays the list, IG never re-renders, and we'd falsely
        # conclude the page is empty (verified: dismissing it brought 172 items back).
        await _clear_blocking_modal(session)
        await _enter_select_mode(session)
        if await _unselected_count(session) > 0:
            return await _settle_items(session)
        await asyncio.sleep(IG_RELOAD_WAIT)
    # Stuck — refresh and give it one full, patient reload before declaring done.
    print_event("[dim]Next batch slow to load — refreshing the page…[/dim]")
    await session.navigate(url, wait=6.0)
    await _clear_blocking_modal(session)
    await _enter_select_mode(session)
    if await _unselected_count(session) > 0:
        return await _settle_items(session)
    return False


async def _clear_blocking_modal(session) -> str | None:
    """Dismiss an OK-only error/rate-limit modal that is blocking the page outside the
    post-confirm window. It can surface during the next-batch wait and freeze the list
    on a perpetual spinner (the 5-minute hang). Real-click OK, let the list re-render.
    Returns the kind cleared ('transient'/'ratelimit'), or None if nothing was blocking."""
    kind = await _error_modal(session)
    if kind:
        await _dismiss_modal(session)
        await asyncio.sleep(IG_ACTION_DELAY)
    return kind


async def _settle_items(session) -> bool:
    """Wait for IG's lazy tile stream to finish before ticking. The page renders its
    ~27 tiles over several seconds; ticking at the first tile produced single-item
    batches (the +1,+1,+1 dribble after every delete / error-modal recovery). Poll the
    unselected count until it stops growing, so a whole settled page is ticked at once.
    Always returns True (caller already confirmed there is at least one item)."""
    prev = await _unselected_count(session)
    for _ in range(IG_SETTLE_POLLS):
        await asyncio.sleep(IG_SETTLE_WAIT)
        cur = await _unselected_count(session)
        if cur <= prev:        # stream has plateaued — render is done
            break
        prev = cur
    return True


async def page_has_activity(session, tries: int = 8, delay: float = 1.5) -> bool:
    """Read-only: does this Your Activity page have items to act on?

    Passive — never clicks. The page is a React app that renders content several
    seconds after navigation (the cold-load race that produced a false 'clean' on a
    populated Likes page), so this POLLS the page-state classifier rather than reading
    once: returns True the instant a populated list is seen, False the instant the
    empty-state copy is seen. Used by the dashboard scan, NOT the delete engine.

    If the budget runs out with neither (a hung/slow load), bias to True — re-running
    delete on an empty page is harmless, a false 'clean' that skips real data is not."""
    for _ in range(tries):
        state = await session.js(_PAGE_STATE_JS)
        if state == "data":
            return True
        if state == "empty":
            return False
        await asyncio.sleep(delay)
    return True


async def _enter_select_mode(session) -> bool:
    """Ensure the page is in batch-select mode (checkboxes visible). Click the
    'Select' control if needed. Returns True once checkboxes are present."""
    if await _checkbox_count(session) > 0:
        return True
    for _ in range(IG_SELECT_RETRIES):
        await session.js("""
        (function(){
            const el = Array.from(document.querySelectorAll('span,div,button,[role="button"]'))
                .find(e => (e.innerText || '').trim() === 'Select' && e.offsetParent !== null);
            if (el) { (el.closest('[role="button"],button') || el).click(); }
        })()
        """)
        await asyncio.sleep(0.9)
        if await _checkbox_count(session) > 0:
            return True
    return False


async def _real_click(session, x: int, y: int):
    """Dispatch a REAL CDP mouse click. IG's bloks action/confirm buttons are
    pointer-events:none and ignore synthetic .click() (same lesson as YouTube's
    Polymer confirm buttons — see services/google/deleters/subscriptions.py)."""
    await session.cdp("Input.dispatchMouseEvent",
                      {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await session.cdp("Input.dispatchMouseEvent",
                      {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


async def _selected_count(session) -> int:
    """Read IG's '<N> selected' action-bar label. -1 if not present (not in select
    mode / nothing selected yet). This is the authoritative selection counter — used
    to VERIFY ticks landed rather than trusting the clicks."""
    n = await session.js(r"""
    (function(){
        const e = Array.from(document.querySelectorAll('span,div'))
            .map(x => (x.innerText || '').trim())
            .find(t => /^\d+ selected$/.test(t));
        return e ? parseInt(e, 10) : -1;
    })()
    """)
    return int(n if n is not None else -1)


async def _tick_batch(session, n: int) -> int:
    """Select up to n currently-unselected tiles, staggered. There is NO aria-checked
    on IG's tiles — selection state lives in the checkbox icon's mask-image
    (circle__outline -> circle-check), so we skip already-selected tiles by that
    signal and always advance to the next unselected one (the old code re-clicked
    boxes[0] forever, toggling a single tile on/off). Returns the count actually
    selected, verified against the 'N selected' counter."""
    before = await _selected_count(session)
    base = before if before >= 0 else 0
    for _ in range(n):
        did = await session.js(f"""
        (function(){{
            const boxes = Array.from(document.querySelectorAll('{_CB}'))
                .filter(b => b.offsetParent !== null);
            for (const b of boxes) {{
                const ic = b.querySelector('[data-bloks-name="ig.components.Icon"]');
                const sel = ic && /circle-check/.test(ic.getAttribute('style') || '');
                if (!sel) {{ b.click(); return true; }}   // synthetic click selects fine
            }}
            return false;   // every visible tile already selected
        }})()
        """)
        if not did:
            break
        await asyncio.sleep(IG_TICK_DELAY)
    after = await _selected_count(session)
    return max(0, after - base) if after >= 0 else 0


async def _click_action(session, action: str) -> bool:
    """Click the bottom action button ('Unlike'/'Delete') with a REAL CDP click."""
    coords = await session.js("""
    (function(label){
        const el = Array.from(document.querySelectorAll('span,div,button,[role="button"]'))
            .find(e => (e.innerText || '').trim() === label && e.offsetParent !== null);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
    })(%r)
    """ % action)
    if not coords:
        return False
    await _real_click(session, coords["x"], coords["y"])
    return True


async def _confirm_action(session, action: str) -> bool:
    """Confirm in the popup with a REAL CDP click. Scoped to the VISIBLE dialog (IG
    keeps stale hidden dialogs). The affirmative button text is the action label or a
    generic confirm; 'Cancel'/'Go back' are explicitly avoided."""
    coords = await session.js("""
    (function(label){
        const dlgs = Array.from(document.querySelectorAll('[role="dialog"]'))
            .filter(d => d.offsetParent !== null);
        const ok = [label.toUpperCase(), 'DELETE', 'CONFIRM', 'REMOVE', 'UNLIKE'];
        const no = ['CANCEL', 'GO BACK', 'NOT NOW', 'DISMISS'];
        for (const d of dlgs) {
            const btn = Array.from(d.querySelectorAll('button, [role="button"]'))
                .find(b => {
                    const t = (b.innerText || '').trim().toUpperCase();
                    return ok.includes(t) && !no.includes(t);
                });
            if (btn) {
                const r = btn.getBoundingClientRect();
                return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
            }
        }
        return null;
    })(%r)
    """ % action)
    if not coords:
        return False
    await _real_click(session, coords["x"], coords["y"])
    return True


async def _error_modal(session) -> str | None:
    """Classify a blocking OK-only modal that IG throws after a confirm.
      'transient' -> "Something went wrong / problem deleting … try deleting it again":
                     a mid-bulk hiccup. Dismiss and retry — NOT a real throttle. Left
                     undismissed it overlays the page and jams the run (the stall, and
                     the cause of the +1 dribble once selection is wiped).
      'ratelimit' -> "try again later / limit / please wait": a genuine throttle. Back
                     off, hard-stop on repeats.
      None        -> no blocking modal (the normal confirm dialog has no OK button)."""
    return await session.js("""
    (function(){
        const dlgs = Array.from(document.querySelectorAll('[role="dialog"]'))
            .filter(d => d.offsetParent !== null);
        for (const d of dlgs) {
            const t = (d.innerText || '').toLowerCase();
            const hasOK = Array.from(d.querySelectorAll('button, [role="button"]'))
                .some(b => (b.innerText || '').trim().toUpperCase() === 'OK');
            if (!hasOK) continue;
            if (t.includes('something went wrong') || t.includes('problem deleting') ||
                t.includes('try deleting it again')) return 'transient';
            if (t.includes('try again later') || t.includes('try again in') ||
                t.includes('limit') || t.includes('please wait')) return 'ratelimit';
        }
        return null;
    })()
    """)


async def _dismiss_modal(session) -> bool:
    """Click a modal's OK with a REAL CDP click. Synthetic .click() is ignored on
    bloks buttons (pointer-events:none) — same lesson as the action/confirm buttons.
    Returns True if an OK button was found and clicked."""
    coords = await session.js("""
    (function(){
        const dlgs = Array.from(document.querySelectorAll('[role="dialog"]'))
            .filter(d => d.offsetParent !== null);
        for (const d of dlgs) {
            const ok = Array.from(d.querySelectorAll('button, [role="button"]'))
                .find(b => (b.innerText || '').trim().toUpperCase() === 'OK');
            if (ok) {
                const r = ok.getBoundingClientRect();
                return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
            }
        }
        return null;
    })()
    """)
    if not coords:
        return False
    await _real_click(session, coords["x"], coords["y"])
    return True


async def bulk_delete_activity(session, url: str, action: str = "Delete") -> int:
    """Delete/unlike everything on a Your Activity page. Returns count actioned.
    Hard-stops (and tells Sensei) on repeated rate-limit modals rather than risking
    an action-block."""
    await session.navigate(url, wait=6.0)

    total = 0
    rl_hits = 0

    while total < IG_MAX_ACTIONS:
        # Patiently wait for the next page of items (IG loads it after each delete and
        # can lag); refresh if stuck. False == genuinely empty -> done.
        if not await _wait_for_items(session, url):
            break

        ticked = await _tick_batch(session, IG_BATCH_SIZE)
        if ticked == 0:
            # Selected tiles exist but none newly ticked — let IG settle, then retry.
            if not await _wait_for_items(session, url):
                break
            continue

        await asyncio.sleep(IG_ACTION_DELAY)
        if not await _click_action(session, action):
            print_event(f"[yellow]Action button '{action}' not found — stopping.[/yellow]")
            break

        # Wait for the confirm dialog ("Unlike this post?" / "Delete?") to render,
        # then confirm with a real click. Verify it closes — never trust the click.
        for _ in range(6):
            await asyncio.sleep(IG_ACTION_DELAY)
            if await _confirm_action(session, action):
                break
        else:
            print_event("[yellow]Confirm dialog never appeared — stopping.[/yellow]")
            break
        await asyncio.sleep(IG_ACTION_DELAY)

        # Post-confirm modal handling.
        kind = await _error_modal(session)
        if kind == "transient":
            # "Something went wrong" — IG's intermittent bulk hiccup. Dismiss with a
            # real click and retry the page; if left undismissed it overlays the tiles
            # and every later tick lands on the overlay (the stall + single-tile dribble).
            await _dismiss_modal(session)
            total += ticked
            print_event(f"[dim]Instagram hiccup ('something went wrong') — dismissed, "
                        f"continuing ({total} so far)[/dim]")
            await asyncio.sleep(IG_ACTION_DELAY)
            continue

        # Rate-limit guard — back off, and HARD STOP if it keeps happening.
        if kind == "ratelimit":
            await _dismiss_modal(session)
            rl_hits += 1
            print_event(f"[yellow]Instagram rate-limit modal ({rl_hits}/{IG_RATELIMIT_MAX_HITS}) "
                        f"— backing off {IG_RATELIMIT_BACKOFF:.0f}s[/yellow]")
            if rl_hits >= IG_RATELIMIT_MAX_HITS:
                print_event("[red]Repeated rate-limits — stopping to protect the account.[/red]")
                break
            await asyncio.sleep(IG_RATELIMIT_BACKOFF)
            continue

        total += ticked
        print_event(f"[green]…{action.lower()}d {total} so far[/green]")
        await asyncio.sleep(IG_POST_DELETE_WAIT)

    return total

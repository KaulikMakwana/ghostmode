"""
YouTube subscriptions — list channels and unsubscribe selected ones.

Subscriptions are NOT My Activity items (there are no "Delete activity item" X
buttons on the My Activity subscriptions page). They are managed on YouTube itself
at /feed/channels, where each channel has a "Subscribed" button that opens an
"Unsubscribe" confirmation. The same logged-in profile works there.

YouTube markup is volatile, so every selector below falls back to matching button
TEXT ("Subscribed" / "Unsubscribe"), and every unsubscribe is verified by re-reading
the channel's button state — never trust the click.
"""
import asyncio
from config import SCROLL_STEPS, SCROLL_STEP_PX
from core.auth import handle_auth

CHANNELS_URL = "https://www.youtube.com/feed/channels"

# Scrape one entry per channel row. href pathname (/@handle or /channel/UC...) is
# the stable unique key; names can collide.
_LIST_JS = """
(function(){
    const rows = Array.from(document.querySelectorAll('ytd-channel-renderer'));
    const out = [];
    for (const r of rows) {
        const a = r.querySelector('a#main-link, a.channel-link, a[href^="/@"], a[href*="/channel/"], a[href]');
        if (!a) continue;
        let path;
        try { path = new URL(a.href, location.origin).pathname; } catch (e) { continue; }
        const nameEl = r.querySelector('#channel-title #text, #channel-title, ytd-channel-name #text, yt-formatted-string#text');
        const name = nameEl ? (nameEl.innerText || nameEl.textContent || '').trim() : path;
        out.push({ href: path, name: name || path });
    }
    return out;
})()
"""

# Click the "Subscribed" button of the channel whose link pathname == path.
_CLICK_SUBSCRIBED_JS = """
(function(path){
    const rows = Array.from(document.querySelectorAll('ytd-channel-renderer'));
    const r = rows.find(r => {
        const a = r.querySelector('a[href]');
        if (!a) return false;
        try { return new URL(a.href, location.origin).pathname === path; } catch (e) { return false; }
    });
    if (!r) return 'not_found';
    r.scrollIntoView({block: 'center'});
    let btn = r.querySelector('ytd-subscribe-button-renderer button, ytd-subscribe-button-renderer tp-yt-paper-button');
    if (!btn) {
        btn = Array.from(r.querySelectorAll('button, [role="button"]')).find(b => {
            const t = (b.innerText || '').trim().toLowerCase();
            const a = (b.getAttribute('aria-label') || '').toLowerCase();
            return t === 'subscribed' || a.startsWith('unsubscribe') || a.includes('subscribed');
        });
    }
    if (!btn) return 'no_btn';
    btn.click();
    return 'clicked';
})(%r)
"""

# Return the viewport-center {x,y} of the affirmative button in the VISIBLE confirm
# dialog, or null. Two traps handled here:
#   1. YouTube keeps STALE hidden dialog elements in the DOM — we filter to the
#      visible one (offsetParent !== null).
#   2. The Polymer confirm button IGNORES a synthetic .click() — so we don't click in
#      JS at all. We return coordinates and dispatch a REAL mouse event over CDP
#      (Input.dispatchMouseEvent). The live affirmative button reads "Unsubscribe".
#      We prefer the inner <button> over its yt-button-renderer wrapper.
_UNSUB_BTN_COORDS_JS = """
(function(){
    const dlgs = Array.from(document.querySelectorAll(
        'yt-confirm-dialog-renderer, tp-yt-paper-dialog, ytd-popup-container [role="dialog"], [role="dialog"]'));
    const dlg = dlgs.find(d => d.offsetParent !== null);
    if (!dlg) return null;
    const cands = Array.from(dlg.querySelectorAll('button, a, tp-yt-paper-button, [role="button"]'))
        .filter(e => {
            const t = (e.innerText || '').trim().toLowerCase();
            return t === 'unsubscribe' || t === 'confirm';
        });
    if (!cands.length) return null;
    const el = cands.find(e => e.tagName.toLowerCase() === 'button') || cands[0];
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return null;
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
})()
"""

# Verify one channel's state. Distinguishes a transitional empty read ('pending')
# from a real flip so we don't report a false unsubscribe mid-re-render.
_VERIFY_JS = """
(function(path){
    const rows = Array.from(document.querySelectorAll('ytd-channel-renderer'));
    const r = rows.find(r => {
        const a = r.querySelector('a[href]');
        if (!a) return false;
        try { return new URL(a.href, location.origin).pathname === path; } catch (e) { return false; }
    });
    if (!r) return 'gone';                       // removed from list = unsubscribed
    const btn = r.querySelector('ytd-subscribe-button-renderer button, ytd-subscribe-button-renderer tp-yt-paper-button')
        || r.querySelector('button, [role="button"]');
    const t = btn ? (btn.innerText || '').trim().toLowerCase() : '';
    if (t.includes('subscribed')) return 'still_subscribed';
    if (t === 'subscribe') return 'unsubscribed';
    return 'pending';                            // empty/transition — caller re-polls
})(%r)
"""


async def _renderer_count(session) -> int:
    return int(await session.js(
        "document.querySelectorAll('ytd-channel-renderer').length") or 0)


async def list_subscriptions(session) -> list[dict]:
    """Return [{name, href}] for every subscribed channel. Read-only."""
    await session.navigate(CHANNELS_URL, wait=6.0)
    if await handle_auth(session):
        await session.navigate(CHANNELS_URL, wait=6.0)

    # Cold-load guard: a freshly launched browser can take >6s to render the channel
    # rows. Poll until at least one renderer appears (or the page is genuinely empty)
    # before deciding the list is empty — otherwise we'd break the scroll loop at 0.
    for _ in range(15):
        if await _renderer_count(session) > 0:
            break
        if await session.js(
            "/no subscriptions|haven.t subscribed|don.t have any subscriptions/i"
            ".test(document.body.innerText)"
        ):
            return []
        await asyncio.sleep(1.0)

    # Scroll until the channel count stops growing (lazy-loaded list).
    prev = -1
    stale = 0
    for _ in range(60):  # hard cap
        n = len(await session.js(_LIST_JS) or [])
        if n == prev:
            stale += 1
            if stale >= 2:
                break
        else:
            stale = 0
        prev = n
        for _ in range(SCROLL_STEPS):
            await session.js(f"window.scrollBy(0, {SCROLL_STEP_PX})")
            await asyncio.sleep(0.4)
        await asyncio.sleep(1.2)

    # De-dupe by href, preserve order.
    seen, channels = set(), []
    for c in (await session.js(_LIST_JS) or []):
        h = c.get("href")
        if h and h not in seen:
            seen.add(h)
            channels.append(c)
    return channels


async def unsubscribe_selected(session, hrefs: list[str]) -> int:
    """Unsubscribe the given channels (by href). Returns count actually unsubscribed."""
    if not hrefs:
        return 0
    await session.navigate(CHANNELS_URL, wait=6.0)
    if await handle_auth(session):
        await session.navigate(CHANNELS_URL, wait=6.0)
    # Make sure every target is loaded into the DOM before we start.
    await list_subscriptions(session)

    done = 0
    for href in hrefs:
        clicked = await session.js(_CLICK_SUBSCRIBED_JS % href)
        if clicked != "clicked":
            continue

        # Poll for the VISIBLE confirm dialog and grab the affirmative button coords.
        coords = None
        for _ in range(12):  # up to ~4.8s
            await asyncio.sleep(0.4)
            coords = await session.js(_UNSUB_BTN_COORDS_JS)
            if coords:
                break
        if not coords:
            await session.js("document.dispatchEvent(new KeyboardEvent("
                             "'keydown',{key:'Escape',keyCode:27,bubbles:true}))")
            continue

        # Dispatch a REAL mouse click — YouTube's Polymer button ignores .click().
        for ev in ("mousePressed", "mouseReleased"):
            await session.cdp("Input.dispatchMouseEvent", {
                "type": ev, "x": coords["x"], "y": coords["y"],
                "button": "left", "clickCount": 1,
            })

        # Verify — poll through the re-render transition; don't trust the click.
        for _ in range(8):  # up to ~4s
            await asyncio.sleep(0.5)
            state = await session.js(_VERIFY_JS % href)
            if state in ("gone", "unsubscribed"):
                done += 1
                break
            if state == "still_subscribed":
                break  # confirm didn't take
    return done

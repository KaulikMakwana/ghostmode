"""Turns off activity tracking toggles across Google services."""
import asyncio
import json
from core.auth import handle_auth

_json = json.dumps
BASE = "https://myactivity.google.com"

TOGGLE_CONTROLS = [
    # These three share the /activitycontrols page (multiple cards), so each must
    # be targeted by the aria-label substring of ITS OWN button, not page-wide.
    {
        "name": "Web & App Activity",
        "url": f"{BASE}/activitycontrols",
        "type": "turn_off_button",
        "match": "Web & App Activity",
    },
    {
        "name": "YouTube History",
        "url": f"{BASE}/product/youtube/controls",
        "type": "turn_off_button",
    },
    {
        "name": "Timeline",
        "url": f"{BASE}/activitycontrols",
        "type": "turn_off_button",
        "match": "Timeline",
    },
    {
        "name": "Play Personalisation",
        "url": f"{BASE}/activitycontrols",
        "type": "turn_off_button",
        "match": "Play",
    },
    {
        "name": "Gemini",
        "url": f"{BASE}/product/gemini",
        "type": "turn_off_button",
        "button_texts": ["Turn off", "TURN OFF"],
    },
    {
        "name": "Google Home",
        "url": f"{BASE}/product/home",
        "type": "turn_off_button",
        "button_texts": ["Turn off", "TURN OFF"],
    },
    {
        "name": "Google Photos",
        "url": f"{BASE}/product/photos",
        "type": "turn_off_button",
        "button_texts": ["Turn off", "TURN OFF"],
    },
    {
        "name": "Google Wallet — Pass Usage",
        "url": f"{BASE}/product/wallet",
        "type": "aria_switch",
        "aria_label": "On",  # toggle with aria-checked="true"
    },
    {
        "name": "Play Content Personalisation",
        "url": f"{BASE}/product/google_play/personalization_options/",
        "type": "aria_switch",
        "aria_label": None,  # find any checked switch
    },
]


async def turn_off_toggle(session, control: dict) -> str:
    """Turn off one tracking control. Returns 'turned_off' | 'already_off' | 'not_found'."""
    await session.navigate(control["url"], wait=6.0)
    if await handle_auth(session):
        await session.navigate(control["url"], wait=6.0)

    ctype = control.get("type")

    if ctype == "turn_off_button":
        # Turn off ONLY if currently ON. Two UI styles:
        #   A) explicit "Turn off"/"Pause" button (activity-controls pages)
        #   B) an "On" DROPDOWN button (Gemini, Google Home) that opens a menu
        #      with "Turn off" (1 step) / "Turn off and delete activity" (2 steps),
        #      followed by a confirm dialog whose button is "Got it".
        trigger = await session.js("""
        (function(m){
            let btns = Array.from(document.querySelectorAll('button'));
            // On multi-control pages, restrict to THIS control's button by aria-label.
            if (m) btns = btns.filter(b => (b.getAttribute('aria-label') || '').includes(m));
            // A) direct turn-off / pause button (by text OR aria-label)
            let direct = btns.find(b => {
                const t = (b.innerText || '').trim().toUpperCase();
                const a = (b.getAttribute('aria-label') || '').toUpperCase();
                return t.startsWith('TURN OFF') || t.startsWith('PAUSE') ||
                       a.startsWith('TURN OFF') || a.startsWith('PAUSE');
            });
            if (direct) { direct.click(); return 'direct'; }
            // B) "On" dropdown — click only when its text actually reads "On"
            let on = btns.find(b => (b.innerText || '').trim().toUpperCase() === 'ON');
            if (on) { on.click(); return 'menu'; }
            return 'none';
        })(%s)
        """ % _json(control.get("match")))
        if trigger == "none":
            return "already_off"  # only "Turn on" / "Off" present → already off

        await asyncio.sleep(1.5)

        # If a dropdown menu opened, pick "Turn off" (1 step — NOT the delete variant)
        if trigger == "menu":
            await session.js("""
            (function(){
                const items = Array.from(document.querySelectorAll(
                    '[role="menuitem"],[role="menuitemradio"],[role="option"],li'));
                const m = items.find(x => {
                    const t = (x.innerText || '').trim().toUpperCase();
                    return t.startsWith('TURN OFF') && !t.includes('DELETE');
                });
                if (m) m.click();
            })()
            """)
            await asyncio.sleep(2)

        # Confirm dialog (button text is usually "Got it"; also handle Turn off/Pause/OK)
        await session.js("""
        (function(){
            const scope = document.querySelector('[role="dialog"]') || document;
            const btns = Array.from(scope.querySelectorAll('button, [role="button"]'))
                .filter(b => ['GOT IT','TURN OFF','PAUSE','OK','CONFIRM']
                    .includes((b.innerText || '').trim().toUpperCase()));
            if (btns.length) btns[btns.length - 1].click();
        })()
        """)
        await asyncio.sleep(2)

        # Verify it actually flipped off (avoid false "turned off" reports). Re-read
        # the SAME control's state so the report is honest.
        after = await read_toggle_state(session, control)
        return "turned_off" if after != "on" else "not_found"

    elif ctype == "aria_switch":
        # Some switches (Play "device details") are GATED by a parent control:
        # when the page says personalisation is off, the switch is inert and
        # clicking it does nothing — so it is effectively already off.
        if await _is_gated_off(session):
            return "already_off"

        before = int(await session.js(
            'document.querySelectorAll(\'button[role="switch"][aria-checked="true"]\').length'
        ) or 0)
        if before == 0:
            return "already_off"

        await session.js("""
        (async function(){
            const btns = Array.from(document.querySelectorAll('button[role="switch"][aria-checked="true"]'));
            for (const btn of btns) {
                btn.click();
                await new Promise(r => setTimeout(r, 250));
            }
        })()
        """, await_promise=True, timeout=60)
        await asyncio.sleep(1)

        # Verify the switches actually flipped off (don't trust the click).
        after = int(await session.js(
            'document.querySelectorAll(\'button[role="switch"][aria-checked="true"]\').length'
        ) or 0)
        return "turned_off" if after < before else "not_found"

    return "not_found"


async def _is_gated_off(session) -> bool:
    """True if the page indicates personalisation is off (parent gate disables sub-toggles)."""
    return bool(await session.js("""
        (function(){
            const t = document.body.innerText;
            return t.includes('Personalization is off') ||
                   t.includes('Personalisation is off') ||
                   t.includes('only when Personalize Play is turned on') ||
                   t.includes('only when Personalise Play is turned on');
        })()
    """))


async def toggle_off_all(session) -> dict:
    results = {}
    for ctrl in TOGGLE_CONTROLS:
        state = await turn_off_toggle(session, ctrl)
        results[ctrl["name"]] = state
    return results


async def read_toggle_state(session, control: dict) -> str:
    """Read a control's current state WITHOUT changing it. Returns 'on'|'off'|'not_found'."""
    await session.navigate(control["url"], wait=6.0)
    if await handle_auth(session):
        await session.navigate(control["url"], wait=6.0)

    ctype = control.get("type")
    if ctype == "turn_off_button":
        match = control.get("match")
        if match:
            # Multi-control page: read ONLY this control's button (located by its
            # aria-label substring). The button TEXT ("Turn on"/"Turn off") is the
            # reliable state signal — aria wording varies ("Start personalizing…").
            state = await session.js("""
            (function(m){
                const btn = Array.from(document.querySelectorAll('button'))
                    .find(b => (b.getAttribute('aria-label') || '').includes(m));
                if (!btn) return 'not_found';
                const t = (btn.innerText || '').trim().toUpperCase();
                const a = (btn.getAttribute('aria-label') || '').toUpperCase();
                if (t.startsWith('TURN OFF') || t.startsWith('PAUSE') || t === 'ON') return 'on';
                if (t.startsWith('TURN ON') || t === 'OFF') return 'off';
                if (a.startsWith('TURN OFF') || a.startsWith('PAUSE') || a.startsWith('STOP')) return 'on';
                if (a.startsWith('TURN ON') || a.startsWith('START')) return 'off';
                return 'not_found';
            })(%s)
            """ % _json(match))
            return str(state or "not_found")

        buttons = await session.js("""
            Array.from(document.querySelectorAll('button'))
                .map(b => (b.innerText || '').trim().toUpperCase()).filter(t => t)
        """) or []
        if not buttons:
            return "not_found"
        # Single-control pages use explicit "Turn off"/"Turn on" button text...
        if any(b.startswith("TURN OFF") or b.startswith("PAUSE") for b in buttons):
            return "on"
        if "TURN ON" in buttons:
            return "off"
        # ...or a plain status button whose TEXT is the state ("On"/"Off").
        if "ON" in buttons:
            return "on"
        if "OFF" in buttons:
            return "off"
        return "not_found"
    elif ctype == "aria_switch":
        # Gated sub-toggles (parent personalisation off) are effectively off.
        if await _is_gated_off(session):
            return "off"
        on = int(await session.js(
            'document.querySelectorAll(\'button[role="switch"][aria-checked="true"]\').length'
        ) or 0)
        return "on" if on > 0 else "off"
    return "not_found"


async def scan_toggles_all(session, progress_cb=None) -> dict:
    """Read every control's state (read-only). Returns {name: 'on'|'off'|'not_found'}."""
    states = {}
    total = len(TOGGLE_CONTROLS)
    for i, ctrl in enumerate(TOGGLE_CONTROLS, 1):
        if progress_cb:
            progress_cb(ctrl["name"], i, total)
        try:
            states[ctrl["name"]] = await read_toggle_state(session, ctrl)
        except Exception:
            states[ctrl["name"]] = "not_found"
    return states


async def turn_off_selected(session, names: list) -> dict:
    """Turn off only the named controls."""
    results = {}
    for ctrl in TOGGLE_CONTROLS:
        if ctrl["name"] in names:
            results[ctrl["name"]] = await turn_off_toggle(session, ctrl)
    return results

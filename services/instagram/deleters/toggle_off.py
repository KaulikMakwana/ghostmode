"""Turns off tracking-related toggles on Instagram / the Meta Accounts Center.

Unlike Google's My Activity (one dashboard, many named controls), IG's
tracking-relevant switches live on separate single-purpose pages:
  - instagram.com/accounts/...            (legacy IG settings)
  - accountscenter.instagram.com/...      (cross-app Meta hub IG folded ad
                                            personalization into)

Each page renders exactly one primary on/off switch, so — unlike Google's
per-control button-text variants — this uses one generic "read/flip the
switch" routine for all of them.

NOTE: Meta reshuffles Accounts Center URLs/markup periodically; these were
not live-verified against a real session in this change (no logged-in
Instagram account was available to test against). If a control reports
`not_found` where you expect `on`/`off`, the page changed — fix the URL or
selector here, the pattern (scan/read → flip → verify) does not need to change.
"""
import asyncio

BASE = "https://www.instagram.com"
AC_BASE = "https://accountscenter.instagram.com"

TOGGLE_CONTROLS = [
    {
        # "Show Activity Status" — lets others (and, by extension, the
        # platform's presence pipeline) see when you're active. Off = one
        # less real-time signal fed back into the graph.
        "name": "Activity Status",
        "url": f"{BASE}/accounts/activity_status/",
    },
    {
        # Meta's own "use my activity from partner sites/apps to personalize
        # ads and content" switch — the most direct lever on cross-site
        # tracking feeding the recommendation/ad system.
        "name": "Ad Activity From Partners",
        "url": f"{AC_BASE}/ads/activity_information/?entry_point=ads_preferences",
    },
]

_SWITCH_ON = '[role="switch"][aria-checked="true"], input[type="checkbox"]:checked'
_SWITCH_OFF = '[role="switch"][aria-checked="false"], input[type="checkbox"]:not(:checked)'


async def _read_switch_state(session) -> str:
    """'on'|'off'|'not_found' for the single primary switch on the current page."""
    if int(await session.js(f'document.querySelectorAll(\'{_SWITCH_ON}\').length') or 0) > 0:
        return "on"
    if int(await session.js(f'document.querySelectorAll(\'{_SWITCH_OFF}\').length') or 0) > 0:
        return "off"
    return "not_found"


async def read_toggle_state(session, control: dict) -> str:
    """Read a control's current state WITHOUT changing it."""
    await session.navigate(control["url"], wait=4.0)
    return await _read_switch_state(session)


async def turn_off_toggle(session, control: dict) -> str:
    """Turn off one tracking control. Returns 'turned_off' | 'already_off' | 'not_found'."""
    await session.navigate(control["url"], wait=4.0)

    before = await _read_switch_state(session)
    if before != "on":
        return "already_off" if before == "off" else "not_found"

    await session.js(f"""
    (function(){{
        const el = document.querySelector('{_SWITCH_ON}');
        if (el) el.click();
    }})()
    """)
    await asyncio.sleep(1.5)

    # Some flows (ad partners) confirm via a follow-up dialog.
    await session.js("""
    (function(){
        const scope = document.querySelector('[role="dialog"]') || document;
        const btns = Array.from(scope.querySelectorAll('button, [role="button"]'))
            .filter(b => ['TURN OFF','CONFIRM','OK','DONE','GOT IT']
                .includes((b.innerText || '').trim().toUpperCase()));
        if (btns.length) btns[btns.length - 1].click();
    })()
    """)
    await asyncio.sleep(1.5)

    after = await _read_switch_state(session)
    return "turned_off" if after == "off" else "not_found"


async def scan_toggles_all(session, progress_cb=None) -> dict:
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
    results = {}
    for ctrl in TOGGLE_CONTROLS:
        if ctrl["name"] in names:
            results[ctrl["name"]] = await turn_off_toggle(session, ctrl)
    return results

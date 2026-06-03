"""Handles the inline Delete buttons on the more-activity page."""
import asyncio
from core.auth import handle_auth
from services.google.deleters.common import confirm_dialog

BASE = "https://myactivity.google.com"
MORE_ACTIVITY_URL = f"{BASE}/more-activity"

# Services with Delete buttons directly on more-activity page (label → row index position)
INLINE_SERVICES = [
    "YouTube survey answers",
    "YouTube customise your feed feedback",
    "Google Word Coach",
    "Your interests and notifications",
    "Government exam quiz activity",
    "Translate language selections",
    "Dictionary and pronunciation search info",
    "Promo activity",
    "Product price tracking",
    "Place suggested answers feedback",
]


async def delete_inline(session, service_label: str) -> bool:
    """Find the Delete button adjacent to a named service row and click it."""
    await session.navigate(MORE_ACTIVITY_URL, wait=6.0)
    if await handle_auth(session):
        await session.navigate(MORE_ACTIVITY_URL, wait=6.0)

    # Scroll to load all content
    await session.js("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(2)

    clicked = await session.js(f"""
    (function(){{
        const label = {repr(service_label)};
        // Find the element containing this text
        const allEls = Array.from(document.querySelectorAll('*'));
        for (const el of allEls) {{
            if (el.children.length === 0 && el.innerText?.trim() === label) {{
                // Walk up to the section container, find adjacent Delete button
                let parent = el;
                for (let i = 0; i < 5; i++) {{
                    parent = parent.parentElement;
                    if (!parent) break;
                    const btn = parent.querySelector('button');
                    if (btn && btn.innerText.trim().toUpperCase() === 'DELETE') {{
                        btn.click();
                        return true;
                    }}
                }}
            }}
        }}
        return false;
    }})()
    """)

    if clicked:
        # The confirm button is a <div role="button"> inside the dialog —
        # use the shared helper that matches it correctly.
        confirmed = await confirm_dialog(session)
        return confirmed
    return False


async def delete_all_inline(session) -> dict:
    """Delete all inline services from the more-activity page."""
    results = {}
    for label in INLINE_SERVICES:
        ok = await delete_inline(session, label)
        results[label] = "deleted" if ok else "not_found"
    return results

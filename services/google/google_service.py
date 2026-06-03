import asyncio
import websockets
from core.base_service import BaseService
from core.auth import handle_auth
from core.tui import print_event
from services.google.categories import SERVICES, get_by_category
from services.google.deleters.per_item import delete_per_item
from services.google.deleters.bulk_delete import delete_tab_history
from services.google.deleters.delete_all import (
    click_delete_all, nuclear_delete, delete_all_time)
from services.google.deleters.inline_delete import delete_inline
from services.google.deleters.toggle_off import (
    toggle_off_all, scan_toggles_all, turn_off_selected)
from services.google.deleters.subscriptions import (
    list_subscriptions, unsubscribe_selected)
from services.google.deleters.common import page_is_empty
from config import RECONNECT_WAIT

BASE = "https://myactivity.google.com"
LOGIN_URL = "https://accounts.google.com/"


class GoogleService(BaseService):
    name = "google"
    login_url = LOGIN_URL

    async def login(self, browser) -> bool:
        session = await browser.connect()
        await session.navigate(LOGIN_URL, wait=3.0)
        print_event("[cyan]Browser opened — please sign in to your Google account[/cyan]")
        print_event("[dim]GhostMode will detect login automatically...[/dim]")
        # Wait up to 5 minutes for the user to log in
        for _ in range(300):
            url = await session.current_url()
            if "accounts.google" not in url and "myaccount" not in url.lower():
                # Navigate to My Activity to confirm
                await session.navigate(f"{BASE}/myactivity", wait=4.0)
                url = await session.current_url()
                if "myactivity" in url:
                    print_event("[green]✓ Login detected — session saved[/green]")
                    await session.close()
                    return True
            await asyncio.sleep(1)
        await session.close()
        return False

    async def login_interactive(self, browser) -> str | None:
        """Open Google sign-in, wait for the user, return their email (or "" / None)."""
        session = await browser.connect()
        await session.navigate(LOGIN_URL, wait=3.0)
        print_event("[bold yellow]Sign in to your Google account in the browser.[/bold yellow]")
        print_event("[dim]GhostMode will detect login automatically...[/dim]")
        try:
            for _ in range(300):  # up to 5 minutes
                url = await session.current_url()
                if "myaccount.google.com" in url or "myactivity.google.com" in url:
                    email = await session.js(
                        "document.querySelector('[data-email], [aria-label*=\"@\"]')?.getAttribute('data-email') || "
                        "document.querySelector('a[aria-label*=\"@\"]')?.getAttribute('aria-label') || ''"
                    ) or ""
                    return email.strip()  # "" if logged in but unreadable
                await asyncio.sleep(1)
            return None  # timed out
        finally:
            await session.close()

    async def scan(self, browser, progress_cb=None) -> dict:
        """Scan every service. progress_cb(category, name, index, total) fires per service."""
        session = await browser.connect()
        results = {}
        categories = get_by_category()
        total = sum(len(v) for v in categories.values())
        idx = 0

        for category, services in categories.items():
            results[category] = {}
            for svc in services:
                idx += 1
                if progress_cb:
                    progress_cb(category, svc["name"], idx, total)
                if svc["delete_type"] == "external":
                    results[category][svc["name"]] = None
                    continue
                try:
                    count = await self._count_items(session, svc)
                    results[category][svc["name"]] = count
                except Exception:
                    results[category][svc["name"]] = None

        await session.close()
        return results

    async def _count_items(self, session, svc: dict) -> int:
        """Return: >=0 exact count, -1 = has data (uncountable), -2 = actionable/unknown."""
        await session.navigate(svc["url"], wait=5.0)
        await handle_auth(session)

        dtype = svc["delete_type"]
        if dtype in ("per_item", "per_item_lm", "yt_history"):
            # yt_history deletes via "Delete all time" but still shows per-item X
            # buttons, so we can give a real (visible) count in the dashboard.
            for _ in range(3):
                await session.js("window.scrollBy(0, 2000)")
                await asyncio.sleep(0.5)
            count = await session.js(
                "document.querySelectorAll('button[aria-label^=\"Delete activity item\"]').length"
            )
            return int(count or 0)
        elif dtype == "play_toggles":
            count = await session.js(
                'document.querySelectorAll(\'button[role="switch"][aria-checked="true"]\').length'
            )
            return int(count or 0)
        elif dtype in ("service_delete", "delete_all_btn", "nuclear"):
            # Empty if page shows any "no data" phrase (No activity/results/history)
            if await page_is_empty(session):
                return 0
            return -1  # has data, but not individually countable
        elif dtype == "inline":
            # more-activity rows are always present with a Delete button — Google
            # exposes no count. Mark as actionable/unknown rather than faking "has data".
            return -2
        elif dtype == "subscriptions":
            # Enumerating channels means loading /feed/channels + scrolling — too slow
            # for every dashboard scan. Mark actionable; the real list is fetched only
            # when the user actually selects Subscriptions.
            return -2
        return 0

    async def delete(self, browser, targets: list, progress_cb=None,
                     sub_hrefs: list = None) -> dict:
        results = {}
        for target_name in targets:
            svc = next((s for s in SERVICES if s["name"] == target_name), None)
            if not svc:
                continue
            print_event(f"[cyan]Starting:[/cyan] {svc['name']}")
            deleted = await self._delete_service(browser, svc, sub_hrefs)
            results[svc["name"]] = deleted
            print_event(f"[green]✓ Done:[/green] {svc['name']} — {deleted:,} items")
        return results

    async def _delete_service(self, browser, svc: dict, sub_hrefs: list = None) -> int:
        dtype = svc["delete_type"]
        conn_errors = 0
        while True:
            try:
                session = await browser.connect()
                result = await self._run_deleter(session, svc, dtype, sub_hrefs)
                await session.close()
                return result
            except (websockets.exceptions.ConnectionClosed, TimeoutError):
                # Transient — reconnect, but cap so we never loop forever
                conn_errors += 1
                if conn_errors > 5:
                    print_event(f"[red]✘ Gave up on {svc['name']} after 5 reconnects[/red]")
                    return 0
                print_event("[yellow]↻ Reconnecting...[/yellow]")
                await asyncio.sleep(RECONNECT_WAIT)
            except Exception as e:
                # Real bug in a deleter — report and move on, don't spin
                print_event(f"[red]✘ {svc['name']} failed: {type(e).__name__}: {e}[/red]")
                return 0

    async def _run_deleter(self, session, svc: dict, dtype: str,
                           sub_hrefs: list = None) -> int:
        if dtype == "subscriptions":
            return await unsubscribe_selected(session, sub_hrefs or [])
        if dtype == "per_item":
            return await delete_per_item(session, svc["url"], use_load_more=False)
        elif dtype == "per_item_lm":
            return await delete_per_item(session, svc["url"], use_load_more=True)
        elif dtype == "delete_all_btn":
            ok = await click_delete_all(session, svc["url"], svc.get("button_text", "Delete All"))
            return 1 if ok else 0
        elif dtype == "service_delete":
            # My Activity product pages use the time-range flow (Delete → "All time"
            # → Next → Delete), NOT a one-click confirm — verified live. Reuse the
            # same engine as nuclear delete, scoped to this product URL.
            await session.navigate(svc["url"], wait=6.0)
            if await handle_auth(session):
                await session.navigate(svc["url"], wait=6.0)
            ok = await delete_all_time(session)
            return 1 if ok else 0
        elif dtype == "yt_history":
            ok = await delete_tab_history(session, svc["url"])
            return 1 if ok else 0
        elif dtype == "nuclear":
            ok = await nuclear_delete(session)
            return 1 if ok else 0
        elif dtype == "inline":
            ok = await delete_inline(session, svc.get("inline_label", svc["name"]))
            return 1 if ok else 0
        elif dtype == "play_toggles":
            return await self._delete_play_toggles(session, svc["url"])
        elif dtype == "external":
            print_event(f"[yellow]⚠  External service — {svc.get('note', 'handle manually')}[/yellow]")
            return 0
        return 0

    async def _delete_play_toggles(self, session, url: str) -> int:
        await session.navigate(url, wait=6.0)
        await handle_auth(session)
        total = 0
        while True:
            toggled = int(await session.js("""
            (async function(){
                const btns = Array.from(document.querySelectorAll('button[role="switch"][aria-checked="true"]'));
                let n = 0;
                for (const btn of btns) {
                    btn.click();
                    await new Promise(r => setTimeout(r, 200));
                    n++;
                }
                return n;
            })()
            """, await_promise=True, timeout=120) or 0)
            total += toggled
            if toggled == 0:
                # Try Load More
                clicked = await session.js("""
                (function(){
                    const btn = Array.from(document.querySelectorAll('button'))
                        .find(b => b.innerText.trim().toLowerCase() === 'load more');
                    if (btn) { btn.click(); return true; }
                    return false;
                })()
                """)
                if clicked:
                    await asyncio.sleep(3)
                else:
                    break
        return total

    async def scan_subscriptions(self, browser) -> list:
        """List subscribed channels [{name, href}] without changing anything."""
        session = await browser.connect()
        channels = await list_subscriptions(session)
        await session.close()
        return channels

    async def unsubscribe(self, browser, hrefs: list) -> int:
        """Unsubscribe the chosen channels. Returns count unsubscribed."""
        session = await browser.connect()
        count = await unsubscribe_selected(session, hrefs)
        await session.close()
        return count

    async def toggle_off(self, browser) -> dict:
        session = await browser.connect()
        results = await toggle_off_all(session)
        await session.close()
        return results

    async def scan_toggles(self, browser, progress_cb=None) -> dict:
        """Read current toggle states without changing them."""
        session = await browser.connect()
        states = await scan_toggles_all(session, progress_cb)
        await session.close()
        return states

    async def toggle_off_selected(self, browser, names: list) -> dict:
        session = await browser.connect()
        results = await turn_off_selected(session, names)
        await session.close()
        return results

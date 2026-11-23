"""InstagramService — second GhostMode platform (Phase 1: Your Activity bulk wipe).

Phase 1 covers posts/media + engagement (likes/comments/story replies) via the
"Your Activity" bulk Select->Delete flow. DMs (ig_dms) and account deletion
(ig_account) are scaffolded but deferred to Phases 2 & 3.
"""
import asyncio
from core.base_service import BaseService
from core.tui import print_event
from services.instagram.categories import SERVICES, get_by_category
from services.instagram.deleters.bulk_activity import bulk_delete_activity, page_has_activity
from services.instagram.deleters.toggle_off import (
    scan_toggles_all, turn_off_selected)

BASE = "https://www.instagram.com"
LOGIN_URL = f"{BASE}/accounts/login/"


class InstagramService(BaseService):
    name = "instagram"
    login_url = LOGIN_URL

    async def login(self, browser) -> bool:
        ident = await self.login_interactive(browser)
        return ident is not None

    async def login_interactive(self, browser) -> str | None:
        """Open IG login, wait for the user (and any checkpoint), return @username."""
        session = await browser.connect()
        await session.navigate(LOGIN_URL, wait=4.0)
        print_event("[bold yellow]Sign in to Instagram in the browser.[/bold yellow]")
        print_event("[dim]Complete any 'confirm it's you' checkpoint — GhostMode waits.[/dim]")
        try:
            for _ in range(300):  # up to 5 minutes
                url = await session.current_url()
                if "instagram.com" in url and "/accounts/login" not in url:
                    # Logged in. Best-effort scrape of the username from the nav.
                    handle = await session.js("""
                    (function(){
                        const a = Array.from(document.querySelectorAll('a[href^="/"]'))
                            .find(a => /profile/i.test(a.getAttribute('aria-label') || ''));
                        if (a) {
                            const m = (a.getAttribute('href') || '').match(/^\\/([^/]+)\\//);
                            if (m) return m[1];
                        }
                        return '';
                    })()
                    """) or ""
                    return handle.strip()
                await asyncio.sleep(1)
            return None
        finally:
            await session.close()

    async def scan(self, browser, progress_cb=None) -> dict:
        """Enumerate for real (like Google): verify the session on the main URL, then
        visit each Your Activity page and report has-data (-1) / clean (0). IG exposes
        no exact totals, so we never fabricate counts. ig_account -> None (manual)."""
        session = await browser.connect()
        categories = get_by_category()
        total = sum(len(v) for v in categories.values())
        try:
            # ── 1. Main-URL / login gate ──────────────────────────────────────────
            await session.navigate(BASE + "/", wait=5.0)
            url = await session.current_url()
            if "/accounts/login" in url or "instagram.com" not in url:
                print_event("[red]Instagram session expired or not logged in.[/red]  "
                            "Re-run: [bold]python main.py login add --service instagram[/bold]")
                # Mark everything manual so the dashboard doesn't claim fake state.
                return {cat: {s["name"]: None for s in svcs}
                        for cat, svcs in categories.items()}

            # ── 2. Per-category enumeration ───────────────────────────────────────
            results = {}
            idx = 0
            for category, svcs in categories.items():
                results[category] = {}
                for svc in svcs:
                    idx += 1
                    if progress_cb:
                        progress_cb(category, svc["name"], idx, total)
                    dtype = svc["delete_type"]
                    if dtype == "ig_account":
                        results[category][svc["name"]] = None       # not a scan target
                        continue
                    try:
                        # page_has_activity polls for the React content to settle, so
                        # only a short post-navigate wait is needed here.
                        await session.navigate(svc["url"], wait=1.5)
                        if dtype == "ig_dms":
                            has = await self._inbox_has_threads(session)
                        else:
                            has = await page_has_activity(session)
                        results[category][svc["name"]] = -1 if has else 0
                    except Exception:
                        results[category][svc["name"]] = None
        finally:
            await session.close()
        return results

    async def _inbox_has_threads(self, session) -> bool:
        """Read-only: does the DM inbox contain any conversation threads?

        Verified live 2026-06-03: IG renders inbox threads as `div[role="button"]`
        rows — NOT `<a href="/direct/t/…">` or `[role="listitem"]` (the old selectors
        matched nothing → false 'clean' on an inbox full of DMs). A thread row carries
        an avatar (img/canvas) AND a conversation preview: a relative timestamp
        (`· 4h`/`· 1w`) or a marker ("sent an attachment"/"You:"/"Reacted"). The own
        profile / "Your note" / "Send message" buttons lack that combo and are skipped.
        Polls for the cold-load race (inbox is React, ~5s to render)."""
        for _ in range(8):
            n = int(await session.js(r"""
            (function(){
                return Array.from(document.querySelectorAll('[role="button"]'))
                    .filter(e => e.offsetParent !== null)
                    .filter(e => e.querySelector('img,canvas'))
                    .filter(e => {
                        const t = e.innerText || '';
                        return /·\s*\d+\s*[smhdwy]\b/i.test(t)
                            || /sent an attachment|reacted|you:|· now|· active/i.test(t);
                    }).length;
            })()
            """) or 0)
            if n > 0:
                return True
            await asyncio.sleep(1.5)
        return False

    async def delete(self, browser, targets: list, progress_cb=None, sub_hrefs: list = None) -> dict:
        results = {}
        for name in targets:
            svc = next((s for s in SERVICES if s["name"] == name), None)
            if not svc:
                continue
            dtype = svc["delete_type"]
            if dtype == "ig_bulk":
                print_event(f"[cyan]Starting:[/cyan] {svc['name']} ({svc['action'].lower()})")
                session = await browser.connect()
                try:
                    n = await bulk_delete_activity(session, svc["url"], svc.get("action", "Delete"))
                finally:
                    await session.close()
                results[name] = n
                print_event(f"[green]✓ Done:[/green] {svc['name']} — {n:,} items")
            elif dtype == "ig_dms":
                print_event("[yellow]Direct Messages deletion is Phase 2 — not yet implemented.[/yellow]")
                results[name] = 0
            elif dtype == "ig_account":
                print_event("[yellow]Account deletion is Phase 3 (gated) — not yet implemented.[/yellow]")
                results[name] = 0
        return results

    async def toggle_off(self, browser) -> dict:
        session = await browser.connect()
        try:
            states = await scan_toggles_all(session)
            return await turn_off_selected(session, list(states.keys()))
        finally:
            await session.close()

    async def scan_toggles(self, browser, progress_cb=None) -> dict:
        """Read current toggle states without changing them."""
        session = await browser.connect()
        try:
            return await scan_toggles_all(session, progress_cb)
        finally:
            await session.close()

    async def toggle_off_selected(self, browser, names: list) -> dict:
        session = await browser.connect()
        try:
            return await turn_off_selected(session, names)
        finally:
            await session.close()

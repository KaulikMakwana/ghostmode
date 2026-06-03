#!/usr/bin/env python3
"""GhostMode — Digital Footprint Eraser CLI"""
import asyncio
import time
import sys
from pathlib import Path

import click
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent))

from config import PROFILES_DIR
from core.browser import Browser, running_profile_dir, kill_running_browser
from core import database as db
from core.tui import (print_banner, print_accounts_table, print_dashboard,
                       print_event, print_summary, make_progress, make_scan_progress,
                       print_toggle_table)
from core.selector import (select_services, select_account, select_account_to_delete,
                           select_toggles, select_subscriptions, confirm)
from services.google.google_service import GoogleService
from services.google.categories import SERVICES
from services.instagram.instagram_service import InstagramService

console = Console()

SERVICE_REGISTRY = {
    "google": GoogleService,
    "instagram": InstagramService,
}

# Set by the global --headless flag on the cli group; read by every browser launch.
HEADLESS = False


def _get_service_obj(service_name: str):
    cls = SERVICE_REGISTRY.get(service_name)
    if not cls:
        console.print(f"[red]Unknown service: {service_name}[/red]")
        raise SystemExit(1)
    return cls()


def _catalog(service_name: str) -> list:
    """Return the service's list of data categories (SERVICES) so command logic
    isn't hard-coded to Google. Explicit per service — never silently fall back to
    Google for an unknown name (that fallback made `list --service snapchat` print
    Google's catalog under a 'snapchat' title)."""
    if service_name == "instagram":
        from services.instagram.categories import SERVICES as IG_SERVICES
        return IG_SERVICES
    if service_name == "google":
        return SERVICES
    raise ValueError(f"No catalog for unimplemented service: {service_name}")


def _require_active(service_name: str) -> dict:
    acc = db.get_active_account(service_name)
    if not acc:
        console.print(f"[yellow]No active {service_name} account.[/yellow]  "
                      f"Run: [bold]python main.py login add --service {service_name}[/bold]")
        raise SystemExit(1)
    return acc


def _get_browser(acc: dict) -> Browser:
    # Use the exact profile_dir stored in the DB — this is where the session lives
    b = Browser(
        profile=f"{acc['service']}_{acc['id']}",
        profile_dir=acc["profile_dir"],
    )
    desired = str(Path(acc["profile_dir"]).resolve())
    if b.is_running():
        current = running_profile_dir()
        if current == desired:
            return b  # right account already loaded — reuse it
        # A different account owns the port. CDP only serves one --user-data-dir at
        # a time, so reusing it would silently keep the old account. Kill + relaunch.
        console.print(f"[yellow]Switching account → restarting browser as "
                      f"[bold]{acc['email']}[/bold]...[/yellow]")
        if not kill_running_browser():
            console.print("[red]Could not free the browser port. Close Chromium "
                          "manually and retry.[/red]")
            raise SystemExit(1)
    else:
        console.print(f"[yellow]Launching Chromium{' (headless)' if HEADLESS else ''}...[/yellow]")
    b.launch(headless=HEADLESS)
    return b


# ── CLI root ──────────────────────────────────────────────────────────────────

@click.group()
@click.option("--headless", is_flag=True,
              help="Run Chromium headless (no visible window). Default: visible. "
                   "Goes before the command, e.g. 'main.py --headless dashboard ...'.")
def cli(headless):
    """GhostMode — Erase your digital footprint."""
    global HEADLESS
    HEADLESS = headless


# ── login group ──────────────────────────────────────────────────────────────

@cli.group()
def login():
    """Manage accounts: add, list, select, delete."""


@login.command("list")
@click.option("--service", default=None, help="Filter by service")
def login_list(service):
    """List all saved accounts."""
    print_banner()
    accounts = db.list_accounts(service)
    if not accounts:
        console.print("[dim]No accounts saved yet.  Run: ghostmode login add[/dim]")
        return
    print_accounts_table(accounts)


@login.command("add")
@click.option("--service", default="google", show_default=True)
def login_add(service):
    """Open browser and log in to add a new account."""
    print_banner()
    svc_obj = _get_service_obj(service)

    profile_id = f"new_{int(time.time())}"
    b = Browser(profile=f"{service}_{profile_id}")
    if HEADLESS:
        console.print("[yellow]⚠  --headless during login means no visible window to "
                      "sign in. Use a visible browser for 'login add'.[/yellow]")
    console.print(f"[cyan]Launching browser for [bold]{service}[/bold]...[/cyan]")
    b.launch(headless=HEADLESS)

    # Each service owns its own login URL + detection; the CLI just drives it.
    identifier = asyncio.run(svc_obj.login_interactive(b))

    if identifier is None:
        console.print("\n[red]✘  Login not detected (timed out). Nothing saved.[/red]")
        return
    if not identifier:
        identifier = click.prompt("  Enter the username/email you logged in with")

    # The session lives in b.profile_dir — save that path directly to DB.
    acc_id = db.add_account(service, identifier, str(b.profile_dir))
    db.set_active_account(acc_id)
    console.print(f"\n[bold green]✔  Account saved:[/bold green] {identifier}  (id={acc_id})")
    console.print(f"   Profile: {b.profile_dir}")
    console.print(f"   Run [bold]python main.py dashboard --service {service}[/bold] to continue.\n")


@login.command("select")
@click.option("--service", default="google", show_default=True)
def login_select(service):
    """Set which account is active for operations."""
    print_banner()
    accounts = db.list_accounts(service)
    if not accounts:
        console.print("[dim]No accounts. Run: ghostmode login add[/dim]")
        return
    acc = select_account(accounts)
    if acc:
        db.set_active_account(acc["id"])
        console.print(f"[green]✔  Active account set to:[/green] {acc['email']}")


@login.command("delete")
@click.option("--service", default=None)
def login_delete(service):
    """Remove a saved account and its data."""
    print_banner()
    accounts = db.list_accounts(service)
    acc = select_account_to_delete(accounts)
    if not acc:
        return
    if confirm(f"Delete account {acc['email']} and all its saved data?"):
        db.delete_account(acc["id"])
        # Also remove profile directory
        profile_dir = Path(acc["profile_dir"])
        if profile_dir.exists():
            import shutil
            shutil.rmtree(profile_dir, ignore_errors=True)
        console.print(f"[green]✔  Deleted:[/green] {acc['email']}")


# ── dashboard ─────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--service", default="google", show_default=True)
@click.option("--cached", is_flag=True, help="Show last saved scan without rescanning")
@click.option("--delete", "do_delete", is_flag=True,
              help="After display, pick services to delete interactively")
def dashboard(service, cached, do_delete):
    """Scan all data, display dashboard, optionally delete from within."""
    acc = _require_active(service)
    print_banner(acc["email"])

    # ── async scan phase (no interactive prompts inside the event loop) ──
    async def _scan():
        svc_obj = _get_service_obj(service)
        if cached:
            saved = db.latest_scan(acc["id"])
            if saved:
                return saved["results"], saved["scanned_at"]
            console.print("[yellow]No saved scan. Running fresh scan...[/yellow]")
        b = _get_browser(acc)
        prog = make_scan_progress()
        with prog:
            task = prog.add_task("starting...", total=1)

            def cb(category, name, idx, total):
                prog.update(task, total=total, completed=idx,
                            description=f"[cyan]{category}[/cyan] [white]{name[:34]}[/white]")

            results = await svc_obj.scan(b, progress_cb=cb)
            prog.update(task, description="[green]done[/green]")
        db.save_scan(acc["id"], results)
        db.touch_account(acc["id"])
        return results, None

    results, last_scan_ts = asyncio.run(_scan())

    hist = db.delete_history_summary(acc["id"])
    total = print_dashboard(results, last_scan_ts, hist)

    if total == 0:
        console.print("[bold green]  Everything is clean![/bold green]\n")
        return

    # ── sync interactive selection (outside any event loop) ──
    if not (do_delete or confirm("  Select services to delete now?")):
        return
    targets = select_services(results, preselect_all=False)
    if not targets:
        console.print("[dim]Nothing selected.[/dim]")
        return

    # If Subscriptions is selected, pick which channels to unsubscribe (sync).
    targets, sub_hrefs = _resolve_subscriptions(service, acc, targets)
    if not targets:
        console.print("[dim]Nothing selected.[/dim]")
        return

    # ── async delete phase (fresh event loop) ──
    asyncio.run(_execute_delete(service, acc, targets, sub_hrefs))


# ── delete ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--service", default="google", show_default=True)
@click.option("--all", "delete_all", is_flag=True, help="Delete from all services")
@click.option("--pick", is_flag=True, help="Interactive checkbox selection")
@click.option("--nuclear", is_flag=True, help="Delete ALL activity in one click")
@click.option("--only", default=None, help="Single service name")
def delete(service, delete_all, pick, nuclear, only):
    """Delete your data — choose interactively or run all at once."""
    acc = _require_active(service)
    print_banner(acc["email"])

    # ── Nuclear path (Google-only) ──
    if nuclear:
        if service != "google":
            console.print(f"[yellow]--nuclear is Google-only. For {service}, use "
                          f"[bold]--pick[/bold], [bold]--all[/bold], or [bold]--only <name>[/bold].[/yellow]")
            return
        if not confirm("NUCLEAR DELETE — delete ALL Google activity forever?"):
            return

        async def _nuke():
            b = _get_browser(acc)
            from services.google.deleters.delete_all import nuclear_delete
            session = await b.connect()
            print_event("[red]Executing nuclear delete...[/red]")
            await nuclear_delete(session)
            await session.close()
            print_event("[bold green]✔ Nuclear delete complete[/bold green]")
            db.save_delete(acc["id"], "Nuclear Delete (All Activity)", 1)

        asyncio.run(_nuke())
        return

    # ── Determine targets (interactive selection runs OUTSIDE any event loop) ──
    catalog = _catalog(service)
    if only:
        targets = [only]
    elif delete_all:
        targets = [s["name"] for s in catalog if s["delete_type"] not in _SKIP_IN_ALL]
    else:
        # Default (no flag) AND --pick: interactive selection, same as dashboard.
        # Use the latest scan; if there isn't one, scan fresh so the picker shows real
        # state instead of fabricated guesses.
        saved = db.latest_scan(acc["id"])
        scan_data = saved["results"] if saved else None
        if not scan_data:
            console.print("[cyan]No recent scan — scanning first...[/cyan]")
            scan_data = _scan_service(service, acc)
        targets = select_services(scan_data, preselect_all=False)

    if not targets:
        console.print("[dim]Nothing selected.[/dim]")
        return

    # If Subscriptions is selected, pick which channels to unsubscribe (sync).
    targets, sub_hrefs = _resolve_subscriptions(service, acc, targets)
    if not targets:
        console.print("[dim]Nothing selected.[/dim]")
        return

    asyncio.run(_execute_delete(service, acc, targets, sub_hrefs))


# ── toggle ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--service", default="google", show_default=True)
def toggle(service):
    """Turn off all activity tracking toggles."""
    acc = _require_active(service)
    print_banner(acc["email"])

    svc_obj = _get_service_obj(service)
    if not hasattr(svc_obj, "scan_toggles"):
        console.print(f"[yellow]'{service}' has no tracking toggles to turn off.[/yellow]")
        return
    b = _get_browser(acc)

    # ── scan phase (read-only, live progress) ──
    async def _scan():
        prog = make_scan_progress()
        with prog:
            task = prog.add_task("starting...", total=1)

            def cb(name, idx, total):
                prog.update(task, total=total, completed=idx,
                            description=f"[cyan]{name[:34]}[/cyan]")

            states = await svc_obj.scan_toggles(b, progress_cb=cb)
            prog.update(task, description="[green]done[/green]")
        return states

    states = asyncio.run(_scan())
    n_on = print_toggle_table(states)

    if n_on == 0:
        console.print("[bold green]  All tracking controls are already off.[/bold green]\n")
        return

    # ── sync selection (outside event loop) ──
    targets = select_toggles(states)
    if not targets:
        console.print("[dim]Nothing selected.[/dim]")
        return

    # ── act phase ──
    async def _act():
        return await svc_obj.toggle_off_selected(b, targets)

    console.print(f"\n[cyan]Turning off {len(targets)} control(s)...[/cyan]\n")
    results = asyncio.run(_act())
    done = 0
    for name, state in results.items():
        if state == "turned_off":
            console.print(f"  [green]✔[/green]  {name:<42} [green]turned off[/green]")
            done += 1
        else:
            console.print(f"  [dim]○  {name:<42} {state}[/dim]")
    console.print(f"\n  [bold green]{done}[/bold green] control(s) turned off.\n")


# ── list ──────────────────────────────────────────────────────────────────────

@cli.command(name="list")
@click.option("--service", default=None,
              help="Show one service's data catalog. Omit to list implemented services.")
def list_services(service):
    """List implemented services, or one service's data catalog with --service."""
    from rich.table import Table
    from rich import box as rbox

    # No --service: overview of what GhostMode actually implements.
    if service is None:
        table = Table(title="GhostMode — Implemented Services", box=rbox.ROUNDED,
                      border_style="cyan", header_style="bold cyan")
        table.add_column("NO", justify="right", style="grey50", width=3)
        table.add_column("Service", style="white", min_width=14)
        table.add_column("Data Categories", justify="right", style="yellow", min_width=15)
        table.add_column("Inspect", style="dim")
        for i, name in enumerate(SERVICE_REGISTRY, 1):
            table.add_row(str(i), name, str(len(_catalog(name))),
                          f"python main.py list --service {name}")
        console.print(table)
        return

    # --service X: reject anything not implemented instead of falling back to Google.
    if service not in SERVICE_REGISTRY:
        console.print(f"[red]Unknown service: {service}[/red]  "
                      f"Implemented: [bold]{', '.join(SERVICE_REGISTRY)}[/bold]")
        raise SystemExit(1)

    table = Table(title=f"Supported Services — {service}", box=rbox.ROUNDED,
                  border_style="cyan", header_style="bold cyan")
    table.add_column("NO", justify="right", style="grey50", width=3)
    table.add_column("Service", style="white", min_width=38)
    table.add_column("Category", style="cyan", min_width=14)
    table.add_column("Delete Type", style="yellow", min_width=15)
    for i, s in enumerate(_catalog(service), 1):
        table.add_row(str(i), s["name"], s["category"], s["delete_type"])
    console.print(table)


# ── Shared helpers ────────────────────────────────────────────────────────────

_SUBSCRIPTIONS = "YouTube Subscriptions"

# Delete-types that --all must NEVER auto-include: external (manual), and IG's gated
# account deletion / not-yet-implemented DMs. --all is for bulk-erasable data only.
_SKIP_IN_ALL = {"external", "ig_account", "ig_dms"}


def _scan_service(service: str, acc: dict) -> dict:
    """Fresh scan with live progress (the same flow dashboard uses), saved to DB.
    Lets `delete` show the real state when there's no recent scan, instead of guessing."""
    svc_obj = _get_service_obj(service)

    async def _s():
        b = _get_browser(acc)
        prog = make_scan_progress()
        with prog:
            task = prog.add_task("starting...", total=1)

            def cb(category, name, idx, total):
                prog.update(task, total=total, completed=idx,
                            description=f"[cyan]{category}[/cyan] [white]{name[:34]}[/white]")

            results = await svc_obj.scan(b, progress_cb=cb)
            prog.update(task, description="[green]done[/green]")
        db.save_scan(acc["id"], results)
        db.touch_account(acc["id"])
        return results

    return asyncio.run(_s())


def _resolve_subscriptions(service: str, acc: dict, targets: list):
    """If 'YouTube Subscriptions' is among targets, scan channels and let the user
    pick which to unsubscribe (per-channel). Runs OUTSIDE any event loop.
    Returns (targets, sub_hrefs). Drops Subscriptions from targets if none chosen."""
    if _SUBSCRIPTIONS not in targets:
        return targets, None
    svc_obj = _get_service_obj(service)
    b = _get_browser(acc)
    console.print("\n[cyan]Loading your YouTube subscriptions...[/cyan]")
    channels = asyncio.run(svc_obj.scan_subscriptions(b))
    if not channels:
        console.print("[yellow]No subscriptions found — skipping.[/yellow]")
        return [t for t in targets if t != _SUBSCRIPTIONS], None
    hrefs = select_subscriptions(channels)
    if not hrefs:
        console.print("[dim]No channels picked — skipping subscriptions.[/dim]")
        return [t for t in targets if t != _SUBSCRIPTIONS], None
    console.print(f"[cyan]{len(hrefs)} channel(s) queued to unsubscribe.[/cyan]")
    return targets, hrefs


async def _execute_delete(service: str, acc: dict, targets: list, sub_hrefs: list = None):
    from services.google.google_service import GoogleService
    import websockets

    svc_obj = _get_service_obj(service)
    b = _get_browser(acc)
    start = time.time()
    results = {}

    console.print(f"\n[cyan]Deleting {len(targets)} service(s)...[/cyan]\n")

    with make_progress() as progress:
        overall = progress.add_task("[bold]Overall[/bold]", total=len(targets))

        for target in targets:
            progress.update(overall, description=f"[cyan]{target[:42]}[/cyan]")

            # Reconnect loop per service
            while True:
                try:
                    partial = await svc_obj.delete(b, [target], sub_hrefs=sub_hrefs)
                    results.update(partial)
                    # Save to DB
                    count = partial.get(target, 0)
                    db.save_delete(acc["id"], target, count or 0)
                    break
                except (websockets.exceptions.ConnectionClosed, TimeoutError):
                    print_event("[yellow]↻ Reconnecting...[/yellow]")
                    await asyncio.sleep(5)

            progress.advance(overall)

    elapsed = time.time() - start
    print_summary(results, {}, elapsed)
    db.touch_account(acc["id"])


if __name__ == "__main__":
    cli()

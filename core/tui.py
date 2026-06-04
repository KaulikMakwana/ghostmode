import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TaskProgressColumn
from rich.text import Text
from rich import box

from core import version

console = Console()


def print_banner(account_email: str = ""):
    lines = [
        "  ██████╗ ██╗  ██╗ ██████╗ ███████╗████████╗███╗   ███╗ ██████╗ ██████╗ ███████╗",
        "  ██╔════╝██║  ██║██╔═══██╗██╔════╝╚══██╔══╝████╗ ████║██╔═══██╗██╔══██╗██╔════╝",
        "  ██║  ███╗███████║██║   ██║███████╗   ██║   ██╔████╔██║██║   ██║██║  ██║█████╗  ",
        "  ██║   ██║██╔══██║██║   ██║╚════██║   ██║   ██║╚██╔╝██║██║   ██║██║  ██║██╔══╝  ",
        "  ╚██████╔╝██║  ██║╚██████╔╝███████║   ██║   ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗",
        "   ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝",
    ]
    banner = Text()
    for line in lines:
        banner.append(line + "\n", style="bold cyan")
    sub = f"                     Digital Footprint Eraser  ·  v{version.__version__}"
    if account_email:
        sub += f"  ·  {account_email}"
    banner.append(sub, style="dim white")
    note = version.notice()
    if note:
        banner.append("\n" + note, style="yellow")
    console.print(Panel(banner, border_style="cyan", padding=(0, 2)))
    console.print()


def print_accounts_table(accounts: list[dict]):
    table = Table(
        title="[bold]Saved Accounts[/bold]",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
    )
    table.add_column("NO", justify="right", style="grey50", width=3)
    table.add_column("ID", justify="center", style="dim", width=4)
    table.add_column("Active", justify="center", width=7)
    table.add_column("Service", style="cyan", min_width=10)
    table.add_column("Email", style="white", min_width=30)
    table.add_column("Added", style="dim", min_width=12)
    table.add_column("Last Used", style="dim", min_width=12)

    for i, acc in enumerate(accounts, 1):
        active = "[bold green]★ YES[/bold green]" if acc["active"] else "[dim]  —[/dim]"
        table.add_row(
            str(i),
            str(acc["id"]),
            active,
            acc["service"],
            acc["email"],
            acc["created_at"][:10],
            (acc["last_used"] or "—")[:10],
        )
    console.print(table)


def print_dashboard(scan_results: dict, last_scan: str = None, history_summary: list = None) -> int:
    """
    Render the main dashboard table.
    Returns total item count.
    """
    table = Table(
        box=box.SIMPLE_HEAD,
        border_style="grey37",
        header_style="bold cyan",
        expand=True,
        pad_edge=False,
        collapse_padding=True,
    )
    table.add_column("NO", justify="right", style="grey50", width=3, no_wrap=True)
    table.add_column(" ", justify="center", width=3, no_wrap=True)
    table.add_column("Service", style="white", min_width=34, ratio=3)
    table.add_column("Items", justify="right", min_width=8)
    table.add_column("Last Erased", justify="center", style="dim", min_width=11)
    table.add_column("Status", justify="left", min_width=14)

    hist_map = {}
    if history_summary:
        for h in history_summary:
            hist_map[h["service"]] = h["last_deleted"][:10]

    total = 0
    n_data = n_clean = n_action = n_ext = 0
    row_no = 0

    for ci, (category, services) in enumerate(scan_results.items()):
        if ci > 0:
            table.add_section()
        # Category header row (no number)
        table.add_row("", "", f"[bold cyan]{category.upper()}[/bold cyan]", "", "", "")
        for name, count in services.items():
            row_no += 1
            last_del = hist_map.get(name, "[grey30]—[/grey30]")
            if count is None:
                icon, items, status = "[grey50]⊘[/grey50]", "[grey50]ext[/grey50]", "[grey50]manual[/grey50]"
                n_ext += 1
            elif count == 0:
                icon, items, status = "[green]✔[/green]", "[green]0[/green]", "[green]clean[/green]"
                n_clean += 1
            elif count == -1:
                icon, items, status = "[yellow]●[/yellow]", "[yellow]has data[/yellow]", "[yellow]needs erase[/yellow]"
                n_data += 1
            elif count == -2:
                icon, items, status = "[blue]◌[/blue]", "[blue]deletable[/blue]", "[blue dim]on request[/blue dim]"
                n_action += 1
            else:
                icon, items, status = "[red]✘[/red]", f"[red bold]{count:,}[/red bold]", "[red]needs erase[/red]"
                total += count
                n_data += 1
            table.add_row(str(row_no), icon, f"  {name}", items, last_del, status)

    console.print(table)

    # Summary footer
    bits = []
    if total:
        bits.append(f"[red bold]{total:,}[/red bold] items")
    bits.append(f"[yellow]{n_data}[/yellow] with data")
    bits.append(f"[blue]{n_action}[/blue] deletable")
    bits.append(f"[green]{n_clean}[/green] clean")
    bits.append(f"[grey50]{n_ext}[/grey50] manual")
    footer = "   ·   ".join(bits)
    sub = f"[grey42]Last scan {last_scan}[/grey42]" if last_scan else ""
    console.print(Panel(footer + (f"\n{sub}" if sub else ""),
                        border_style="grey37", padding=(0, 2)))
    console.print()
    return total + n_data + n_action


def print_toggle_table(states: dict) -> int:
    """Show tracking-control states. Returns count currently ON."""
    table = Table(
        box=box.SIMPLE_HEAD,
        border_style="grey37",
        header_style="bold cyan",
        expand=True,
        pad_edge=False,
    )
    table.add_column("NO", justify="right", style="grey50", width=3)
    table.add_column(" ", justify="center", width=3)
    table.add_column("Tracking Control", style="white", min_width=34, ratio=3)
    table.add_column("State", justify="left", min_width=12)
    table.add_column("Action", justify="left", min_width=16)

    n_on = 0
    for i, (name, state) in enumerate(states.items(), 1):
        if state == "on":
            icon, st, act = "[red]●[/red]", "[red]ON[/red]", "[yellow]will turn OFF[/yellow]"
            n_on += 1
        elif state == "off":
            icon, st, act = "[green]○[/green]", "[green]off[/green]", "[dim]already off[/dim]"
        else:
            icon, st, act = "[grey50]⊘[/grey50]", "[grey50]n/a[/grey50]", "[grey50]not found[/grey50]"
        table.add_row(str(i), icon, f"  {name}", st, act)

    console.print(table)
    if n_on:
        console.print(Panel(f"[red bold]{n_on}[/red bold] control(s) still tracking you",
                            border_style="grey37", padding=(0, 2)))
    console.print()
    return n_on


def print_event(message: str):
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(f"  [dim]{ts}[/dim]  {message}")


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TextColumn("[dim]{task.completed:,}/{task.total:,}[/dim]"),
        TimeElapsedColumn(),
        console=console,
        expand=True,
    )


def make_scan_progress() -> Progress:
    """Live progress bar for the scanning phase (shows current service)."""
    return Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]Scanning[/bold cyan]"),
        BarColumn(bar_width=30, complete_style="cyan", finished_style="green"),
        TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
        TextColumn("·"),
        TextColumn("{task.description}"),
        console=console,
        expand=True,
    )


def print_summary(results: dict, controls_result: dict, elapsed: float,
                  auth_count: int = 0, twofa_count: int = 0):
    table = Table(
        box=box.DOUBLE_EDGE,
        border_style="green",
        show_header=False,
        expand=True,
        padding=(0, 2),
    )
    table.add_column("NO", justify="right", style="grey50", width=3)
    table.add_column("Service", style="white")
    table.add_column("Count", justify="right", style="bold")
    table.add_column("Result", justify="center")

    grand_total = 0
    row_no = 0
    for service, count in results.items():
        count = int(count or 0)
        row_no += 1
        if count > 0:
            table.add_row(str(row_no), service, f"{count:,}", "[green]✔ Erased[/green]")
            grand_total += count
        else:
            table.add_row(str(row_no), service, "0", "[dim]Nothing to delete[/dim]")

    for toggle, state in (controls_result or {}).items():
        row_no += 1
        if state == "turned_off":
            table.add_row(str(row_no), toggle, "—", "[green]✔ Toggled Off[/green]")
        else:
            table.add_row(str(row_no), toggle, "—", "[dim]Already off[/dim]")

    table.add_section()
    table.add_row("", "[bold]TOTAL ERASED[/bold]", f"[bold red]{grand_total:,}[/bold red]", "")
    table.add_row("", "[bold]Auth walls handled[/bold]", str(auth_count), "")
    table.add_row("", "[bold]2FA pauses[/bold]", str(twofa_count), "")
    mins, secs = divmod(int(elapsed), 60)
    table.add_row("", "[bold]Time elapsed[/bold]", f"{mins}m {secs}s", "")

    console.print()
    console.print(Panel(
        table,
        title="[bold green] GHOSTMODE COMPLETE [/bold green]",
        border_style="green",
        padding=(1, 2),
    ))

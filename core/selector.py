"""
Interactive TUI selectors — color-coded to match the Rich dashboard (core/tui.py).

Rendering is handled by core/picker.py (a small prompt_toolkit checkbox/radio engine)
because InquirerPy cannot color choices per-status. Each row's status mirrors the
dashboard exactly: green=clean, yellow=has-data, blue=deletable, red=counts,
grey=manual, cyan headers. The y/N confirm stays on InquirerPy, themed to match.
"""
from InquirerPy import inquirer
from InquirerPy.utils import get_style
from rich.console import Console

from core import picker
from core.picker import Row

console = Console()

_INSTR_MULTI = "Space toggle · A all · I invert · Enter confirm · Ctrl-C cancel"

# Themed style for the InquirerPy confirm prompt (cyan questionmark / green answer).
_CONFIRM_STYLE = get_style(
    {"questionmark": "#56b6c2", "answermark": "#56b6c2", "answer": "#98c379"},
    style_override=False,
)


# ── segment helpers (mirror tui.print_dashboard mapping) ────────────────────────

def _header_seg(category: str) -> list:
    label = f" {category.upper()} "
    line = "──" + label + "─" * max(2, 46 - len(label))
    return [("class:gm.header", line)]


def _row_seg(name: str, statusword: str, status_class: str) -> list:
    return [("", name.ljust(34)), (status_class, f"· {statusword}")]


def _summary_seg(total, n_data, n_action, n_clean, n_ext) -> list:
    sep = ("class:gm.dim", "   ·   ")
    seg = []
    if total:
        seg += [("class:gm.count", f"{total:,} items"), sep]
    seg += [("class:gm.data", f"{n_data} with data"), sep,
            ("class:gm.deletable", f"{n_action} deletable"), sep,
            ("class:gm.clean", f"{n_clean} clean"), sep,
            ("class:gm.manual", f"{n_ext} manual")]
    return seg


# ── selectors ───────────────────────────────────────────────────────────────────

def select_services(scan_results: dict, preselect_all: bool = False) -> list[str]:
    """Checkbox list grouped by category, color-coded by status. Returns chosen names.
    scan_results: {category: {service_name: count_or_sentinel}}"""
    rows: list[Row] = []
    total = n_data = n_clean = n_action = n_ext = 0

    for category, services in scan_results.items():
        if category == "External":
            continue
        rows.append(Row(segments=_header_seg(category), selectable=False, is_header=True))
        for name, count in services.items():
            if count is None:
                rows.append(Row(name, _row_seg(name, "manual", "class:gm.manual"),
                                selectable=False))
                n_ext += 1
            elif count == 0:
                rows.append(Row(name, _row_seg(name, "clean", "class:gm.clean"),
                                selectable=False))
                n_clean += 1
            elif count == -1:
                rows.append(Row(name, _row_seg(name, "has data", "class:gm.data"),
                                selectable=True, enabled=preselect_all))
                n_data += 1
            elif count == -2:
                rows.append(Row(name, _row_seg(name, "deletable", "class:gm.deletable"),
                                selectable=True, enabled=preselect_all))
                n_action += 1
            else:
                rows.append(Row(name, _row_seg(name, f"{count:,} items", "class:gm.count"),
                                selectable=True, enabled=preselect_all))
                total += count
                n_data += 1

    if not any(r.selectable and not r.is_header for r in rows):
        console.print("[green]Nothing to delete — everything is already clean.[/green]")
        return []

    return picker.checkbox(
        "Select services to delete", rows,
        instruction=_INSTR_MULTI,
        summary=_summary_seg(total, n_data, n_action, n_clean, n_ext),
    )


def select_subscriptions(channels: list[dict]) -> list[str]:
    """Checkbox list of YouTube channels. Returns chosen channel hrefs (the key)."""
    if not channels:
        console.print("[yellow]No subscriptions found.[/yellow]")
        return []
    rows = [
        Row(c["href"], [("class:gm.deletable", f"▶ {c['name']}")],
            selectable=True, enabled=False)
        for c in channels
    ]
    return picker.checkbox(
        f"Select channels to UNSUBSCRIBE  ({len(channels)} total)", rows,
        instruction=_INSTR_MULTI,
    )


def select_toggles(states: dict) -> list[str]:
    """Checkbox list of tracking controls currently ON (pre-checked). Returns names."""
    rows = [
        Row(name, _row_seg(name, "currently ON", "class:gm.count"),
            selectable=True, enabled=True)
        for name, state in states.items() if state == "on"
    ]
    if not rows:
        return []
    return picker.checkbox(
        "Select controls to turn OFF", rows,
        instruction="Space toggle · A all · I invert · Enter confirm · Ctrl-C cancel",
    )


def select_account(accounts: list[dict]) -> dict | None:
    """Single-select account picker. Active account is starred."""
    if not accounts:
        console.print("[yellow]No accounts saved.[/yellow]")
        return None
    rows = []
    for acc in accounts:
        if acc["active"]:
            seg = [("class:gm.clean", f"★ {acc['email']} "),
                   ("class:gm.dim", f"[{acc['service']}]  (added {acc['created_at'][:10]})")]
        else:
            seg = [("", f"  {acc['email']} "),
                   ("class:gm.dim", f"[{acc['service']}]  (added {acc['created_at'][:10]})")]
        rows.append(Row(acc, seg, selectable=True))
    default = next((a for a in accounts if a["active"]), accounts[0])
    return picker.select("Select account", rows, default=default)


def select_account_to_delete(accounts: list[dict]) -> dict | None:
    """Single-select picker for removing an account."""
    if not accounts:
        console.print("[yellow]No accounts saved.[/yellow]")
        return None
    rows = [
        Row(acc, [("", f"{acc['email']} "),
                  ("class:gm.dim", f"[{acc['service']}]  (id={acc['id']})")],
            selectable=True)
        for acc in accounts
    ]
    return picker.select("Select account to delete", rows)


def confirm(message: str, default: bool = False) -> bool:
    return inquirer.confirm(
        message=message, default=default, style=_CONFIRM_STYLE,
        qmark="?", amark="✔",
    ).execute()

"""GhostMode version + self-update.

Single source of truth for the running version, the once-a-day GitHub update check,
and the `update` command body. Everything network-facing here is FAIL-SILENT: an
offline box, a 404 (private repo / no token), or a malformed response must never crash
the tool or print a traceback — at worst the update notice simply doesn't appear.

Release workflow (the only way "latest" advances):
    1. Bump __version__ below.
    2. git commit -am "release vX.Y.Z"  &&  git tag vX.Y.Z  &&  git push --tags
    3. gh release create vX.Y.Z --notes "..."
    4. The repo must be PUBLIC (or users supply a token) for the check to resolve.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

__version__ = "1.0.0"

REPO = "KaulikMakwana/ghostmode"
_CACHE = Path.home() / ".ghostmode" / "update_check.json"
_TTL = 24 * 60 * 60          # re-check GitHub at most once per day
_TIMEOUT = 2.5               # seconds; keep startup snappy / fail fast when offline


def _parse(v) -> tuple:
    """'v1.2.3' / '1.2' / junk → (1,2,3) / (1,2,0) / (0,0,0). Tolerant by design."""
    if not v:
        return (0, 0, 0)
    nums = re.findall(r"\d+", str(v))
    nums = (nums + ["0", "0", "0"])[:3]
    return tuple(int(n) for n in nums)


def latest_known() -> str | None:
    """The latest version we last learned from GitHub — cache only, no network."""
    try:
        data = json.loads(_CACHE.read_text())
        return data.get("latest")
    except Exception:
        return None


def update_available() -> bool:
    latest = latest_known()
    return bool(latest) and _parse(latest) > _parse(__version__)


def notice() -> str | None:
    """One-line banner notice, or None when up to date."""
    if not update_available():
        return None
    return (f"⬆ Update available: v{__version__} → v{latest_known()}"
            f"   ·   run: python main.py update")


def refresh_cache(force: bool = False) -> str | None:
    """Throttled, fail-silent GitHub poll. Returns the latest tag (or None).

    No-op (just returns the cached value) unless the cache is older than _TTL or
    `force` is set. Any error — offline, 404, timeout, bad JSON — is swallowed."""
    try:
        if not force and _CACHE.exists():
            age = time.time() - json.loads(_CACHE.read_text()).get("checked_at", 0)
            if age < _TTL:
                return latest_known()

        import requests
        latest = None
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest",
                         timeout=_TIMEOUT)
        if r.status_code == 200:
            latest = r.json().get("tag_name")
        else:
            # No releases yet (404 on /releases/latest) → fall back to tags.
            r = requests.get(f"https://api.github.com/repos/{REPO}/tags",
                             timeout=_TIMEOUT)
            if r.status_code == 200:
                tags = r.json()
                if tags:
                    latest = tags[0].get("name")

        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps({"checked_at": time.time(), "latest": latest}))
        return latest
    except Exception:
        return latest_known()


def _file_version(repo_root: Path) -> str:
    """Read __version__ straight from the on-disk file (post-pull), without re-importing
    — the running process still holds the old constant."""
    try:
        txt = (repo_root / "core" / "version.py").read_text()
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', txt)
        return m.group(1) if m else __version__
    except Exception:
        return __version__


def do_update(console) -> None:
    """`update` command body: git pull --ff-only + reinstall deps. Caller has already
    confirmed (mutates the install)."""
    repo_root = Path(__file__).resolve().parent.parent

    if not (repo_root / ".git").exists():
        console.print("[yellow]Not a git checkout — can't self-update.[/yellow]")
        console.print("Update manually:")
        console.print(f"  [bold]cd {repo_root} && git pull && "
                      f"pip install -r requirements.txt[/bold]")
        return

    before = _file_version(repo_root)

    console.print("[cyan]Pulling latest from GitHub...[/cyan]")
    pull = subprocess.run(["git", "-C", str(repo_root), "pull", "--ff-only"],
                          capture_output=True, text=True)
    out = (pull.stdout + pull.stderr).strip()
    if out:
        console.print(f"[dim]{out}[/dim]")
    if pull.returncode != 0:
        console.print("[red]✘  git pull failed.[/red]  Local edits or a diverged branch "
                      "block a fast-forward — stash/commit them, then retry:")
        console.print(f"  [bold]cd {repo_root} && git stash && python main.py update[/bold]")
        return

    console.print("[cyan]Installing dependencies...[/cyan]")
    pip = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r",
                          str(repo_root / "requirements.txt")],
                         capture_output=True, text=True)
    if pip.returncode != 0:
        console.print(f"[yellow]⚠  dependency install reported an issue:[/yellow]\n"
                      f"[dim]{(pip.stdout + pip.stderr).strip()}[/dim]")

    after = _file_version(repo_root)
    refresh_cache(force=True)

    if _parse(after) > _parse(before):
        console.print(f"\n[bold green]✔  Updated v{before} → v{after}.[/bold green]  "
                      f"Re-run your command to use the new version.\n")
    else:
        console.print(f"\n[green]✔  Already up to date (v{after}).[/green]\n")

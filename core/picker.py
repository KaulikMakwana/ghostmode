"""
GhostMode interactive picker — a small prompt_toolkit checkbox / radio selector with
per-row color, built to match the Rich dashboard (core/tui.py) exactly.

InquirerPy 0.3.4 renders every choice with an empty style class
(`prompts/checkbox.py:91` → `("", choice["name"])`), so it cannot color rows by status.
This engine owns the rendering, so each row carries its own colored segments and the
selection screens read like the dashboard: green=clean, yellow=has-data, blue=deletable,
red=counts, grey=manual, cyan headers.

Called synchronously (between `asyncio.run()` calls) — same context InquirerPy was used
in. `Application.run()` runs its own loop, so it must NOT be awaited inside one.
"""
from dataclasses import dataclass, field

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension as D
from prompt_toolkit.styles import Style

# Palette mirrors core/tui.py (one-dark-ish). Class names are namespaced `gm.*`.
GM_STYLE = Style.from_dict({
    "gm.header":      "bold #56b6c2",
    "gm.clean":       "#98c379",
    "gm.data":        "#e5c07b",
    "gm.deletable":   "#61afef",
    "gm.count":       "bold #e06c75",
    "gm.manual":      "#6c6c6c",
    "gm.pointer":     "bold #56b6c2",
    "gm.marker":      "#98c379",
    "gm.dim":         "#6c6c6c",
    "gm.title":       "bold #56b6c2",
    "gm.instruction": "#7f848e",
})

_MAX_VISIBLE = 18          # rows shown before the window scrolls


@dataclass
class Row:
    """One line in a picker. Headers are non-selectable; everything else is a choice."""
    value: object = None
    segments: list = field(default_factory=list)   # [(style_class, text), ...]
    selectable: bool = True
    enabled: bool = False                           # pre-checked (checkbox only)
    is_header: bool = False


def _first_selectable(rows: list[Row]) -> int:
    for i, r in enumerate(rows):
        if r.selectable and not r.is_header:
            return i
    return 0


class _Picker:
    def __init__(self, title, rows, *, multiselect, instruction=None,
                 summary=None, default=None):
        self.title = title
        self.rows = rows
        self.multiselect = multiselect
        self.instruction = instruction
        self.summary = summary or []
        self.cursor = _first_selectable(rows)
        if default is not None:
            for i, r in enumerate(rows):
                if r.selectable and r.value == default:
                    self.cursor = i
                    break
        self.result = None          # set on accept; stays None on cancel

    # ── rendering ──────────────────────────────────────────────────────────────
    def _fragments(self):
        frags = []
        for i, r in enumerate(self.rows):
            is_cursor = (i == self.cursor)
            if r.is_header:
                frags.append(("", "  "))
                frags.extend(r.segments)
                frags.append(("", "\n"))
                continue
            if not r.selectable:
                # context-only row (clean / manual): align under pointer+marker, no box
                frags.append(("", "    "))
                frags.extend(r.segments)
                frags.append(("", "\n"))
                continue
            if is_cursor:
                frags.append(("[SetCursorPosition]", ""))
                frags.append(("class:gm.pointer", "❯ "))
            else:
                frags.append(("", "  "))
            if self.multiselect:
                if r.enabled:
                    frags.append(("class:gm.marker", "◉ "))
                else:
                    frags.append(("class:gm.dim", "◯ "))
            else:  # radio
                frags.append(("class:gm.marker" if is_cursor else "class:gm.dim",
                              "◉ " if is_cursor else "◯ "))
            frags.extend(r.segments)
            frags.append(("", "\n"))
        if frags and frags[-1] == ("", "\n"):
            frags = frags[:-1]
        return frags

    def _header_fragments(self):
        out = []
        if self.title:
            out.append(("class:gm.title", self.title))
        if self.title and self.instruction:
            out.append(("", "\n"))
        if self.instruction:
            out.append(("class:gm.instruction", "  " + self.instruction))
        return out

    def _header_lines(self):
        return (1 if self.title else 0) + (1 if self.instruction else 0)

    def _footer_fragments(self):
        if not self.summary:
            return []
        return [("", "  ")] + self.summary

    # ── navigation ─────────────────────────────────────────────────────────────
    def _move(self, step):
        n = len(self.rows)
        i = self.cursor
        for _ in range(n):
            i = (i + step) % n
            if self.rows[i].selectable and not self.rows[i].is_header:
                self.cursor = i
                return

    def _toggle(self):
        r = self.rows[self.cursor]
        if r.selectable and not r.is_header:
            r.enabled = not r.enabled

    def _toggle_all(self):
        targets = [r for r in self.rows if r.selectable and not r.is_header]
        new = not all(r.enabled for r in targets) if targets else False
        for r in targets:
            r.enabled = new

    def _invert(self):
        for r in self.rows:
            if r.selectable and not r.is_header:
                r.enabled = not r.enabled

    # ── run ────────────────────────────────────────────────────────────────────
    def run(self):
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _(e): self._move(-1)

        @kb.add("down")
        @kb.add("j")
        def _(e): self._move(1)

        @kb.add("enter")
        def _(e):
            if self.multiselect:
                self.result = [r.value for r in self.rows
                               if r.selectable and not r.is_header and r.enabled]
            else:
                self.result = self.rows[self.cursor].value
            e.app.exit()

        @kb.add("c-c")
        @kb.add("q")
        def _(e):
            self.result = None
            e.app.exit()

        if self.multiselect:
            @kb.add("space")
            def _(e): self._toggle()

            @kb.add("a")
            def _(e): self._toggle_all()

            @kb.add("i")
            def _(e): self._invert()

        body = Window(
            FormattedTextControl(self._fragments, focusable=True, show_cursor=False),
            height=D(min=1, max=_MAX_VISIBLE, preferred=min(len(self.rows), _MAX_VISIBLE)),
            wrap_lines=False,
            always_hide_cursor=True,
        )
        parts = []
        if self._header_lines():
            parts.append(Window(FormattedTextControl(self._header_fragments),
                                height=self._header_lines()))
            parts.append(Window(height=1))   # spacer
        parts.append(body)
        if self.summary:
            parts.append(Window(height=1))   # spacer
            parts.append(Window(FormattedTextControl(self._footer_fragments), height=1))

        app = Application(
            layout=Layout(HSplit(parts), focused_element=body),
            key_bindings=kb,
            style=GM_STYLE,
            full_screen=False,
            mouse_support=False,
        )
        app.run()
        return self.result


def checkbox(title, rows, *, instruction=None, summary=None) -> list:
    """Multi-select. Returns the values of checked rows; [] on cancel."""
    if not any(r.selectable and not r.is_header for r in rows):
        return []
    res = _Picker(title, rows, multiselect=True,
                  instruction=instruction, summary=summary).run()
    return res or []


def select(title, rows, *, default=None):
    """Single-select. Returns the chosen value, or None on cancel."""
    if not any(r.selectable and not r.is_header for r in rows):
        return None
    return _Picker(title, rows, multiselect=False, default=default).run()

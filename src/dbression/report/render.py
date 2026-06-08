"""Live, DBFit-web-UI-style rendering of a single ``.test.md`` page.

The page is rendered to the terminal as a flowing document: prose blocks stay as rendered
Markdown, and each ``### Fixture`` block becomes a bordered card. Cards start *pending*
(grey) and, as the runner executes each fixture, light up green (pass) or red (fail) in
place via :class:`rich.live.Live` — the closest terminal analogue to watching a DBFit wiki
page run in the browser.

Wiring: :class:`RenderObserver` is a :class:`~dbression.runner.RunObserver`. It maps each
``on_fixture_*`` callback for the rendered page to its card and refreshes the live view.
Fixtures from SuiteSetUp / SuiteTearDown (a different ``page_name``) drive a small status
line in the header instead of the cards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from dbression.fixtures.base import FixtureResult
from dbression.parser.ast import Suite, Table
from dbression.runner import CommitMode, RunObserver, SuiteResult, TagFilter, run_suite

_DIRECTIVE_COMMENT_RE = re.compile(r"<!--\s*dbression:.*?-->", flags=re.DOTALL)


def _strip_sql_preamble(details: str) -> str:
    """Drop the leading ``SQL:\\n<sql>\\n\\n`` block from a failure detail.

    The card already shows the SQL as a syntax-highlighted fence, so repeating it in the
    detail block is noise — keep only the Expected/Actual (or Error) part.
    """
    if details.startswith("SQL:"):
        head, sep, rest = details.partition("\n\n")
        if sep:
            return rest
    return details

# state → (border style, marker glyph, marker style)
_STATE_STYLE: dict[str, tuple[str, str, str]] = {
    "pending": ("grey42", "○", "grey42"),
    "running": ("yellow", "▶", "bold yellow"),
    "pass": ("green", "✓", "bold green"),
    "fail": ("red", "✗", "bold red"),
    "skip": ("grey42", "⊝", "grey42"),
}


@dataclass(slots=True)
class _Prose:
    text_md: str


@dataclass(slots=True)
class _Fixture:
    title: str
    body_md: str
    state: str = "pending"
    message: str = ""
    details: str = ""
    duration: float = 0.0


def parse_segments(source: str) -> list[_Prose | _Fixture]:
    """Split ``.test.md`` source into ordered prose / fixture segments.

    Every ``### `` heading starts a fixture card (matching the markdown parser, which treats
    each H3 as one fixture); its body runs up to the next H1/H2/H3 or EOF. Text outside H3
    blocks is prose. ``<!-- dbression:… -->`` directive comments are stripped from prose.
    """
    lines = source.splitlines()
    segments: list[_Prose | _Fixture] = []
    buf: list[str] = []

    def flush_prose() -> None:
        text = _DIRECTIVE_COMMENT_RE.sub("", "\n".join(buf)).strip("\n")
        if text.strip():
            segments.append(_Prose(text))
        buf.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("### "):
            flush_prose()
            title = line[4:].strip()
            body: list[str] = []
            i += 1
            while i < len(lines) and not (
                lines[i].startswith("### ")
                or lines[i].startswith("## ")
                or lines[i].startswith("# ")
            ):
                body.append(lines[i])
                i += 1
            segments.append(_Fixture(title=title, body_md="\n".join(body).strip("\n")))
            continue
        buf.append(line)
        i += 1
    flush_prose()
    return segments


@dataclass
class PageRenderer:
    """Holds the page segments and renders them as a live ``Group`` of cards.

    ``__rich__`` is recomputed on every ``Live`` refresh, so mutating a fixture's ``state``
    and calling ``live.refresh()`` repaints just that card's color.
    """

    page_name: str
    segments: list[_Prose | _Fixture]
    setup_done: int = 0
    setup_failed: bool = False
    finished: bool = False
    passed: int = 0
    failed: int = 0

    fixtures: list[_Fixture] = field(init=False)

    def __post_init__(self) -> None:
        self.fixtures = [s for s in self.segments if isinstance(s, _Fixture)]

    # ── header ────────────────────────────────────────────────────────────────
    def _header(self) -> Text:
        t = Text()
        if not self.finished:
            t.append("▶ ", style="bold yellow")
            t.append(self.page_name, style="bold")
            t.append("  running…", style="yellow")
        else:
            ok = self.failed == 0
            t.append("✓ " if ok else "✗ ", style="bold green" if ok else "bold red")
            t.append(self.page_name, style="bold")
            t.append(
                f"  {self.passed} passed, {self.failed} failed",
                style="green" if ok else "red",
            )
        if self.setup_failed:
            t.append("   (SuiteSetUp failed)", style="bold red")
        elif self.setup_done:
            t.append(f"   setup ✓{self.setup_done}", style="dim")
        return t

    def _card(self, seg: _Fixture) -> Panel:
        border, glyph, glyph_style = _STATE_STYLE[seg.state]
        title = Text()
        title.append(f"{glyph} ", style=glyph_style)
        title.append(seg.title)
        if seg.message:
            title.append(f"  ·  {seg.message}", style="dim")
        if seg.duration:
            title.append(f"  {seg.duration * 1000:.0f}ms", style="dim")
        body: list[RenderableType] = []
        if seg.body_md:
            body.append(Markdown(seg.body_md))
        if seg.state == "fail" and seg.details:
            body.append(Text(_strip_sql_preamble(seg.details), style="red"))
        inner: RenderableType = Group(*body) if body else Text("")
        return Panel(inner, title=title, title_align="left", border_style=border)

    def __rich__(self) -> Group:
        items: list[RenderableType] = [self._header(), Text("")]
        for seg in self.segments:
            if isinstance(seg, _Prose):
                items.append(Markdown(seg.text_md))
            else:
                items.append(self._card(seg))
        return Group(*items)

    # ── mutations driven by the observer ───────────────────────────────────────
    def mark_running(self, idx: int) -> None:
        if 0 <= idx < len(self.fixtures):
            self.fixtures[idx].state = "running"

    def mark_result(self, idx: int, result: FixtureResult, duration: float) -> None:
        if not (0 <= idx < len(self.fixtures)):
            return
        seg = self.fixtures[idx]
        seg.state = "pass" if result.passed else "fail"
        seg.message = result.message
        seg.details = result.details
        seg.duration = duration

    def finalize(self, passed: int, failed: int) -> None:
        for seg in self.fixtures:
            if seg.state in ("pending", "running"):
                seg.state = "skip"
                seg.message = "not run"
        self.passed = passed
        self.failed = failed
        self.finished = True


class RenderObserver(RunObserver):
    """Drive a :class:`PageRenderer` from runner callbacks, refreshing a ``Live`` view."""

    def __init__(self, renderer: PageRenderer, live: Live) -> None:
        self.r = renderer
        self.live = live
        self._idx = -1

    def on_fixture_start(self, page_name: str, table: Table) -> None:
        if page_name != self.r.page_name:
            return  # setup/teardown fixture — header tracks those on completion
        self._idx += 1
        self.r.mark_running(self._idx)
        self.live.refresh()

    def on_fixture_end(
        self, page_name: str, table: Table, result: FixtureResult, duration: float
    ) -> None:
        if page_name != self.r.page_name:
            if not result.passed:
                self.r.setup_failed = True
            else:
                self.r.setup_done += 1
            self.live.refresh()
            return
        self.r.mark_result(self._idx, result, duration)
        self.live.refresh()


def render_run(
    console: Console,
    suite: Suite,
    engine,
    source: str,
    commit_mode: CommitMode = "test",
    tag_filter: TagFilter | None = None,
) -> SuiteResult:
    """Run a single-page suite and render it live as a DBFit-style colored document.

    `source` is the raw ``.test.md`` text of the page being rendered. The suite is expected
    to contain exactly one test page (single-file run); its SuiteSetUp/SuiteTearDown still
    execute and drive the header status line.
    """
    page_name = suite.pages[0].name if suite.pages else suite.name
    renderer = PageRenderer(page_name=page_name, segments=parse_segments(source))
    with Live(
        renderer,
        console=console,
        auto_refresh=False,
        vertical_overflow="visible",
    ) as live:
        live.refresh()
        observer = RenderObserver(renderer, live)
        result = run_suite(
            suite,
            engine,
            commit_mode=commit_mode,
            tag_filter=tag_filter,
            observer=observer,
        )
        # Reflect this page's own pass/fail (not sub-suites — single-file has none).
        page = result.pages[0] if result.pages else None
        passed = sum(1 for t in page.tables if t.result.passed) if page else 0
        failed = sum(1 for t in page.tables if not t.result.passed) if page else 0
        renderer.finalize(passed=passed, failed=failed)
        live.refresh()
    return result

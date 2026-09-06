"""Repository-wide guards on the app's visual register.

Three criteria from the shell rework are project-wide rather than per-screen,
so they are enforced by walking the source tree rather than by rendering a
component: no emoji anywhere in the app, no marketing-era chrome left in the
stylesheet, and exactly one accent colour reachable only through the theme
primary.

Each is written as a walk rather than a checklist of known offenders. A sweep
done by hand passes once and then rots; the point of these three is that a
re-introduced emoji, a gradient that arrives with an unreviewed component, or a
hard-coded accent fails the suite on the commit that adds it.
"""

from __future__ import annotations

import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "spec4"
LAYOUTS = SRC / "layouts"
STYLESHEET = SRC / "assets" / "v3.css"


# ---------------------------------------------------------------------------
# Emoji
# ---------------------------------------------------------------------------

# The emoji and pictographic ranges, per UTS #51. Written as ranges rather than
# as the set of characters this sweep happened to remove, so a *different*
# emoji arriving later still fails.
#
# What is deliberately **not** here: the arrow block (U+2190–U+21FF), the
# box-drawing block, and the typographic punctuation the app uses in prose and
# in the status bar — `— … – · × § • ≈`. Those are text, not pictographs; `·`
# is the status bar's own separator and `—` appears 1700 times in docstrings.
# ASCII is excluded for the same reason: `#`, `*` and the digits carry the
# Emoji property in UTS #51 and are obviously not what the criterion means.
_EMOJI_RANGES = (
    (0x2139, 0x2139),  # information source
    (0x20E3, 0x20E3),  # combining enclosing keycap
    (0x203C, 0x203C),  # double exclamation mark
    (0x2049, 0x2049),  # exclamation question mark
    (0x2300, 0x23FF),  # misc technical: clocks, media controls
    (0x2460, 0x24FF),  # enclosed alphanumerics used as pictographs
    (0x2600, 0x27BF),  # misc symbols and dingbats
    (0x2B00, 0x2BFF),  # misc symbols and arrows: the emoji arrows and stars
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3297),
    (0x3299, 0x3299),
    (0xFE0F, 0xFE0F),  # variation selector-16, the emoji presentation flag
    (0x1F000, 0x1FAFF),  # the supplementary pictographic planes
)

_EMOJI = re.compile(
    "[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _EMOJI_RANGES) + "]"
)


def _source_files() -> list[pathlib.Path]:
    """Every .py and .css file under src/spec4/, with nothing excluded."""
    return sorted(
        p
        for p in SRC.rglob("*")
        if p.suffix in (".py", ".css") and "__pycache__" not in p.parts
    )


class TestNoEmoji:
    def test_the_walk_actually_finds_the_source(self) -> None:
        """A guard that silently walks an empty tree passes forever."""
        files = _source_files()
        assert len(files) > 40
        assert STYLESHEET in files

    def test_no_emoji_anywhere_in_the_app(self) -> None:
        """The sweep is global: layouts, callbacks, agent strings and assets.

        An emoji beside a word was deleted and the word kept; an emoji standing
        alone as a label or indicator was replaced by a short text label saying
        what it meant. Nothing was replaced by an icon component or an icon
        font — `dash-iconify` is installed but unused, and stays that way.
        """
        offenders = []
        for path in _source_files():
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                for match in _EMOJI.finditer(line):
                    char = match.group()
                    offenders.append(
                        f"{path.relative_to(SRC.parent.parent)}:{lineno} "
                        f"U+{ord(char):04X} in {line.strip()[:80]!r}"
                    )
        assert not offenders, "emoji found in the app:\n" + "\n".join(offenders)

    def test_the_pattern_would_catch_one(self) -> None:
        """The guard's own regression test: an inert pattern proves nothing."""
        assert _EMOJI.search("\U0001f680 Deployer")  # rocket
        assert _EMOJI.search("⚠️ Heads up")  # warning sign
        assert _EMOJI.search("✅ done")  # heavy check mark
        assert not _EMOJI.search("Continue to Designer →")  # a plain arrow
        assert not _EMOJI.search("dir · round v1")  # the status separator


# ---------------------------------------------------------------------------
# Marketing-era chrome
# ---------------------------------------------------------------------------

# The removal list, as property patterns rather than as class names — a rule
# reintroduced under a new selector is the same rule. Each entry is
# (what it implements, the pattern that finds it).
_BANNED_CSS = (
    ("gradient text", re.compile(r"background-clip\s*:\s*text", re.I)),
    ("gradient text", re.compile(r"-webkit-text-fill-color\s*:\s*transparent", re.I)),
    ("gradient fill", re.compile(r"(linear|radial|conic)-gradient\s*\(", re.I)),
    ("grid background", re.compile(r"background-image\s*:", re.I)),
    ("grid background", re.compile(r"background-size\s*:", re.I)),
    ("hover transform", re.compile(r":hover[^{]*\{[^}]*transform\s*:", re.I | re.S)),
    ("hover glow", re.compile(r":hover[^{]*\{[^}]*box-shadow\s*:", re.I | re.S)),
    ("button glow", re.compile(r"box-shadow\s*:", re.I)),
    ("text glow", re.compile(r"text-shadow\s*:", re.I)),
)


class TestNoMarketingChrome:
    def test_the_stylesheet_is_where_we_think_it_is(self) -> None:
        assert STYLESHEET.is_file()

    def test_no_marketing_era_declaration_survives(self) -> None:
        """Deleted at the source, not overridden.

        An override only reaches the components that receive it, which is the
        exact failure mode this guards: a style bleeding back in through a
        component nobody reviewed. There is no allow-list here, so a rule that
        genuinely needs a shadow has to argue for itself in review rather than
        slip in behind an existing one.
        """
        css = STYLESHEET.read_text(encoding="utf-8")
        offenders = []
        for what, pattern in _BANNED_CSS:
            found = pattern.search(css)
            if found:
                offenders.append(f"{what}: {found.group()!r}")
        assert not offenders, "marketing-era CSS in v3.css:\n" + "\n".join(offenders)

    def test_the_patterns_would_catch_them(self) -> None:
        """One sample per checklist item, so no pattern can go inert."""

        def caught(css: str) -> bool:
            return any(pattern.search(css) for _, pattern in _BANNED_CSS)

        assert caught(".kicker{background-clip: text}")
        assert caught(".hero h1{-webkit-text-fill-color: transparent}")
        assert caught(".hero{background: linear-gradient(#000, #fff)}")
        assert caught(".bg{background-image: url(grid.svg)}")
        assert caught(".bg{background-size: 40px 40px}")
        assert caught(".card:hover{transform: translateY(-2px)}")
        assert caught(".btn:hover{box-shadow: 0 0 12px #39FF14}")
        assert caught(".btn{box-shadow: 0 0 12px #39FF14}")
        assert caught(".logo{text-shadow: 0 0 8px #39FF14}")
        # …and the register that replaced them is not itself flagged.
        assert not caught(STYLESHEET.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The single accent
# ---------------------------------------------------------------------------

_SPEC4_GREEN = re.compile(r"#39FF14", re.I)
_WORDMARK_BLUE = re.compile(r"#1E88E5", re.I)


class TestSingleAccent:
    def test_no_layout_module_hard_codes_the_accent(self) -> None:
        """The accent is reachable only through the theme primary (D-LR2).

        A component that wants the accent omits `color` and inherits it; one
        that needs it in CSS reaches it as `--mantine-primary-color-filled`.
        Neither route lets a layout module name the green, so a per-view accent
        cannot drift from the rest of the app.
        """
        offenders = [
            str(p.relative_to(SRC.parent.parent))
            for p in sorted(LAYOUTS.rglob("*.py"))
            if "__pycache__" not in p.parts
            and _SPEC4_GREEN.search(p.read_text(encoding="utf-8"))
        ]
        assert not offenders, f"accent hard-coded in {offenders}"

    def test_the_accent_is_written_down_exactly_once(self) -> None:
        """One definition, in app_constants, feeding the theme primary."""
        from spec4.app_constants import DARK_THEME, SPEC4_GREEN

        named = [
            str(p.relative_to(SRC.parent.parent))
            for p in _source_files()
            if _SPEC4_GREEN.search(p.read_text(encoding="utf-8"))
        ]
        assert named == ["src/spec4/app_constants.py"]
        assert SPEC4_GREEN == "#39FF14"
        assert DARK_THEME["primaryColor"] in DARK_THEME["colors"]

    def test_the_second_colour_appears_only_in_the_wordmark(self) -> None:
        """`#1E88E5` is the wordmark's blue and nothing else's.

        Pinned to the `.logo-spec` rule specifically, not merely to a count:
        one occurrence that had migrated to some other component would satisfy
        a count and break the criterion.
        """
        css = STYLESHEET.read_text(encoding="utf-8")
        assert len(_WORDMARK_BLUE.findall(css)) == 1
        assert re.search(r"\.logo-spec\s*\{[^}]*#1E88E5", css, re.I)

        elsewhere = [
            str(p.relative_to(SRC.parent.parent))
            for p in sorted(LAYOUTS.rglob("*.py"))
            if "__pycache__" not in p.parts
            and _WORDMARK_BLUE.search(p.read_text(encoding="utf-8"))
        ]
        assert not elsewhere, f"wordmark blue used in {elsewhere}"

    def test_no_layout_module_passes_a_local_accent_colour(self) -> None:
        """`color=` survives only for semantics the accent does not carry.

        Red for errors, yellow and orange for warnings, gray for neutral. A
        `color` naming a hex value, the theme primary key, or a hue that reads
        as an accent is the drift this catches.
        """
        allowed = {"red", "yellow", "orange", "gray"}
        offenders = []
        for path in sorted(LAYOUTS.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), 1):
                for value in re.findall(r'\bcolor="([^"]+)"', line):
                    if value not in allowed:
                        rel = path.relative_to(SRC.parent.parent)
                        offenders.append(f"{rel}:{lineno} color={value!r}")
        assert not offenders, "local accent colour in:\n" + "\n".join(offenders)

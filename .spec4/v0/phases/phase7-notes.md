# Phase 7 notes — Global Register Audit

Recorded 2026-09-05 on branch `look-rework`, closing the shell rework's
project-wide criteria: the app-wide emoji sweep, the marketing-era removal list
reviewed as a checklist against every screen, and proof that no component sets
an accent colour of its own.

---

## 1. Quality gate — measured against the Phase 1 baseline

| Gate | Command | Phase 1 baseline | This phase |
| --- | --- | --- | --- |
| Tests | `uv run pytest` | 3028 passed | **3258 passed, 0 failed** |
| Lint | `uv run ruff check src/ tests/` | clean | **clean** |
| Types | `uv run mypy src/` | 38 errors / 15 files | **38 errors / 15 files** |

At or better than baseline on all three. The mypy count is unchanged and the
distribution is identical — no error was fixed, none was added, and no
`# type: ignore` was introduced.

`tests/test_cost_summary.py` and `tests/test_agent_llm_selection.py` are
**byte-for-byte unmodified** (`git status --porcelain` on both is empty) and
both pass, so the two relative-ordering pins from Phase 1 §5 —
`chat-scroll-area < cost-summary-card < chat-token-count`, and
`_child_ids(footer) == ["btn-agent-llm-chip", "chat-status-line"]` — still hold.

### The one existing test that had to change

`tests/agentifier/test_agentifier_orchestrator.py:510` asserted
`"⚠️" in display`. That glyph *was* the tier-mismatch marker, so the assertion
had to follow the marker to its replacement word:

```python
assert "(mismatch)" in display  # the marker, now a word (phase 7)
```

Nothing else in `tests/` was renamed, deleted or reordered. Every other test
that touched a swept string asserted on a substring that survives the removal
(`"Scan complete"`, `"Web search disabled"`, `"Priority analysis unavailable"`,
`"Heads-up"`), which is why the suite went green on the second run.

---

## 2. The emoji sweep

### What counts as an emoji here

The criterion is enforced by a walk, not by a list of what was removed, so it
needed a definition sharp enough to write down. `tests/test_visual_register.py`
uses the UTS #51 emoji and pictographic ranges:

```
U+2139  U+20E3  U+203C  U+2049
U+2300–U+23FF   misc technical (clocks, media controls)
U+2460–U+24FF   enclosed alphanumerics used as pictographs
U+2600–U+27BF   misc symbols and dingbats
U+2B00–U+2BFF   misc symbols and arrows (the emoji arrows and stars)
U+3030 U+303D U+3297 U+3299
U+FE0F          variation selector-16, the emoji presentation flag
U+1F000–U+1FAFF the supplementary pictographic planes
```

**Deliberately outside the ban**, and this is the line the round drew:

- **The arrow block, U+2190–U+21FF.** `→` appears 98 times, `←` 10, `↺` 8,
  `↔` 3, `↑` once. They are directional typography, not pictographs, and the
  overwhelming majority are prose in docstrings, comments and LLM prompts
  (`Scout → Composer`, `name→id map`). Banning them would have meant rewriting
  a hundred lines of documentation to satisfy a criterion about decoration.
- **Punctuation and box drawing** — `— … – · × § • ′ ≈ ─ ├ │ └`. `·` is the
  status bar's own separator, and `—` occurs 1,729 times.
- **ASCII.** `#`, `*` and the digits carry the Emoji property in UTS #51 and
  are obviously not what the criterion means.

`test_the_pattern_would_catch_one` pins both sides of that line so the pattern
cannot quietly go inert: a rocket, a warning sign and a heavy check mark match;
`"Continue to Designer →"` and `"dir · round v1"` do not.

### The census

Before: **29 files, 192 hits** across layouts, callbacks, agent-authored
strings and prompts. After: **zero** emoji or pictographic characters under
`src/spec4/`. What remains is the punctuation and arrow set above.

### Where an emoji sat beside a word — deleted, word unchanged

| File | Was | Now |
| --- | --- | --- |
| `layouts/__init__.py` | `📁 {d.name}` | `{d.name}` |
| `layouts/__init__.py` | `✓ Select This Directory` | `Select This Directory` |
| `layouts/__init__.py` | `📁 Create a new subdirectory here` | `Create a new subdirectory here` |
| `layouts/_chat.py` | `🔍 CodeScanner` · `🧠 Brainstormer` · `🤖 Agentifier` · `🎨 Designer` · `⚙️ StackAdvisor` · `📋 Phaser` · `🚀 Deployer` | the seven names alone |
| `layouts/_chat.py` | `⏩ Fast Forward` | `Fast Forward` |
| `layouts/_chat.py` | `💾 Download …` ×6, `🔄 Re-scan Project` | the labels alone |
| `layouts/_shared.py` | `💵 Estimated cost` | `Estimated cost` |
| `layouts/designer.py` | `⛶ Full Screen`, `✏ Refine` ×2, `✓ Approve`, `🎨 Designer`, `ℹ️ How to use Designer` | the labels alone |
| `agentifier/agentifier.py` | `### 🧭 …`, `### 🧬 Composer`, `### 🎚️ Prioritizer`, `### 🔍 Scout`, `### 🔗 Linker`, `### ⚠️ …` ×2, `✅ Scout surfaced`, `✅ Tier analysis complete`, `ℹ️ **Heads-up:**`, `💾 Download ai_features.json`, `⏩ **Fast Forward**` | the headings and sentences alone |
| `agents/code_scanner.py` | `⚠️ No project directory…`, `🔍 **{mode}**`, `✅ Scan complete` | the sentences alone |
| `agents/deployer.py` | `👋 I'm **Deployer**`, `✓ Your deployment plan…` ×2, `⚠️ **Heads up:**` | the sentences alone |
| `agents/_seam_check.py` | `⚠️ **Possible data-flow seams…**` | the heading alone |
| `llm.py` | `> ⚠️ Web search disabled…`, `*🔍 Searching: {query}*`, `> ⚠️ {result}` | the lines alone |

`llm.py`'s `> ⚠️ {result}` needed no substitute: `result` already begins
`"Search failed:"` or `"No search tool"`, so the glyph was decorating a line
that already said what went wrong.

### Where an emoji stood alone — what it meant, and the word that replaced it

Five glyphs carried information nothing else on screen carried. Each was
recorded before deletion and replaced by a **short text label, never an icon**:

| Site | Glyph | What it indicated | Now |
| --- | --- | --- | --- |
| `agentifier.py:734` | `⚠️` | the decided tier differs from the recommended one | `" (mismatch)"` |
| `agentifier.py:2527` | `⚠️` | the line that follows lists blocking problems | `"Problems: "` |
| `layouts/_chat.py:68` | `✓ {label}` | this pipeline stage is finished | `"{label} done"` |
| `layouts/_chat.py:259` | `ⓘ` | opens the Fast Forward explainer | `"About Fast Forward"` |
| `layouts/designer.py:177, 486` | `✕` | delete this screenshot / refine image | `"Remove"` |

The done pill mattered most. Its three states are *active* (filled), *done*
(light) and *unreached* (outline); the tick was the only thing that named the
middle one, and a variant alone is not a label.

Two of these sat on a `dmc.ActionIcon`, which is a fixed square and cannot hold
a word, so those two controls became `dmc.Button` in the same slot with the
same id, the same `variant`, and the same `color`. Ids are unchanged
(`btn-ff-info`, and the two pattern-matched `…-delete` ids), which is what
keeps `tests/test_fast_forward.py` and the co-presence guard passing.

`_setup.py` had `icon="⚠️"` on two alerts. There the glyph was redundant rather
than load-bearing — each alert already has `title="No Image Support"` /
`title="No Tool Support"` and `color="yellow"` — so the `icon` prop was dropped
rather than given a word that would repeat the title.

### No icons were added

`dash-iconify` is still an installed dependency and is still imported by
nothing. No icon component and no icon font entered the app in this sweep.

---

## 3. The marketing-era removal checklist, reviewed against every screen

This is the list, and this is the review. **Screens** are the families the
co-presence guard renders (Phase 1 §4): every one of the 54 screens falls into
one of these twelve rows.

| Screen | drawer | footer | landing page | grid bg | kicker | gradient text | hero spacing | card hover | button glow | emoji |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| project-view (`/agents`) | — | — | — | — | — | — | — | — | — | clear |
| directory picker (`/dir`, and root) | — | — | — | — | — | — | — | — | — | **swept** |
| setup: provider | — | — | — | — | — | — | — | — | — | clear |
| setup: model | — | — | — | — | — | — | — | — | — | **swept** |
| setup: web search | — | — | — | — | — | — | — | — | — | **swept** |
| project mode question | — | — | — | — | — | — | — | — | — | clear |
| chat frame (6 agents × 4 states) | — | — | — | — | — | — | — | — | — | **swept** |
| chat: retry panel | — | — | — | — | — | — | — | — | — | clear |
| chat: breadth panel | — | — | — | — | — | — | — | — | — | clear |
| model gate card (5 states) | — | — | — | — | — | — | — | — | — | clear |
| designer: gate | — | — | — | — | — | — | — | — | — | clear |
| designer: wizard + 14 steps | — | — | — | — | — | — | — | — | — | **swept** |

`—` = the element is not present on that screen. `swept` = an emoji was found
there and removed; `clear` = none was there to begin with.

The first eight columns are uniform for a structural reason worth writing down:
**the drawer, the footer, the landing page and the grid background were shell
elements, not screen elements.** They lived in `app.layout`, so removing them in
Phase 2 removed them from all 54 screens at once. `tests/test_status_bar.py`
pins that as `_REMOVED_SHELL_IDS` — `nav-drawer`, `nav-overlay`, `nav-burger`,
`nav-close-btn`, `blueprint-grid` — and asserts none of them is reachable from
`app.layout`. `blueprint-grid` now appears **nowhere** in `src/spec4/`.

Kicker labels, gradient text, hero spacing, card hover effects and button glows
were all CSS, and all of them were deleted from the stylesheet rather than
overridden — see §4. A grep for `kicker`, `hero`, `glow`, `gradient` and
`drawer` across `src/spec4/` now returns only this round's own prose: the
D-LR7 comment in `layouts/__init__.py` that names the checklist, and one
unrelated hit in `designer.py:522` where "hero section" is example text inside a
placeholder the developer types over.

**One `<footer>` remains, and it is not a footer.** `app.py:57` wraps
`{%config%}{%scripts%}{%renderer%}` in `<footer>` because that is Dash's
`index_string` contract for the bootstrap payload. It renders nothing and
carries no content. It is the only `<footer>` element in the app.

---

## 4. The stylesheet grep

Grepped `src/spec4/assets/v3.css` for every property that could implement a
checklist item:

| Looked for | Found |
| --- | --- |
| `background-clip: text`, `-webkit-text-fill-color: transparent` | none |
| `linear-gradient(`, `radial-gradient(`, `conic-gradient(` | none |
| `background-image:`, `background-size:` | none |
| `transform:` inside a `:hover` block | none |
| `box-shadow:` anywhere, `text-shadow:` anywhere | none |

**Nothing survived to delete.** Phase 2 removed these at the source when it
replaced the header, and the four surfaces built in Phases 3–6 were written
against the mock's flat register, so none of them reintroduced one. The file's
six `:hover` rules are all colour or border-colour changes — no lift, no
shadow, no glow.

Since a grep that finds nothing is a grep nobody can repeat, the same patterns
are now `_BANNED_CSS` in `tests/test_visual_register.py`, asserted against the
live stylesheet. `test_the_patterns_would_catch_them` feeds each pattern a
sample it must match *and* re-checks that the real `v3.css` matches none of
them, so a pattern cannot rot into one that passes by matching nothing.

There is no allow-list. A rule that genuinely needs a shadow has to argue for
itself in review rather than slip in behind an existing one.

---

## 5. The single accent

### What the grep of `src/spec4/layouts/` found

No layout module passes a hex colour to a `color` prop, and no `color=` names a
hue that reads as an accent. Every `color=` in `src/spec4/layouts/` is one of
four semantic values the accent does not carry, exactly as D-LR2 allows:

```
color="gray"   ×20   neutral
color="yellow" × 8   warn
color="red"    × 7   error
color="orange" × 6   warn
```

`c="dimmed"` ×30 is Mantine's secondary text token, not a colour.

### Two accents that had drifted, now removed

1. **`layouts/designer.py:790`** — the "How to use Designer" accordion drew its
   border and its 3px left rule in `var(--mantine-color-blue-4)`. That was the
   last per-view accent in the app: a blue edge on one panel of one wizard step,
   inheriting nothing. Both halves now take
   `var(--mantine-primary-color-filled)`, so a re-themed accent lands here too.
2. **`assets/v3.css:141`** — `.logo-4` hard-coded `#39FF14`. The `4` of the
   wordmark **is** the accent, so it now reaches it the way every other accented
   surface does, through the theme primary.

Also neutralised: `layouts/designer.py`'s `_PLACEHOLDER_HTML` drew its `<h1>` in
`#42a5f5`. That document is served into an iframe and cannot see the theme, so
there was nothing for it to inherit — the heading takes the plain text colour
`#f5f5f7` instead, and the app is left with no second accent anywhere.

### Where the two colours are written down now

| Literal | Occurrences under `src/spec4/` (`.py` + `.css`) |
| --- | --- |
| `#39FF14` | **one** — `app_constants.py:39`, `SPEC4_GREEN`, feeding `SPEC4_GREEN_SHADES[5]` and the theme `primaryColor` |
| `#1E88E5` | **one** — `v3.css`, the `.logo-spec` rule, which is the wordmark |

Both are asserted, and the blue is pinned to the `.logo-spec` rule specifically
rather than merely counted: one occurrence that had migrated to some other
component would satisfy a count while breaking the criterion.

`assets/favicon.svg` carries both literals and is not covered by the walk. It is
the wordmark rendered as a 32px icon, outside any stylesheet or theme — an SVG
served to the browser as a file has no `var()` to reach. It is the wordmark, so
it is the exception the criterion already grants, not a second place the accent
appears on screen.

`DARK_THEME["colors"]["blue"]` stays registered. Nothing passes `color="blue"`
any more, but shade 5 of that palette is `#1e88e5` — it *is* the wordmark's hue,
declared once in the theme, and the two existing tests that pin its shape
(`test_has_blue_palette`, `test_blue_palette_has_ten_shades`) were left alone.

---

## 6. Confinement — the four screens that keep their layouts

The sweep changed strings on these screens. It changed no layout on any of
them, which was the constraint.

| Screen | What changed | What did not |
| --- | --- | --- |
| chat frame | 7 pill labels, the done pill's text, 6 download labels, `Fast Forward`, `Re-scan Project`; `btn-ff-info` became a `Button` in the same slot | the frame, the action row, the footer row, the composer, every id |
| setup wizard | two alerts lost a redundant `icon` prop | the three steps, their fields, their ordering |
| gate card | nothing — it had no emoji | everything |
| Designer wizard | the title, `Full Screen`, `Refine` ×2, `Approve`, the how-to label; the two `✕` icons became `Remove` buttons with the same ids; the accordion's blue edge became the theme primary | the 14 steps, the stepper, the preview, every id |

Verified by running the screens' own suites, not by reading the diff:
`test_cost_summary.py`, `test_agent_llm_selection.py`, `test_status_bar.py`,
`test_callback_co_presence.py`, `test_designer.py`,
`test_designer_fullscreen.py`, `test_fast_forward.py`,
`test_setup_search_provider.py` — **396 passed**. The co-presence guard is the
load-bearing one: it derives each screen's ids by rendering it, so a control
that changed component type but kept its id passes, and one that lost its id
does not.

---

## 7. Visual conformance against the mock

`uv run python scripts/screenshot_ui.py` against the dev server, compared side
by side with `.spec4/v0/design/mock.html` rendered at the same 1280×900.

**Matches.** Status bar at 40px on `--panel` with a 1px bottom rule; wordmark
blue-`Spec` + accent-`4`; mono context line with `·` separators; nav with
`Project` in the accent under a 1px accent underline and `Settings` / `Docs`
dimmed; version in mono behind a 16px left border. Below it the mono
`.spec4/…/` heading, the zebra-striped tree with lane colours and a
right-aligned status only where there is one, the agent table with the mock's
five columns and its right-aligned 24px actions, and the cost panel closing the
view. Empty model and token cells on a not-yet-run agent are genuinely empty,
as the mock draws them. No emoji anywhere on either screen.

Root (`/`) resolved to the directory picker, since no working directory was
remembered — D-LR6's behaviour, and the in-app landing page is gone.

**One delta, and it is not this phase's.** The mock's `.view` caps content at
`max-width: 1100px`; the app wraps `page-content` in `dmc.Container(size="xl")`,
which is Mantine's 1320px. At a 1280px viewport the app's tree and table run to
the window edge while the mock's stop at 1100px.

It was left alone deliberately. That container is the shell's, so narrowing it
would change the width of the chat frame, the setup wizard, the gate card and
the Designer wizard — the four screens this round is explicitly required to
leave alone. It is a one-token change (`size="1100px"`) for whoever takes the
shell next, and it should land in the same round that re-checks those four
screens.

---

## 8. What was added to `tests/`

One new file, `tests/test_visual_register.py`, ten cases in three classes:

- **`TestNoEmoji`** — walks every `.py` and `.css` under `src/spec4/` with
  nothing excluded, and reports offenders as `path:line U+XXXX` rather than a
  bare boolean. `test_the_walk_actually_finds_the_source` guards the walk
  itself, because a guard that silently walks an empty tree passes forever.
- **`TestNoMarketingChrome`** — the §4 patterns against the live stylesheet,
  plus the self-test that keeps them from going inert.
- **`TestSingleAccent`** — no `#39FF14` in any layout module; the accent named
  in exactly one file; `#1E88E5` present once and in the `.logo-spec` rule; and
  no layout module passing a `color` outside the four semantic values.

No existing test file was reorganised, and no id enumeration was touched.

---

## 9. D-LR7 — the standing gate

Recorded as the module docstring of `src/spec4/layouts/__init__.py`, which is
the file anyone adding a screen opens first.

> If an element on screen is not a fact, a command, an artifact, or a control,
> it does not ship.

The removal list is the shorthand; that sentence is what it is shorthand for. A
pictograph beside a word is none of the four — the word already said it. A glow,
a gradient or a lift on hover is none of the four either; it decorates a control
that was already legible.

Three items on the list are now machine-checked and three-quarters of it is
still the reviewer's job, which is the honest split: a checklist a machine can
run is the part that stops rotting, and the part that stops being read.

`D-LR5` remains unused; this round's decisions run `D-LR1`, `D-LR2`, `D-LR3`,
`D-LR4`, `D-LR6`, `D-LR7`, plus `D-AR1`–`D-AR3` in the agent rows.

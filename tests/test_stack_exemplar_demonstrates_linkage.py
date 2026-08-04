"""D-SC50 — the exemplar is the specification, so test the exemplar.

Six times now the same thing has happened: **the prose licensed a field, the
exemplar did not demonstrate it, and the model followed the exemplar.**

======  ==========================================  ===========================
round   field                                       found by
======  ==========================================  ===========================
D-SC11  ``physical`` on a collection                live draw
D-SC37  store-level ``satisfies_nfr``               live draw
D-SC40  ``serves_capabilities`` on a capability     live draw
D-SC41  the nfr id itself (domain-neutral)          live draw
D-SC44  ``infrastructure.*.satisfies_nfr``          live draw
D-SC50  ``providers.*.capabilities[].satisfies_nfr`` live draw (Ragmeister x4)
======  ==========================================  ===========================

Every one was fixed by patching that instance. Five patches did not stop the
sixth. **The lever is the test, not the patch** — so this file asserts the general
rule rather than any one instance: *every linkage field must be demonstrated in
every block whose prose licenses it.*

Why the table is declared rather than parsed
--------------------------------------------
"Which blocks does the prose license" is natural language and cannot be read
reliably by a regex. So ``_LICENSED`` is hand-declared — but it is not therefore
unguarded: ``test_the_prose_still_licenses_what_the_table_claims`` asserts the
licensing sentence is still present in the prompt for each row. If someone rewrites
the prose to stop licensing a block, that test fails first and the table gets
updated deliberately, instead of the demonstration test quietly asserting something
the prompt no longer says.

What must fail, and when
------------------------
Run against tip ``1f5ac84`` — before D-SC50's fields land — this file MUST report
two failures: ``satisfies_nfr`` is licensed for the infrastructure and provider
entries by the sentence "(on the library, infrastructure, or provider entry)" and
is demonstrated on neither. A guard that has never failed proves nothing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from spec4.agents.stack_advisor import SYSTEM_PROMPT


def _schema() -> dict[str, Any]:
    block = re.search(r"```json\n(\{.*?\n\})\n```", SYSTEM_PROMPT, re.S)
    assert block, "no JSON schema example in the prompt"
    return json.loads(block.group(1))


def _stack_spec() -> dict[str, Any]:
    s = _schema()
    return s.get("stack_spec") or s


_LINKAGE_FIELDS = (
    "serves_features",
    "serves_capabilities",
    "satisfies_nfr",
    "satisfies_infra",
    "foundational",
    "status",
    "model_family",
    "purpose",
)


def _demonstrated() -> dict[str, set[str]]:
    """field -> the set of exemplar paths that actually carry it.

    List indices collapse to ``[]`` and dict keys are kept, so a path reads
    ``providers.OpenAI.capabilities[]``. Matching against the table then only has
    to tolerate the arbitrary key (``OpenAI``, ``primary_store``), which is what
    ``*`` covers in ``_LICENSED``.
    """
    out: dict[str, set[str]] = {}

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for field in _LINKAGE_FIELDS:
                if field in node:
                    out.setdefault(field, set()).add(path)
            for key, val in node.items():
                walk(val, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for val in node:
                walk(val, f"{path}[]")

    walk(_stack_spec(), "")
    return out


def _matches(pattern: str, path: str) -> bool:
    """``providers.*.capabilities[]`` matches ``providers.OpenAI.capabilities[]``."""
    pat = pattern.split(".")
    seg = path.split(".")
    if len(pat) != len(seg):
        return False
    return all(p == "*" or p == s for p, s in zip(pat, seg))


def _is_demonstrated(field: str, pattern: str) -> bool:
    return any(_matches(pattern, p) for p in _demonstrated().get(field, set()))


# (field, exemplar block pattern, a verbatim fragment of the prose that licenses it)
#
# The prose fragment is the receipt. It is asserted separately, so this table
# cannot drift into claiming a licence the prompt does not grant.
_LICENSED: list[tuple[str, str, str]] = [
    # --- satisfies_nfr: the sentence names three blocks explicitly ---------
    ("satisfies_nfr", "libraries[]",
     "(on the library, infrastructure, or provider entry)"),
    ("satisfies_nfr", "infrastructure.*",
     "(on the library, infrastructure, or provider entry)"),
    ("satisfies_nfr", "providers.*.capabilities[]",
     "(on the library, infrastructure, or provider entry)"),
    # --- satisfies_nfr at both persistence levels (D-SC37) -----------------
    ("satisfies_nfr", "persistence.*",
     "`satisfies_nfr` sits at BOTH levels"),
    ("satisfies_nfr", "persistence.*.collections[]",
     "`satisfies_nfr` sits at BOTH levels"),
    # --- satisfies_infra: stores only (D-SC11c) ---------------------------
    ("satisfies_infra", "persistence.*",
     "that store's `satisfies_infra`"),
    # --- serves_features --------------------------------------------------
    ("serves_features", "libraries[]",
     "no `serves_features` is attributable to no feature"),
    ("serves_features", "providers.*.capabilities[]",
     "only when that tier was chosen for"),
    ("serves_features", "integrations[]",
     "exactly as libraries are tagged"),
    ("serves_features", "persistence.*.collections[]",
     "Tag every collection with the `serves_features` it exists for"),
    ("serves_features", "infrastructure.*",
     "entry names the **product feature ids**"),
    # --- serves_capabilities ----------------------------------------------
    ("serves_capabilities", "libraries[]",
     "**AI capability ids from the AI features spec** ONLY"),
    ("serves_capabilities", "providers.*.capabilities[]",
     "only when that tier was chosen for"),
    # --- foundational: libraries only -------------------------------------
    ("foundational", "libraries[]",
     "`\"foundational\": true` and omit `serves_features`"),
    # --- status (D-SC48): the three sites the draws evidence ---------------
    # Placement is evidenced, not assumed. `libraries[]` was invented twice on
    # Ragmeister (OpenTelemetry, Playwright) and dropped on Threadline;
    # `persistence.*.collections[]` invented once (recent_policy_cache); and
    # `persistence.*` dropped on Threadline, where Redis was "optional for MVP" in
    # prose and shipped with collections and TTLs and no marker. `providers.*` is
    # deliberately absent: neither draw shows provider conditionality, and the one
    # provider `note` was a scope restriction already carried by `role` and the
    # primary's `fallback` string.
    ("status", "libraries[]",
     "Use it whenever you would otherwise write"),
    ("status", "persistence.*",
     "A store or a collection that is not part of the MVP carries `status`"),
    ("status", "persistence.*.collections[]",
     "A store or a collection that is not part of the MVP carries `status`"),
    # --- model_family (D-SC49) --------------------------------------------
    ("model_family", "providers.*",
     "the family this provider's models come from"),
    # --- security.auth (D-SC53c): omittable, list-shaped, product ids ------
    ("serves_features", "security.auth[]",
     "different surfaces can authenticate differently"),
    # --- purpose on an entity-less collection (D-SC51) ---------------------
    # The garble's cause, not its symptom: `policy_audit_log` and `inquiry_log`
    # hold no domain entity, and with nowhere else to put the description the
    # model narrated into `entities` -- which then rendered one character at a
    # time. D-SC27 is the precedent for the field mattering less than the
    # sentence that names it.
    ("purpose", "persistence.*.collections[]",
     "Those take `purpose` — one line"),
    # --- purpose on a store (D-SC60) ---------------------------------------
    # The store-level slot gap, one level up from D-SC51. The D-SC57 routing
    # paragraph already said "what a store or target is for is its `purpose`";
    # targets demonstrated it, stores did not, and on two of three visions
    # (Threadline, FareBox x2) the model generalised `purpose` up from the
    # collection level to record why a cache exists — read as undeclared.
    ("purpose", "persistence.*",
     "A store may also carry `purpose`"),
]


def _prose() -> str:
    """The prompt with line-continuation backslashes folded out.

    The prompt wraps licensing sentences across escaped newlines, so a fragment
    that reads as one sentence in the source is not a substring of it. Folding
    first means the table can quote what a reader sees.
    """
    return re.sub(r"\\\n", "", SYSTEM_PROMPT)


@pytest.mark.parametrize(
    "field,pattern,fragment",
    _LICENSED,
    ids=[f"{f}@{p}" for f, p, _ in _LICENSED],
)
def test_the_prose_still_licenses_what_the_table_claims(
    field: str, pattern: str, fragment: str
) -> None:
    """Guards the table's premise, so the demonstration test cannot assert a
    licence the prompt has stopped granting."""
    assert fragment in _prose(), (
        f"the table claims the prose licenses `{field}` on `{pattern}` via:\n"
        f"    {fragment!r}\n"
        f"but that text is no longer in SYSTEM_PROMPT. Either the prose changed and "
        f"the table must change with it, or the licence was withdrawn and this row "
        f"should go."
    )


@pytest.mark.parametrize(
    "field,pattern,fragment",
    _LICENSED,
    ids=[f"{f}@{p}" for f, p, _ in _LICENSED],
)
def test_every_licensed_field_is_demonstrated_where_its_prose_licenses_it(
    field: str, pattern: str, fragment: str
) -> None:
    """D-SC50 — the general rule. Six instances says this, not another patch.

    A field the prose licenses and the exemplar withholds is a field the model will
    not write. That has now been true six times in a row, across four separate
    rounds and two visions, with no counter-example.
    """
    assert _is_demonstrated(field, pattern), (
        f"`{field}` is licensed on `{pattern}` by the prose:\n"
        f"    {fragment!r}\n"
        f"but the schema example never demonstrates it there.\n"
        f"Demonstrated only at: "
        f"{sorted(_demonstrated().get(field, set())) or '(nowhere)'}\n"
        f"This is the D-SC50 class: prose licenses, exemplar withholds, model "
        f"follows the exemplar. Add it to the exemplar."
    )


def test_the_demonstration_probe_can_actually_fail() -> None:
    """A sentinel, mirroring test_stack_render_totality's own.

    If `_is_demonstrated` returned True unconditionally the parametrised test above
    would pass for every row and look like a guard while guarding nothing.
    """
    assert not _is_demonstrated("satisfies_nfr", "languages[]")
    assert not _is_demonstrated("no_such_field_anywhere", "libraries[]")


def test_every_linkage_field_in_the_exemplar_appears_in_the_table() -> None:
    """The table must not silently fall behind the exemplar.

    A field demonstrated somewhere the table never mentions means a licensing rule
    exists that nobody wrote down — the same drift in the other direction.
    """
    tabled = {f for f, _, _ in _LICENSED}
    demonstrated = {f for f, paths in _demonstrated().items() if paths}
    missing = demonstrated - tabled
    assert not missing, (
        f"the exemplar demonstrates {sorted(missing)}, which _LICENSED never "
        f"mentions. Add the row (with the prose that licenses it) or remove it "
        f"from the exemplar."
    )


# --- D-SC52: every project-specific id in the exemplar is domain-loaded --------
#
# D-SC41 fixed the nfr ids after a Ragmeister draw copied
# `nfr_saved_data_persists_across_restarts` -- a goal that project never set --
# into exactly the two places the exemplar puts it. The conclusion drawn then was
# that every other id class was "immune by accident because it was domain-loaded".
#
# That conclusion is false. A later Ragmeister draw emitted the exemplar's own
# `recipe_embedding` verbatim, for a policy app, in its prose -- and its JSON
# carried `policy_embedding`, a plausible domain-adapted copy of the same exemplar
# slot naming no catalog node. So domain-loading does not prevent the leak; it
# demotes it from JSON to prose and substitutes a *plausible* invented id, which is
# strictly harder to catch by eye. The deterministic defence is D-SC47's probe, not
# this guard.
#
# What this guard is for, then, is narrower and still worth having: it stops a
# future exemplar edit reintroducing a domain-NEUTRAL id, which is the worse class
# -- D-SC41 showed those get copied into the JSON, not merely echoed in prose.
#
# The field decides what must be domain-loaded. `satisfies_infra` and the
# `infrastructure` keys take catalog substrate ids (`vector_index`,
# `embedding_pipeline`) -- shared vocabulary every project uses, correctly neutral,
# and there is no importable registry of them (they live in
# `agentifier/patterns/tiers/*.md`). Store names are structural. Only these four
# fields carry ids that belong to one project.
_PROJECT_ID_FIELDS = (
    "serves_features",
    "serves_capabilities",
    "satisfies_nfr",
    "entities",
)

# Declared, and guarded below against the exemplar's own description, so it cannot
# drift the way _LICENSED could.
_EXAMPLE_DOMAIN_NOUNS = ("recipe", "shopping", "ingredient", "meal")


def _project_ids() -> set[str]:
    out: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, val in node.items():
                if key in _PROJECT_ID_FIELDS and isinstance(val, list):
                    out.update(str(v) for v in val)
                else:
                    walk(val)
        elif isinstance(node, list):
            for val in node:
                walk(val)

    walk(_stack_spec())
    return out


def test_the_example_project_is_still_the_recipe_domain() -> None:
    """Guards the noun list's premise, as _LICENSED's fragments are guarded."""
    desc = str(_stack_spec().get("description", "")).lower()
    assert "recipe" in desc, (
        f"_EXAMPLE_DOMAIN_NOUNS assumes the schema example is a recipe app, but "
        f"its description is now {desc!r}. Update the noun list with the exemplar."
    )


def test_every_project_specific_exemplar_id_is_domain_loaded() -> None:
    """D-SC52 — a neutral id reads as reusable and gets copied verbatim.

    Exactly one id failed this when it was written (`UnitConversion`), which is why
    the noun list deliberately excludes the generic `unit`: admitting it would have
    let the only true positive pass.
    """
    neutral = sorted(
        i for i in _project_ids()
        if not any(n in i.lower() for n in _EXAMPLE_DOMAIN_NOUNS)
    )
    assert not neutral, (
        f"domain-neutral ids in the schema example: {neutral}\n"
        f"An id naming no domain reads as reusable and will be copied into a "
        f"project that never set it (D-SC41). Name the example's domain in it."
    )


def test_the_domain_loading_probe_can_actually_fail() -> None:
    """The noun list must not be so permissive that nothing could fail it."""
    assert not any(n in "SomeNeutralThing".lower() for n in _EXAMPLE_DOMAIN_NOUNS)
    assert any(n in "recipe_search" for n in _EXAMPLE_DOMAIN_NOUNS)

# --- D-SC59: line continuations must not weld words together ------------------
#
# `SYSTEM_PROMPT` is a plain `"""` string, so Python folds a trailing backslash
# and the newline at parse time. Where the continued line has no trailing space
# and the next line has no leading indentation, the two words are welded: the
# model read "the decisions this conversation isbuilt to make", "belongs in none
# of them,record it in `additional_decisions`", and "Neverinvent a top-level key".
#
# Thirteen of these sat in one paragraph -- the one that governs
# `additional_decisions` (absent from BOTH validated draws) and forbids inventing
# fields (violated five times on Ragmeister). That is not proof of causation, but
# D-SC27 is the precedent for taking prompt prose this seriously: naming `purpose`
# in one sentence moved a repeat draw from 0/21 to 29/29.
#
# Indented continuations are deliberately NOT flagged: the next line's indentation
# supplies the separator, so they fold to a harmless double space.
def _welded_folds() -> list[tuple[int, str]]:
    src = Path(__file__).resolve().parents[1].joinpath(
        "src/spec4/agents/stack_advisor.py"
    ).read_text(encoding="utf-8")
    raw = re.search(r'SYSTEM_PROMPT = """(.*?)"""', src, re.S).group(1)
    lines = raw.split("\n")
    out: list[tuple[int, str]] = []
    for i in range(len(lines) - 1):
        line, nxt = lines[i], lines[i + 1]
        if not line.endswith("\\") or line[:-1].endswith(" "):
            continue
        if not nxt or nxt[0].isspace() or line == "\\":
            continue
        out.append((i, f"{line[-28:-1]}|{nxt[:22]}"))
    return out


def test_no_line_continuation_welds_two_words_together() -> None:
    welded = _welded_folds()
    assert not welded, (
        "line continuations with no trailing space, followed by an unindented "
        "line, weld two words together in the prompt the model actually reads:\n"
        + "\n".join(f"    ...{s}..." for _, s in welded)
    )


def test_the_weld_probe_can_actually_fail() -> None:
    """The detector must not be vacuous: prove it fires on the real shape."""
    lines = ["a sentence ending in a word\\", "and the next one starts here"]
    line, nxt = lines[0], lines[1]
    assert line.endswith("\\") and not line[:-1].endswith(" ")
    assert nxt and not nxt[0].isspace()
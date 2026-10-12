"""Which files the scan seed shows, and in what form (CodeScanner v2 step 2a).

``gather_project_context`` assembles the evidence block a seed carries in four
tiers, spent in order against one token budget (D-SC2-5):

- **A — fixed.** The file tree (a directory rollup plus every non-test source
  path, D-SC2-3), the README, manifests, CI, deployment signals and the
  Project Conventions (D-SC2-10). Formatted in ``_scan``; not budgeted beyond
  their own caps. Since 2.6.0 two blocks rendered from the scan close the
  tier: the external packages with the modules that import them (D-SC3-6)
  and the prior round's feature ids with the phases that declared them
  (D-SC3-8) — the evidence step 3's ``integrations`` and ``implemented``
  asks are answered from.
- **B — signatures.** Every load-bearing candidate and entrypoint candidate as
  a compact signature block (D-SC2-8), up to ``_TIER_B_TOKENS``, headed by
  the candidate list itself (D-SC3-9) so the ``load_bearing`` ask names its
  set.
- **C — bodies.** Entrypoint candidates, then the top ``_TOP_FAN_IN_BODIES``
  candidates by fan-in, then the files most touched since the round boundary
  (``git.since_last_round.most_touched``, D-SC2-6, step 2b), each whole when
  it is at most ``_WHOLE_BODY_TOKENS``, else its head plus its signatures
  (D-SC2-7). Up to ``_TIER_C_TOKENS`` plus whatever B left unspent, less the
  share D needs. Without a ``git`` block or a round boundary the third group
  is empty and C is as in 2a.
- **D — breadth.** One signature block per product package no B or C file sits
  in, from its highest fan-in member, up to ``_TIER_D_TOKENS``.

Within every tier, files reached from an entrypoint go first (D-SC2-4): reach
is what separates product code from tooling without an exclusion list. A thin
``__init__.py`` never takes a B, C or D slot (D-SC2-9).

The graph, signatures and reached set come from the pre-seed half of
``collect_scan`` (D-SC2-1) as a ``ScanEvidence``, so the walk is parsed once.
Without one — a caller outside ``run`` — they are computed here, once.
``scan`` itself stays LLM-invisible (1a): the seed carries *rendered*
evidence from the same computation, and the ``SampleRecord`` notes all of it.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import TYPE_CHECKING, Any

from spec4.agents.code_scanner._graph import (
    analyse,
    file_signatures,
    graph_nodes,
    signatures_block,
)
from spec4.agents.code_scanner._scan import (
    _SOURCE_EXTENSIONS,
    EVIDENCE_TOKEN_BUDGET,
    SampleRecord,
    _is_entrypoint_candidate,
    _read_text_safely,
    _rel,
    approx_tokens,
    collect_files,
    file_tree_lines,
    format_ci_block,
    format_conventions_block,
    format_deployment_signals,
    format_readme_block,
    manifest_file_lines,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

_TIER_B_TOKENS = 6_000
_TIER_C_TOKENS = 12_000
_TIER_D_TOKENS = 3_000
_WHOLE_BODY_TOKENS = 4_000
_HEAD_BODY_LINES = 150
_TOP_FAN_IN_BODIES = 3
_THIN_INIT_LINES = 20
_INIT_NAME = "__init__.py"
_MAX_BODY_CHARS = 2_000_000
_ENTRYPOINT_LABEL = "entrypoint candidate"
_CONFIG_KEY = "scan_context_tokens"
_UNKNOWN_REACH = "none"
_ROOT_DIR_LABEL = "."
_MAX_IMPORTERS_SHOWN = 6
_MAX_PRIOR_IDS_SHOWN = 50


@dataclasses.dataclass(frozen=True)
class ScanEvidence:
    """What the pre-seed half of ``collect_scan`` hands the sampler (D-SC2-1).

    ``scan`` holds every block but ``coverage``, which is attached after the
    seed from the record the sampler fills. ``reached`` is the graph's
    in-memory reached set; only its summary is persisted. ``budget_tokens``
    is the evidence budget for this scan (D-SC2-2).
    """

    files: list[pathlib.Path]
    scan: dict[str, Any]
    reached: frozenset[str]
    budget_tokens: int = EVIDENCE_TOKEN_BUDGET


def evidence_budget(llm_config: dict[str, Any]) -> int:
    """``llm_config["scan_context_tokens"]`` when a positive int, else the default."""
    value = llm_config.get(_CONFIG_KEY)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return EVIDENCE_TOKEN_BUDGET


def local_evidence(root: pathlib.Path, all_files: list[pathlib.Path]) -> ScanEvidence:
    """Graph and signatures computed here, for a caller with no measured scan."""
    graph = analyse(root, all_files)
    scan = {
        "module_graph": graph.block,
        "signatures": signatures_block(root, all_files, graph.block),
    }
    return ScanEvidence(all_files, scan, graph.reached)


def gather_project_context(
    working_dir: str,
    all_files: list[pathlib.Path] | None = None,
    record: SampleRecord | None = None,
    scan: ScanEvidence | None = None,
) -> str:
    """The evidence block a scan seed carries; see the module docstring.

    With ``record``, every tier notes what it pasted (D-SC1b-4); the text is
    the same either way.
    """
    root = pathlib.Path(working_dir)
    if record is None:
        record = SampleRecord()
    if all_files is None:
        all_files = scan.files if scan is not None else collect_files(root)
    lines: list[str] = [f"## Project Directory: `{root}`\n"]
    if not all_files:
        lines.append("The directory appears to be empty (no non-hidden files found).\n")
        text = "\n".join(lines)
        record.evidence_tokens = approx_tokens(text)
        return text
    evidence = scan if scan is not None else local_evidence(root, all_files)
    sampler = _Sampler(root, all_files, evidence, record)
    lines.extend(sampler.tier_a())
    lines.extend(sampler.tiers_bcd(approx_tokens("\n".join(lines))))
    text = "\n".join(lines)
    record.evidence_tokens = approx_tokens(text)
    return text


class _Sampler:
    """One gather's tiers over one walk; holds the lookups they share."""

    def __init__(
        self,
        root: pathlib.Path,
        all_files: list[pathlib.Path],
        evidence: ScanEvidence,
        record: SampleRecord,
    ) -> None:
        self.root = root
        self.all_files = all_files
        self.record = record
        self.budget = evidence.budget_tokens
        self.nodes = {_rel(root, n): n for n in graph_nodes(root, all_files)}
        graph = evidence.scan.get("module_graph") or {}
        self.fan_in: dict[str, int] = graph.get("fan_in") or {}
        self.candidates = [
            c["path"] for c in graph.get("load_bearing_candidates") or []
        ]
        reach = graph.get("reach") or {}
        self.reach_known = reach.get("basis", _UNKNOWN_REACH) != _UNKNOWN_REACH
        self.reached = evidence.reached
        signatures = evidence.scan.get("signatures") or {}
        self.signatures: dict[str, Any] = signatures.get("files") or {}
        self.entrypoints = [
            rel for rel, p in self.nodes.items() if _is_entrypoint_candidate(p)
        ]
        since = (evidence.scan.get("git") or {}).get("since_last_round") or {}
        self.touches: dict[str, int] = {
            m["path"]: m["commits"] for m in since.get("most_touched") or []
        }
        self.external_imports: dict[str, list[str]] = (
            graph.get("external_imports") or {}
        )
        self.prior_round: dict[str, Any] = evidence.scan.get("prior_round") or {}

    # -- tier A ------------------------------------------------------------

    def tier_a(self) -> list[str]:
        root, files, record = self.root, self.all_files, self.record
        lines: list[str] = []
        file_tree_lines(root, files, list(self.nodes), lines, record)
        lines.extend(format_readme_block(root, files, record))
        manifest_file_lines(root, files, lines, record)
        lines.extend(format_ci_block(root, files, record))
        lines.extend(format_deployment_signals(root, files, record))
        lines.extend(format_conventions_block(root, files, record))
        lines.extend(self._external_imports_block())
        lines.extend(self._prior_round_block())
        record.source_files_total = sum(1 for f in files if _is_source(f))
        return lines

    def _external_imports_block(self) -> list[str]:
        """External packages and the modules that import them (D-SC3-6).

        Rendered from ``module_graph.external_imports``, most-imported package
        first, up to ``_MAX_IMPORTERS_SHOWN`` modules each — the evidence an
        ``integrations[].client_module`` cites. Empty when the graph has none.
        """
        if not self.external_imports:
            return []
        self.record.external_imports_shown = True
        out = ["### External Packages and Their Importers\n"]
        for package, modules in self.external_imports.items():
            shown = ", ".join(f"`{m}`" for m in modules[:_MAX_IMPORTERS_SHOWN])
            more = len(modules) - _MAX_IMPORTERS_SHOWN
            tail = f" (+{more} more)" if more > 0 else ""
            out.append(f"- {package}: {shown}{tail}")
        out.append("")
        return out

    def _prior_round_block(self) -> list[str]:
        """The prior round's product-feature ids, with their phases (D-SC3-8).

        Rendered from ``scan.prior_round``: the vision's ids first, then any
        id a phase declared that the vision did not, each with the numbers of
        the phases declaring it. The ids are the vocabulary for
        ``implemented[].prior_feature_ids``. Empty when no round is implemented.
        """
        prior = self.prior_round
        if not prior:
            return []
        phases_of: dict[str, list[int]] = {}
        for phase in prior.get("phases") or []:
            for feature in phase.get("features") or []:
                phases_of.setdefault(feature["id"], [])
                if phase.get("number") is not None:
                    phases_of[feature["id"]].append(phase["number"])
        ids = list(
            dict.fromkeys(
                [*(prior.get("vision") or {}).get("feature_ids", []), *phases_of]
            )
        )
        if not ids:
            return []
        self.record.prior_round_shown = True
        when = prior.get("implemented")
        head = f"### Prior Round (v{prior.get('version')}"
        head += f", implemented {when[:10]})\n" if isinstance(when, str) else ")\n"
        out = [
            head,
            "Product features the last Spec4 round planned, with the phases that "
            "built them (ids are the vocabulary for `implemented[].prior_feature_ids`):",
        ]
        for fid in ids[:_MAX_PRIOR_IDS_SHOWN]:
            numbers = phases_of.get(fid) or []
            phases = (
                " — phase " + ", ".join(str(n) for n in numbers)
                if numbers
                else " — no phase declared it"
            )
            out.append(f"- `{fid}`{phases}")
        if len(ids) > _MAX_PRIOR_IDS_SHOWN:
            out.append(f"(+{len(ids) - _MAX_PRIOR_IDS_SHOWN} more)")
        out.append("")
        return out

    # -- tiers B, C, D -------------------------------------------------------

    def tiers_bcd(self, spent: int) -> list[str]:
        """B, C and D against what tier A left of the budget (D-SC2-5)."""
        left = max(0, self.budget - spent)
        b_budget = min(_TIER_B_TOKENS, left)
        # D-SC3-9: the candidate line is B's first block; its cost for the
        # full candidate list is reserved before the signatures fill, so the
        # line for the subset actually shown always fits what was reserved.
        line_cost = sum(approx_tokens(t) for t in self._candidate_line(self.candidates))
        b_paths, b_text = self._fill(
            self._tier_b_paths(), self._signature_block, max(0, b_budget - line_cost)
        )
        b_line = self._candidate_line(b_paths) if b_text else []
        b_spent = sum(approx_tokens(t) for t in [*b_line, *b_text])
        left -= b_spent
        d_reserve = self._d_cost(set(b_paths), min(_TIER_D_TOKENS, left))
        c_budget = min(_TIER_C_TOKENS + (b_budget - b_spent), left - d_reserve)
        c_paths, c_text = self._fill(self._tier_c_paths(), self._body_block, c_budget)
        left -= sum(approx_tokens(t) for t in c_text)
        d_paths, d_text = self._fill(
            self._tier_d_paths(set(b_paths) | set(c_paths)),
            self._package_block,
            min(_TIER_D_TOKENS, left),
        )
        self.record.signatures_shown.extend(b_paths + d_paths)
        self.record.sampled.extend(c_paths)
        out: list[str] = []
        if b_text:
            out.append("### Key Module Signatures\n")
            out.extend(b_line)
            out.extend(b_text)
        out.append("### Source File Samples\n")
        out.extend(c_text)
        if d_text:
            out.append("### Other Package Signatures\n")
            out.extend(d_text)
        return out

    def _fill(
        self,
        paths: Iterable[str],
        render: Callable[[str], str | None],
        budget: int,
    ) -> tuple[list[str], list[str]]:
        """Each path's rendering while it fits; a block that does not is skipped.

        Skipping rather than stopping lets a smaller file later in the order
        use what a large one could not.
        """
        chosen: list[str] = []
        blocks: list[str] = []
        spent = 0
        for rel in paths:
            block = render(rel)
            if block is None:
                continue
            cost = approx_tokens(block)
            if spent + cost > budget:
                continue
            chosen.append(rel)
            blocks.append(block)
            spent += cost
        return chosen, blocks

    # -- selection -----------------------------------------------------------

    def _ranked(self, paths: Iterable[str]) -> list[str]:
        """Reached first, the given order kept within each half; no repeats."""
        unique = [p for p in dict.fromkeys(paths) if p in self.nodes]
        unique = [p for p in unique if not self._thin_init(p)]
        if not self.reach_known:
            return unique
        return sorted(unique, key=lambda p: p not in self.reached)

    def _tier_b_paths(self) -> list[str]:
        return self._ranked([*self.candidates, *self.entrypoints])

    def _candidate_line(self, shown: list[str]) -> list[str]:
        """The load-bearing candidates B shows, as one list (D-SC3-9).

        Fan-in order, candidates only — an entrypoint shown in B is not one
        unless the graph ranks it. The ``load_bearing`` ask names this set.
        """
        listed = [p for p in self.candidates if p in shown]
        if not listed:
            return []
        return [
            "Load-bearing candidates (by fan-in, emit one `load_bearing` entry "
            "for each): " + ", ".join(f"`{p}`" for p in listed) + "\n"
        ]

    def _tier_c_paths(self) -> list[str]:
        """Entrypoints, the top fan-in candidates, then the most-touched files.

        The third group (D-SC2-6) keeps the git block's order — most commits
        first — reached files ahead of unreached, and skips anything the first
        two already show.
        """
        entry = self._ranked(self.entrypoints)
        top = [p for p in self._ranked(self.candidates) if p not in entry]
        shown = entry + top[:_TOP_FAN_IN_BODIES]
        touched = [p for p in self._ranked(self.touches) if p not in shown]
        return shown + touched

    def _tier_d_paths(self, taken: set[str]) -> list[str]:
        """The highest fan-in member of each product package no B/C file is in."""
        taken_dirs = {_parent(p) for p in taken}
        product = [
            rel
            for rel in self.nodes
            if (not self.reach_known or rel in self.reached)
            and not self._thin_init(rel)
            and _parent(rel) not in taken_dirs
        ]
        best: dict[str, str] = {}
        for rel in sorted(product, key=lambda p: (-self.fan_in.get(p, 0), p)):
            best.setdefault(_parent(rel), rel)
        return sorted(best.values(), key=lambda p: (-self.fan_in.get(p, 0), p))

    def _d_cost(self, taken: set[str], cap: int) -> int:
        """What D would spend excluding only B — its reserve inside C (D-SC2-5)."""
        if cap <= 0:
            return 0
        _, blocks = self._fill(self._tier_d_paths(taken), self._package_block, cap)
        return sum(approx_tokens(b) for b in blocks)

    def _thin_init(self, rel: str) -> bool:
        """An ``__init__.py`` under ``_THIN_INIT_LINES`` non-blank lines (D-SC2-9)."""
        path = self.nodes[rel]
        if path.name != _INIT_NAME:
            return False
        text = _read_text_safely(path, _MAX_BODY_CHARS) or ""
        return sum(1 for line in text.splitlines() if line.strip()) < _THIN_INIT_LINES

    # -- rendering -----------------------------------------------------------

    def _label(self, rel: str) -> str:
        """Why the file is shown: entrypoint or fan-in, and its churn (2b)."""
        parts: list[str] = []
        if rel in self.entrypoints:
            parts.append(_ENTRYPOINT_LABEL)
        elif self.fan_in.get(rel, 0):
            parts.append(f"fan-in {self.fan_in[rel]}")
        touches = self.touches.get(rel, 0)
        if touches:
            parts.append(
                f"{touches} commit{'' if touches == 1 else 's'} since last round"
            )
        return f" ({', '.join(parts)})" if parts else ""

    def _entry(self, rel: str) -> dict[str, Any] | None:
        entry = self.signatures.get(rel)
        return entry if entry is not None else file_signatures(self.nodes[rel])

    def _signature_block(self, rel: str) -> str | None:
        entry = self._entry(rel)
        if entry is None:
            return None
        return render_signatures(rel, entry, self._label(rel))

    def _package_block(self, rel: str) -> str | None:
        entry = self._entry(rel)
        if entry is None or not entry["symbols"]:
            return None
        label = f" (package `{_parent(rel)}/`{self._fan_in_note(rel)})"
        return render_signatures(rel, entry, label)

    def _fan_in_note(self, rel: str) -> str:
        fan_in = self.fan_in.get(rel, 0)
        return f", fan-in {fan_in}" if fan_in else ""

    def _body_block(self, rel: str) -> str | None:
        """Whole when small enough, else the head and its signatures (D-SC2-7)."""
        text = _read_text_safely(self.nodes[rel], _MAX_BODY_CHARS)
        if text is None:
            return None
        lines = text.splitlines()
        label = self._label(rel)
        if approx_tokens(text) <= _WHOLE_BODY_TOKENS:
            return (
                f"#### `{rel}` (whole file, {len(lines)} lines){label}\n"
                f"```\n{text}\n```\n"
            )
        head = "\n".join(lines[:_HEAD_BODY_LINES])
        block = (
            f"#### `{rel}` (first {_HEAD_BODY_LINES} of {len(lines)} lines){label}\n"
            f"```\n{head}\n```\n"
        )
        entry = self._entry(rel)
        if entry is not None and entry["symbols"]:
            block += f"_Signatures of `{rel}`:_\n```\n{_symbol_lines(entry)}\n```\n"
        return block


def render_signatures(rel: str, entry: dict[str, Any], label: str) -> str:
    """One file's compact signature block (D-SC2-8).

    ``def name(sig)  # first doc line``, one symbol per line, under the
    module's own first doc line — the same symbols ``scan.signatures`` stores,
    at about half the size of their JSON.
    """
    head = f"#### `{rel}`{label}\n"
    if entry.get("doc"):
        head += f"_{entry['doc']}_\n"
    body = _symbol_lines(entry) if entry["symbols"] else "(no public symbols)"
    return f"{head}```\n{body}\n```\n"


def _symbol_lines(entry: dict[str, Any]) -> str:
    lines = [
        f"{s['signature']}  # {s['doc']}" if s.get("doc") else s["signature"]
        for s in entry["symbols"]
    ]
    if entry.get("truncated"):
        lines.append("# … more public symbols not shown")
    return "\n".join(lines)


def _parent(rel: str) -> str:
    head, sep, _ = rel.rpartition("/")
    return head if sep else _ROOT_DIR_LABEL


def _is_source(path: pathlib.Path) -> bool:
    return path.suffix in _SOURCE_EXTENSIONS

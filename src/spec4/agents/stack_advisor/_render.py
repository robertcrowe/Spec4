"""Rendering a ``stack_spec`` artifact as chat-transcript text.

``_format_stack_as_text``, the two generic fall-through renderers it leans on
(``_render_any`` / ``_render_rest``, the total-renderer half of D-SC33), the
id-array helpers (``_render_entry_links``, ``_as_ids``) and the small coercions
(``_as_list``, ``_scalar_text``, ``_label``) that guard against the shapes an
LLM actually returns. Output only -- nothing here reads the filesystem, the
session, or the LLM.

This output is golden-pinned by ``tests/test_renderer_goldens.py``, so it is
a frozen surface in the same sense as the prompt.

Split out of ``stack_advisor.py`` in Phase 4d; the package ``__init__``
re-exports every name below under its original spelling.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._stack_context import render_references


def _as_list(value: Any) -> list[Any]:
    """Coerce a leaf that should be a list into one (D-SC51).

    D-SC33 made the renderer total, which closed the DROP path: a field the
    renderer does not know about now reaches the page instead of vanishing. It did
    not close the GARBLE path. Every bespoke join site iterates its argument, and a
    string is iterable one character at a time — so ``entities: "Policy change
    history"`` rendered as ``holds P, o, l, i, c, y,  , c, h, a, n, g, e...``.
    Three collections on one live Ragmeister draw.

    A garble is worse than a drop: actively misleading rather than merely absent,
    and it lands on the receipt, which is the developer's only view of what was
    actually persisted.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _as_ids(values: Any) -> str:
    """Render ids as code spans (D-SC21).

    ``nfr_<slug>`` keys carry leading and trailing underscores, which markdown
    reads as emphasis delimiters and consumes — the user saw `nfrfare_lookups...`
    where the artifact said `nfr_fare_lookups...`. A code span is inert.

    Coerces (D-SC51): a bare string here garbles into one code span per character.
    """
    return ", ".join(f"`{v}`" for v in _as_list(values))


def _scalar_text(value: Any) -> str:
    """One-line human form for a leaf value."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _label(key: Any) -> str:
    return str(key).replace("_", " ").strip().title()


_ID_KEYS = (
    "serves_features",
    "serves_capabilities",
    "satisfies_nfr",
    "satisfies_infra",
)

# Labels for the id arrays whose key name alone does not read as English.
_ID_LABELS = {
    "satisfies_nfr": "Satisfies",
    "satisfies_infra": "Satisfies required substrate",
}


def _render_any(label: str, value: Any, lines: list[str], indent: str = "") -> None:
    """Render an arbitrary value under ``label``, recursing into containers.

    The fall-through half of the total renderer (D-SC33). Every block hands the
    keys it did not consume to this function, so a field the schema never
    declared still reaches the page under a generic heading rather than being
    dropped. That inverts the old failure: guessing the schema wrong now costs
    cosmetics instead of invisibility.
    """
    if value is None or value == "" or value == [] or value == {}:
        return
    if isinstance(value, dict):
        lines.append(f"{indent}- {label}:")
        for k, v in value.items():
            _render_any(_label(k), v, lines, indent + "  ")
    elif isinstance(value, list):
        if all(isinstance(v, (str, int, float, bool)) for v in value):
            lines.append(
                f"{indent}- {label}: {', '.join(_scalar_text(v) for v in value)}"
            )
        else:
            lines.append(f"{indent}- {label}:")
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("path") or item.get("standard")
                    head = _scalar_text(name) if name else "-"
                    lines.append(f"{indent}  - {head}")
                    _render_rest(
                        item, {"name", "path", "standard"}, lines, indent + "    "
                    )
                else:
                    _render_any("-", item, lines, indent + "  ")
    else:
        lines.append(f"{indent}- {label}: {_scalar_text(value)}")


def _render_rest(
    block: Any, handled: set[str], lines: list[str], indent: str = ""
) -> None:
    """Render every key of ``block`` that its own renderer did not consume."""
    if not isinstance(block, dict):
        if block not in (None, "", [], {}):
            _render_any("Value", block, lines, indent)
        return
    for key, value in block.items():
        if key in handled:
            continue
        if key in _ID_KEYS and isinstance(value, list) and value:
            lines.append(
                f"{indent}- {_ID_LABELS.get(key, _label(key))}: {_as_ids(value)}"
            )
            continue
        _render_any(_label(key), value, lines, indent)


def _render_entry_links(entry: dict[str, Any], lines: list[str], indent: str) -> None:
    """Render the four id arrays every attributable entry may carry."""
    for key in _ID_KEYS:
        vals = entry.get(key) or []
        if vals:
            lines.append(
                f"{indent}- {_ID_LABELS.get(key, _label(key))}: {_as_ids(vals)}"
            )


def _format_stack_as_text(stack: dict[str, Any]) -> str:
    ss: dict[str, Any] = stack.get("stack_spec") or stack.get("stack") or stack
    if not isinstance(ss, dict):
        return str(ss)
    lines: list[str] = []

    name = ss.get("name", "")
    lines.append(f"**Tech Stack: {name}**\n" if name else "**Tech Stack**\n")
    if ss.get("description"):
        lines.append(f"{ss['description']}\n")

    languages: Any = ss.get("languages") or []
    if languages:
        lines.append("**Languages:**")
        if all(isinstance(x, str) for x in languages):
            lines.append(f"- {', '.join(languages)}")
        else:
            for lang in languages:
                if not isinstance(lang, dict):
                    lines.append(f"- {_scalar_text(lang)}")
                    continue
                head = str(lang.get("name", "language"))
                if lang.get("version"):
                    head += f" {lang['version']}"
                if lang.get("role"):
                    head += f" — {lang['role']}"
                lines.append(f"- {head}")
                _render_rest(lang, {"name", "version", "role"}, lines, "  ")
        lines.append("")

    deployment: Any = ss.get("deployment") or {}
    if deployment:
        lines.append("**Deployment:**")
        targets = deployment.get("targets") if isinstance(deployment, dict) else None
        if isinstance(targets, list):
            for tgt in targets:
                if not isinstance(tgt, dict):
                    lines.append(f"- {_scalar_text(tgt)}")
                    continue
                head = str(tgt.get("name", "target"))
                if tgt.get("kind"):
                    head += f" ({tgt['kind']})"
                lines.append(f"- {head}")
                _render_rest(tgt, {"name", "kind"}, lines, "  ")
        _render_rest(deployment, {"targets"}, lines)
        lines.append("")

    providers: Any = ss.get("providers") or {}
    if providers:
        lines.append("**Providers:**")
        if not isinstance(providers, dict):
            _render_any("Providers", providers, lines)
            providers = {}
        for prov_name, prov in providers.items():
            if not isinstance(prov, dict):
                lines.append(f"- {prov_name}: {_scalar_text(prov)}")
                continue
            lines.append(f"- {prov_name}")
            caps = prov.get("capabilities")
            if isinstance(caps, list):
                for cap in caps:
                    if not isinstance(cap, dict):
                        lines.append(f"  - {_scalar_text(cap)}")
                        continue
                    head = str(cap.get("tier", "capability"))
                    if cap.get("capability_class"):
                        head += f": {cap['capability_class']}"
                    if cap.get("role"):
                        head += f" ({cap['role']})"
                    lines.append(f"  - {head}")
                    _render_rest(
                        cap, {"tier", "capability_class", "role"}, lines, "    "
                    )
            _render_rest(prov, {"capabilities"}, lines, "  ")
        lines.append("")

    integrations: Any = ss.get("integrations") or []
    if integrations:
        lines.append("**Integrations:**")
        for item in integrations if isinstance(integrations, list) else [integrations]:
            if not isinstance(item, dict):
                lines.append(f"- {_scalar_text(item)}")
                continue
            head = str(item.get("name", "integration"))
            if item.get("purpose"):
                head += f" — {item['purpose']}"
            lines.append(f"- {head}")
            _render_rest(item, {"name", "purpose"}, lines, "  ")
        lines.append("")

    libraries: Any = ss.get("libraries") or {}
    if libraries:
        lines.append("**Libraries:**")
        if isinstance(libraries, list):
            _render_library_entries(libraries, lines)
        elif isinstance(libraries, dict):
            for category, libs in libraries.items():
                if not libs:
                    continue
                lines.append(f"\n*{_label(category)}:*")
                if isinstance(libs, list):
                    _render_library_entries(libs, lines)
                else:
                    _render_library_entries([libs], lines)
        lines.append("")

    persistence: Any = ss.get("persistence") or {}
    if persistence:
        lines.append("**Data & persistence:**")
        if not isinstance(persistence, dict):
            _render_any("Persistence", persistence, lines)
            persistence = {}
        for store_name, store in persistence.items():
            if not isinstance(store, dict):
                lines.append(f"- {store_name}: {_scalar_text(store)}")
                continue
            choice = store.get("choice", "")
            lines.append(f"- {store_name} — {choice}" if choice else f"- {store_name}")
            if store.get("purpose"):
                lines.append(f"  - Purpose: {_scalar_text(store['purpose'])}")
            if store.get("durability"):
                lines.append(f"  - Durability: {store['durability']}")
            _render_entry_links(store, lines, "  ")
            collections = store.get("collections") or []
            if isinstance(collections, list):
                for col in collections:
                    if not isinstance(col, dict):
                        lines.append(f"  - {_scalar_text(col)}")
                        continue
                    bits = []
                    if col.get("entities"):
                        bits.append(
                            "holds "
                            + ", ".join(
                                _scalar_text(e) for e in _as_list(col["entities"])
                            )
                        )
                    if col.get("purpose"):
                        bits.append(_scalar_text(col["purpose"]))
                    if col.get("serves_features"):
                        bits.append(f"serves {_as_ids(col['serves_features'])}")
                    suffix = f" ({'; '.join(bits)})" if bits else ""
                    lines.append(f"  - {col.get('name', 'collection')}{suffix}")
                    _render_rest(
                        col,
                        {"name", "entities", "serves_features", "purpose"},
                        lines,
                        "    ",
                    )
            _render_rest(
                store,
                {"choice", "purpose", "durability", "collections", *_ID_KEYS},
                lines,
                "  ",
            )
        lines.append("")

    infrastructure: Any = ss.get("infrastructure") or {}
    if infrastructure:
        lines.append("**Infrastructure:**")
        if not isinstance(infrastructure, dict):
            _render_any("Infrastructure", infrastructure, lines)
            infrastructure = {}
        for comp, spec in infrastructure.items():
            if not isinstance(spec, dict):
                lines.append(f"- {comp}: {_scalar_text(spec)}")
                continue
            choice = spec.get("choice", "")
            lines.append(f"- {comp}: {choice}" if choice else f"- {comp}")
            _render_rest(spec, {"choice"}, lines, "  ")
        lines.append("")

    conventions: Any = ss.get("ai_conventions") or {}
    if conventions:
        lines.append("**AI conventions:**")
        if isinstance(conventions, dict):
            for conv_name, value in conventions.items():
                _render_any(_label(conv_name), value, lines)
        else:
            _render_any("AI Conventions", conventions, lines)
        lines.append("")

    structure: Any = ss.get("project_structure") or []
    if structure:
        lines.append("**Project structure:**")
        if isinstance(structure, list):
            for item in structure:
                if isinstance(item, dict):
                    path = item.get("path", "")
                    purpose = item.get("purpose", "")
                    lines.append(
                        f"- `{path}` — {purpose}" if purpose else f"- `{path}`"
                    )
                    _render_rest(item, {"path", "purpose"}, lines, "  ")
                else:
                    lines.append(f"- {_scalar_text(item)}")
        else:
            _render_any("Project Structure", structure, lines)
        lines.append("")

    style: Any = ss.get("coding_style") or {}
    if style:
        lines.append("**Coding Style:**")
        if isinstance(style, dict):
            _render_rest(style, set(), lines)
        else:
            _render_any("Coding Style", style, lines)
        lines.append("")

    extra: Any = ss.get("additional_decisions") or []
    if extra:
        lines.append("**Additional decisions:**")
        for item in extra if isinstance(extra, list) else [extra]:
            if isinstance(item, dict):
                head = str(item.get("name", "decision"))
                value = item.get("value")
                lines.append(
                    f"- {head}: {_scalar_text(value)}"
                    if value is not None
                    else f"- {head}"
                )
                if item.get("description"):
                    lines.append(f"  - {item['description']}")
                _render_rest(item, {"name", "value", "description"}, lines, "  ")
            else:
                lines.append(f"- {_scalar_text(item)}")
        lines.append("")

    render_references(ss.get("references", []), lines)

    _render_rest(ss, _TOP_LEVEL_HANDLED, lines)

    lines.append(
        "---\n\n"
        "We've finished defining the tech stack, so now you're ready to move on to "
        "creating implementation phases for your coding agent. Please click on the "
        "**Continue to Phaser** button below."
    )
    return "\n".join(lines)


_TOP_LEVEL_HANDLED = {
    "name",
    "description",
    "languages",
    "deployment",
    "providers",
    "integrations",
    "libraries",
    "persistence",
    "infrastructure",
    "ai_conventions",
    "project_structure",
    "coding_style",
    "additional_decisions",
    "references",
}


def _render_library_entries(libs: list[Any], lines: list[str]) -> None:
    """Render a flat list of library entries (D-SC27)."""
    for lib in libs:
        if not isinstance(lib, dict):
            lines.append(f"- {_scalar_text(lib)}")
            continue
        lib_name = lib.get("name", "")
        purpose = lib.get("purpose", "")
        entry = f"- {lib_name} — {purpose}" if purpose else f"- {lib_name}"
        bits = []
        if lib.get("language"):
            bits.append(str(lib["language"]))
        if lib.get("category"):
            bits.append(str(lib["category"]))
        if bits:
            entry += f" [{', '.join(bits)}]"
        lines.append(entry)
        _render_rest(lib, {"name", "purpose", "language", "category"}, lines, "  ")

"""Rendering a validated ``code_review`` artifact as chat-transcript text.

``_format_review_as_text`` and the seven section renderers it delegates to,
plus the small coercion helpers (``_as_str_list``, ``_name_label``,
``_style_value``, ``_normalize_style_for_renderer``) that guard against the
shapes an LLM actually returns. Output only -- nothing here reads the
filesystem, the session, or the LLM.

This output is golden-pinned by ``tests/test_renderer_goldens.py``, so it is
a frozen surface in the same sense as the prompt.

Split out of ``code_scanner.py`` in Phase 4c; the package ``__init__``
re-exports every name below under its original spelling.
"""

from __future__ import annotations

from typing import Any

from spec4.agents._stack_context import render_coding_style


def _as_str_list(value: Any) -> list[str]:
    """Coerce a value to list[str], guarding against the LLM returning a string."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value] if value else []
    return []


def _name_label(item: Any) -> str:
    """Render an entry as 'Name' or 'Name (source: foo)' across legacy/new shapes."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        name = str(item.get("name", "") or "")
        source = item.get("source")
        return f"{name} (source: {source})" if name and source else name or str(item)
    return str(item)


def _style_value(field: Any) -> str:
    """Render a coding_style field as 'value' or 'value (source: X)' / 'value (from: X)'.

    Accepts either a raw scalar (legacy) or a dict with value+source/inferred_from.
    """
    if isinstance(field, dict):
        value = field.get("value", "")
        source = field.get("source")
        inferred = field.get("inferred_from")
        if source:
            return f"{value} (source: {source})"
        if inferred:
            return f"{value} (inferred from: {inferred})"
        return str(value)
    return str(field) if field is not None else ""


def _normalize_style_for_renderer(style: dict[str, Any]) -> dict[str, Any]:
    """Flatten provenance-tagged style entries to scalars for legacy renderer."""
    if not isinstance(style, dict):
        return {}
    flat: dict[str, Any] = {}
    for key, val in style.items():
        if key == "naming_conventions" and isinstance(val, dict):
            flat[key] = {
                k: v.get("value") if isinstance(v, dict) else v for k, v in val.items()
            }
        elif isinstance(val, dict) and "value" in val:
            flat[key] = _style_value(val)
        else:
            flat[key] = val
    return flat


def _format_empty_review(cr: dict[str, Any]) -> str:
    """Render the is_software_project=false display."""
    lines = ["**Code Review Complete**\n"]
    summary = cr.get("summary")
    notes = cr.get("notes")
    if summary:
        lines.append(f"{summary}\n")
    elif isinstance(notes, str):
        lines.append(f"{notes}\n")
    elif isinstance(notes, list):
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")
    else:
        lines.append("This directory does not appear to contain a software project.\n")
    lines.append(
        "---\n\n"
        "You can still continue to the **Brainstormer** to define a vision for a new "
        "project in this directory."
    )
    return "\n".join(lines)


def _format_review_as_text(review: dict[str, Any]) -> str:
    cr = review.get("code_review", {})
    if cr.get("is_software_project") is False:
        return _format_empty_review(cr)

    lines: list[str] = ["**Code Review Complete**\n"]

    if "project_type" in cr:
        lines.append(f"**Project Type:** {cr['project_type']}\n")

    self_desc = cr.get("existing_self_description")
    if isinstance(self_desc, dict) and self_desc.get("text"):
        src = self_desc.get("source", "")
        suffix = f" _(from {src})_" if src else ""
        lines.append(f"**Existing self-description:** {self_desc['text']}{suffix}\n")
    elif isinstance(self_desc, str) and self_desc:
        lines.append(f"**Existing self-description:** {self_desc}\n")

    arch = cr.get("architecture")
    if isinstance(arch, dict):
        summary = arch.get("summary", "")
        pattern = arch.get("pattern", "")
        if summary or pattern:
            label = " / ".join(p for p in (pattern, summary) if p)
            lines.append(f"**Architecture:** {label}\n")
    elif isinstance(arch, str) and arch:
        lines.append(f"**Architecture:** {arch}\n")

    langs = cr.get("languages", [])
    frameworks = cr.get("frameworks", [])
    parts: list[str] = []
    for item in langs if isinstance(langs, list) else []:
        parts.append(_name_label(item))
    for item in frameworks if isinstance(frameworks, list) else []:
        parts.append(_name_label(item))
    if isinstance(langs, str) and langs:
        parts.append(langs)
    if isinstance(frameworks, str) and frameworks:
        parts.append(frameworks)
    if parts:
        lines.append(f"**Languages & Frameworks:** {', '.join(parts)}\n")

    protocols = cr.get("protocols_implemented")
    if isinstance(protocols, list) and protocols:
        lines.append("**Protocols Implemented:**")
        for proto in protocols:
            if isinstance(proto, dict):
                name = proto.get("name", "")
                version = proto.get("version", "")
                location = proto.get("location", "")
                head = f"{name} v{version}" if version else name
                tail = f" — `{location}`" if location else ""
                lines.append(f"- {head}{tail}" if head else f"- {proto}")
            else:
                lines.append(f"- {proto}")
        lines.append("")

    runtime = cr.get("runtime_versions")
    if isinstance(runtime, dict) and runtime:
        items = [f"{k}: {v}" for k, v in runtime.items() if not k.startswith("_") and v]
        if items:
            lines.append(f"**Runtime versions:** {', '.join(items)}\n")

    build = cr.get("build_system")
    if isinstance(build, dict):
        tool = build.get("tool", "")
        manifest = build.get("manifest", "")
        backend = build.get("build_backend", "")
        suffix_bits = [b for b in (manifest, backend) if b]
        suffix = f" ({', '.join(suffix_bits)})" if suffix_bits else ""
        if tool:
            lines.append(f"**Build System:** {tool}{suffix}\n")
    elif isinstance(build, str) and build:
        lines.append(f"**Build System:** {build}\n")

    raw_deps = cr.get("dependencies", [])
    deps: list[Any] = raw_deps if isinstance(raw_deps, list) else []
    if deps:
        lines.append("**Dependencies:**")
        for d in deps:
            if isinstance(d, dict):
                name = d.get("name", "")
                purpose = d.get("purpose", "")
                source = d.get("source", "")
                suffix_bits = [
                    p for p in (purpose, f"source: {source}" if source else "") if p
                ]
                suffix = f" — {' · '.join(suffix_bits)}" if suffix_bits else ""
                lines.append(f"- {name}{suffix}" if name else f"- {d}")
            else:
                lines.append(f"- {d}")
        lines.append("")

    commands = cr.get("commands")
    if isinstance(commands, dict) and commands:
        lines.append("**Commands:**")
        for key in ("build", "test", "lint", "typecheck", "run", "dev", "deploy"):
            if key in commands and commands[key]:
                lines.append(f"- {key}: `{commands[key]}`")
        lines.append("")

    entrypoints = cr.get("entrypoints")
    if isinstance(entrypoints, dict) and entrypoints:
        lines.append("**Entrypoints:**")
        for key in ("main", "wsgi_app", "cli_script", "dev_server", "ui_root"):
            if key in entrypoints and entrypoints[key]:
                lines.append(f"- {key.replace('_', ' ')}: `{entrypoints[key]}`")
        lines.append("")

    dmap = cr.get("directory_map")
    if isinstance(dmap, list) and dmap:
        lines.append("**Directory Map:**")
        for entry in dmap:
            if isinstance(entry, dict):
                path = entry.get("path", "")
                role = entry.get("role", "")
                if path:
                    lines.append(f"- `{path}` — {role}")
                elif role:
                    lines.append(f"- {role}")
            else:
                lines.append(f"- {entry}")
        lines.append("")

    _render_persistence(cr.get("persistence"), lines)
    _render_env_vars(cr.get("env_vars"), lines)
    _render_deployment(cr.get("deployment"), lines)
    _render_api_surface(cr.get("api_surface"), lines)
    _render_auth(cr.get("auth"), lines)
    _render_ai_capabilities(cr.get("ai_capabilities"), lines)

    ui = cr.get("ui_summary")
    if isinstance(ui, dict) and ui:
        has_ui = ui.get("has_ui")
        if has_ui is False:
            lines.append("**UI:** none (CLI / library / API-only)\n")
        elif has_ui is True:
            kind = ui.get("kind", "")
            framework = ui.get("framework", "")
            styling = ui.get("styling", "")
            bits = [b for b in (kind, framework, styling) if b]
            lines.append(
                f"**UI:** {' · '.join(bits)}\n" if bits else "**UI:** present\n"
            )

    render_coding_style(
        _normalize_style_for_renderer(cr.get("coding_style", {})), lines
    )

    notes = cr.get("notes")
    if isinstance(notes, dict):
        _render_typed_notes(notes, lines)
    else:
        notes_list = _as_str_list(notes if notes is not None else [])
        if notes_list:
            lines.append("**Notable Observations:**")
            for note in notes_list:
                lines.append(f"- {note}")
            lines.append("")

    lines.append(
        "---\n\n"
        "We've finished the code review, so now you're ready to move on to creating "
        "a vision. Please click on the **Continue to Brainstormer** button below."
    )
    return "\n".join(lines)


def _render_persistence(persistence: Any, lines: list[str]) -> None:
    if not isinstance(persistence, dict) or not persistence:
        return
    bits: list[str] = []
    dbs = persistence.get("databases") or []
    if isinstance(dbs, list) and dbs:
        db_parts: list[str] = []
        for db in dbs:
            if not isinstance(db, dict):
                continue
            engine = db.get("engine", "")
            role = db.get("role", "")
            if engine and role:
                db_parts.append(f"{engine} ({role})")
            elif engine:
                db_parts.append(engine)
        if db_parts:
            bits.append(f"databases: {', '.join(db_parts)}")
    orm = persistence.get("orm")
    if isinstance(orm, dict) and orm.get("name"):
        bits.append(f"ORM: {orm['name']}")
    migration = persistence.get("migration_tool")
    if isinstance(migration, dict) and migration.get("name"):
        bits.append(f"migrations: {migration['name']}")
    mig_path = persistence.get("migrations_path")
    if mig_path:
        bits.append(f"migrations path: `{mig_path}`")
    if bits:
        lines.append(f"**Persistence:** {' · '.join(bits)}\n")


def _render_env_vars(env_vars: Any, lines: list[str]) -> None:
    if not isinstance(env_vars, list) or not env_vars:
        return
    lines.append("**Environment Variables:**")
    for entry in env_vars:
        if not isinstance(entry, dict):
            lines.append(f"- {entry}")
            continue
        name = entry.get("name", "")
        if not name:
            continue
        purpose = entry.get("purpose", "")
        required = entry.get("required")
        flag = (
            " (required)"
            if required is True
            else " (optional)"
            if required is False
            else ""
        )
        suffix = f" — {purpose}" if purpose else ""
        lines.append(f"- `{name}`{flag}{suffix}")
    lines.append("")


def _render_deployment(deployment: Any, lines: list[str]) -> None:
    if not isinstance(deployment, dict) or not deployment:
        return
    bits: list[str] = []
    container = deployment.get("containerization")
    if isinstance(container, dict) and container:
        tool = container.get("tool", "")
        dfp = container.get("dockerfile_path")
        compose = container.get("compose_path")
        base = container.get("base_image")
        sub_bits = [
            b
            for b in (
                f"`{dfp}`" if dfp else "",
                f"compose: `{compose}`" if compose else "",
                f"base: `{base}`" if base else "",
            )
            if b
        ]
        head = tool or "container"
        bits.append(f"{head} ({', '.join(sub_bits)})" if sub_bits else head)
    orch = deployment.get("orchestration")
    if isinstance(orch, dict) and orch:
        tool = orch.get("tool", "")
        manifests = orch.get("manifests_path")
        suffix = f" — `{manifests}`" if manifests else ""
        if tool:
            bits.append(f"orchestration: {tool}{suffix}")
    paas = deployment.get("paas")
    if isinstance(paas, dict) and paas:
        platform = paas.get("platform", "")
        config = paas.get("config_path")
        suffix = f" — `{config}`" if config else ""
        if platform:
            bits.append(f"PaaS: {platform}{suffix}")
    iac = deployment.get("iac")
    if isinstance(iac, dict) and iac:
        tool = iac.get("tool", "")
        path = iac.get("path")
        suffix = f" — `{path}`" if path else ""
        if tool:
            bits.append(f"IaC: {tool}{suffix}")
    if bits:
        lines.append("**Deployment:**")
        for bit in bits:
            lines.append(f"- {bit}")
        lines.append("")


def _render_api_surface(api_surface: Any, lines: list[str]) -> None:
    if not isinstance(api_surface, list) or not api_surface:
        return
    lines.append("**API Surface:**")
    for entry in api_surface:
        if not isinstance(entry, dict):
            lines.append(f"- {entry}")
            continue
        protocol = entry.get("protocol", "")
        path_or_method = entry.get("path_or_method", "")
        handler = entry.get("handler", "")
        summary = entry.get("summary", "")
        head = f"[{protocol}] `{path_or_method}`" if path_or_method else f"[{protocol}]"
        tail_bits = [
            b
            for b in (
                f"→ `{handler}`" if handler else "",
                summary,
            )
            if b
        ]
        tail = f" — {' · '.join(tail_bits)}" if tail_bits else ""
        lines.append(f"- {head}{tail}")
    lines.append("")


def _render_auth(auth: Any, lines: list[str]) -> None:
    if not isinstance(auth, dict) or not auth:
        return
    model = auth.get("model", "")
    provider = auth.get("provider", "")
    library = auth.get("library", "")
    bits = [b for b in (model, provider, library) if b]
    if bits:
        lines.append(f"**Authentication:** {' · '.join(bits)}\n")


def _render_ai_capabilities(ai_caps: Any, lines: list[str]) -> None:
    if not isinstance(ai_caps, list) or not ai_caps:
        return
    lines.append("**AI Capabilities:**")
    for entry in ai_caps:
        if not isinstance(entry, dict):
            lines.append(f"- {entry}")
            continue
        name = entry.get("name", "")
        kind = entry.get("kind", "")
        location = entry.get("location", "")
        head = f"{name} [{kind}]" if name and kind else name or str(entry)
        tail_bits = [
            b
            for b in (
                entry.get("description", ""),
                f"`{location}`" if location else "",
            )
            if b
        ]
        tail = f" — {' · '.join(tail_bits)}" if tail_bits else ""
        lines.append(f"- {head}{tail}")
    lines.append("")


def _render_typed_notes(notes: dict[str, Any], lines: list[str]) -> None:
    tc = notes.get("test_coverage")
    if isinstance(tc, dict):
        bits: list[str] = []
        if tc.get("has_tests") is False:
            bits.append("no tests detected")
        else:
            fw = tc.get("framework")
            if fw:
                bits.append(f"framework: {fw}")
            summary = tc.get("coverage_summary")
            covered = tc.get("covered_modules") or []
            uncovered = tc.get("uncovered_modules") or []
            if summary:
                bits.append(str(summary))
            else:
                if covered:
                    bits.append(f"covered: {', '.join(covered)}")
                if uncovered:
                    bits.append(f"uncovered: {', '.join(uncovered)}")
        if bits:
            lines.append(f"**Test Coverage:** {' · '.join(bits)}\n")

    ci = notes.get("ci_cd")
    if isinstance(ci, dict):
        if ci.get("present"):
            path = ci.get("path") or ci.get("type") or "detected"
            lines.append(f"**CI/CD:** {path}\n")
        elif ci.get("present") is False:
            lines.append("**CI/CD:** none detected\n")

    dead = notes.get("incomplete_or_dead_code") or []
    if isinstance(dead, list) and dead:
        lines.append("**Incomplete or Dead Code:**")
        for item in dead:
            lines.append(f"- {item}")
        lines.append("")

    risks = notes.get("change_risks") or []
    if isinstance(risks, list) and risks:
        lines.append("**Change Risks:**")
        for risk in risks:
            if isinstance(risk, dict):
                area = risk.get("area", "")
                desc = risk.get("risk", "")
                mit = risk.get("mitigation_hint", "")
                head = f"**{area}** — {desc}" if area else desc
                lines.append(f"- {head}")
                if mit:
                    lines.append(f"  - Mitigation: {mit}")
            else:
                lines.append(f"- {risk}")
        lines.append("")

    sec = notes.get("security_observations") or []
    if isinstance(sec, list) and sec:
        lines.append("**Security Observations:**")
        for item in sec:
            lines.append(f"- {item}")
        lines.append("")

    other = notes.get("other_notes") or []
    if isinstance(other, list) and other:
        lines.append("**Other Notes:**")
        for note in other:
            lines.append(f"- {note}")
        lines.append("")

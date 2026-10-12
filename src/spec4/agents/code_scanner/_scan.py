"""Repo walk, project-context gathering, and the size budgets that bound it.

Everything CodeScanner knows about a directory before an LLM is involved:
which paths to skip, which manifest/CI/deployment files are worth reading,
how much of each to read, and the assembly of that evidence into the single
markdown block the seed messages carry. Pure filesystem and string work --
no LLM, no session, no Dash.

``approx_tokens`` is here rather than beside ``run`` because it is the last
of the budgets. It was display-only (D-SC-P2); since 2.4.0 it is also the
meter the sampler spends ``EVIDENCE_TOKEN_BUDGET`` with (D-SC2-2).

Which files the seed shows, and in what form, is decided in ``_sample``
(step 2a): this module keeps the walk, the fixed-evidence formatters (tree,
README, manifests, CI, deployment, conventions) and their size constants.

``SampleRecord`` is the ledger of what the formatters below actually pasted
into that block. ``gather_project_context`` fills one when handed it, and the
1b ``coverage`` collector turns it into the stored ``scan.coverage`` — so the
record of what the model was shown comes from the code that showed it, not
from a second pass re-deriving the same selection (D-SC1b-4).

Split out of ``code_scanner.py`` in Phase 4c; the package ``__init__``
re-exports every name below under its original spelling.
"""

from __future__ import annotations

import collections
import dataclasses
import pathlib


_SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    "env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    ".cargo",
    ".spec4",
}

_MANIFEST_FILES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "Pipfile",
    "package.json",
    "package-lock.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "tsconfig.json",
    "babel.config.js",
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.yaml",
    ".prettierrc",
    ".prettierrc.json",
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    ".mypy.ini",
    "tox.ini",
    ".flake8",
    "pylintrc",
    ".pylintrc",
}

_DEPLOY_SIGNAL_FILES = {
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Procfile",
    "fly.toml",
    "render.yaml",
    "vercel.json",
    "netlify.toml",
    "app.yaml",
    "Caddyfile",
    "deploy.sh",
    "nginx.conf",
}
# A systemd unit is named for its service (``bws4-api.service``), so it is
# matched by suffix rather than by name (D-SC2-11).
_DEPLOY_SIGNAL_SUFFIXES = {".service"}
_MAX_DEPLOY_FILES = 5
_MAX_CI_FILES = 5
_MAX_SIGNAL_FILE_CHARS = 1_500

_README_NAMES = {"README.md", "README.rst", "README.txt", "README"}
_CI_DIR_PARTS = ((".github", "workflows"),)
_CI_FILE_BASENAMES = {
    ".gitlab-ci.yml",
    ".circleci",
    "azure-pipelines.yml",
    "bitbucket-pipelines.yml",
    "Jenkinsfile",
}
_TERRAFORM_DIRS = {"terraform", "infra", "infrastructure"}

# Project Conventions (D-SC2-10): root-level files only. An env example is
# pasted whole up to its cap; the agent-instruction and contributor docs by
# their head; the legal files are named, never pasted.
_ENV_EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template")
_CONVENTION_DOC_NAMES = ("CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md")
_PRESENT_ONLY_NAMES = ("CLA.md", "LICENSE", "LICENSE.md", "LICENSE.txt")
_MAX_ENV_EXAMPLE_CHARS = 1_500
_MAX_CONVENTION_LINES = 80
# Read cap for a file read only for its head lines; generous, it bounds memory.
_MAX_SOURCE_READ_CHARS = 2_000_000

# The whole evidence block's budget in ``approx_tokens`` (D-SC2-2). With the
# ~8.9 k-token system prompt and an update-mode prior review it keeps a fresh
# scan under ~45 k tokens for every provider in the fallback chain.
# ``llm_config["scan_context_tokens"]`` overrides it (``_sample``).
EVIDENCE_TOKEN_BUDGET = 24_000

_MAX_TREE_NODES = 400
_TOP_TREE_EXTENSIONS = 3
_TREE_FORM = "rollup+nodes"
_TREE_EMPTY = "empty"
_MAX_MANIFEST_CHARS = 10_000
_MAX_MANIFEST_FILE_CHARS = 3_000
_MAX_README_LINES = 80

_SOURCE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".rb",
    ".php",
    ".scala",
    ".r",
    ".R",
    ".lua",
    ".ex",
    ".exs",
}

_ENTRYPOINT_NAME_STEMS = {"main", "app", "index", "server", "cli", "__main__"}


@dataclasses.dataclass
class SampleRecord:
    """What ``gather_project_context`` pasted, as root-relative POSIX paths.

    Every list holds only files whose *contents* reached the seed; a file that
    was listed in the tree but never read is not sampled. ``tree_listed`` is
    the number of source paths the tree's node list named before its cap
    (2.4.0; the directory rollup above it is never capped), ``tree_form`` the
    shape of the tree section. ``sampled`` holds bodies, whole or headed;
    ``signatures_shown`` the files shown as signature blocks only;
    ``evidence_tokens`` the ``approx_tokens`` of the whole block (D-SC2-13).
    """

    tree_listed: int = 0
    tree_truncated: bool = False
    tree_form: str = _TREE_EMPTY
    readme: str | None = None
    manifests: list[str] = dataclasses.field(default_factory=list)
    ci: list[str] = dataclasses.field(default_factory=list)
    deploy: list[str] = dataclasses.field(default_factory=list)
    conventions: list[str] = dataclasses.field(default_factory=list)
    sampled: list[str] = dataclasses.field(default_factory=list)
    signatures_shown: list[str] = dataclasses.field(default_factory=list)
    source_files_total: int = 0
    evidence_tokens: int = 0


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def _is_entrypoint_candidate(path: pathlib.Path) -> bool:
    stem = path.stem.lower()
    return stem in _ENTRYPOINT_NAME_STEMS


def _read_text_safely(path: pathlib.Path, limit: int) -> str | None:
    try:
        return path.read_text(errors="replace")[:limit]
    except OSError:
        return None


def collect_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Walk the project tree, skipping vendored/build directories.

    Split out of `gather_project_context` so `run()` can perform the walk
    itself, report the file count as progress, and hand the result back for
    formatting instead of walking the tree twice (D-SC-P1).
    """
    all_files: list[pathlib.Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        all_files.append(path)
    return all_files


def file_tree_lines(
    root: pathlib.Path,
    all_files: list[pathlib.Path],
    nodes: list[str],
    lines: list[str],
    record: SampleRecord,
) -> None:
    """The file tree: a directory rollup, then the source node list (D-SC2-3).

    The rollup names every directory that holds a file, with its file count
    and top extensions, and is never capped. The node list names every
    non-test source file (``nodes``, the graph's) up to ``_MAX_TREE_NODES``.
    """
    by_dir: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    for f in all_files:
        parent = f.parent.relative_to(root).as_posix()
        by_dir[parent][f.suffix or f.name] += 1
    lines.append("### File Tree\n")
    lines.append("Directories (files, top extensions):\n```")
    for d in sorted(by_dir, key=lambda x: (x != ".", x)):
        counts = by_dir[d]
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        top = ", ".join(f"{k} {n}" for k, n in ranked[:_TOP_TREE_EXTENSIONS])
        label = "./" if d == "." else f"{d}/"
        lines.append(f"{label}  {sum(counts.values())}  ({top})")
    lines.append("```\n")
    shown = nodes[:_MAX_TREE_NODES]
    lines.append(f"Source files (non-test, {len(nodes)}):\n```")
    lines.extend(shown)
    if len(nodes) > _MAX_TREE_NODES:
        lines.append(f"(+{len(nodes) - _MAX_TREE_NODES} more)")
    lines.append("```\n")
    record.tree_form = _TREE_FORM
    record.tree_listed = len(shown)
    record.tree_truncated = len(nodes) > _MAX_TREE_NODES


def manifest_file_lines(
    root: pathlib.Path,
    all_files: list[pathlib.Path],
    lines: list[str],
    record: SampleRecord,
) -> None:
    """Config and manifest file contents, within the character budget."""
    lines.append("### Config and Manifest Files\n")
    manifest_chars = 0
    for f in all_files:
        if f.name in _MANIFEST_FILES and manifest_chars < _MAX_MANIFEST_CHARS:
            content = _read_text_safely(f, _MAX_MANIFEST_FILE_CHARS)
            if content is None:
                continue
            lines.append(f"#### `{f.relative_to(root)}`\n```\n{content}\n```\n")
            manifest_chars += len(content)
            record.manifests.append(_rel(root, f))


def _is_test_path(root: pathlib.Path, p: pathlib.Path) -> bool:
    """True when a path lies under a test/spec directory."""
    parts = [x.lower() for x in p.relative_to(root).parts]
    return any(x in ("test", "tests", "spec", "specs") for x in parts)


def format_readme_block(
    root: pathlib.Path, all_files: list[pathlib.Path], record: SampleRecord
) -> list[str]:
    readme = next(
        (f for f in all_files if f.name in _README_NAMES and f.parent == root),
        None,
    )
    if readme is None:
        return []
    try:
        text = readme.read_text(errors="replace")
    except OSError:
        return []
    record.readme = _rel(root, readme)
    sample_lines = text.splitlines()[:_MAX_README_LINES]
    sample = "\n".join(sample_lines)
    return [
        "### README Excerpt\n"
        f"_Source: `{readme.relative_to(root)}` (first {len(sample_lines)} lines)_\n"
        f"```\n{sample}\n```\n"
    ]


def format_ci_block(
    root: pathlib.Path, all_files: list[pathlib.Path], record: SampleRecord
) -> list[str]:
    ci_files: list[pathlib.Path] = []
    for f in all_files:
        rel_parts = f.relative_to(root).parts
        if any(rel_parts[: len(dp)] == dp for dp in _CI_DIR_PARTS):
            ci_files.append(f)
            continue
        if f.name in _CI_FILE_BASENAMES:
            ci_files.append(f)
    if not ci_files:
        return []
    out: list[str] = ["### CI / Workflow Files\n"]
    for f in ci_files[:_MAX_CI_FILES]:
        content = _read_text_safely(f, _MAX_SIGNAL_FILE_CHARS)
        if content is None:
            continue
        out.append(f"#### `{f.relative_to(root)}`\n```\n{content}\n```\n")
        record.ci.append(_rel(root, f))
    return out


def format_deployment_signals(
    root: pathlib.Path, all_files: list[pathlib.Path], record: SampleRecord
) -> list[str]:
    deploy_files: list[pathlib.Path] = []
    has_terraform = False
    for f in all_files:
        rel_parts = f.relative_to(root).parts
        if f.name in _DEPLOY_SIGNAL_FILES or f.suffix in _DEPLOY_SIGNAL_SUFFIXES:
            deploy_files.append(f)
        if any(p in _TERRAFORM_DIRS for p in rel_parts) and f.suffix in {
            ".tf",
            ".tfvars",
        }:
            has_terraform = True
    if not deploy_files and not has_terraform:
        return []
    out: list[str] = ["### Deployment Signals\n"]
    for f in deploy_files[:_MAX_DEPLOY_FILES]:
        content = _read_text_safely(f, _MAX_SIGNAL_FILE_CHARS)
        if content is None:
            out.append(f"- `{f.relative_to(root)}` present\n")
            continue
        out.append(f"#### `{f.relative_to(root)}`\n```\n{content}\n```\n")
        record.deploy.append(_rel(root, f))
    if has_terraform:
        out.append(
            "- Terraform configuration detected under infrastructure directory\n"
        )
    return out


def format_conventions_block(
    root: pathlib.Path, all_files: list[pathlib.Path], record: SampleRecord
) -> list[str]:
    """The Project Conventions section (D-SC2-10); empty when none is present.

    Root-level files only, in the order the name tuples give: env examples
    whole up to ``_MAX_ENV_EXAMPLE_CHARS``, the agent and contributor docs by
    their first ``_MAX_CONVENTION_LINES`` lines, the legal files by name.
    """
    at_root = {f.name: f for f in all_files if f.parent == root}
    out: list[str] = []
    for name in _ENV_EXAMPLE_NAMES:
        f = at_root.get(name)
        content = None if f is None else _read_text_safely(f, _MAX_ENV_EXAMPLE_CHARS)
        if content is not None:
            out.append(f"#### `{name}`\n```\n{content}\n```\n")
            record.conventions.append(name)
    for name in _CONVENTION_DOC_NAMES:
        f = at_root.get(name)
        content = None if f is None else _read_text_safely(f, _MAX_SOURCE_READ_CHARS)
        if content is not None:
            head = content.splitlines()[:_MAX_CONVENTION_LINES]
            out.append(
                f"#### `{name}` (first {len(head)} lines)\n```\n"
                + "\n".join(head)
                + "\n```\n"
            )
            record.conventions.append(name)
    present = [n for n in _PRESENT_ONLY_NAMES if n in at_root]
    if present:
        out.append("- Also present: " + ", ".join(f"`{n}`" for n in present) + "\n")
    if not out:
        return []
    return ["### Project Conventions\n", *out]


def approx_tokens(text: str) -> int:
    """Rough token count: four characters per token.

    D-SC-P2 introduced it for display only — telling the user how much was
    sent. Since 2.4.0 it is also the meter the sampler spends the evidence
    budget with (D-SC2-2, superseding D-SC-P2's "never used for budgeting"):
    one rule of thumb for what is shown and what is reported, so the budget
    and the narrated request size agree. It still decides only how much
    evidence is pasted, never a request parameter, so no tokenizer dependency
    is warranted.
    """
    return len(text) // 4

"""Repo walk, project-context gathering, and the size budgets that bound it.

Everything CodeScanner knows about a directory before an LLM is involved:
which paths to skip, which manifest/CI/deployment files are worth reading,
how much of each to read, and the assembly of that evidence into the single
markdown block the seed messages carry. Pure filesystem and string work --
no LLM, no session, no Dash.

``_approx_tokens`` is here rather than beside ``run`` because it is the last
of the budgets: the same display-only sizing that the ``_MAX_*`` constants
above enforce, reported back to the user (D-SC-P2).

Split out of ``code_scanner.py`` in Phase 4c; the package ``__init__``
re-exports every name below under its original spelling.
"""

from __future__ import annotations

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
}

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

_MAX_TREE_FILES = 150
_MAX_MANIFEST_CHARS = 10_000
_MAX_MANIFEST_FILE_CHARS = 3_000
_MAX_README_LINES = 80
_MAX_PRIORITY_SOURCE_FILES = 8
_MAX_SOURCE_SAMPLE_CHARS = 8_000
_MAX_SOURCE_SAMPLE_LINES = 80

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


def _is_entrypoint_candidate(path: pathlib.Path) -> bool:
    stem = path.stem.lower()
    return stem in _ENTRYPOINT_NAME_STEMS


def _read_text_safely(path: pathlib.Path, limit: int) -> str | None:
    try:
        return path.read_text(errors="replace")[:limit]
    except OSError:
        return None


def _collect_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Walk the project tree, skipping vendored/build directories.

    Split out of `_gather_project_context` so `run()` can perform the walk
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


def _gather_project_context(
    working_dir: str, all_files: list[pathlib.Path] | None = None
) -> str:
    root = pathlib.Path(working_dir)
    lines: list[str] = [f"## Project Directory: `{root}`\n"]

    if all_files is None:
        all_files = _collect_files(root)

    if not all_files:
        lines.append("The directory appears to be empty (no non-hidden files found).\n")
        return "\n".join(lines)

    _file_tree_lines(root, all_files, lines)

    readme_lines = _format_readme_block(root, all_files)
    if readme_lines:
        lines.extend(readme_lines)

    _manifest_file_lines(root, all_files, lines)

    ci_block = _format_ci_block(root, all_files)
    if ci_block:
        lines.extend(ci_block)

    deploy_block = _format_deployment_signals(root, all_files)
    if deploy_block:
        lines.extend(deploy_block)

    lines.append("### Source File Samples\n")
    source_files = [f for f in all_files if f.suffix in _SOURCE_EXTENSIONS]

    priority_files = _priority_source_files(root, source_files)
    _source_sample_lines(root, priority_files, lines)

    return "\n".join(lines)


def _file_tree_lines(
    root: pathlib.Path, all_files: list[pathlib.Path], lines: list[str]
) -> None:
    """The truncated file tree."""
    lines.append("### File Tree\n```")
    for f in all_files[:_MAX_TREE_FILES]:
        lines.append(str(f.relative_to(root)))
    if len(all_files) > _MAX_TREE_FILES:
        lines.append(
            f"... and {len(all_files) - _MAX_TREE_FILES} more files (truncated)"
        )
    lines.append("```\n")


def _manifest_file_lines(
    root: pathlib.Path, all_files: list[pathlib.Path], lines: list[str]
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


def _is_test_path(root: pathlib.Path, p: pathlib.Path) -> bool:
    """True when a path lies under a test/spec directory."""
    parts = [x.lower() for x in p.relative_to(root).parts]
    return any(x in ("test", "tests", "spec", "specs") for x in parts)


def _priority_source_files(
    root: pathlib.Path, source_files: list[pathlib.Path]
) -> list[pathlib.Path]:
    """Non-test sources, entrypoint candidates first, capped."""
    non_test_sources = [f for f in source_files if not _is_test_path(root, f)]
    entrypoint_files = [f for f in non_test_sources if _is_entrypoint_candidate(f)]
    other_files = [f for f in non_test_sources if not _is_entrypoint_candidate(f)]
    priority_files = (entrypoint_files + other_files)[:_MAX_PRIORITY_SOURCE_FILES]
    return priority_files


def _source_sample_lines(
    root: pathlib.Path, priority_files: list[pathlib.Path], lines: list[str]
) -> None:
    """Head samples of the priority source files, within the character budget."""
    source_chars = 0
    for f in priority_files:
        if source_chars >= _MAX_SOURCE_SAMPLE_CHARS:
            break
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue
        sample_lines = content.splitlines()[:_MAX_SOURCE_SAMPLE_LINES]
        sample = "\n".join(sample_lines)
        label = " (entrypoint candidate)" if _is_entrypoint_candidate(f) else ""
        lines.append(
            f"#### `{f.relative_to(root)}` (first {len(sample_lines)} lines){label}\n"
            f"```\n{sample}\n```\n"
        )
        source_chars += len(sample)


def _format_readme_block(
    root: pathlib.Path, all_files: list[pathlib.Path]
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
    sample_lines = text.splitlines()[:_MAX_README_LINES]
    sample = "\n".join(sample_lines)
    return [
        "### README Excerpt\n"
        f"_Source: `{readme.relative_to(root)}` (first {len(sample_lines)} lines)_\n"
        f"```\n{sample}\n```\n"
    ]


def _format_ci_block(root: pathlib.Path, all_files: list[pathlib.Path]) -> list[str]:
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
    for f in ci_files[:5]:
        content = _read_text_safely(f, 1500)
        if content is None:
            continue
        out.append(f"#### `{f.relative_to(root)}`\n```\n{content}\n```\n")
    return out


def _format_deployment_signals(
    root: pathlib.Path, all_files: list[pathlib.Path]
) -> list[str]:
    deploy_files: list[pathlib.Path] = []
    has_terraform = False
    for f in all_files:
        rel_parts = f.relative_to(root).parts
        if f.name in _DEPLOY_SIGNAL_FILES:
            deploy_files.append(f)
        if any(p in _TERRAFORM_DIRS for p in rel_parts) and f.suffix in {
            ".tf",
            ".tfvars",
        }:
            has_terraform = True
    if not deploy_files and not has_terraform:
        return []
    out: list[str] = ["### Deployment Signals\n"]
    for f in deploy_files[:5]:
        content = _read_text_safely(f, 1500)
        if content is None:
            out.append(f"- `{f.relative_to(root)}` present\n")
            continue
        out.append(f"#### `{f.relative_to(root)}`\n```\n{content}\n```\n")
    if has_terraform:
        out.append(
            "- Terraform configuration detected under infrastructure directory\n"
        )
    return out


def _approx_tokens(text: str) -> int:
    """Rough token count for display only (D-SC-P2).

    Four characters per token is the usual English-prose rule of thumb and is
    close enough to set an expectation about request size. It is never used for
    truncation, budgeting, or any request decision — only to tell the user how
    much was sent — so no tokenizer dependency is warranted.
    """
    return len(text) // 4

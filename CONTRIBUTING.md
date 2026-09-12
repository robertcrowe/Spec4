# Contributing to Spec4 AI

Thank you for your interest in contributing to **Spec4 AI**! This document explains how the project is governed and how you can get involved.

---

## Project Governance: BDFL

Spec4 AI follows the **Benevolent Dictator For Life (BDFL)** (Robert Crowe) model. This means:

- One maintainer holds final decision-making authority over all aspects of the project — its direction, design, and what gets merged.
- Community input, discussion, and contributions are genuinely welcomed and valued.
- However, there is no voting process or consensus requirement. Final decisions rest with the BDFL.

This model keeps the project coherent and moving quickly, especially at its current stage.

---

## How to Contribute

### Reporting Bugs

1. Search [existing issues](../../issues) to avoid duplicates.
2. Open a new issue using the **Bug Report** template.
3. Include a clear description, steps to reproduce, expected vs. actual behavior, and your environment (OS, version, etc.).

### Suggesting Features

1. Search existing issues and discussions first.
2. Open a new issue using the **Feature Request** template.
3. Describe the problem you're trying to solve, not just the solution you have in mind.
4. Be prepared for the possibility that a suggestion may be declined if it doesn't fit the project's vision — and that's okay.

### Contributing to the Pattern Library

The `src/spec4/agentifier/patterns/` directory contains the tier and mechanism pattern library that drives Agentifier's recommendations. Each pattern is a Markdown file with YAML frontmatter — see `patterns/SCHEMA.md` for the required structure.

**Good contributions to the pattern library include:**

- **New mechanism patterns** — a novel technique or architectural pattern with clear when-it-works and when-it-doesn't guidance (e.g., a new agentic evaluation pattern, a new memory mechanism)
- **Anti-pattern additions** — concrete over-engineering and under-engineering signs drawn from real-world experience, added to existing patterns
- **Reference updates** — updated canonical URLs or new authoritative references for existing patterns

Each pattern file must pass `make test` (the loader validates every pattern against the schema). Keep pattern descriptions grounded in observable trade-offs, not vendor marketing.

To check whether a tier-pattern or Tier Analyst prompt change affects calibration, run the eval harness in `evals/tier_calibration/` (see its README) before and after your change and compare the over-engineering rate. This harness is **not part of `make test`** — it makes real LLM calls and costs tokens.

### Development Setup and the Gate

Spec4 uses [uv](https://docs.astral.sh/uv/). After cloning:

```sh
uv sync
git config core.hooksPath scripts/hooks
```

The second line enables the repository's git hooks: a `pre-commit` hook runs the static checks, and a `pre-push` hook runs the test suite and the regression floor. They are the same checks CI runs, so enabling them means a push that fails CI is rare.

A change is done when all five of these pass:

```sh
uv run ruff check .
uv run ruff format --check src/ tests/
uv run mypy src/            # strict
uv run pytest --cov=spec4 --cov-report=term-missing -q
uv run python scripts/cleanup/floor_check.py
```

Three rules go with them:

- **Coverage must not fall.** New code arrives with its tests. The `pytest --cov` run prints the current missed-line count; a PR that raises it will be asked to add tests before review.
- **The regression floor is off-limits.** `scripts/cleanup/data/floor.json` names a set of test node ids that pin the application's core behaviour. They are not edited, renamed, moved, or deleted in an ordinary PR. If a change genuinely needs one to move, `scripts/cleanup/README.md` describes the petition process, and the PR must say which entry and why.
- **A `noqa` needs a reason.** Every lint suppression carries a comment on the same line explaining why the code is that way. The promoted ruff rules, strict mypy, and the complexity limits (C901 ≤ 10, branches ≤ 12, statements ≤ 50) are not relaxed for a feature.

Don't use `--no-verify` to get past a hook. If a hook fails on something that isn't your change, open an issue.

The full set of conventions the codebase follows — session-key handling, test patterns, typing, layout — is in [AGENTS.md](AGENTS.md). It is written for coding agents but applies to everyone.

### Submitting Code

1. **Open an issue first** before starting significant work. This avoids wasted effort if the change isn't a good fit.
2. Fork the repository and create a branch from `main`.
3. Follow the existing code style and conventions (see **Development Setup and the Gate** above and [AGENTS.md](AGENTS.md)).
4. Write or update tests as appropriate.
5. Keep commits focused and write clear commit messages.
6. Open a Pull Request (PR) against `main` with a clear description of what it does and why.
7. **Sign the CLA.** By opening a PR you confirm you have read and agree to the [Contributor License Agreement](CLA.md). Signing is handled automatically by the CLA assistant bot on your first PR. Corporate contributors should contact the maintainer directly before submitting — see [CLA.md](CLA.md) for details.

> **Note:** Opening a PR does not guarantee it will be merged. PRs that conflict with the project's direction or design philosophy may be closed, even if the code is technically sound.

---

## Decision-Making

All final decisions — including roadmap priorities, API design, feature acceptance, and breaking changes — are made by the BDFL. The process generally looks like this:

1. **Discussion**: Issues and PRs are open for community discussion.
2. **Input is considered**: Feedback, use cases, and alternative approaches are taken seriously.
3. **Decision is made**: The BDFL makes the final call and may explain the reasoning, though is not obligated to do so for every decision.

Disagreement is welcome; disputes are not. Respectful discussion is always encouraged.

---

## Code of Conduct

All contributors are expected to engage respectfully. This means:

- Be kind and constructive in all interactions.
- Critique ideas, not people.
- Accept that decisions may not always go your way.

Harassment or hostile behavior of any kind will result in removal from the project.

---

## Contributor License Agreement

All contributors must agree to the [Contributor License Agreement (CLA)](CLA.md) before their code can be merged. The CLA grants the maintainer the rights needed to distribute your contribution and covers copyright, patent, and warranty terms.

- **Individual contributors:** Signing is automatic — the CLA assistant bot will prompt you when you open your first PR.
- **Corporate contributors:** Contact Robert Crowe before submitting. See [CLA.md](CLA.md) for details.

---

## Questions?

Open a [Discussion](../../discussions) or file an issue. The maintainer will do their best to respond in a timely manner, though response times may vary.

---

*Spec4 AI is maintained by a single person, Robert Crowe. Patience and good faith go a long way — thank you for being part of it.*
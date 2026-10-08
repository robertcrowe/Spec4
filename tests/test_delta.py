"""CodeScanner v2 step 1d: the ``delta`` block.

Covers ``code_scanner._delta`` — which earlier review supplies the prior
scan, and the four scan-to-scan comparisons — with the trimmed BWS4 v9
2.2.0 review (``scan_bws4_2_2_0.json``, the first real-shaped ``scan``) as
the prior, plus the block's place in ``collect_scan`` and the schema.
"""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any
from unittest.mock import patch

from spec4.agents._code_review_schema import validate_code_review
from spec4.agents.code_scanner import _collect, _delta
from spec4.agents.code_scanner._scan import SampleRecord, collect_files
from tests._golden import load_fixture
from tests._review_helpers import review_envelope
from tests.test_prior import install_rounds

_FIXTURE = "scan_bws4_2_2_0.json"


def _prior_scan() -> dict[str, Any]:
    return copy.deepcopy(load_fixture(_FIXTURE)["code_review"]["scan"])


def _install_review(root: pathlib.Path, version: int, envelope: dict[str, Any]) -> None:
    d = root / ".spec4" / f"v{version}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "code_review.json").write_text(json.dumps(envelope))


def _descriptor() -> dict[str, Any]:
    return {"kind": "prior_review", "version": 9, "head": "861c009"}


class TestPriorScan:
    def test_nothing_on_disk_is_none(self, tmp_path: pathlib.Path) -> None:
        assert _delta.prior_scan(str(tmp_path), None) is None

    def test_active_round_prior_review_when_the_implemented_one_is_v1(
        self, tmp_path: pathlib.Path
    ) -> None:
        # BWS4 today: v8 implemented with a v1 review, v9 active with the
        # 2.2.0 scan this scan replaces.
        install_rounds(tmp_path, 8)
        _install_review(tmp_path, 9, load_fixture(_FIXTURE))
        found = _delta.prior_scan(str(tmp_path), {"phase_version": 9})
        assert found is not None
        descriptor, scan = found
        assert descriptor == _descriptor()
        assert scan["inventory"]["files_total"] == 41

    def test_implemented_round_wins_when_it_carries_a_measured_scan(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 8)
        _install_review(tmp_path, 8, load_fixture(_FIXTURE))
        other = load_fixture(_FIXTURE)
        other["code_review"]["scan"]["git"]["head"] = "fffffff"
        _install_review(tmp_path, 9, other)
        found = _delta.prior_scan(str(tmp_path), {"phase_version": 9})
        assert found is not None
        assert found[0] == {"kind": "implemented", "version": 8, "head": "861c009"}

    def test_a_scan_without_an_inventory_is_not_a_prior(
        self, tmp_path: pathlib.Path
    ) -> None:
        # A 2.0.0 envelope carries ``scan: {}``; a v1 file has no envelope.
        _install_review(tmp_path, 3, review_envelope())
        assert _delta.prior_scan(str(tmp_path), {"phase_version": 3}) is None
        _install_review(tmp_path, 3, {"code_review": {"schema_version": 1}})
        assert _delta.prior_scan(str(tmp_path), {"phase_version": 3}) is None

    def test_unreadable_review_is_skipped(self, tmp_path: pathlib.Path) -> None:
        d = tmp_path / ".spec4" / "v2"
        d.mkdir(parents=True)
        (d / "code_review.json").write_text("{")
        assert _delta.prior_scan(str(tmp_path), None) is None

    def test_head_is_null_without_a_git_block(self, tmp_path: pathlib.Path) -> None:
        envelope = load_fixture(_FIXTURE)
        del envelope["code_review"]["scan"]["git"]
        _install_review(tmp_path, 4, envelope)
        found = _delta.prior_scan(str(tmp_path), None)
        assert found is not None
        assert found[0] == {"kind": "prior_review", "version": 4, "head": None}


class TestComparisons:
    def test_identical_scans_yield_a_present_empty_block(self) -> None:
        prior = _prior_scan()
        delta = _delta.delta_block(copy.deepcopy(prior), prior, _descriptor())
        assert delta["prior"] == _descriptor()
        assert delta["files"] == {
            "added": [],
            "removed": [],
            "partial": False,
            "truncated": False,
        }
        assert delta["dependencies"] == {}
        assert delta["candidates"] == {"entered": [], "left": []}
        assert set(delta["signatures"]) == set(prior["signatures"]["files"])
        assert all(
            v == {"added": [], "removed": [], "changed": [], "truncated": False}
            for v in delta["signatures"].values()
        )

    def test_files_added_and_removed(self) -> None:
        prior = _prior_scan()
        current = copy.deepcopy(prior)
        listed = current["inventory"]["listed"]
        listed.remove("CLA.md")
        listed.append("deploy/Caddyfile")
        delta = _delta.delta_block(current, prior, _descriptor())
        assert delta["files"]["added"] == ["deploy/Caddyfile"]
        assert delta["files"]["removed"] == ["CLA.md"]

    def test_partial_when_either_listing_was_capped(self) -> None:
        prior = _prior_scan()
        current = copy.deepcopy(prior)
        current["inventory"]["truncated"] = True
        assert _delta.delta_block(current, prior, _descriptor())["files"]["partial"]
        assert _delta.delta_block(prior, current, _descriptor())["files"]["partial"]
        assert not _delta.delta_block(prior, prior, _descriptor())["files"]["partial"]

    def test_file_lists_are_capped_and_say_so(self) -> None:
        prior = _prior_scan()
        current = copy.deepcopy(prior)
        current["inventory"]["listed"].extend(f"new/{i}.py" for i in range(5))
        with patch.object(_delta, "_MAX_LIST", 3):
            delta = _delta.delta_block(current, prior, _descriptor())
        assert delta["files"]["added"] == ["new/0.py", "new/1.py", "new/2.py"]
        assert delta["files"]["truncated"] is True

    def test_manifests_in_both_scans_only(self) -> None:
        prior = _prior_scan()
        prior["dependencies"] = {
            "files": {
                "pyproject.toml": {"fastapi": ">=0.100", "tenacity": "", "gone": "1"},
                "old/package.json": {"x": "1"},
            },
            "truncated": False,
        }
        current = copy.deepcopy(prior)
        current["dependencies"] = {
            "files": {
                "pyproject.toml": {"fastapi": ">=0.110", "tenacity": "", "new": "1"},
                "frontend/package.json": {"react": "^18"},
            },
            "truncated": False,
        }
        delta = _delta.delta_block(current, prior, _descriptor())
        assert delta["dependencies"] == {
            "pyproject.toml": {
                "added": ["new"],
                "removed": ["gone"],
                "bumped": ["fastapi"],
                "truncated": False,
            }
        }

    def test_a_prior_without_manifests_compares_none(self) -> None:
        # The 2.2.0 prior predates the block; the first delta has nothing to
        # say about dependencies, and says so by comparing no manifest.
        prior = _prior_scan()
        current = copy.deepcopy(prior)
        current["dependencies"] = {"files": {"go.mod": {"a": "v1"}}, "truncated": False}
        assert _delta.delta_block(current, prior, _descriptor())["dependencies"] == {}

    def test_candidates_entered_and_left(self) -> None:
        prior = _prior_scan()
        current = copy.deepcopy(prior)
        ranked = current["module_graph"]["load_bearing_candidates"]
        ranked.pop()  # session.py leaves
        ranked.append({"path": "backend/app/main.py", "fan_in": 9, "consumers": []})
        delta = _delta.delta_block(current, prior, _descriptor())
        assert delta["candidates"] == {
            "entered": ["backend/app/main.py"],
            "left": ["backend/app/db/session.py"],
        }

    def test_signatures_by_name_on_files_in_both(self) -> None:
        prior = _prior_scan()
        current = copy.deepcopy(prior)
        files = current["signatures"]["files"]
        config = files["backend/app/core/config.py"]["symbols"]
        config[1]["signature"] = "def get_settings(*, reload: bool = False) -> Settings"
        config.append(
            {
                "kind": "variable",
                "name": "settings",
                "signature": "settings",
                "doc": None,
            }
        )
        del files["backend/app/services/agent_runtime.py"]
        files["backend/app/new.py"] = {
            "language": "python",
            "doc": None,
            "symbols": [],
            "truncated": False,
        }
        scenarios = files["backend/app/collab/scenarios.py"]["symbols"]
        scenarios.pop(0)  # CollabAgent removed
        delta = _delta.delta_block(current, prior, _descriptor())
        assert set(delta["signatures"]) == {
            "backend/app/core/config.py",
            "backend/app/collab/scenarios.py",
        }
        assert delta["signatures"]["backend/app/core/config.py"] == {
            "added": ["settings"],
            "removed": [],
            "changed": ["get_settings"],
            "truncated": False,
        }
        assert delta["signatures"]["backend/app/collab/scenarios.py"]["removed"] == [
            "CollabAgent"
        ]

    def test_odd_shapes_compare_as_empty(self) -> None:
        delta = _delta.delta_block(
            {"inventory": {"listed": "x"}, "dependencies": {"files": {"a": 1}}},
            {"module_graph": {"load_bearing_candidates": [{"fan_in": 1}, "x"]}},
            _descriptor(),
        )
        assert delta["files"] == {
            "added": [],
            "removed": [],
            "partial": True,
            "truncated": False,
        }
        assert delta["dependencies"] == {}
        assert delta["candidates"] == {"entered": [], "left": []}
        assert delta["signatures"] == {}


class TestAssembly:
    def test_collect_scan_diffs_against_the_prior_review_on_disk(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 8)
        _install_review(tmp_path, 9, load_fixture(_FIXTURE))
        (tmp_path / "CLA.md").write_text("# CLA\n")
        (tmp_path / "deploy").mkdir()
        (tmp_path / "deploy" / "Caddyfile").write_text("example.com {\n}\n")
        files = collect_files(tmp_path)
        scan = _collect.collect_scan(
            str(tmp_path), files, SampleRecord(), {"phase_version": 9}
        )
        delta = scan["delta"]
        assert delta["prior"] == _descriptor()
        assert delta["files"]["added"] == ["deploy/Caddyfile"]
        assert "CLA.md" not in delta["files"]["removed"]
        assert ".env.example" in delta["files"]["removed"]
        assert delta["candidates"]["left"] == [
            "backend/app/collab/scenarios.py",
            "backend/app/core/config.py",
            "backend/app/db/models.py",
            "backend/app/db/session.py",
            "backend/app/services/agent_runtime.py",
        ]
        assert validate_code_review(review_envelope(scan=scan)) == []

    def test_without_a_prior_scan_the_block_is_absent(
        self, tmp_path: pathlib.Path
    ) -> None:
        install_rounds(tmp_path, 8)
        scan = _collect.collect_scan(str(tmp_path), [], SampleRecord(), None)
        assert "delta" not in scan
        assert "prior_round" in scan

    def test_the_block_is_closed(self, tmp_path: pathlib.Path) -> None:
        _install_review(tmp_path, 9, load_fixture(_FIXTURE))
        scan = _collect.collect_scan(
            str(tmp_path), [], SampleRecord(), {"phase_version": 9}
        )
        assert validate_code_review(review_envelope(scan=scan)) == []
        scan["delta"]["files"]["renamed"] = []
        errors = validate_code_review(review_envelope(scan=scan))
        assert errors
        assert any("renamed" in e for e in errors)

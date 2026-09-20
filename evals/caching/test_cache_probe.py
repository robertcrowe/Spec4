"""Synthetic usage.json fixtures for cache_probe. No project data, no LLM."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cache_probe  # noqa: E402


def _call(ts: str, **fields):
    base = {
        "timestamp": ts, "agent": "a", "model": "m", "provider": "p",
        "prompt_tokens": None, "cached_tokens": None,
        "cache_creation_input_tokens": None, "cache_read_input_tokens": None,
        "computed_cost_usd": None, "usage_missing": False,
    }  # fmt: skip
    return {**base, **fields}


def _write(root: Path, agents: dict, version: int = 1) -> Path:
    path = root / ".spec4" / f"v{version}" / "usage.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"agents": {n: {"history": h} for n, h in agents.items()}})
    )
    return root


def _agent(tmp_path: Path, history: list) -> dict:
    _write(tmp_path, {"a": history})
    (rep,) = cache_probe.report_projects([tmp_path])
    return rep["agents"]["a"]


def test_no_cache_fields_prints_dash_not_zero(tmp_path):
    s = _agent(tmp_path, [_call("2026-01-01T00:00:00+00:00", prompt_tokens=100)])
    assert s["prompt_tokens"] == 100
    assert s["cache_read"] is None
    assert s["cache_creation"] is None
    assert s["calls_with_read"] is None
    assert s["read_ratio"] is None
    assert s["computed_cost_usd"] is None
    (rep,) = cache_probe.report_projects([tmp_path])
    row = cache_probe.render_file(rep).splitlines()[3]
    assert row.split()[:6] == ["a", "-", "1", "0", "100", "-"]


def test_openai_cached_tokens_only(tmp_path):
    s = _agent(
        tmp_path,
        [
            _call("2026-01-01T00:00:00+00:00", prompt_tokens=100, cached_tokens=40, computed_cost_usd=0.5),
            _call("2026-01-01T00:01:00+00:00", prompt_tokens=100, cached_tokens=0, computed_cost_usd=0.25),
        ],
    )  # fmt: skip
    assert s["cache_read"] == 40
    assert s["cache_creation"] is None
    assert s["calls_with_read"] == 1
    assert s["read_ratio"] == 0.2
    assert s["computed_cost_usd"] == 0.75


def test_anthropic_read_and_creation(tmp_path):
    s = _agent(
        tmp_path,
        [
            _call("2026-01-01T00:00:00+00:00", prompt_tokens=1000, cache_creation_input_tokens=900, cache_read_input_tokens=0),
            _call("2026-01-01T00:04:00+00:00", prompt_tokens=1000, cache_creation_input_tokens=0, cache_read_input_tokens=900, cached_tokens=5),
            _call("2026-01-01T00:14:00+00:00", prompt_tokens=1000, cache_creation_input_tokens=900, cache_read_input_tokens=0),
        ],
    )  # fmt: skip
    assert s["cache_read"] == 900  # cache_read_input_tokens wins over cached_tokens
    assert s["cache_creation"] == 1800
    assert s["calls_with_read"] == 1
    assert s["gap_count"] == 2
    assert s["gap_median_s"] == 420.0
    assert s["gap_max_s"] == 600.0
    assert (
        s["gaps_over_ttl"] == 1
    )  # the 240 s gap is inside the TTL, the 600 s one is not


def test_usage_missing_record(tmp_path):
    s = _agent(
        tmp_path,
        [
            _call("2026-01-01T00:00:00+00:00", usage_missing=True),
            _call("2026-01-01T00:00:10+00:00", prompt_tokens=50, cache_read_input_tokens=10),
        ],
    )  # fmt: skip
    assert s["calls"] == 2
    assert s["calls_missing_usage"] == 1
    assert s["prompt_tokens"] == 50
    assert s["cache_read"] == 10


def test_only_missing_usage_is_all_dashes(tmp_path):
    s = _agent(tmp_path, [_call("2026-01-01T00:00:00+00:00", usage_missing=True)])
    assert s["calls_missing_usage"] == 1
    assert s["prompt_tokens"] is None
    assert s["cache_read"] is None
    assert s["gap_median_s"] is None
    assert s["gaps_over_ttl"] is None


def test_distinct_model_pairs(tmp_path):
    s = _agent(
        tmp_path,
        [
            _call("2026-01-01T00:00:00+00:00", model="x", provider="anthropic"),
            _call("2026-01-01T00:00:01+00:00", model="x", provider="anthropic"),
            _call("2026-01-01T00:00:02+00:00", model="y", provider="openai"),
        ],
    )  # fmt: skip
    assert s["models"] == [["x", "anthropic"], ["y", "openai"]]


def test_compare_deltas_and_json(tmp_path, capsys):
    before, after = tmp_path / "before", tmp_path / "after"
    _write(
        before,
        {
            "a": [
                _call(
                    "2026-01-01T00:00:00+00:00",
                    prompt_tokens=100,
                    computed_cost_usd=1.0,
                )
            ]
        },
    )
    _write(after, {"a": [_call("2026-01-01T00:00:00+00:00", prompt_tokens=100, cache_read_input_tokens=80, cache_creation_input_tokens=20, computed_cost_usd=0.4)]})  # fmt: skip
    assert cache_probe.main(["--compare", str(before), str(after), "--json"]) == 0
    row = json.loads(capsys.readouterr().out)["agents"]["a"]
    assert row["cache_read"] == {"before": None, "after": 80, "delta": 80}
    assert row["cache_creation"]["delta"] == 20
    assert abs(row["computed_cost_usd"]["delta"] - -0.6) < 1e-9


def test_main_no_usage_files_exits_nonzero(tmp_path, capsys):
    assert cache_probe.main([str(tmp_path)]) == 1
    assert "no .spec4" in capsys.readouterr().err


def _agentifier_report(tmp_path: Path) -> dict:
    _write(
        tmp_path,
        {
            "phaser": [_call("2026-01-01T00:00:00+00:00", agent="phaser", prompt_tokens=10)],
            "agentifier": [
                _call("2026-01-01T00:00:00+00:00", agent="tier_analyst", prompt_tokens=100),
                _call("2026-01-01T00:01:00+00:00", agent="spec_drafter", prompt_tokens=200),
                _call("2026-01-01T00:02:00+00:00", agent="agentifier", prompt_tokens=300),
                _call("2026-01-01T00:03:00+00:00", agent=None, prompt_tokens=400),  # no agent: rollup key
            ],
        },
    )  # fmt: skip
    (rep,) = cache_probe.report_projects([tmp_path])
    return rep


def test_sub_agents_report_as_own_rows_under_parent(tmp_path):
    agents = _agentifier_report(tmp_path)["agents"]
    assert list(agents) == ["agentifier", "spec_drafter", "tier_analyst", "phaser"]
    assert agents["tier_analyst"]["parent"] == "agentifier"
    assert agents["spec_drafter"]["parent"] == "agentifier"
    assert agents["tier_analyst"]["prompt_tokens"] == 100
    assert agents["spec_drafter"]["prompt_tokens"] == 200
    # the parent's own row holds its own record plus the record with no agent field
    assert agents["agentifier"]["parent"] is None
    assert agents["agentifier"]["calls"] == 2
    assert agents["agentifier"]["prompt_tokens"] == 700
    assert agents["phaser"]["parent"] is None
    assert "agentifier" not in {
        a["parent"] for a in agents.values() if a["parent"] is None
    }


def test_gaps_are_per_raw_agent(tmp_path):
    agents = _agentifier_report(tmp_path)["agents"]
    assert agents["tier_analyst"]["gap_count"] == 0  # one call: no gap
    assert agents["tier_analyst"]["gap_max_s"] is None
    assert agents["agentifier"]["gap_max_s"] == 60.0  # 00:02 -> 00:03 only
    assert agents["agentifier"]["gap_count"] == 1


def test_parent_column_renders(tmp_path):
    rows = cache_probe.render_file(_agentifier_report(tmp_path)).splitlines()
    by_name = {r.split()[0]: r.split() for r in rows[3:]}
    assert by_name["tier_analyst"][1] == "agentifier"
    assert by_name["agentifier"][1] == "-"


def test_clock_skew_and_min_gap(tmp_path):
    s = _agent(
        tmp_path,
        [
            _call("2026-01-01T00:00:00+00:00", duration_s=10.0),
            _call("2026-01-01T00:00:05+00:00", duration_s=1.0),  # stamped inside the first
            _call("2026-01-01T00:00:30+00:00", duration_s=1.0),  # stamped after the second's duration
        ],
    )  # fmt: skip
    assert s["clock_skew"] == 1
    assert s["min_gap_s"] == 5.0
    assert s["gap_max_s"] == 25.0


def test_no_clock_skew_when_stamps_clear_durations_and_dash_without_pairs(tmp_path):
    s = _agent(
        tmp_path,
        [
            _call("2026-01-01T00:00:00+00:00", duration_s=1.0),
            _call("2026-01-01T00:00:05+00:00", duration_s=1.0),
        ],
    )  # fmt: skip
    assert s["clock_skew"] == 0
    single = cache_probe.agent_stats([_call("2026-01-01T00:00:00+00:00")])
    assert single["clock_skew"] is None
    assert single["min_gap_s"] is None


def test_both_differ_counts_unequal_pairs_only(tmp_path):
    s = _agent(
        tmp_path,
        [
            _call("2026-01-01T00:00:00+00:00", cache_read_input_tokens=90, cached_tokens=80),
            _call("2026-01-01T00:00:01+00:00", cache_read_input_tokens=50, cached_tokens=50),
            _call("2026-01-01T00:00:02+00:00", cache_read_input_tokens=7),
        ],
    )  # fmt: skip
    assert s["both_differ"] == 1
    assert s["cache_read"] == 147  # read-first precedence unchanged
    only_one_field = cache_probe.agent_stats([_call("t", cached_tokens=5)])
    assert only_one_field["both_differ"] is None

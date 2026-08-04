"""Unit tests for the relevance judge (parse/prompt) and scoring harness."""

from __future__ import annotations

import pytest

from relevance_judge import (
    VARIANTS,
    Verdict,
    build_judge_user_prompt,
    judge_system_prompt,
    parse_judge_response,
)
from relevance_scoring import (
    adjacent_to_offdomain_fp_rate,
    confusion_matrix,
    gate_for,
    off_domain_recall,
    pair_drift,
    per_class_metrics,
    score_by_tier,
    score_verdicts,
)


def _vision() -> dict:
    return {
        "purpose": "A fare calculator for a regional rail network.",
        "target_audience": ["Riders looking up exact fares"],
        "key_features_mvp": [
            {"fare_lookup": {"description": "Return the exact published fare."}},
            {"saved_trips": {"description": "Save frequent origin/destination pairs."}},
        ],
    }


# --- prompt builder ----------------------------------------------------------


def test_prompt_includes_purpose_features_and_candidate() -> None:
    prompt = build_judge_user_prompt(
        _vision(),
        {"name": "station_name_matching", "rough_description": "Resolve typed names."},
    )
    assert "fare calculator" in prompt
    assert "fare_lookup" in prompt and "saved_trips" in prompt
    assert "station_name_matching" in prompt
    assert "Resolve typed names." in prompt


def test_prompt_handles_pipeline_shape() -> None:
    vision = {"name": "X", "vision": {"purpose": "P", "key_features_mvp": [
        {"feat_a": {"description": "d"}}]}}
    prompt = build_judge_user_prompt(vision, {"name": "c"})
    assert "feat_a" in prompt and "Purpose: P" in prompt


# --- parser ------------------------------------------------------------------


def test_parse_clean_json() -> None:
    txt = ('{"classification": "grounded", "cited_support": "fare_lookup", '
           '"borderline": false, "reason": "needed to look up fares"}')
    v = parse_judge_response(txt, "station_name_matching")
    assert v.classification == "grounded"
    assert v.cited_support == "fare_lookup"
    assert v.borderline is False
    assert v.ok


def test_parse_tolerates_code_fence_and_prose() -> None:
    fence = "```"
    txt = (
        "Here is my judgement:\n" + fence + "json\n"
        + '{"classification":"off_domain","cited_support":"","borderline":true,'
        + '"reason":"operator-facing"}\n' + fence + "\n"
    )
    v = parse_judge_response(txt, "fare_anomaly_detection")
    assert v.classification == "off_domain"
    assert v.borderline is True


def test_parse_no_json_is_error() -> None:
    v = parse_judge_response("I cannot answer that.", "x")
    assert v.classification == "error"
    assert not v.ok


def test_parse_bad_class_is_error() -> None:
    v = parse_judge_response('{"classification": "maybe"}', "x")
    assert v.classification == "error"


def test_parse_reads_stated_jobs() -> None:
    txt = ('{"stated_jobs": ["cook tonight", "save recipes"], '
           '"classification": "adjacent", "cited_support": "cook tonight", '
           '"borderline": true, "reason": "helps the cook job"}')
    v = parse_judge_response(txt, "substitutions")
    assert v.stated_jobs == ["cook tonight", "save recipes"]
    assert v.classification == "adjacent"


def test_stated_jobs_defaults_empty_when_absent() -> None:
    v = parse_judge_response('{"classification": "grounded"}', "x")
    assert v.stated_jobs == []


# --- variant prompts ---------------------------------------------------------


def test_variants_share_grounded_but_differ_on_adjacency() -> None:
    a = judge_system_prompt("drop_domain")
    b = judge_system_prompt("audience_goal")
    # grounded (necessity) step is identical in both
    assert "Necessity test" in a and "Necessity test" in b
    # drop_domain never says "domain" as a criterion and has no jobs
    assert "stated_jobs" not in a
    # audience_goal derives jobs, feature-bounded
    assert "stated_jobs" in b and "AT MOST\nONE job per feature" in b
    assert a != b


def test_unknown_variant_raises() -> None:
    with pytest.raises(ValueError):
        judge_system_prompt("nonsense")


def test_variants_constant() -> None:
    assert VARIANTS == ("drop_domain", "audience_goal")


# --- scoring: confusion matrix + metrics ------------------------------------


def _v(name: str, cls: str, borderline: bool = False) -> Verdict:
    return Verdict(name, cls, borderline=borderline)


def test_confusion_matrix_counts() -> None:
    gold = [_v("a", "grounded"), _v("b", "adjacent"), _v("c", "off_domain")]
    pred = [_v("a", "grounded"), _v("b", "off_domain"), _v("c", "off_domain")]
    cm = confusion_matrix(gold, pred)
    assert cm["grounded"]["grounded"] == 1
    assert cm["adjacent"]["off_domain"] == 1   # the FP we care about
    assert cm["off_domain"]["off_domain"] == 1


def test_confusion_matrix_name_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        confusion_matrix([_v("a", "grounded")], [_v("b", "grounded")])


def test_error_prediction_bucketed() -> None:
    cm = confusion_matrix([_v("a", "grounded")], [_v("a", "error")])
    assert cm["grounded"]["error"] == 1


def test_off_domain_recall_and_adjacent_fp() -> None:
    gold = [
        _v("o1", "off_domain"), _v("o2", "off_domain"),
        _v("j1", "adjacent"), _v("j2", "adjacent"),
    ]
    pred = [
        _v("o1", "off_domain"), _v("o2", "adjacent"),   # 1 of 2 off_domain caught
        _v("j1", "off_domain"), _v("j2", "adjacent"),   # 1 of 2 adjacent mis-flagged
    ]
    cm = confusion_matrix(gold, pred)
    assert off_domain_recall(cm) == pytest.approx(0.5)
    assert adjacent_to_offdomain_fp_rate(cm) == pytest.approx(0.5)


def test_per_class_metrics_perfect() -> None:
    gold = [_v("a", "grounded"), _v("b", "adjacent"), _v("c", "off_domain")]
    cm = confusion_matrix(gold, list(gold))
    m = per_class_metrics(cm)
    for label in ("grounded", "adjacent", "off_domain"):
        assert m[label]["precision"] == pytest.approx(1.0)
        assert m[label]["recall"] == pytest.approx(1.0)


def test_score_verdicts_report_shape() -> None:
    gold = [_v("a", "grounded"), _v("b", "off_domain")]
    pred = [_v("a", "grounded"), _v("b", "off_domain", borderline=True)]
    report = score_verdicts(gold, pred)
    assert report["n"] == 2
    assert report["off_domain_recall"] == pytest.approx(1.0)
    assert report["n_borderline_pred"] == 1
    assert report["n_parse_errors"] == 0


# --- scoring: tier slice + matched-pair drift -------------------------------


def test_gate_for_none_when_no_denominator() -> None:
    gold = [_v("a", "grounded"), _v("b", "grounded")]
    g = gate_for(gold, list(gold))
    # no gold off_domain and no gold adjacent -> both rates undefined, not 0.0
    assert g["off_domain_recall"] is None
    assert g["adjacent_to_offdomain_fp_rate"] is None


def test_score_by_tier_buckets_and_untagged() -> None:
    gold = [_v("o", "off_domain"), _v("j", "adjacent"), _v("x", "grounded")]
    pred = [_v("o", "off_domain"), _v("j", "off_domain"), _v("x", "grounded")]
    by_tier = score_by_tier(gold, pred, {"o": "tool_agent", "j": "tool_agent"})
    assert by_tier["tool_agent"]["off_domain_recall"] == pytest.approx(1.0)
    assert by_tier["tool_agent"]["adjacent_to_offdomain_fp_rate"] == pytest.approx(1.0)
    assert by_tier["untagged"]["n"] == 1  # "x" had no tier tag
    assert by_tier["untagged"]["off_domain_recall"] is None


def test_pair_drift_flags_within_pair_split() -> None:
    split = pair_drift(
        [_v("lo", "grounded"), _v("hi", "off_domain"), _v("solo", "adjacent")],
        {"lo": "P", "hi": "P"},
    )
    assert split["P"]["drift"] is True
    assert "solo" not in {n for members in split.values() for n, _ in members["members"]}
    agree = pair_drift(
        [_v("lo", "grounded"), _v("hi", "grounded")], {"lo": "P", "hi": "P"}
    )
    assert agree["P"]["drift"] is False
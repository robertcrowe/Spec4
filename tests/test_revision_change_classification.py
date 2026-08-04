"""Unit tests for Brainstormer's deterministic change-categorization
reconciliation (``_reclassify_changes`` via ``_apply_revision_history``).

The model authors a revision's ``changes`` (added / modified / removed feature
names) and can mislabel a brand-new feature as ``modified`` — notably when it
was added and then edited within the same revision session, so the model
categorizes against the intermediate vision rather than the prior *implemented*
baseline. Reconciliation recomputes the add/remove axis from
``key_features_mvp`` membership and keeps ``modified`` only for features present
in both versions. Fully deterministic — no behavioral draw required.
"""

from __future__ import annotations

from typing import Any

from spec4.agents.brainstormer import _apply_revision_history, _feature_names


def _vision(names: list[str], history: list[dict[str, Any]] | None = None) -> dict:
    kf = [{n: {"description": f"desc of {n}"}} for n in names]
    vs: dict[str, Any] = {"vision_statement": {"vision": {"key_features_mvp": kf}}}
    if history is not None:
        vs["vision_statement"]["revision_history"] = history
    return vs


def _emitted(names: list[str], changes: dict[str, list[str]]) -> dict:
    e = _vision(names)
    e["revision"] = {"goal": "g", "changes": changes, "rationale": "r"}
    return e


def _changes_after(emitted: dict, prior: dict, current: dict | None = None,
                   version: int = 1, based_on: int = 0) -> dict:
    out = _apply_revision_history(emitted, prior, current, version, based_on)
    return out["vision_statement"]["revision_history"][-1]["changes"]


# --- the reported bug -------------------------------------------------------


def test_new_feature_labelled_modified_is_reclassified_added() -> None:
    # v0 has no Trash_Talk; v1 adds it; model (mis)labelled it modified after an
    # add-then-edit within the session.
    base = ["Board", "AI_Opponent", "Rules"]
    prior = _vision(base)
    emitted = _emitted(base + ["Trash_Talk"], {"modified": ["Trash_Talk"]})
    ch = _changes_after(emitted, prior)
    assert ch == {"added": ["Trash_Talk"], "modified": [], "removed": []}


# --- the other reconciliations ---------------------------------------------


def test_genuine_modify_of_existing_feature_stays_modified() -> None:
    base = ["Board", "Rules"]
    prior = _vision(base)
    emitted = _emitted(base, {"modified": ["Rules"]})
    ch = _changes_after(emitted, prior)
    assert ch == {"added": [], "modified": ["Rules"], "removed": []}


def test_existing_feature_mislabelled_added_is_reclassified_modified() -> None:
    base = ["Board", "Rules"]
    prior = _vision(base)
    emitted = _emitted(base, {"added": ["Rules"]})
    ch = _changes_after(emitted, prior)
    assert ch == {"added": [], "modified": ["Rules"], "removed": []}


def test_removed_is_computed_from_membership_even_if_model_omits() -> None:
    prior = _vision(["Board", "Rules", "Legacy"])
    emitted = _emitted(["Board", "Rules"], {})  # model said nothing
    ch = _changes_after(emitted, prior)
    assert ch == {"added": [], "modified": [], "removed": ["Legacy"]}


def test_added_completeness_when_model_omits_it() -> None:
    prior = _vision(["Board"])
    emitted = _emitted(["Board", "Brand_New"], {})  # model omitted the add
    ch = _changes_after(emitted, prior)
    assert ch == {"added": ["Brand_New"], "modified": [], "removed": []}


def test_rename_is_remove_plus_add() -> None:
    prior = _vision(["Board", "Old_Name"])
    emitted = _emitted(["Board", "New_Name"], {"modified": ["New_Name"]})
    ch = _changes_after(emitted, prior)
    assert ch == {"added": ["New_Name"], "modified": [], "removed": ["Old_Name"]}


def test_ordering_added_by_v1_removed_by_v0() -> None:
    prior = _vision(["A", "B", "C"])
    emitted = _emitted(["B", "Z", "Y"], {})
    ch = _changes_after(emitted, prior)
    assert ch["added"] == ["Z", "Y"]  # v1 appearance order
    assert ch["removed"] == ["A", "C"]  # v0 appearance order


# --- guards / shapes --------------------------------------------------------


def test_no_v1_key_features_leaves_model_changes_untouched() -> None:
    # No ground truth to reconcile against → preserve the model's lists.
    prior = _vision(["Board"])
    emitted = {
        "vision_statement": {"name": "App"},
        "revision": {"goal": "g", "changes": {"modified": ["Whatever"]}},
    }
    ch = _changes_after(emitted, prior)
    assert ch == {"added": [], "modified": ["Whatever"], "removed": []}


def test_reentry_path_is_also_reconciled() -> None:
    # No fresh revision block; the current session vision carries this round's
    # entry with a stale 'modified' for a feature new to this revision.
    prior = _vision([])
    current = {
        "vision_statement": {
            "revision_history": [
                {
                    "version": 1,
                    "based_on_version": 0,
                    "goal": "g",
                    "changes": {"added": [], "modified": ["Trash_Talk"],
                                "removed": []},
                }
            ]
        }
    }
    emitted = _vision(["Trash_Talk"])  # no 'revision' block on re-edit
    ch = _changes_after(emitted, prior, current)
    assert ch == {"added": ["Trash_Talk"], "modified": [], "removed": []}


def test_feature_names_handles_dict_and_string_shapes() -> None:
    dict_shape = _vision(["A", "B"])
    assert _feature_names(dict_shape) == ["A", "B"]
    string_shape = {"vision_statement": {"vision": {"key_features_mvp": ["X", "Y"]}}}
    assert _feature_names(string_shape) == ["X", "Y"]


def test_feature_names_fallback_to_top_level_key_features() -> None:
    # Some simplified shapes put key_features_mvp directly under vision_statement.
    v = {"vision_statement": {"key_features_mvp": ["P", "Q"]}}
    assert _feature_names(v) == ["P", "Q"]


def test_feature_names_empty_when_absent() -> None:
    assert _feature_names({"vision_statement": {"name": "App"}}) == []
    assert _feature_names(None) == []


def test_string_entry_revision_reconciles() -> None:
    prior = {"vision_statement": {"vision": {"key_features_mvp": ["A", "B"]}}}
    emitted = {
        "vision_statement": {"vision": {"key_features_mvp": ["A", "B", "C"]}},
        "revision": {"goal": "g", "changes": {"modified": ["C"]}},
    }
    ch = _changes_after(emitted, prior)
    assert ch == {"added": ["C"], "modified": [], "removed": []}

"""Full Screen is available wherever Designer shows a mock preview.

A brownfield revision round enters Designer through carry-forward, which lands
directly on the refine view (step 7) with the prior round's mock already loaded.
That view rendered the same 600px iframe as the preview view but no Full Screen
control, so the first mock a brownfield developer sees was the one mock they
could not open full size. Both views now share ``_fullscreen_row``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from spec4.callbacks.designer import on_designer_carry_forward
from spec4.layouts.designer import _step6_content, _step7_content


def _ids(node: Any, acc: list[Any] | None = None) -> list[Any]:
    acc = [] if acc is None else acc
    if isinstance(node, (list, tuple)):
        for item in node:
            _ids(item, acc)
        return acc
    node_id = getattr(node, "id", None)
    if node_id is not None:
        acc.append(node_id)
    children = getattr(node, "children", None)
    if children is not None and not isinstance(children, str):
        _ids(children, acc)
    return acc


_MOCK = "<!DOCTYPE html><html><body><h1>Hi</h1></body></html>"


class TestPreviewView:
    def test_step6_still_offers_full_screen(self) -> None:
        ids = _ids(_step6_content({"mock_html": _MOCK, "finalized": False}))
        assert "mock-fullscreen-btn" in ids
        assert "mock-iframe" in ids

    def test_step6_offers_it_when_finalized_too(self) -> None:
        ids = _ids(_step6_content({"mock_html": _MOCK, "finalized": True}))
        assert "mock-fullscreen-btn" in ids


class TestRefineView:
    def test_step7_offers_full_screen(self) -> None:
        ids = _ids(_step7_content({"mock_html": _MOCK}))
        assert "mock-fullscreen-btn" in ids, (
            "the refine view renders the mock at 600px like the preview view, "
            "and in a brownfield revision it is the first view the developer sees"
        )

    def test_step7_keeps_its_own_controls(self) -> None:
        ids = _ids(_step7_content({"mock_html": _MOCK}))
        for expected in (
            "mock-iframe",
            "designer-refine-input",
            "btn-designer-regenerate",
            "btn-designer-refine-cancel",
        ):
            assert expected in ids

    def test_step7_offers_it_without_image_support(self) -> None:
        """The upload zone is swapped for a hidden div in that mode — the
        preview controls are unaffected."""
        ids = _ids(_step7_content({"mock_html": _MOCK}, image_support=False))
        assert "mock-fullscreen-btn" in ids

    def test_button_id_matches_the_clientside_handler(self) -> None:
        """One id serves both steps because only one renders at a time; it has to
        be the id the handler listens on."""
        from spec4.app import app

        triggers = {
            (d["id"], d["property"])
            for entry in app._callback_list
            for d in (
                entry.get("inputs")
                if isinstance(entry.get("inputs"), list)
                else [entry.get("inputs")]
            )
            if isinstance(d, dict) and "id" in d and "property" in d
        }
        assert ("mock-fullscreen-btn", "n_clicks") in triggers


class TestBrownfieldEntryPoint:
    """Carry-forward is the path that exposed the gap — pin where it lands."""

    def test_carry_forward_lands_on_the_refine_view_with_the_mock(self) -> None:
        session = {"working_dir": "/tmp/proj", "vision_statement": {}}
        with (
            patch(
                "spec4.callbacks.designer.project_manager.load_prior_mock",
                return_value=_MOCK,
            ),
            patch("spec4.callbacks.designer.revision_delta", return_value=None),
        ):
            store = on_designer_carry_forward(1, {"step": 2}, session)
        assert store["step"] == 7
        assert store["mock_html"] == _MOCK
        # The store field the Full Screen handler reads is populated, so the
        # button on that view has something to open.
        assert "mock-fullscreen-btn" in _ids(_step7_content(store))

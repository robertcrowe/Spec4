import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from dash import no_update

from spec4.agents.designer import (
    DesignerSession,
    build_mock_prompt,
    build_revision_note,
    clear_session,
    collect_ui_source_files,
    detect_has_ui_source,
    detect_no_ui,
    generate_mock_streaming,
    load_session,
    revision_delta,
    save_mock,
    save_session,
)


def _session(**overrides: object) -> DesignerSession:
    base: DesignerSession = {
        "step": 1,
        "preference_text": "Modern dark theme",
        "screenshots": [],
        "mock_html": "",
        "finalized": False,
    }
    for k, v in overrides.items():
        base[k] = v  # type: ignore[literal-required]
    return base


# ---------------------------------------------------------------------------
# detect_no_ui
# ---------------------------------------------------------------------------


class TestDetectNoUi:
    def test_returns_true_for_cli_vision(self) -> None:
        assert detect_no_ui({"purpose": "a CLI tool for batch processing"}, {}) is True

    def test_returns_true_for_cli_code_review(self) -> None:
        assert detect_no_ui({}, {"project_type": "command-line utility"}) is True

    def test_returns_true_for_no_ui_keyword(self) -> None:
        assert detect_no_ui({"description": "no ui, headless service"}, {}) is True

    def test_returns_false_for_web_app(self) -> None:
        assert (
            detect_no_ui(
                {"purpose": "a web application for managing tasks"},
                {"project_type": "web service"},
            )
            is False
        )

    def test_returns_false_for_empty_dicts(self) -> None:
        assert detect_no_ui({}, {}) is False

    def test_non_string_field_value_ignored(self) -> None:
        assert detect_no_ui({"project_type": 42}, {"is_cli": True}) is False

    def test_ui_summary_has_ui_false_takes_precedence(self) -> None:
        # ui_summary.has_ui=False wins even when prose says web app
        cr = {
            "code_review": {
                "project_type": "web application",
                "ui_summary": {"has_ui": False, "kind": "none"},
            }
        }
        assert detect_no_ui({}, cr) is True

    def test_ui_summary_has_ui_true_takes_precedence(self) -> None:
        # ui_summary.has_ui=True wins even when prose contains 'cli'
        cr = {
            "code_review": {
                "project_type": "cli utility with a web dashboard",
                "ui_summary": {"has_ui": True, "kind": "spa"},
            }
        }
        assert detect_no_ui({}, cr) is False

    def test_envelope_unwrapping_for_legacy_callers(self) -> None:
        # Passing the full envelope (as the production layout caller does)
        # should still resolve the keyword sweep correctly.
        cr_envelope = {"code_review": {"project_type": "command-line utility"}}
        assert detect_no_ui({}, cr_envelope) is True

    def test_vision_ui_surface_matched(self) -> None:
        # Brainstormer captures the UI surface as vision.ui_surface; ensure
        # we honour it even when nested under the vision envelope.
        v_envelope = {
            "vision_statement": {"vision": {"ui_surface": "CLI tool for batch jobs"}}
        }
        assert detect_no_ui(v_envelope, {}) is True


# ---------------------------------------------------------------------------
# detect_has_ui_source
# ---------------------------------------------------------------------------


class TestDetectHasUiSource:
    def test_true_when_mock_html_exists(self, tmp_path: Path) -> None:
        design_dir = tmp_path / ".spec4" / "design"
        design_dir.mkdir(parents=True)
        (design_dir / "mock.html").write_text("<html></html>")
        assert detect_has_ui_source(tmp_path, design_dir) is True

    def test_true_when_html_file_in_project(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<html></html>")
        assert detect_has_ui_source(tmp_path) is True

    def test_true_when_css_file_in_project(self, tmp_path: Path) -> None:
        (tmp_path / "styles.css").write_text("body { margin: 0; }")
        assert detect_has_ui_source(tmp_path) is True

    def test_true_when_tsx_file_in_project(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "App.tsx").write_text("export default function App() {}")
        assert detect_has_ui_source(tmp_path) is True

    def test_false_when_no_ui_files_and_no_mock(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1")
        assert detect_has_ui_source(tmp_path) is False

    def test_false_when_empty_project(self, tmp_path: Path) -> None:
        assert detect_has_ui_source(tmp_path) is False

    def test_ui_files_in_excluded_dirs_not_counted(self, tmp_path: Path) -> None:
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "index.html").write_text("<html></html>")
        assert detect_has_ui_source(tmp_path) is False

    def test_no_mock_html_without_design_dir(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1")
        assert detect_has_ui_source(tmp_path, None) is False


# ---------------------------------------------------------------------------
# load_session
# ---------------------------------------------------------------------------


class TestLoadSession:
    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        assert load_session(tmp_path) is None

    def test_returns_session_for_valid_json(self, tmp_path: Path) -> None:
        data = {
            "step": 2,
            "preference_text": "Minimalist",
            "screenshots": [],
            "mock_html": "<html/>",
            "finalized": True,
        }
        (tmp_path / "session.json").write_text(
            __import__("json").dumps(data), encoding="utf-8"
        )
        result = load_session(tmp_path)
        assert result is not None
        assert result["step"] == 2
        assert result["preference_text"] == "Minimalist"
        assert result["mock_html"] == "<html/>"
        assert result["finalized"] is True

    def test_returns_none_for_malformed_json(self, tmp_path: Path) -> None:
        (tmp_path / "session.json").write_text("not valid json {{", encoding="utf-8")
        assert load_session(tmp_path) is None

    def test_returns_none_for_missing_key(self, tmp_path: Path) -> None:
        (tmp_path / "session.json").write_text('{"step": 1}', encoding="utf-8")
        assert load_session(tmp_path) is None


# ---------------------------------------------------------------------------
# save_session / round-trip
# ---------------------------------------------------------------------------


class TestSaveSession:
    def test_creates_directory_and_file(self, tmp_path: Path) -> None:
        design_dir = tmp_path / "design"
        session = _session(step=3, preference_text="Bold")
        save_session(session, design_dir)
        assert (design_dir / "session.json").exists()

    def test_round_trip(self, tmp_path: Path) -> None:
        design_dir = tmp_path / "design"
        original = _session(
            step=2,
            preference_text="Pastel colours",
            screenshots=[{"data": "data:image/png;base64,abc", "annotation": "good"}],
            mock_html="<html/>",
            finalized=True,
        )
        save_session(original, design_dir)
        loaded = load_session(design_dir)
        assert loaded == original

    def test_overwrites_existing_session(self, tmp_path: Path) -> None:
        design_dir = tmp_path / "design"
        save_session(_session(step=1), design_dir)
        save_session(_session(step=5), design_dir)
        loaded = load_session(design_dir)
        assert loaded is not None
        assert loaded["step"] == 5


# ---------------------------------------------------------------------------
# save_mock
# ---------------------------------------------------------------------------


class TestSaveMock:
    def test_writes_html_content(self, tmp_path: Path) -> None:
        design_dir = tmp_path / "design"
        save_mock("<html><body>hello</body></html>", design_dir)
        result = (design_dir / "mock.html").read_text(encoding="utf-8")
        assert result == "<html><body>hello</body></html>"

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        design_dir = tmp_path / "nested" / "design"
        save_mock("<html/>", design_dir)
        assert (design_dir / "mock.html").exists()


# ---------------------------------------------------------------------------
# clear_session
# ---------------------------------------------------------------------------


class TestClearSession:
    def test_deletes_session_and_mock_files(self, tmp_path: Path) -> None:
        (tmp_path / "session.json").write_text("{}", encoding="utf-8")
        (tmp_path / "mock.html").write_text("<html/>", encoding="utf-8")
        clear_session(tmp_path)
        assert not (tmp_path / "session.json").exists()
        assert not (tmp_path / "mock.html").exists()

    def test_no_error_when_files_absent(self, tmp_path: Path) -> None:
        clear_session(tmp_path)  # must not raise

    def test_only_deletes_target_files(self, tmp_path: Path) -> None:
        (tmp_path / "session.json").write_text("{}", encoding="utf-8")
        (tmp_path / "screenshot_0.png").write_bytes(b"\x89PNG")
        clear_session(tmp_path)
        assert (tmp_path / "screenshot_0.png").exists()


# ---------------------------------------------------------------------------
# build_mock_prompt
# ---------------------------------------------------------------------------


class TestBuildMockPrompt:
    def test_basic_structure(self) -> None:
        session = _session(preference_text="Clean and minimal")
        messages = build_mock_prompt(session, [], False)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_message_is_string(self) -> None:
        messages = build_mock_prompt(_session(), [], False)
        assert isinstance(messages[0]["content"], str)

    def test_preference_text_in_user_content(self) -> None:
        session = _session(preference_text="Bright and playful")
        messages = build_mock_prompt(session, [], False)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        texts = [p["text"] for p in parts if p.get("type") == "text"]
        assert any("Bright and playful" in str(t) for t in texts)

    def test_includes_images_when_image_support_true(self) -> None:
        session = _session(
            screenshots=[
                {"data": "data:image/png;base64,abc", "annotation": "looks good"},
            ]
        )
        messages = build_mock_prompt(session, [], True)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        types = [p["type"] for p in parts]
        assert "image_url" in types

    def test_excludes_images_when_image_support_false(self) -> None:
        session = _session(
            screenshots=[{"data": "data:image/png;base64,abc", "annotation": "x"}]
        )
        messages = build_mock_prompt(session, [], False)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        assert all(p["type"] != "image_url" for p in parts)

    def test_excludes_images_when_screenshots_empty(self) -> None:
        session = _session(screenshots=[])
        messages = build_mock_prompt(session, [], True)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        assert all(p["type"] != "image_url" for p in parts)

    def test_annotation_included_with_image(self) -> None:
        session = _session(
            screenshots=[
                {"data": "data:image/png;base64,xyz", "annotation": "too dark"}
            ]
        )
        messages = build_mock_prompt(session, [], True)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "too dark" in combined

    def test_includes_source_snippets(self) -> None:
        messages = build_mock_prompt(_session(), ["<nav>...</nav>"], False)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "<nav>...</nav>" in combined

    def test_excludes_snippets_section_when_empty(self) -> None:
        messages = build_mock_prompt(_session(), [], False)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "starting point" not in combined

    def test_ends_with_html_instruction(self) -> None:
        messages = build_mock_prompt(_session(), [], False)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        last_text = str(parts[-1].get("text", ""))
        assert "HTML" in last_text or "html" in last_text.lower()

    def test_multiple_screenshots_all_included(self) -> None:
        session = _session(
            screenshots=[
                {"data": "data:image/png;base64,a", "annotation": "first"},
                {"data": "data:image/png;base64,b", "annotation": "second"},
            ]
        )
        messages = build_mock_prompt(session, [], True)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        image_parts = [p for p in parts if p["type"] == "image_url"]
        assert len(image_parts) == 2

    def test_capture_mode_uses_different_system_prompt(self) -> None:
        normal = build_mock_prompt(_session(), [], False)
        capture = build_mock_prompt(_session(), [], False, capture_mode=True)
        assert normal[0]["content"] != capture[0]["content"]

    def test_capture_mode_instruction_emphasises_preservation(self) -> None:
        messages = build_mock_prompt(_session(), ["<nav/>"], False, capture_mode=True)
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        combined = " ".join(str(p.get("text", "")) for p in parts).lower()
        assert "baseline" in combined or "faithfully" in combined

    def test_capture_mode_snippet_label_differs_from_normal(self) -> None:
        normal = build_mock_prompt(_session(), ["<nav/>"], False)
        capture = build_mock_prompt(_session(), ["<nav/>"], False, capture_mode=True)
        normal_combined = " ".join(
            str(p.get("text", ""))
            for p in normal[1]["content"]  # type: ignore[index]
            if isinstance(p, dict)
        )
        capture_combined = " ".join(
            str(p.get("text", ""))
            for p in capture[1]["content"]  # type: ignore[index]
            if isinstance(p, dict)
        )
        assert "starting point" in normal_combined
        assert "look and feel" in capture_combined

    def test_existing_html_and_planning_context_both_included(self) -> None:
        # Refine path with planning context — used when an upstream artifact
        # (vision) was updated after the mock was already generated. Both the
        # current mock HTML and the new vision must appear in the prompt.
        messages = build_mock_prompt(
            _session(preference_text=""),
            [],
            False,
            planning_context={"vision_statement": {"name": "FreshApp"}},
            existing_html="<html><body><h1>Old</h1></body></html>",
        )
        parts = messages[1]["content"]
        assert isinstance(parts, list)
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "Existing Mock" in combined
        assert "<h1>Old</h1>" in combined
        assert "Project Vision" in combined
        assert "FreshApp" in combined

    _MANIFEST = {"screens": [{"id": "home"}], "surfaces": [{"name": "kept-list"}]}

    def _texts(self, **kwargs: Any) -> list[str]:
        parts = build_mock_prompt(_session(preference_text=""), [], False, **kwargs)[1][
            "content"
        ]
        assert isinstance(parts, list)
        return [str(p.get("text", "")) for p in parts]

    def test_refine_includes_the_existing_manifest(self) -> None:
        """D-DM9: the refine note asks the model to carry surviving entries
        through unchanged, which it can only do if it sees them."""
        texts = self._texts(
            existing_html="<html><body>old</body></html>",
            existing_manifest=self._MANIFEST,
        )
        section = [t for t in texts if t.startswith("## Existing Manifest")]
        assert len(section) == 1
        assert '"kept-list"' in section[0]
        assert "```json" in section[0]

    def test_existing_manifest_follows_the_mock_and_precedes_the_schema(
        self,
    ) -> None:
        texts = self._texts(
            existing_html="<html><body>old</body></html>",
            existing_manifest=self._MANIFEST,
        )
        i_mock = next(
            i for i, t in enumerate(texts) if t.startswith("## Existing Mock")
        )
        i_man = next(
            i for i, t in enumerate(texts) if t.startswith("## Existing Manifest")
        )
        i_schema = next(i for i, t in enumerate(texts) if MANIFEST_START in t)
        assert i_mock < i_man < i_schema

    def test_greenfield_and_capture_ignore_an_existing_manifest(self) -> None:
        """Only a refine has a mock for the manifest to describe."""
        for kwargs in ({}, {"capture_mode": True}):
            texts = self._texts(existing_manifest=self._MANIFEST, **kwargs)
            assert not any(t.startswith("## Existing Manifest") for t in texts)
            assert '"kept-list"' not in " ".join(texts)

    def test_refine_without_a_manifest_has_no_section(self) -> None:
        texts = self._texts(existing_html="<html><body>old</body></html>")
        assert not any(t.startswith("## Existing Manifest") for t in texts)

    def test_ai_surfaces_section_injected_from_planning_context(self) -> None:
        ai_features = {
            "ai_features": [
                {
                    "name": "policy_qa",
                    "scope": "feature",
                    "tier": "chained_calls",
                    "purpose": "answer policy questions",
                    "invocation": {"mode": "synchronous", "trigger": "user asks"},
                    "decision_authority": "suggest",
                    "linked_vision_features": ["policy_answers"],
                    "inputs": [{"name": "question", "description": "the q"}],
                    "outputs": {"primary": "a grounded answer"},
                }
            ]
        }
        messages = build_mock_prompt(
            _session(preference_text=""),
            [],
            False,
            planning_context={
                "vision_statement": {"name": "App"},
                "ai_features": ai_features,
            },
        )
        combined = " ".join(str(p.get("text", "")) for p in messages[1]["content"])
        assert "User-Facing AI Surfaces" in combined
        assert "policy_qa" in combined
        assert "a grounded answer" in combined

    def test_greenfield_system_prompt_is_multi_screen(self) -> None:
        messages = build_mock_prompt(_session(), [], False)
        system = str(messages[0]["content"]).lower()
        assert "screen" in system
        assert "audience" in system
        instruction = str(messages[1]["content"][-1]["text"]).lower()
        assert "screen" in instruction

    def test_refine_system_prompt_is_pure_preserve(self) -> None:
        messages = build_mock_prompt(
            _session(), [], False, existing_html="<html><body>old</body></html>"
        )
        system = str(messages[0]["content"]).lower()
        assert "preserve everything" in system
        # No AI-surface reconciliation or marker language remains.
        assert "authoritative" not in system
        assert "data-ai-surface" not in system
        assert "add these surfaces" not in system

    def test_greenfield_prompt_has_no_reconciliation_clause(self) -> None:
        messages = build_mock_prompt(_session(), [], False)
        system = str(messages[0]["content"]).lower()
        assert "authoritative" not in system
        assert "absent from the list" not in system


# ---------------------------------------------------------------------------
# collect_ui_source_files
# ---------------------------------------------------------------------------


def _make_stream_chunk(content: str, finish_reason: str | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].finish_reason = finish_reason
    return chunk


def _mock_designer_stream(text: str) -> Any:
    chunks = [_make_stream_chunk(c) for c in text]
    chunks.append(_make_stream_chunk("", finish_reason="stop"))
    return patch(
        "spec4.llm.litellm.completion",
        return_value=iter(chunks),
    )


class TestCollectUiSourceFiles:
    def test_collects_html_files(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_text("<html/>")
        result = collect_ui_source_files(tmp_path)
        assert len(result) == 1

    def test_collects_css_and_js(self, tmp_path: Path) -> None:
        for ext in [".html", ".css", ".js", ".jsx", ".ts", ".tsx"]:
            (tmp_path / f"file{ext}").write_text("content")
        result = collect_ui_source_files(tmp_path)
        assert len(result) == 6

    def test_excludes_non_ui_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "README.md").write_text("# readme")
        result = collect_ui_source_files(tmp_path)
        assert result == []

    def test_excludes_git_dir(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "index.html").write_text("<html/>")
        result = collect_ui_source_files(tmp_path)
        assert result == []

    def test_excludes_node_modules(self, tmp_path: Path) -> None:
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "style.css").write_text("body{}")
        result = collect_ui_source_files(tmp_path)
        assert result == []

    def test_excludes_venv_and_pycache(self, tmp_path: Path) -> None:
        for d in [".venv", "__pycache__"]:
            dpath = tmp_path / d
            dpath.mkdir()
            (dpath / "app.js").write_text("x=1")
        result = collect_ui_source_files(tmp_path)
        assert result == []

    def test_truncates_long_files(self, tmp_path: Path) -> None:
        (tmp_path / "big.html").write_text("x" * 9000)
        result = collect_ui_source_files(tmp_path)
        assert len(result) == 1
        assert "# [truncated]" in result[0]
        # header + 8000 chars + marker — total well under 9000+header
        assert len(result[0]) < 9000

    def test_no_truncation_for_small_files(self, tmp_path: Path) -> None:
        (tmp_path / "small.html").write_text("x" * 100)
        result = collect_ui_source_files(tmp_path)
        assert "# [truncated]" not in result[0]

    def test_twenty_file_cap(self, tmp_path: Path) -> None:
        for i in range(25):
            (tmp_path / f"file{i:02d}.html").write_text("<html/>")
        result = collect_ui_source_files(tmp_path)
        assert len(result) == 20

    def test_format_includes_filename(self, tmp_path: Path) -> None:
        (tmp_path / "app.css").write_text("body { color: red; }")
        result = collect_ui_source_files(tmp_path)
        assert result[0].startswith("# ---")
        assert "app.css" in result[0]

    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        assert collect_ui_source_files(tmp_path) == []


# ---------------------------------------------------------------------------
# generate_mock_streaming
# ---------------------------------------------------------------------------


def _gen_session() -> DesignerSession:
    return {
        "step": 5,
        "preference_text": "dark theme",
        "screenshots": [],
        "mock_html": "",
        "finalized": False,
    }


class TestGenerateMockStreaming:
    def test_yields_streamed_chunks(self) -> None:
        with _mock_designer_stream("Hello World"):
            chunks = list(
                generate_mock_streaming(_gen_session(), "gpt-4o", "sk-test", [], True)
            )
        text = "".join(c for c in chunks if not c.startswith("__"))
        assert text == "Hello World"

    def test_yields_done_sentinel_last(self) -> None:
        with _mock_designer_stream("Hi"):
            chunks = list(
                generate_mock_streaming(_gen_session(), "gpt-4o", "sk-test", [], True)
            )
        assert chunks[-1] == "__DONE__"

    def test_yields_error_on_exception(self) -> None:
        with patch(
            "spec4.llm.litellm.completion",
            side_effect=Exception("timeout"),
        ):
            chunks = list(
                generate_mock_streaming(_gen_session(), "gpt-4o", "sk-test", [], True)
            )
        error_chunks = [c for c in chunks if c.startswith("__GENERATION_ERROR__:")]
        assert len(error_chunks) == 1
        assert "timeout" in error_chunks[0]

    def test_stop_event_prevents_done(self) -> None:
        ev = threading.Event()
        ev.set()
        with _mock_designer_stream("A" * 100):
            chunks = list(
                generate_mock_streaming(
                    _gen_session(), "gpt-4o", "sk-test", [], True, stop_event=ev
                )
            )
        assert "__DONE__" not in chunks

    def test_includes_source_snippets_in_prompt(self) -> None:
        captured: list[object] = []

        def fake_completion(**kwargs: object) -> object:
            captured.append(kwargs)
            return iter([_make_stream_chunk("", finish_reason="stop")])

        with patch("spec4.llm.litellm.completion", side_effect=fake_completion):
            list(
                generate_mock_streaming(
                    _gen_session(), "gpt-4o", "sk-test", ["<nav>nav</nav>"], False
                )
            )
        msgs = captured[0]["messages"]  # type: ignore[index]
        content_parts = msgs[1]["content"]
        combined = " ".join(
            str(p.get("text", "")) for p in content_parts if isinstance(p, dict)
        )
        assert "<nav>nav</nav>" in combined


# ---------------------------------------------------------------------------
# Revision mode — revision_delta
# ---------------------------------------------------------------------------


def _revision_vision(
    added: list[str] | None = None,
    modified: list[str] | None = None,
    removed: list[str] | None = None,
    goal: str = "",
    history_extra: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    entry = {
        "version": 1,
        "based_on_version": 0,
        "goal": goal,
        "changes": {
            "added": added or [],
            "modified": modified or [],
            "removed": removed or [],
        },
        "rationale": "",
    }
    history = list(history_extra or []) + [entry]
    return {"vision_statement": {"name": "App", "revision_history": history}}


class TestRevisionDelta:
    def test_none_for_greenfield_vision(self) -> None:
        assert revision_delta({"vision_statement": {"name": "Fresh"}}) is None

    def test_none_for_empty_or_missing(self) -> None:
        assert revision_delta(None) is None
        assert revision_delta({}) is None
        assert revision_delta({"vision_statement": {"revision_history": []}}) is None

    def test_returns_last_history_entry(self) -> None:
        vision = _revision_vision(
            added=["Returns"], goal="Add returns", history_extra=[{"version": 0}]
        )
        delta = revision_delta(vision)
        assert delta is not None
        assert delta["goal"] == "Add returns"
        assert delta["changes"]["added"] == ["Returns"]

    def test_non_dict_last_entry_is_none(self) -> None:
        vision = {"vision_statement": {"revision_history": ["not a dict"]}}
        assert revision_delta(vision) is None


# ---------------------------------------------------------------------------
# Revision mode — build_revision_note
# ---------------------------------------------------------------------------


class TestBuildRevisionNote:
    def test_includes_all_change_buckets_and_goal(self) -> None:
        delta = {
            "goal": "Add online play",
            "changes": {
                "added": ["Online Multiplayer"],
                "modified": ["Board"],
                "removed": ["Local Only"],
            },
        }
        note = build_revision_note(delta)
        assert note.startswith("[") and note.endswith("]")
        assert "Add online play" in note
        assert "Online Multiplayer" in note
        assert "Board" in note
        assert "Local Only" in note
        # Scoping intent is explicit.
        assert "Preserve the existing look and feel" in note

    def test_omits_goal_when_blank(self) -> None:
        note = build_revision_note(
            {"goal": "", "changes": {"added": ["X"], "modified": [], "removed": []}}
        )
        assert "Goal:" not in note
        assert "added features (X)" in note

    def test_empty_changes_still_preserves(self) -> None:
        # Degenerate delta (no feature changes) → still a valid carry-forward note.
        note = build_revision_note({"changes": {}})
        assert "Preserve the existing look and feel" in note
        assert "Update the mock" not in note

    def test_missing_changes_key(self) -> None:
        note = build_revision_note({"goal": "g"})
        assert "Goal: g" in note
        assert note.endswith("]")


# ---------------------------------------------------------------------------
# Revision mode — carry-forward callback wiring
# ---------------------------------------------------------------------------


class TestCarryForwardCallback:
    """on_designer_carry_forward ties load_prior_mock + revision_delta +
    build_revision_note into the refine flow. The @callback decorator returns
    the plain function, so it is exercised directly here (no Dash app, no LLM).
    """

    def _implement_prior_mock(self, tmp_path: Path, html: str) -> None:
        from spec4 import project_manager

        design_dir = project_manager.get_version_dir(str(tmp_path), 0) / "design"
        design_dir.mkdir(parents=True, exist_ok=True)
        (design_dir / "mock.html").write_text(html, encoding="utf-8")
        project_manager.get_version_dir(str(tmp_path), 0).joinpath(
            "IMPLEMENTED"
        ).write_text("")

    def test_seeds_prior_mock_and_note_into_refine(self, tmp_path: Path) -> None:
        from spec4.callbacks.designer import on_designer_carry_forward

        prior = "<!DOCTYPE html><html><body><h1>Checkers</h1></body></html>"
        self._implement_prior_mock(tmp_path, prior)
        session = {
            "working_dir": str(tmp_path),
            "vision_statement": _revision_vision(
                added=["Online Multiplayer"], goal="Add online play"
            ),
        }
        out = on_designer_carry_forward(1, {"step": 2, "mock_html": "PH"}, session)
        assert out["step"] == 7
        assert out["mock_html"] == prior
        assert "Online Multiplayer" in out["refine_text"]
        assert out["refine_images"] == []

    def test_fallback_to_create_when_no_prior_mock(self, tmp_path: Path) -> None:
        from spec4.callbacks.designer import on_designer_carry_forward

        # working_dir present but no implemented mock on disk.
        session = {
            "working_dir": str(tmp_path),
            "vision_statement": _revision_vision(added=["X"]),
        }
        out = on_designer_carry_forward(1, {"step": 2, "mock_html": "PH"}, session)
        assert out["step"] == 3
        assert out["mock_html"] == "PH"

    def test_no_op_without_click_or_store(self, tmp_path: Path) -> None:
        from dash import no_update

        from spec4.callbacks.designer import on_designer_carry_forward

        assert on_designer_carry_forward(0, {"step": 2}, {}) is no_update
        assert on_designer_carry_forward(1, None, {}) is no_update

    def test_prior_mock_without_delta_still_carries(self, tmp_path: Path) -> None:
        # Prior mock exists but vision has no revision_history (defensive):
        # carry the mock forward with an empty note rather than failing.
        from spec4.callbacks.designer import on_designer_carry_forward

        prior = "<html><body>x</body></html>"
        self._implement_prior_mock(tmp_path, prior)
        session = {
            "working_dir": str(tmp_path),
            "vision_statement": {"vision_statement": {"name": "App"}},
        }
        out = on_designer_carry_forward(1, {"step": 2, "mock_html": "PH"}, session)
        assert out["step"] == 7
        assert out["mock_html"] == prior
        assert out["refine_text"] == ""


class TestCapturePassesPlanningContext:
    """D-DM7: the "Modify existing" capture draw carries the manifest
    instruction and is the only manifest-bearing draw in a brownfield run — it
    must receive the planning context that instruction references. _start_gen
    is monkeypatched to capture the arguments without launching generation.
    """

    def _run(self, monkeypatch, session, store=None):
        from spec4.callbacks import designer as dmod

        captured: dict[str, Any] = {}

        def fake_start_gen(
            store_arg,
            wd,
            model,
            api_key,
            tavily_key,
            support,
            planning_context=None,
            **kwargs,
        ):
            captured["pc"] = planning_context
            captured["kwargs"] = kwargs
            return {}, {}, False

        monkeypatch.setattr(dmod._wizard, "_start_gen", fake_start_gen)
        monkeypatch.setattr(dmod._wizard, "ctx", _Ctx("btn-designer-modify-existing"))
        dmod.on_designer_step2_choice(1, None, store or {"step": 2}, session, True)
        return captured

    def _session(self, tmp_path: Path) -> dict[str, Any]:
        return {
            "working_dir": str(tmp_path),
            "vision_statement": {"name": "App"},
            "ai_features": {
                "ai_features": [
                    {"name": "Surf", "scope": "feature", "tier": "single_call"}
                ]
            },
        }

    def test_capture_mode_is_still_requested(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            _dmod().project_manager, "load_ai_features", lambda wd: None
        )
        monkeypatch.setattr(
            _dmod().project_manager, "load_feature_specs", lambda wd: None
        )
        out = self._run(monkeypatch, self._session(tmp_path))
        assert out["kwargs"]["capture_mode"] is True

    def test_planning_context_is_passed(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            _dmod().project_manager, "load_ai_features", lambda wd: None
        )
        monkeypatch.setattr(
            _dmod().project_manager, "load_feature_specs", lambda wd: None
        )
        pc = self._run(monkeypatch, self._session(tmp_path))["pc"]
        assert pc is not None
        assert pc["vision_statement"] == {"name": "App"}
        assert pc["ai_features"]["ai_features"][0]["name"] == "Surf"

    def test_disk_catalog_wins_over_session(self, tmp_path: Path, monkeypatch) -> None:
        disk = {"ai_features": [{"name": "fresh", "scope": "feature"}]}
        monkeypatch.setattr(
            _dmod().project_manager, "load_ai_features", lambda wd: disk
        )
        monkeypatch.setattr(
            _dmod().project_manager, "load_feature_specs", lambda wd: None
        )
        pc = self._run(monkeypatch, self._session(tmp_path))["pc"]
        assert pc["ai_features"] is disk

    def test_no_vision_yields_no_context(self, monkeypatch) -> None:
        out = self._run(monkeypatch, {"working_dir": None})
        assert out["pc"] is None
        assert out["kwargs"]["capture_mode"] is True

    def test_create_new_does_not_generate(self, monkeypatch) -> None:
        from spec4.callbacks import designer as dmod

        monkeypatch.setattr(dmod._wizard, "ctx", _Ctx("btn-designer-create-new"))
        out = dmod.on_designer_step2_choice(None, 1, {"step": 2}, {}, True)
        assert out[0]["step"] == 3


class _Ctx:
    def __init__(
        self, triggered_id: str, triggered: list[dict[str, Any]] | None = None
    ) -> None:
        self.triggered_id = triggered_id
        self.triggered = triggered or []


def _dmod() -> Any:
    from spec4.callbacks import designer as dmod

    return dmod


class TestRetryReproducesTheDraw:
    """D-DM8: a retry must re-run the draw it is retrying — same mode, same
    planning context — not silently fall back to a greenfield design."""

    def _retry(self, monkeypatch, session, store):
        dmod = _dmod()
        captured: dict[str, Any] = {}

        def fake_start_gen(
            store_arg,
            wd,
            model,
            api_key,
            tavily_key,
            support,
            planning_context=None,
            **kwargs,
        ):
            captured["pc"] = planning_context
            captured["kwargs"] = kwargs
            return {}, {}, False

        monkeypatch.setattr(dmod._refine, "_start_gen", fake_start_gen)
        monkeypatch.setattr(dmod.project_manager, "load_ai_features", lambda wd: None)
        monkeypatch.setattr(dmod.project_manager, "load_feature_specs", lambda wd: None)
        dmod.on_designer_retry(1, store, session, True)
        return captured

    def _session(self, tmp_path: Path) -> dict[str, Any]:
        return {
            "working_dir": str(tmp_path),
            "vision_statement": {"name": "App"},
        }

    def test_capture_retry_stays_in_capture_mode(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        out = self._retry(
            monkeypatch,
            self._session(tmp_path),
            {"step": 5, "_capture_mode": True, "_has_existing_html": False},
        )
        assert out["kwargs"]["capture_mode"] is True

    def test_greenfield_retry_stays_greenfield(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        out = self._retry(
            monkeypatch,
            self._session(tmp_path),
            {"step": 5, "_capture_mode": False, "_has_existing_html": False},
        )
        assert out["kwargs"]["capture_mode"] is False

    def test_retry_of_a_refine_gets_planning_context(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The refine draw itself carries planning context, so its retry must
        too — the manifest instruction references those sections."""
        out = self._retry(
            monkeypatch,
            self._session(tmp_path),
            {"step": 5, "_has_existing_html": True},
        )
        assert out["pc"] is not None
        assert out["pc"]["vision_statement"] == {"name": "App"}

    def test_start_gen_records_the_mode_for_the_retry(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        dmod = _dmod()
        monkeypatch.setattr(dmod.threading, "Thread", _NoThread)
        store, _buf, _dis = dmod._start_gen(
            {}, None, "m", "k", None, False, capture_mode=True
        )
        assert store["_capture_mode"] is True

    def test_start_gen_starts_the_draw_clean_of_the_last_error(
        self, monkeypatch
    ) -> None:
        """A retry spreads the failed store, which the poll left carrying
        ``_draw_error``; carried into the new draw it would re-render step 5
        as failed while the model is still drawing."""
        dmod = _dmod()
        monkeypatch.setattr(dmod.threading, "Thread", _NoThread)
        store, _buf, _dis = dmod._start_gen(
            {"_draw_error": "boom"}, None, "m", "k", None, False
        )
        assert store["_draw_error"] is None

    def test_create_new_clears_a_stale_capture_flag(self, monkeypatch) -> None:
        dmod = _dmod()
        monkeypatch.setattr(dmod._wizard, "ctx", _Ctx("btn-designer-create-new"))
        out = dmod.on_designer_step2_choice(
            None, 1, {"step": 2, "_capture_mode": True}, {}, True
        )
        assert out[0]["_capture_mode"] is False


class _SyncThread:
    """Stand-in for threading.Thread that runs the generation body inline."""

    def __init__(self, *args: Any, target: Any = None, **kwargs: Any) -> None:
        self._target = target

    def start(self) -> None:
        if self._target is not None:
            self._target()


class _NoThread:
    """Stand-in for threading.Thread that never runs the generation body."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def start(self) -> None:
        pass


class TestRefinePersistsManifest:
    """D-DM9: the manifest tracks the mock that ships, not just the first draw."""

    def test_persist_is_not_gated_on_the_draw_kind(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A refine draw persists the manifest, same as a first draw."""
        dmod = _dmod()
        calls: list[Any] = []
        monkeypatch.setattr(dmod._mock_gen.threading, "Thread", _SyncThread)
        monkeypatch.setattr(
            dmod._mock_gen,
            "generate_mock_streaming",
            lambda *a, **k: iter(["<html><body>hi</body></html>", "__DONE__"]),
        )
        monkeypatch.setattr(
            dmod._mock_gen, "persist_manifest", lambda *a, **k: calls.append(a)
        )
        dmod._start_gen(
            {},
            str(tmp_path),
            "m",
            "k",
            None,
            False,
            existing_html="<html><body>prior</body></html>",
        )
        assert calls, "a refine draw must still persist the manifest"

    def test_missing_manifest_leaves_the_prior_file_untouched(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        design_dir = tmp_path / "design"
        design_dir.mkdir()
        prior = design_dir / "manifest.json"
        prior.write_text('{"screens": ["kept"]}')
        dmod.persist_manifest("<html>no manifest here</html>", None, design_dir)
        assert prior.read_text() == '{"screens": ["kept"]}'


class TestUnchangedManifestIsNotRewritten:
    """A refine that re-states an unchanged design leaves manifest.json's mtime
    alone, so StackAdvisor's freshness — the button and detect_stale_inputs,
    which now agree — only moves when the design actually changed."""

    _VISION = 1000.0
    _FIRST_DRAW = 2000.0
    _STACK = 3000.0

    @staticmethod
    def _output(surfaces: list[str]) -> str:
        manifest = {
            "entities": [],
            "screens": [{"id": "home", "surfaces": surfaces}],
            "surfaces": [
                {"name": n, "kind": "non_ai", "screen": "home"} for n in surfaces
            ],
            "shared_layout": {"nav": "top", "shell": []},
        }
        return (
            MANIFEST_START
            + "\n"
            + json.dumps(manifest)
            + "\n"
            + MANIFEST_END
            + "\n<html><body>"
            + " ".join(surfaces)
            + "</body></html>"
        )

    def _project(self, tmp_path: Path) -> tuple[str, Path]:
        """v0 with a first draw's manifest, then a newer stack.json."""
        from spec4 import project_manager

        wd = str(tmp_path)
        v0 = project_manager.get_version_dir(wd, 0)
        design = v0 / "design"
        design.mkdir(parents=True)
        for name in ("vision.json", "ai_features.json"):
            (v0 / name).write_text("{}")
            os.utime(v0 / name, (self._VISION, self._VISION))
        _dmod()._mock_gen.persist_manifest(self._output(["list"]), None, design)
        manifest = design / "manifest.json"
        assert manifest.exists()
        os.utime(manifest, (self._FIRST_DRAW, self._FIRST_DRAW))
        (design / "mock.html").write_text("<html><body>list</body></html>")
        os.utime(design / "mock.html", (self._FIRST_DRAW, self._FIRST_DRAW))
        (v0 / "stack.json").write_text("{}")
        os.utime(v0 / "stack.json", (self._STACK, self._STACK))
        return wd, manifest

    def _refine(self, monkeypatch, wd: str, surfaces: list[str]) -> None:
        dmod = _dmod()
        monkeypatch.setattr(dmod._mock_gen.threading, "Thread", _SyncThread)
        monkeypatch.setattr(
            dmod._mock_gen,
            "generate_mock_streaming",
            lambda *a, **k: iter([self._output(surfaces), "__DONE__"]),
        )
        dmod._start_gen(
            {"mock_html": "<html><body>list</body></html>"},
            wd,
            "m",
            "k",
            None,
            False,
            existing_html="<html><body>list</body></html>",
        )

    def test_before_any_refine_the_stack_is_fresh(self, tmp_path: Path) -> None:
        from spec4 import project_manager

        wd, _manifest = self._project(tmp_path)
        assert project_manager.agent_button_state(wd, "stack_advisor") == (
            project_manager.AGENT_BTN_MODIFY
        )
        assert project_manager.detect_stale_inputs(wd, "stack_advisor") == {}

    def test_unchanged_manifest_keeps_its_mtime_and_the_button_at_modify(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from spec4 import project_manager

        wd, manifest = self._project(tmp_path)
        self._refine(monkeypatch, wd, ["list"])
        assert manifest.stat().st_mtime == self._FIRST_DRAW
        # The mock itself was redrawn — only the manifest write was skipped.
        assert (manifest.parent / "mock.html").stat().st_mtime > self._STACK
        assert project_manager.agent_button_state(wd, "stack_advisor") == (
            project_manager.AGENT_BTN_MODIFY
        )
        assert project_manager.detect_stale_inputs(wd, "stack_advisor") == {}

    def test_changed_manifest_is_rewritten_and_flips_the_button(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from spec4 import project_manager

        wd, manifest = self._project(tmp_path)
        self._refine(monkeypatch, wd, ["list", "detail"])
        assert manifest.stat().st_mtime > self._STACK
        names = [s["name"] for s in json.loads(manifest.read_text())["surfaces"]]
        assert names == ["list", "detail"]
        assert project_manager.agent_button_state(wd, "stack_advisor") == (
            project_manager.AGENT_BTN_NEEDS_UPDATE
        )
        stale = project_manager.detect_stale_inputs(wd, "stack_advisor")
        assert set(stale) == {"design manifest"}

    def test_equality_is_parsed_not_byte_for_byte(self, tmp_path: Path) -> None:
        """Key order and whitespace in the model's JSON must not force a write."""
        dmod = _dmod()
        design = tmp_path / "design"
        design.mkdir()
        dmod._mock_gen.persist_manifest(self._output(["list"]), None, design)
        manifest = design / "manifest.json"
        os.utime(manifest, (self._FIRST_DRAW, self._FIRST_DRAW))
        reordered = json.dumps(json.loads(manifest.read_text()), indent=4)
        dmod._mock_gen.persist_manifest(
            MANIFEST_START + "\n" + reordered + "\n" + MANIFEST_END + "\n<html></html>",
            None,
            design,
        )
        assert manifest.stat().st_mtime == self._FIRST_DRAW

    def test_a_manifest_still_lands_when_none_is_on_disk(self, tmp_path: Path) -> None:
        dmod = _dmod()
        design = tmp_path / "design"
        design.mkdir()
        dmod._mock_gen.persist_manifest(self._output(["list"]), None, design)
        assert (design / "manifest.json").exists()


class TestExistingManifestReachesTheDraw:
    """D-DM9: the manifest describing the mock being refined travels from the
    refine call sites through _start_gen and generate_mock_streaming into the
    prompt, so the model updates it rather than re-inventing it."""

    _MANIFEST = {"screens": [{"id": "home"}]}

    def test_generate_mock_streaming_forwards_it_to_the_prompt(
        self, monkeypatch
    ) -> None:
        import spec4.agents.designer as agent_mod

        captured: dict[str, Any] = {}

        def fake_prompt(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            captured.update(kwargs)
            return []

        monkeypatch.setattr(agent_mod, "build_mock_prompt", fake_prompt)
        monkeypatch.setattr(
            agent_mod.llm, "stream_completion", lambda **kwargs: iter([])
        )
        out = list(
            generate_mock_streaming(
                _session(),
                "m",
                "k",
                [],
                False,
                existing_html="<html></html>",
                existing_manifest=self._MANIFEST,
            )
        )
        assert out == ["__DONE__"]
        assert captured["existing_manifest"] == self._MANIFEST

    def test_start_gen_forwards_it_to_the_generator(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        dmod = _dmod()
        captured: dict[str, Any] = {}

        def fake_gen(*args: Any, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return iter(["<html><body>hi</body></html>", "__DONE__"])

        monkeypatch.setattr(dmod._mock_gen.threading, "Thread", _SyncThread)
        monkeypatch.setattr(dmod._mock_gen, "generate_mock_streaming", fake_gen)
        dmod._start_gen(
            {},
            str(tmp_path),
            "m",
            "k",
            None,
            False,
            existing_html="<html></html>",
            existing_manifest=self._MANIFEST,
        )
        assert captured["existing_manifest"] == self._MANIFEST

    def _design_dir(self, tmp_path: Path, version: int) -> Path:
        from spec4 import project_manager

        d = project_manager.get_version_dir(str(tmp_path), version) / "design"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_resolver_reads_the_active_round_when_it_has_a_mock(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        d = self._design_dir(tmp_path, 0)
        (d / "mock.html").write_text("<html></html>")
        (d / "manifest.json").write_text('{"screens": ["active"]}')
        out = dmod._mock_gen.existing_manifest_for_refine({}, str(tmp_path), None)
        assert out == {"screens": ["active"]}

    def test_resolver_gives_none_when_the_active_draw_had_no_manifest(
        self, tmp_path: Path
    ) -> None:
        """A prior round's manifest describes a different mock — never that."""
        dmod = _dmod()
        d0 = self._design_dir(tmp_path, 0)
        (d0 / "mock.html").write_text("<html>old</html>")
        (d0 / "manifest.json").write_text('{"screens": ["prior"]}')
        (d0.parent / "IMPLEMENTED").write_text("")
        d1 = self._design_dir(tmp_path, 1)
        (d1 / "mock.html").write_text("<html>new</html>")
        out = dmod._mock_gen.existing_manifest_for_refine(
            {"_is_revision": True}, str(tmp_path), {"phase_version": 1}
        )
        assert out is None

    def test_resolver_falls_back_to_the_prior_round_for_a_carried_mock(
        self, tmp_path: Path
    ) -> None:
        """Carry-forward seeds the store with the prior round's mock; the
        revision round has no mock of its own, so the prior manifest is the
        one to update."""
        dmod = _dmod()
        d0 = self._design_dir(tmp_path, 0)
        (d0 / "mock.html").write_text("<html>old</html>")
        (d0 / "manifest.json").write_text('{"screens": ["prior"]}')
        (d0.parent / "IMPLEMENTED").write_text("")
        self._design_dir(tmp_path, 1)
        out = dmod._mock_gen.existing_manifest_for_refine(
            {"_is_revision": True}, str(tmp_path), {"phase_version": 1}
        )
        assert out == {"screens": ["prior"]}

    def test_resolver_gives_none_outside_a_revision_with_no_active_mock(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        d0 = self._design_dir(tmp_path, 0)
        (d0 / "manifest.json").write_text('{"screens": ["prior"]}')
        (d0.parent / "IMPLEMENTED").write_text("")
        self._design_dir(tmp_path, 1)
        out = dmod._mock_gen.existing_manifest_for_refine(
            {}, str(tmp_path), {"phase_version": 1}
        )
        assert out is None

    def test_resolver_gives_none_without_a_working_dir(self) -> None:
        dmod = _dmod()
        assert dmod._mock_gen.existing_manifest_for_refine({}, None, None) is None

    def _capture_start_gen(self, monkeypatch) -> dict[str, Any]:
        dmod = _dmod()
        captured: dict[str, Any] = {}

        def fake_start_gen(*args: Any, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return {}, {}, False

        monkeypatch.setattr(dmod._refine, "_start_gen", fake_start_gen)
        monkeypatch.setattr(
            dmod._refine,
            "existing_manifest_for_refine",
            lambda store, wd, sess: self._MANIFEST,
        )
        monkeypatch.setattr(dmod.project_manager, "load_ai_features", lambda wd: None)
        monkeypatch.setattr(dmod.project_manager, "load_feature_specs", lambda wd: None)
        return captured

    def test_regenerate_passes_the_resolved_manifest(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        dmod = _dmod()
        captured = self._capture_start_gen(monkeypatch)
        store = {
            "step": 7,
            "mock_html": "<html>old</html>",
            "preference_text": "",
            "screenshots": [],
            "refine_images": [],
        }
        dmod.on_designer_regenerate(
            1, "tighter spacing", [], store, {"working_dir": str(tmp_path)}, True
        )
        assert captured["existing_manifest"] == self._MANIFEST

    def test_retry_of_a_refine_passes_the_resolved_manifest(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        dmod = _dmod()
        captured = self._capture_start_gen(monkeypatch)
        d = self._design_dir(tmp_path, 0)
        (d / "mock.html").write_text("<html>old</html>")
        dmod.on_designer_retry(
            1,
            {"step": 5, "_has_existing_html": True},
            {"working_dir": str(tmp_path)},
            True,
        )
        assert captured["existing_html"] == "<html>old</html>"
        assert captured["existing_manifest"] == self._MANIFEST

    def test_greenfield_retry_passes_no_manifest(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        dmod = _dmod()
        captured = self._capture_start_gen(monkeypatch)
        dmod.on_designer_retry(
            1,
            {"step": 5, "_has_existing_html": False},
            {"working_dir": str(tmp_path)},
            True,
        )
        assert captured["existing_html"] is None
        assert captured["existing_manifest"] is None


class TestRefineImageAnnotations:
    """Refine images carry an annotation the same way step-4 screenshots do
    (mirrors TestBuildMockPrompt.test_annotation_included_with_image)."""

    def test_upload_syncs_existing_annotation_and_appends_new_image(self) -> None:
        dmod = _dmod()
        store = {
            "step": 7,
            "refine_images": [
                {
                    "data": "data:image/png;base64,a",
                    "filename": "a.png",
                    "annotation": "",
                }
            ],
        }
        out = dmod.on_designer_refine_upload(
            "data:image/png;base64,b",
            "b.png",
            ["match the header style"],
            "",
            store,
        )
        images = out["refine_images"]
        assert images[0]["annotation"] == "match the header style"
        assert images[1] == {
            "data": "data:image/png;base64,b",
            "filename": "b.png",
            "annotation": "",
        }

    def test_multiple_files_selected_at_once_are_all_appended(self) -> None:
        """multiple=True hands contents/filename as parallel lists."""
        dmod = _dmod()
        store = {"step": 7, "refine_images": []}
        out = dmod.on_designer_refine_upload(
            ["data:image/png;base64,a", "data:image/png;base64,b"],
            ["a.png", "b.png"],
            [],
            "",
            store,
        )
        images = out["refine_images"]
        assert [img["filename"] for img in images] == ["a.png", "b.png"]
        assert all(img["annotation"] == "" for img in images)

    def test_delete_preserves_the_other_images_annotations(
        self, monkeypatch: Any
    ) -> None:
        dmod = _dmod()
        monkeypatch.setattr(
            dmod._refine,
            "ctx",
            _Ctx({"type": "designer-refine-image-delete", "index": 1}),
        )
        store = {
            "step": 7,
            "refine_images": [
                {
                    "data": "data:image/png;base64,a",
                    "filename": "a.png",
                    "annotation": "keep this",
                },
                {
                    "data": "data:image/png;base64,b",
                    "filename": "b.png",
                    "annotation": "delete me",
                },
            ],
        }
        # The surviving image's textarea has an edit not yet persisted to the
        # store — it must still be captured on delete, exactly like upload does.
        out = dmod.on_designer_refine_image_delete(
            [None, 1], ["updated note", "delete me"], "", store
        )
        assert out["refine_images"] == [
            {
                "data": "data:image/png;base64,a",
                "filename": "a.png",
                "annotation": "updated note",
            }
        ]


class TestRegeneratePassesRefineImageAnnotations:
    """on_designer_regenerate must fold refine_images into screenshots using
    the same {"data", "annotation"} shape the create path builds — one shape,
    not two — so the Designer agent sees the developer's note, not a filename.
    """

    def test_regenerate_payload_carries_the_refine_annotation(
        self, monkeypatch: Any
    ) -> None:
        dmod = _dmod()
        captured: dict[str, Any] = {}

        def fake_start_gen(
            store_arg, wd, model, api_key, tavily_key, support, *args, **kwargs
        ):
            captured["store"] = store_arg
            return {}, {}, False

        monkeypatch.setattr(dmod._refine, "_start_gen", fake_start_gen)
        store = {
            "step": 7,
            "preference_text": "",
            "mock_html": "<html>old</html>",
            "screenshots": [],
            "refine_images": [
                {
                    "data": "data:image/png;base64,xyz",
                    "filename": "ref.png",
                    "annotation": "",
                }
            ],
        }
        dmod.on_designer_regenerate(1, "", ["match this palette"], store, {}, True)

        screenshots = captured["store"]["screenshots"]
        assert screenshots == [
            {"data": "data:image/png;base64,xyz", "annotation": "match this palette"}
        ]
        # Same structure the create path passes for screenshots: fed through
        # build_mock_prompt, the note appears — the filename never does.
        session = _session(screenshots=screenshots)
        parts = build_mock_prompt(session, [], True)[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "match this palette" in combined
        assert "ref.png" not in combined


class TestRegenerateSourcesCatalogFromDisk:
    """on_designer_regenerate builds the surfaces block from the on-disk
    ai_features.json (which upstream edits write) rather than a possibly-stale
    session snapshot. _start_gen is monkeypatched to capture planning_context
    without launching generation.
    """

    def _run(self, monkeypatch, session, store):
        from spec4.callbacks import designer as dmod

        captured: dict[str, Any] = {}

        def fake_start_gen(
            store_arg,
            wd,
            model,
            api_key,
            tavily_key,
            support,
            planning_context=None,
            **kwargs,
        ):
            captured["pc"] = planning_context
            return {}, {}, False

        monkeypatch.setattr(dmod._refine, "_start_gen", fake_start_gen)
        dmod.on_designer_regenerate(1, "AI features changed", [], store, session, True)
        return captured["pc"]

    def test_disk_ai_features_win_over_session(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from spec4.callbacks import designer as dmod

        disk_cat = {
            "ai_features": [{"name": "kept", "scope": "feature", "tier": "single_call"}]
        }
        stale_cat = {
            "ai_features": [
                {"name": "kept", "scope": "feature", "tier": "single_call"},
                {"name": "removed", "scope": "feature", "tier": "single_call"},
            ]
        }
        monkeypatch.setattr(
            dmod.project_manager, "load_ai_features", lambda wd: disk_cat
        )
        session = {
            "working_dir": str(tmp_path),
            "vision_statement": {"name": "App"},
            "ai_features": stale_cat,
        }
        store = {
            "step": 7,
            "mock_html": "<html>old</html>",
            "preference_text": "",
            "screenshots": [],
            "refine_images": [],
        }
        pc = self._run(monkeypatch, session, store)
        names = [f["name"] for f in pc["ai_features"]["ai_features"]]
        assert names == ["kept"]

    def test_falls_back_to_session_when_no_disk(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from spec4.callbacks import designer as dmod

        sess_cat = {
            "ai_features": [{"name": "s", "scope": "feature", "tier": "single_call"}]
        }
        monkeypatch.setattr(dmod.project_manager, "load_ai_features", lambda wd: None)
        session = {
            "working_dir": str(tmp_path),
            "vision_statement": {"name": "App"},
            "ai_features": sess_cat,
        }
        store = {
            "step": 7,
            "mock_html": "x",
            "preference_text": "",
            "screenshots": [],
            "refine_images": [],
        }
        pc = self._run(monkeypatch, session, store)
        assert pc["ai_features"] is sess_cat


from spec4.agents._manifest import MANIFEST_END, MANIFEST_START  # noqa: E402


class TestManifestInstruction:
    def test_greenfield_includes_manifest_directive(self) -> None:
        parts = build_mock_prompt(_session(), [], False)[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert MANIFEST_START in combined
        assert "design manifest" in combined.lower()

    def test_capture_includes_manifest_directive(self) -> None:
        parts = build_mock_prompt(_session(), ["<nav/>"], False, capture_mode=True)[1][
            "content"
        ]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert MANIFEST_START in combined

    def test_refine_includes_manifest_directive(self) -> None:
        """D-DM9: refinements change the mock, so they must restate the
        manifest — it used to be written once and then frozen."""
        parts = build_mock_prompt(_session(), [], False, existing_html="<html></html>")[
            1
        ]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert MANIFEST_START in combined

    def test_refine_adds_the_restate_note(self) -> None:
        parts = build_mock_prompt(_session(), [], False, existing_html="<html></html>")[
            1
        ]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "re-state the manifest for the updated mock" in combined.lower()
        assert "not a diff" in combined

    def test_refine_note_covers_purely_visual_changes(self) -> None:
        parts = build_mock_prompt(_session(), [], False, existing_html="<html></html>")[
            1
        ]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "re-state it anyway" in combined

    def test_refine_with_a_manifest_says_to_update_it_in_place(self) -> None:
        parts = build_mock_prompt(
            _session(),
            [],
            False,
            existing_html="<html></html>",
            existing_manifest={"screens": []},
        )[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "start from the existing manifest above" in combined.lower()
        assert "update it in place" in combined.lower()
        assert "keep the `name`, `id` and `catalog_surface`" in combined
        # The shared refine contract survives in both variants.
        assert "re-state the manifest for the updated mock" in combined.lower()
        assert "not a diff" in combined
        assert "re-state it anyway" in combined

    def test_refine_without_a_manifest_keeps_the_restate_note(self) -> None:
        parts = build_mock_prompt(_session(), [], False, existing_html="<html></html>")[
            1
        ]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "not the manifest of the mock you were given" in combined
        assert "start from the existing manifest above" not in combined.lower()

    def test_greenfield_omits_the_refine_note(self) -> None:
        parts = build_mock_prompt(_session(), [], False)[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "re-state the manifest" not in combined.lower()

    def test_refine_wins_over_capture_when_both_set(self) -> None:
        """existing_html already decides the system prompt and instruction;
        the manifest note must agree rather than describe a capture."""
        parts = build_mock_prompt(
            _session(), [], False, existing_html="<html></html>", capture_mode=True
        )[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "re-state the manifest" in combined.lower()
        assert "describe what you recreated" not in combined.lower()

    def test_capture_adds_the_describe_what_you_recreated_note(self) -> None:
        parts = build_mock_prompt(_session(), ["<nav/>"], False, capture_mode=True)[1][
            "content"
        ]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "describe what you recreated" in combined.lower()
        assert "Do not invent screens" in combined

    def test_greenfield_omits_the_capture_note(self) -> None:
        parts = build_mock_prompt(_session(), [], False)[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "describe what you recreated" not in combined.lower()

    def test_refine_omits_the_capture_note(self) -> None:
        parts = build_mock_prompt(
            _session(), [], False, existing_html="<html></html>", capture_mode=True
        )[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "describe what you recreated" not in combined.lower()

    def test_capture_manifest_directive_has_its_planning_inputs(self) -> None:
        """D-DM7: the schema references the vision and AI surfaces by name —
        those sections must be in the same prompt or the ask is unsatisfiable."""
        pc = {
            "vision_statement": {
                "vision_statement": {
                    "name": "App",
                    "vision": {
                        "purpose": "do things",
                        "target_audiences": ["users"],
                        "key_features_mvp": [{"name": "Feat"}],
                    },
                }
            },
            "ai_features": {
                "ai_features": [
                    {"name": "Surf", "scope": "feature", "tier": "single_call"}
                ]
            },
        }
        parts = build_mock_prompt(
            _session(), ["<nav/>"], False, planning_context=pc, capture_mode=True
        )[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert MANIFEST_START in combined
        assert "## Project Vision" in combined
        assert "## User-Facing AI Surfaces" in combined


class TestBuildMockPromptFeatureSpecs:
    def test_feature_specs_section_injected(self) -> None:
        fs = {
            "features": [
                {
                    "id": "f",
                    "name": "Feat",
                    "purpose": "does x",
                    "outputs": {"primary": "a result"},
                }
            ],
            "nfr_goals": ["be fast"],
        }
        messages = build_mock_prompt(
            _session(preference_text=""),
            [],
            False,
            planning_context={"vision_statement": {"name": "App"}, "feature_specs": fs},
        )
        combined = " ".join(str(p.get("text", "")) for p in messages[1]["content"])
        assert "Feature Specifications" in combined
        assert "Feat" in combined
        assert "does x" in combined
        assert "a result" in combined
        # No entities in this spec, so the block's vocabulary note is absent. (The
        # phrase "Domain vocabulary" still appears in the manifest instruction's
        # DR3 grounding line, so we check the block-specific phrasing instead.)
        assert "concepts these features operate on" not in combined

    def test_vision_dump_is_slimmed(self) -> None:
        vision = {
            "vision_statement": {
                "name": "App",
                "vision": {
                    "purpose": "the point",
                    "key_features_mvp": [{"SecretFeature": {"id": "secret"}}],
                },
            }
        }
        messages = build_mock_prompt(
            _session(preference_text=""),
            [],
            False,
            planning_context={"vision_statement": vision},
        )
        combined = " ".join(str(p.get("text", "")) for p in messages[1]["content"])
        assert "Project Vision" in combined
        assert "App" in combined
        assert "the point" in combined
        # key_features_mvp is dropped from the slimmed framing dump.
        assert "SecretFeature" not in combined

    def test_no_feature_specs_section_when_absent(self) -> None:
        messages = build_mock_prompt(
            _session(preference_text=""),
            [],
            False,
            planning_context={"vision_statement": {"name": "App"}},
        )
        combined = " ".join(str(p.get("text", "")) for p in messages[1]["content"])
        assert "Feature Specifications" not in combined


# ---------------------------------------------------------------------------
# on_mock_stream_poll — two cadences, acknowledgement-based completion delivery
# ---------------------------------------------------------------------------


class TestMockDeliveryAck:
    """The completion payload is re-delivered until the browser's own poll
    request — its designer-session-store State — proves the store moved off
    step 5. The previous fixed re-delivery window counted requests sent, not
    deliveries applied, and could expire before the first response ever
    reached the browser, stranding the UI at step 5 with the interval off.

    Delivery has two phases because dash-renderer discards the older of two
    in-flight requests of the same callback: the first tick that sees the
    finished mock only slows the poll to ``DELIVERY_MS``, and the ticks after
    it carry the payload. The four outputs are buffer, store, ``disabled``
    and ``interval``.
    """

    _GEN_ID = "test-ack-gen"
    _HTML = "<!DOCTYPE html><html><body>ok</body></html>"

    def _buffer(self, slowed: bool = True) -> Any:
        """A finished draw, by default already past its slow-down tick."""
        dmod = _dmod()
        dmod._MOCK_BUFFERS[self._GEN_ID] = {
            "done": True,
            "stop": threading.Event(),
            "text": self._HTML + "__DONE__",
            "final_html": self._HTML,
            **({"slowed": True} if slowed else {}),
        }
        return dmod

    def teardown_method(self) -> None:
        _dmod()._MOCK_BUFFERS.pop(self._GEN_ID, None)

    def test_first_sight_of_the_mock_slows_the_poll_and_delivers_nothing(
        self,
    ) -> None:
        from dash import no_update

        from spec4.callbacks.designer._mock_gen import DELIVERY_MS

        dmod = self._buffer(slowed=False)
        buf, new_store, disabled, interval = dmod.on_mock_stream_poll(
            1, {"step": 5, "_gen_id": self._GEN_ID}
        )
        assert new_store is no_update
        assert disabled is no_update
        assert interval == DELIVERY_MS
        # A running-tick payload, small enough to land inside the old period.
        assert buf["tokens"] == len(self._HTML + "__DONE__")
        assert buf["progress"] < 100
        assert "mock_html" not in buf
        entry = dmod._MOCK_BUFFERS[self._GEN_ID]
        assert entry["slowed"] is True
        assert "delivered" not in entry

    def test_the_slow_down_happens_once(self) -> None:
        dmod = self._buffer(slowed=False)
        dmod.on_mock_stream_poll(1, {"step": 5, "_gen_id": self._GEN_ID})
        _, new_store, _, interval = dmod.on_mock_stream_poll(
            2, {"step": 5, "_gen_id": self._GEN_ID}
        )
        assert new_store["step"] == 6
        assert dmod._MOCK_BUFFERS[self._GEN_ID]["delivered"] == 1

    def test_delivers_step6_payload_while_store_is_at_step_5(self) -> None:
        from dash import no_update

        from spec4.callbacks.designer._mock_gen import DELIVERY_MS

        dmod = self._buffer()
        buf, new_store, disabled, interval = dmod.on_mock_stream_poll(
            1, {"step": 5, "_gen_id": self._GEN_ID}
        )
        assert new_store["step"] == 6
        assert new_store["mock_html"] == self._HTML
        assert buf == {"tokens": len(self._HTML), "progress": 100, "error": None}
        # Keep polling, at the delivery cadence, until the browser
        # acknowledges; the buffer must survive so a dropped response can be
        # re-delivered. The cadence is re-sent, not left alone: a page rebuilt
        # since the slow-down tick has its interval back at POLL_MS.
        assert disabled is no_update
        assert interval == DELIVERY_MS
        assert self._GEN_ID in dmod._MOCK_BUFFERS

    def test_delivery_preserves_prior_store_keys(self) -> None:
        """The step-6 payload spreads the acknowledged store: a from-scratch
        dict here dropped _capture_mode and regressed D-DM8 (Retry after a
        capture draw regenerated greenfield)."""
        dmod = self._buffer()
        _, new_store, _, _ = dmod.on_mock_stream_poll(
            1,
            {
                "step": 5,
                "_gen_id": self._GEN_ID,
                "_capture_mode": True,
                "_is_revision": True,
                "_stale_inputs": [],
                "refine_text": "note",
                "preference_text": "pref",
                "_has_existing_html": True,
                "screenshots": [{"data": "base64..."}],
                "refine_images": [{"data": "base64..."}],
            },
        )
        assert new_store["_capture_mode"] is True
        assert new_store["_is_revision"] is True
        assert new_store["_stale_inputs"] == []
        assert new_store["refine_text"] == "note"
        assert new_store["preference_text"] == "pref"
        assert new_store["_has_existing_html"] is True
        assert new_store["step"] == 6
        assert new_store["finalized"] is False
        # Image payloads must never re-enter the store (see _start_gen note).
        assert new_store["screenshots"] == []
        assert new_store["refine_images"] == []

    def test_redelivers_far_beyond_the_old_fixed_window(self) -> None:
        dmod = self._buffer()
        new_store: Any = None
        for _ in range(20):
            _, new_store, _, _ = dmod.on_mock_stream_poll(
                1, {"step": 5, "_gen_id": self._GEN_ID}
            )
        assert new_store["step"] == 6
        assert new_store["mock_html"] == self._HTML
        assert self._GEN_ID in dmod._MOCK_BUFFERS

    def test_ack_pops_buffer_and_disables_interval(self) -> None:
        from dash import no_update

        from spec4.layouts.designer import POLL_MS

        dmod = self._buffer()
        dmod.on_mock_stream_poll(1, {"step": 5, "_gen_id": self._GEN_ID})
        buf, new_store, disabled, interval = dmod.on_mock_stream_poll(
            1, {"step": 6, "_gen_id": self._GEN_ID}
        )
        assert new_store is no_update
        assert disabled is True
        assert interval == POLL_MS
        # Nothing for the buffer: a write here would fire the buffer's
        # clientside painter for a bar that is gone, and it is the step-6
        # render in flight from the delivery that must land undisturbed.
        assert buf is no_update
        assert self._GEN_ID not in dmod._MOCK_BUFFERS

    def test_refine_click_between_ticks_is_not_bounced_back(self) -> None:
        from dash import no_update

        dmod = self._buffer()
        _, new_store, disabled, _ = dmod.on_mock_stream_poll(
            1, {"step": 7, "_gen_id": self._GEN_ID}
        )
        assert new_store is no_update
        assert disabled is True

    def test_runaway_valve_reports_the_saved_mock(self) -> None:
        from spec4.layouts.designer import POLL_MS

        dmod = self._buffer()
        dmod._MOCK_BUFFERS[self._GEN_ID]["delivered"] = dmod._MAX_DELIVERY_TICKS
        buf, new_store, disabled, interval = dmod.on_mock_stream_poll(
            1, {"step": 5, "_gen_id": self._GEN_ID}
        )
        assert "Refresh the page" in buf["error"]
        assert disabled is True
        assert interval == POLL_MS
        assert self._GEN_ID not in dmod._MOCK_BUFFERS

    def test_runaway_valve_sends_the_whole_message_and_no_mock(self) -> None:
        """The test above pins one phrase. This pins the whole message -- the only
        thing that tells the user the mock is saved, and both ways back to it --
        and that the valve delivers no step-6 payload alongside it: the store
        carries the error, which is what re-renders the step, and stays at 5."""
        dmod = self._buffer()
        dmod._MOCK_BUFFERS[self._GEN_ID]["delivered"] = dmod._MAX_DELIVERY_TICKS
        store = {"step": 5, "_gen_id": self._GEN_ID, "_capture_mode": True}
        buf, new_store, _, _ = dmod.on_mock_stream_poll(1, store)
        message = (
            "The mock was generated and saved, but this page "
            "stopped receiving updates and could not display it. "
            "Refresh the page to load the saved mock, or click "
            "Retry to regenerate."
        )
        assert buf == {"error": message}
        assert new_store == {**store, "_draw_error": message}

    def test_a_running_tick_keeps_the_running_cadence(self) -> None:
        from dash import no_update

        from spec4.layouts.designer import POLL_MS

        dmod = _dmod()
        dmod._MOCK_BUFFERS[self._GEN_ID] = {
            "done": False,
            "stop": threading.Event(),
            "text": "abc",
        }
        buf, new_store, disabled, interval = dmod.on_mock_stream_poll(
            1, {"step": 5, "_gen_id": self._GEN_ID}
        )
        assert buf["tokens"] == 3
        assert new_store is no_update
        assert disabled is no_update
        assert interval == POLL_MS

    def test_a_failed_draw_puts_the_error_on_both_and_resets_the_cadence(
        self,
    ) -> None:
        from spec4.layouts.designer import POLL_MS

        dmod = _dmod()
        dmod._MOCK_BUFFERS[self._GEN_ID] = {
            "done": True,
            "stop": threading.Event(),
            "text": "<p>__GENERATION_ERROR__: boom",
        }
        store = {"step": 5, "_gen_id": self._GEN_ID, "preference_text": "p"}
        buf, new_store, disabled, interval = dmod.on_mock_stream_poll(1, store)
        assert buf == {"error": "boom"}
        assert new_store == {**store, "_draw_error": "boom"}
        assert disabled is True
        assert interval == POLL_MS
        assert self._GEN_ID not in dmod._MOCK_BUFFERS

    def test_a_gone_buffer_and_a_stopped_draw_reset_the_cadence(self) -> None:
        from dash import no_update

        from spec4.layouts.designer import POLL_MS

        dmod = _dmod()
        stopped = (no_update, no_update, True, POLL_MS)
        assert dmod.on_mock_stream_poll(1, {"step": 5, "_gen_id": "gone"}) == stopped
        dmod._MOCK_BUFFERS[self._GEN_ID] = {
            "done": True,
            "stop": threading.Event(),
            "text": "<html>",
        }
        assert (
            dmod.on_mock_stream_poll(1, {"step": 5, "_gen_id": self._GEN_ID}) == stopped
        )
        assert self._GEN_ID not in dmod._MOCK_BUFFERS


# ---------------------------------------------------------------------------
# render_designer_step — the buffer is its State, never its Input
# ---------------------------------------------------------------------------


class TestRenderStepIgnoresBufferTicks:
    """A buffer tick arrives twice a second for the length of a draw. As an
    Input it cost a server round trip carrying the whole session each time,
    which pushed the poll's own round trip past its period and froze the
    counter (dash-renderer discards the older of two in-flight requests of
    the same callback). Progress is painted clientside; the step re-renders
    on store changes only, and a failed draw's error rides the store."""

    def _render(self, store: dict[str, Any], buffer_data: dict[str, Any]) -> Any:
        return _dmod().render_designer_step(store, buffer_data, True)

    def test_the_buffer_is_registered_as_state_not_input(self) -> None:
        from dash._callback import GLOBAL_CALLBACK_LIST

        from spec4.layouts.designer import DESIGNER_STEPPER_ID

        import spec4.app  # noqa: F401  — registers the callbacks

        # A multi-output key is the outputs joined, each as `id.prop`.
        [spec] = [
            spec
            for spec in GLOBAL_CALLBACK_LIST
            if f"{DESIGNER_STEPPER_ID}.children" in str(spec["output"])
        ]
        assert [dep["id"] for dep in spec["inputs"]] == ["designer-session-store"]
        assert "mock-stream-buffer" in [dep["id"] for dep in spec["state"]]

    def test_nothing_writes_the_store_from_a_buffer_tick(self) -> None:
        """The clientside copy of ``buf.complete`` into the store is gone with
        the duplicated payload it carried; a buffer tick reaches the DOM
        painter and nothing else. Server callbacks register on the global
        list, the app's clientside ones on the app itself, so both are read."""
        from dash._callback import GLOBAL_CALLBACK_LIST

        from spec4.app import app

        outputs = {
            str(spec["output"]).split("@")[0]
            for spec in [*GLOBAL_CALLBACK_LIST, *app._callback_list]
            if any(dep["id"] == "mock-stream-buffer" for dep in spec["inputs"])
        }
        assert outputs == {"_designer-fs-dummy.children"}

    def test_a_store_error_at_step5_renders_retry(self) -> None:
        content, _ = self._render(
            {"step": 5, "_draw_error": "boom"},
            {"tokens": 10, "progress": 1, "error": None},
        )
        assert "btn-designer-retry" in str(content)
        assert "boom" in str(content)

    def test_a_buffer_error_alone_does_not(self) -> None:
        """The pair for the test above: the buffer's copy of the error is the
        retry snapshot's and the counter line's, not the render's."""
        content, _ = self._render(
            {"step": 5}, {"tokens": 10, "progress": 1, "error": "boom"}
        )
        assert "btn-designer-retry" not in str(content)
        assert "Generating the mock" in str(content)

    def test_store_trigger_renders_step6(self) -> None:
        """The second output is the step row itself, re-rendered.

        It was a `dmc.Stepper`'s `active` index; the plain-text row that
        replaced the Stepper has no such property, so the callback writes the
        row into the container instead — which is why what is asserted here is
        the marked label rather than a number.
        """
        from dash import no_update

        from spec4.layouts._shared import STEP_ACTIVE, step_modifier_class
        from spec4.layouts.designer import DESIGNER_STEP_CLASS

        content, row = self._render(
            {"step": 6, "mock_html": "<html></html>", "finalized": False},
            {"tokens": 0, "progress": 100, "error": None},
        )
        assert content is not no_update
        active_class = step_modifier_class(DESIGNER_STEP_CLASS, STEP_ACTIVE)
        marked = [
            entry.children
            for entry in row.children
            if active_class in (entry.className or "").split()
        ]
        assert marked == ["Preview"]

    def test_initial_call_renders(self) -> None:
        from dash import no_update

        content, _ = self._render(
            {"step": 5}, {"tokens": 0, "progress": 0, "error": None}
        )
        assert content is not no_update


# ---------------------------------------------------------------------------
# _start_gen — saves land in the session-pinned version dir; prior buffers
# are cleaned up on regeneration
# ---------------------------------------------------------------------------


class TestGenerationSavesToPinnedVersion:
    def test_saves_into_session_pinned_version_dir(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """The generation thread must save where the readers look: the
        session-pinned version, not the latest on-disk one."""
        from spec4 import project_manager

        dmod = _dmod()
        project_manager.get_version_dir(str(tmp_path), 1).mkdir(parents=True)
        project_manager.get_version_dir(str(tmp_path), 2).mkdir(parents=True)
        html = "<!DOCTYPE html><html><body>x</body></html>"
        monkeypatch.setattr(
            dmod._mock_gen,
            "generate_mock_streaming",
            lambda *a, **kw: iter([html + "__DONE__"]),
        )
        store, _, _ = dmod._start_gen(
            {},
            str(tmp_path),
            "m",
            "key",
            None,
            False,
            session={"phase_version": 1},
        )
        gen_id = store["_gen_id"]
        try:
            entry = dmod._MOCK_BUFFERS[gen_id]
            for _ in range(500):
                if entry.get("done"):
                    break
                time.sleep(0.01)
            assert entry.get("final_html") == html
            v1_mock = (
                project_manager.get_version_dir(str(tmp_path), 1)
                / "design"
                / "mock.html"
            )
            v2_design = project_manager.get_version_dir(str(tmp_path), 2) / "design"
            assert v1_mock.exists()
            assert not v2_design.exists()
        finally:
            dmod._MOCK_BUFFERS.pop(gen_id, None)


class TestStartGenCleansUpPriorBuffer:
    def test_prior_unacked_buffer_is_popped_and_stopped(self, monkeypatch: Any) -> None:
        dmod = _dmod()
        stop_ev = threading.Event()
        dmod._MOCK_BUFFERS["old-gen"] = {
            "done": True,
            "stop": stop_ev,
            "text": "",
        }
        monkeypatch.setattr(
            dmod._mock_gen, "generate_mock_streaming", lambda *a, **kw: iter(())
        )
        store, _, _ = dmod._start_gen(
            {"_gen_id": "old-gen"}, None, "m", "key", None, False
        )
        gen_id = store["_gen_id"]
        try:
            assert "old-gen" not in dmod._MOCK_BUFFERS
            assert stop_ev.is_set()
            assert gen_id in dmod._MOCK_BUFFERS
        finally:
            dmod._MOCK_BUFFERS.pop(gen_id, None)


# ---------------------------------------------------------------------------
# Progress-bar sizing — brownfield rounds size from the prior round's output
# ---------------------------------------------------------------------------


class TestProgressBarSizing:
    """Brownfield revision rounds size the progress denominator from the
    previous implemented round's mock + manifest character counts plus 10%
    headroom; everything else keeps the fixed default.
    """

    _MOCK = "<!DOCTYPE html><html><body>" + "x" * 5000 + "</body></html>"
    _MANIFEST = '{"screens": ["' + "m" * 1000 + '"]}'

    def _implement_prior(self, tmp_path: Path, with_manifest: bool = True) -> None:
        from spec4 import project_manager

        design_dir = project_manager.get_version_dir(str(tmp_path), 0) / "design"
        design_dir.mkdir(parents=True, exist_ok=True)
        (design_dir / "mock.html").write_text(self._MOCK, encoding="utf-8")
        if with_manifest:
            (design_dir / "manifest.json").write_text(self._MANIFEST, encoding="utf-8")
        project_manager.get_version_dir(str(tmp_path), 0).joinpath(
            "IMPLEMENTED"
        ).write_text("")

    def test_default_without_working_dir(self) -> None:
        dmod = _dmod()
        assert dmod.expected_stream_chars(None) == dmod._DEFAULT_EXPECTED_CHARS

    def test_default_when_no_prior_mock(self, tmp_path: Path) -> None:
        dmod = _dmod()
        expected = dmod.expected_stream_chars(str(tmp_path))
        assert expected == dmod._DEFAULT_EXPECTED_CHARS

    def test_sized_from_prior_mock_and_manifest_plus_ten_percent(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        self._implement_prior(tmp_path)
        expected = dmod.expected_stream_chars(str(tmp_path))
        assert expected == int((len(self._MOCK) + len(self._MANIFEST)) * 1.1)

    def test_sized_from_mock_alone_when_manifest_missing(self, tmp_path: Path) -> None:
        dmod = _dmod()
        self._implement_prior(tmp_path, with_manifest=False)
        expected = dmod.expected_stream_chars(str(tmp_path))
        assert expected == int(len(self._MOCK) * 1.1)

    def test_start_gen_stashes_expected_chars_in_buffer(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        dmod = _dmod()
        self._implement_prior(tmp_path)
        monkeypatch.setattr(
            dmod._mock_gen, "generate_mock_streaming", lambda *a, **kw: iter(())
        )
        store, _, _ = dmod._start_gen({}, str(tmp_path), "m", "key", None, False)
        gen_id = store["_gen_id"]
        try:
            entry = dmod._MOCK_BUFFERS[gen_id]
            assert entry["expected_chars"] == int(
                (len(self._MOCK) + len(self._MANIFEST)) * 1.1
            )
        finally:
            dmod._MOCK_BUFFERS.pop(gen_id, None)

    def test_poll_progress_uses_expected_chars(self) -> None:
        dmod = _dmod()
        gen_id = "test-progress-sizing"
        dmod._MOCK_BUFFERS[gen_id] = {
            "done": False,
            "stop": threading.Event(),
            "text": "y" * 5_000,
            "expected_chars": 10_000,
        }
        try:
            buf, _, _, _ = dmod.on_mock_stream_poll(1, {"step": 5, "_gen_id": gen_id})
            assert buf["progress"] == 50
        finally:
            dmod._MOCK_BUFFERS.pop(gen_id, None)

    def test_poll_defaults_when_buffer_has_no_expected_chars(self) -> None:
        # Defensive: a buffer created before this change (or with 0) falls
        # back to the fixed default rather than dividing by zero.
        dmod = _dmod()
        gen_id = "test-progress-default"
        dmod._MOCK_BUFFERS[gen_id] = {
            "done": False,
            "stop": threading.Event(),
            "text": "y" * 35_000,
        }
        try:
            buf, _, _, _ = dmod.on_mock_stream_poll(1, {"step": 5, "_gen_id": gen_id})
            assert buf["progress"] == 35_000 * 100 // dmod._DEFAULT_EXPECTED_CHARS
        finally:
            dmod._MOCK_BUFFERS.pop(gen_id, None)


# ---------------------------------------------------------------------------
# _start_gen background thread — crash resilience
# ---------------------------------------------------------------------------


class TestGenerationThreadResilience:
    """The generation thread must always terminate its buffer. An exception
    anywhere in _run previously died silently in the daemon thread, leaving
    the poll spinning on a buffer that never completed — the UI showed
    'Generating…' forever with no error and no Retry button.
    """

    def _wait_done(self, dmod: Any, gen_id: str, timeout: float = 5.0) -> Any:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            entry = dmod._MOCK_BUFFERS.get(gen_id)
            if entry is not None and entry.get("done"):
                return entry
            time.sleep(0.01)
        raise AssertionError("generation thread did not finish in time")

    def test_crash_surfaces_error_and_retry(self, monkeypatch: Any) -> None:
        dmod = _dmod()

        def boom(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("exploded before streaming")

        monkeypatch.setattr(dmod._mock_gen, "generate_mock_streaming", boom)
        store, _, _ = dmod._start_gen({}, None, "m", "key", None, False)
        gen_id = store["_gen_id"]
        try:
            entry = self._wait_done(dmod, gen_id)
            assert "__GENERATION_ERROR__: RuntimeError" in entry["text"]
            assert entry["done"] is True
            # The poll turns the sentinel into the error alert + Retry button.
            buf, _, disabled, _ = dmod.on_mock_stream_poll(
                1, {"step": 5, "_gen_id": gen_id}
            )
            assert "RuntimeError" in buf["error"]
            assert disabled is True
        finally:
            dmod._MOCK_BUFFERS.pop(gen_id, None)

    def test_version_dir_crash_does_not_lose_the_mock(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        # get_version_dir / active_version used to sit outside the persistence
        # try block: a filesystem error there killed the thread before
        # final_html was set, so a fully generated mock was never delivered.
        dmod = _dmod()
        html = "<!DOCTYPE html><html><body>hi</body></html>"

        def fake_stream(*args: Any, **kwargs: Any) -> Any:
            yield html
            yield "__DONE__"

        def raise_oserror(*args: Any, **kwargs: Any) -> Any:
            raise OSError("filesystem gone")

        monkeypatch.setattr(dmod._mock_gen, "generate_mock_streaming", fake_stream)
        monkeypatch.setattr(dmod.project_manager, "active_version", raise_oserror)
        store, _, _ = dmod._start_gen({}, str(tmp_path), "m", "key", None, False)
        gen_id = store["_gen_id"]
        try:
            entry = self._wait_done(dmod, gen_id)
            # Persistence failed, but delivery must still happen.
            assert entry.get("final_html") == html
            assert "__GENERATION_ERROR__" not in entry["text"]
            # The first sight slows the poll; the tick after it delivers.
            dmod.on_mock_stream_poll(1, {"step": 5, "_gen_id": gen_id})
            _, new_store, _, _ = dmod.on_mock_stream_poll(
                2, {"step": 5, "_gen_id": gen_id}
            )
            assert new_store["step"] == 6
            assert new_store["mock_html"] == html
        finally:
            dmod._MOCK_BUFFERS.pop(gen_id, None)


from spec4.callbacks.designer import extract_html  # noqa: E402


class TestExtractHtmlPrefersTheFinalDocument:
    """A model that rewrites itself mid-response must not ship its draft.

    Observed with openrouter/deepseek: the model produced a full document,
    wrote "Wait — I need to redesign this more careful", and produced a second.
    `re.search` returned the first, so a discarded draft would have been saved
    as the mock. It only escaped notice because that particular draft lacked a
    closing </html> and so matched nothing.
    """

    _DRAFT = "<!DOCTYPE html><html><body>DRAFT</body></html>"
    _FINAL = "<!DOCTYPE html><html><body>FINAL</body></html>"

    def test_the_last_complete_document_wins(self) -> None:
        text = f"{self._DRAFT}\n\nWait — let me redo that.\n\n{self._FINAL}"
        assert "FINAL" in (extract_html(text) or "")
        assert "DRAFT" not in (extract_html(text) or "")

    def test_a_single_document_is_unaffected(self) -> None:
        assert "FINAL" in (extract_html(self._FINAL) or "")

    def test_an_unterminated_tail_does_not_beat_a_complete_document(self) -> None:
        """A cut-off retry must not displace the document that did finish."""
        text = f"{self._FINAL}\n\nActually...\n\n<!DOCTYPE html><html><body>trunc"
        assert "FINAL" in (extract_html(text) or "")

    def test_the_fenced_fallback_also_takes_the_last(self) -> None:
        text = (
            "```html\n<html><body>DRAFT</body></html>\n```\n"
            "no, again\n"
            "```html\n<html><body>FINAL</body></html>\n```"
        )
        assert "FINAL" in (extract_html(text) or "")

    def test_a_fence_without_html_is_skipped(self) -> None:
        text = (
            "```html\n<html><body>FINAL</body></html>\n```\n```\njust some notes\n```"
        )
        assert "FINAL" in (extract_html(text) or "")

    def test_no_document_still_returns_none(self) -> None:
        assert extract_html("I could not build that.") is None


class TestProgressNeverClaimsCompleteMidStream:
    def test_progress_is_capped_below_100_while_streaming(self) -> None:
        from spec4.callbacks import designer as dz

        gen_id = "cap-test"
        dz._MOCK_BUFFERS[gen_id] = {
            "done": False,
            "stop": threading.Event(),
            # Twice the estimate — a draft plus a second document.
            "text": "x" * 140_000,
            "expected_chars": 70_000,
        }
        try:
            buf, _, _, _ = dz.on_mock_stream_poll(1, {"_gen_id": gen_id})
        finally:
            dz._MOCK_BUFFERS.pop(gen_id, None)
        assert buf["tokens"] == 140_000
        assert buf["progress"] == 99, "100% must mean delivered, not 'still going'"

    def test_progress_is_linear_below_the_estimate(self) -> None:
        from spec4.callbacks import designer as dz

        gen_id = "linear-test"
        dz._MOCK_BUFFERS[gen_id] = {
            "done": False,
            "stop": threading.Event(),
            "text": "x" * 35_000,
            "expected_chars": 70_000,
        }
        try:
            buf, _, _, _ = dz.on_mock_stream_poll(1, {"_gen_id": gen_id})
        finally:
            dz._MOCK_BUFFERS.pop(gen_id, None)
        assert buf["progress"] == 50


def _component(node: Any, comp_id: str) -> Any:
    """Depth-first search for a dash component by id."""
    if getattr(node, "id", None) == comp_id:
        return node
    children = getattr(node, "children", None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        found = _component(child, comp_id)
        if found is not None:
            return found
    return None


class TestDesignerRetryWithADifferentModel:
    """A failed draw offers the model picker, and survives the trip.

    Opening the picker writes `session`, which rebuilds the page and re-creates
    the wizard's memory-scoped stores. A failed draw has saved nothing to disk,
    so without the snapshot the developer would come back to the wizard intro
    with their preference text and screenshots gone — and no Retry to click.
    """

    _STORE = {
        "step": 5,
        "preference_text": "warm palette, big hero",
        "screenshots": [],
        "mock_html": "",
        "finalized": False,
        "_capture_mode": True,
        "_has_existing_html": True,
        "_has_existing_ui": True,
        "_is_revision": False,
    }
    _ERROR = "AnthropicException - Network is unreachable"

    def _session(self, **extra: Any) -> dict[str, Any]:
        from spec4.session import default_session

        session = {
            **default_session(),
            "working_dir": "/tmp",
            "phase": "designer",
            "project_mode": "new",
            "provider": "anthropic",
            "api_key": "k",
            "llm_config": {"model": "claude-sonnet-4-6", "api_key": "k"},
            "agent_llm_asked": {"designer": True},
        }
        session.update(extra)
        return session

    _BUF = {"tokens": 120, "progress": 99, "error": None}

    def _failed(self, error: str | None) -> dict[str, Any]:
        """The store the poll leaves behind: the error rides it (``_draw_error``)."""
        return {**self._STORE, "_draw_error": error}

    def _step(self, store: dict[str, Any], buf: dict[str, Any], session: Any) -> Any:
        content, _ = _dmod().render_designer_step(store, buf, True, session)
        return content

    def test_a_failed_draw_offers_both_doors(self) -> None:
        rendered = str(self._step(self._failed(self._ERROR), self._BUF, {}))
        assert "btn-designer-retry" in rendered
        assert "btn-designer-retry-model" in rendered

    def test_a_healthy_draw_offers_neither(self) -> None:
        rendered = str(self._step(self._failed(None), self._BUF, {}))
        assert "btn-designer-retry-model" not in rendered

    def test_the_snapshot_carries_the_draw(self) -> None:
        dmod = _dmod()
        updated = dmod.on_designer_retry_model(
            1, self._failed(self._ERROR), self._session()
        )
        snap = updated["_designer_failed_draw"]
        assert snap["error"] == self._ERROR
        assert snap["preference_text"] == "warm palette, big hero"
        assert snap["_capture_mode"] is True
        assert snap["_has_existing_html"] is True
        assert updated["agent_llm_draft"]["agent"] == "designer"

    def test_no_snapshot_without_an_error(self) -> None:
        dmod = _dmod()
        assert (
            dmod.on_designer_retry_model(1, self._failed(None), self._session())
            is no_update
        )

    def _round_trip(self) -> tuple[dict[str, Any], Any]:
        """Fail → open the picker → choose a model → re-render the page."""
        from spec4 import providers
        from spec4.callbacks import on_gate_connect, on_gate_continue
        from spec4.layouts.designer import designer_layout

        dmod = _dmod()
        opened = dmod.on_designer_retry_model(
            1, self._failed(self._ERROR), self._session()
        )
        with patch.object(providers, "list_models", return_value=(["gpt-5"], "")):
            opened, _ = on_gate_connect(1, "OpenAI", "sk-new", opened, {})
        with (
            patch("spec4.llm_selection.probe_image_support", return_value=True),
            patch("spec4.llm_selection.probe_tool_support", return_value=True),
        ):
            answered, _ = on_gate_continue(1, "gpt-5", None, opened)
        return answered, designer_layout(answered, {})

    def test_the_wizard_waits_behind_the_picker_during_selection(self) -> None:
        from spec4.layouts.designer import designer_layout

        dmod = _dmod()
        opened = dmod.on_designer_retry_model(
            1, self._failed(self._ERROR), self._session()
        )
        rendered = str(designer_layout(opened, {}))
        assert "agent-llm-provider" in rendered
        assert "designer-session-store" not in rendered

    def test_the_failed_draw_comes_back_after_choosing(self) -> None:
        _, layout = self._round_trip()
        store = _component(layout, "designer-session-store").data
        buf = _component(layout, "mock-stream-buffer").data
        assert store["step"] == 5
        assert store["preference_text"] == "warm palette, big hero"
        assert store["_capture_mode"] is True
        assert store["_has_existing_html"] is True
        # On both: the store's copy re-renders the step, the buffer's is the
        # counter line's seed.
        assert store["_draw_error"] == self._ERROR
        assert buf["error"] == self._ERROR

    def test_retry_is_clickable_again_after_choosing(self) -> None:
        answered, layout = self._round_trip()
        store = _component(layout, "designer-session-store").data
        buf = _component(layout, "mock-stream-buffer").data
        assert "btn-designer-retry" in str(self._step(store, buf, answered))

    def test_the_draw_would_now_use_the_new_model(self) -> None:
        from spec4 import llm_selection

        answered, _ = self._round_trip()
        assert llm_selection.resolve(answered, "designer")["model"] == "gpt-5"

    def test_retrying_spends_the_snapshot(self) -> None:
        """Left behind, a later render would resurrect a handled error."""
        dmod = _dmod()
        answered, _ = self._round_trip()
        with patch.object(dmod._refine, "_start_gen", return_value=({}, {}, False)):
            *_, cleared = dmod.on_designer_retry(1, self._STORE, answered, True)
        assert cleared["_designer_failed_draw"] is None

    def test_re_entering_designer_discards_the_snapshot(self) -> None:
        """The wizard's Back button carried this and is gone (the status bar's
        Project link is the way out now), so the discard moved to the route
        back *in*: entering Designer from the project view starts it clean.

        Without it, walking away from a failed draw and coming back would
        resurrect an error the developer already left — and, once the picker
        had armed it, re-fire the auto-retry with it.
        """
        from spec4.callbacks import on_agent_pill_click

        answered, _ = self._round_trip()
        assert answered["_designer_failed_draw"] is not None
        # Designer's own precondition, so the click routes rather than being
        # refused: reaching the wizard at all means the vision is already there.
        answered = {**answered, "vision_statement": {"vision": "v"}}
        with patch("spec4.callbacks._nav.ctx") as fake_ctx:
            fake_ctx.triggered_id = {"type": "agent-pill", "agent": "designer"}
            entered, path = on_agent_pill_click([1], answered)
        assert path == "/design"
        assert entered["_designer_failed_draw"] is None

    def test_a_clean_wizard_is_unaffected(self) -> None:
        from spec4.layouts.designer import designer_layout

        layout = designer_layout(self._session(), {})
        assert _component(layout, "mock-stream-buffer").data["error"] is None


class TestContinueIntoDesigner:
    """Both Continue buttons into Designer arrive the way the pill does.

    They used to write ``phase`` alone, so a failed draw's snapshot left on
    /design survived a trip out to Brainstormer or Agentifier and came back in
    through Continue. Both now go through ``_enter_agent``, the one arrival
    path, so the clear pinned for the pill above holds for them too.
    """

    _SNAPSHOT = {
        "error": "boom",
        "preference_text": "warm palette",
        "screenshots": [],
        "_capture_mode": False,
        "_has_existing_html": False,
    }
    # What an arrival in Designer writes; every other key passes through.
    _WRITTEN = ("phase", "agent_select_error", "_designer_failed_draw")

    def _session(self, source: str, failed: dict[str, Any] | None) -> dict[str, Any]:
        from spec4.session import default_session

        return {
            **default_session(),
            "working_dir": "/tmp",
            "phase": "chat",
            "active_agent": source,
            "vision_statement": {"vision": "v"},
            "llm_config": {"model": "claude-sonnet-4-6", "api_key": "k"},
            "messages": [{"role": "assistant", "content": "done"}],
            "_designer_failed_draw": failed,
        }

    def _continue(self, source: str, session: dict[str, Any]) -> dict[str, Any]:
        from spec4.callbacks._nav import (
            on_agentifier_to_designer,
            on_brainstormer_to_designer,
        )

        button = {
            "brainstormer": on_brainstormer_to_designer,
            "agentifier": on_agentifier_to_designer,
        }[source]
        entered, path = button(1, session)
        assert path == "/design"
        assert entered["phase"] == "designer"
        return entered

    def _rest(self, session: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in session.items() if k not in self._WRITTEN}

    def test_brainstormer_continue_discards_the_snapshot(self) -> None:
        entered = self._continue(
            "brainstormer", self._session("brainstormer", self._SNAPSHOT)
        )
        assert entered["_designer_failed_draw"] is None

    def test_brainstormer_continue_keeps_a_clean_session_clean(self) -> None:
        entered = self._continue("brainstormer", self._session("brainstormer", None))
        assert entered["_designer_failed_draw"] is None

    def test_brainstormer_continue_leaves_the_rest_alone(self) -> None:
        session = self._session("brainstormer", self._SNAPSHOT)
        rest = self._rest(session)
        assert self._rest(self._continue("brainstormer", session)) == rest

    def test_agentifier_continue_discards_the_snapshot(self) -> None:
        entered = self._continue(
            "agentifier", self._session("agentifier", self._SNAPSHOT)
        )
        assert entered["_designer_failed_draw"] is None

    def test_agentifier_continue_keeps_a_clean_session_clean(self) -> None:
        entered = self._continue("agentifier", self._session("agentifier", None))
        assert entered["_designer_failed_draw"] is None

    def test_agentifier_continue_leaves_the_rest_alone(self) -> None:
        session = self._session("agentifier", self._SNAPSHOT)
        rest = self._rest(session)
        assert self._rest(self._continue("agentifier", session)) == rest


class TestDesignerAutoRetry:
    """Choosing a model from a failed draw re-runs it without a second click.

    It cannot happen where the chat one does. Designer's gate replaces its
    wizard, so `designer-session-store` and friends are unmounted while the
    picker is open and `on_gate_continue` has nowhere to write a draw. The
    restored wizard arms a one-shot interval instead.
    """

    _STORE = {
        "step": 5,
        "preference_text": "warm palette",
        "screenshots": [],
        "mock_html": "",
        "finalized": False,
        "_capture_mode": True,
        "_has_existing_html": True,
        "_has_existing_ui": True,
        "_is_revision": False,
    }

    def _session(self, **extra: Any) -> dict[str, Any]:
        from spec4.session import default_session

        session = {
            **default_session(),
            "working_dir": "/tmp",
            "phase": "designer",
            "project_mode": "new",
            "provider": "anthropic",
            "api_key": "k",
            "llm_config": {"model": "claude-sonnet-4-6", "api_key": "k"},
            "agent_llm_asked": {"designer": True},
        }
        session.update(extra)
        return session

    def _choose(self, *, tool_support: bool | None = True) -> dict[str, Any]:
        from spec4 import providers
        from spec4.callbacks import on_gate_connect, on_gate_continue

        dmod = _dmod()
        opened = dmod.on_designer_retry_model(
            1, {**self._STORE, "_draw_error": "unreachable"}, self._session()
        )
        with patch.object(providers, "list_models", return_value=(["gpt-5"], "")):
            opened, _ = on_gate_connect(1, "OpenAI", "sk-new", opened, {})
        with (
            patch("spec4.llm_selection.probe_image_support", return_value=True),
            patch("spec4.llm_selection.probe_tool_support", return_value=tool_support),
        ):
            answered, _ = on_gate_continue(1, "gpt-5", None, opened)
        return answered

    def test_choosing_arms_the_one_shot_trigger(self) -> None:
        from spec4.layouts.designer import designer_layout

        layout = designer_layout(self._choose(), {})
        interval = _component(layout, "designer-autoretry-interval")
        assert interval.max_intervals == 1

    def test_a_failed_draw_not_sent_to_the_picker_does_not_self_fire(self) -> None:
        from spec4.layouts.designer import designer_layout

        session = self._session(
            _designer_failed_draw={
                "error": "boom",
                "preference_text": "",
                "screenshots": [],
                "_capture_mode": False,
                "_has_existing_html": False,
            }
        )
        interval = _component(
            designer_layout(session, {}), "designer-autoretry-interval"
        )
        assert interval.max_intervals == 0

    def test_a_clean_wizard_leaves_it_disabled(self) -> None:
        from spec4.layouts.designer import designer_layout

        interval = _component(
            designer_layout(self._session(), {}), "designer-autoretry-interval"
        )
        assert interval.max_intervals == 0

    def test_the_trigger_reproduces_the_original_draw(self) -> None:
        from spec4.layouts.designer import designer_layout

        dmod = _dmod()
        answered = self._choose()
        store = _component(designer_layout(answered, {}), "designer-session-store").data
        with patch.object(
            dmod._refine, "_start_gen", return_value=({"step": 5}, {"tokens": 0}, False)
        ) as start:
            dmod.on_designer_auto_retry(1, store, answered, True)
        assert start.called
        assert start.call_args[1]["capture_mode"] is True

    def test_the_trigger_spends_the_snapshot(self) -> None:
        """Left armed, every later visit to Designer would draw again."""
        from spec4.layouts.designer import designer_layout

        dmod = _dmod()
        answered = self._choose()
        store = _component(designer_layout(answered, {}), "designer-session-store").data
        with patch.object(
            dmod._refine, "_start_gen", return_value=({"step": 5}, {"tokens": 0}, False)
        ):
            *_, cleared = dmod.on_designer_auto_retry(1, store, answered, True)
        assert cleared["_designer_failed_draw"] is None
        interval = _component(
            designer_layout(cleared, {}), "designer-autoretry-interval"
        )
        assert interval.max_intervals == 0

    def test_the_trigger_survives_a_clean_session(self) -> None:
        """`_designer_failed_draw` is present-and-None on a clean session, so a
        `.get(key, {})` default would never be reached. Found by dispatching the
        interval against a running server."""
        dmod = _dmod()
        with patch.object(dmod._refine, "_start_gen") as start:
            result = dmod.on_designer_auto_retry(1, self._STORE, self._session(), True)
        start.assert_not_called()
        assert all(r is no_update for r in result)

    def test_the_trigger_refuses_without_the_marker(self) -> None:
        dmod = _dmod()
        session = self._session(
            _designer_failed_draw={"error": "boom", "preference_text": ""}
        )
        with patch.object(dmod._refine, "_start_gen") as start:
            result = dmod.on_designer_auto_retry(1, self._STORE, session, True)
        start.assert_not_called()
        assert all(r is no_update for r in result)

    def test_a_tool_less_model_keeps_the_picker_open(self) -> None:
        from spec4.layouts.designer import designer_layout

        answered = self._choose(tool_support=False)
        assert answered["agent_llm"] == {}
        rendered = str(designer_layout(answered, {}))
        assert "agent-llm-model" in rendered
        assert "no tool support" in rendered
        assert "designer-session-store" not in rendered


class TestDesignerLayoutWithoutProject:
    """The wizard renders when the session names no working directory.

    Nothing on disk can be read without a project, and every disk read in the
    layout already guards on ``working_dir`` — but the round lookup used to run
    unguarded and reached ``Path(None)``.
    """

    def test_no_project_renders_the_wizard(self) -> None:
        from spec4.layouts.designer import designer_layout
        from spec4.session import default_session

        session = {
            **default_session(),
            "working_dir": None,
            "phase": "designer",
            "provider": "anthropic",
            "api_key": "k",
            "llm_config": {"model": "claude-sonnet-4-6", "api_key": "k"},
            "agent_llm_asked": {"designer": True},
        }
        layout = designer_layout(session, {})
        interval = _component(layout, "designer-autoretry-interval")
        assert interval.max_intervals == 0


class TestStepFiveImageNotice:
    """A draw handed an image-less model says so where it is being watched.

    Step 4 already carries this notice, but a draw given a different model
    mid-flight never passes back through step 4 to be told there.
    """

    _BUF = {"tokens": 5, "progress": 3, "error": None}
    _STORE = {"step": 5, "screenshots": [], "refine_images": [], "mock_html": ""}
    # The notice is a dimmed line rather than the orange alert it was; what is
    # asserted is that it is said at all, so this is the fragment of it that
    # survives a rewording of the rest.
    _NOTICE = "takes no image input"

    def _render(self, session: dict[str, Any]) -> str:
        content, _ = _dmod().render_designer_step(self._STORE, self._BUF, True, session)
        return str(content)

    def _override(self, image_support: bool | None) -> dict[str, Any]:
        return {
            "agent_llm": {
                "designer": {
                    "provider": "openrouter",
                    "model": "m",
                    "llm_config": {"model": "m"},
                    "image_support": image_support,
                    "tool_support": True,
                }
            }
        }

    def test_shown_for_an_image_less_model(self) -> None:
        assert self._NOTICE in self._render(self._override(False))

    def test_silent_for_a_capable_model(self) -> None:
        assert self._NOTICE not in self._render(self._override(True))

    def test_silent_with_no_override(self) -> None:
        assert self._NOTICE not in self._render({})


class TestGenerateMockCallback:
    """``on_designer_generate_mock``: its click, the screenshot annotations and the
    image-support flag, driven with their props' values.

    No test reached it before (PHASE8_RECORD.md 1.2, P22).
    """

    def _start(self, monkeypatch: Any) -> dict[str, Any]:
        from spec4.callbacks.designer import _wizard

        captured: dict[str, Any] = {}

        def fake_start_gen(
            store_arg, wd, model, api_key, search_cfg, support, planning, **kwargs
        ):
            captured.update(store=store_arg, support=support, planning=planning)
            return {"step": 5}, {"tokens": 0}, False

        monkeypatch.setattr(_wizard, "_start_gen", fake_start_gen)
        return captured

    def test_each_annotation_lands_on_its_screenshot(self, monkeypatch: Any) -> None:
        from spec4.callbacks.designer._wizard import on_designer_generate_mock

        captured = self._start(monkeypatch)
        store = {"step": 4, "screenshots": [{"data": "a"}, {"data": "b"}]}
        out = on_designer_generate_mock(1, ["the header", None], store, {}, False)
        assert out == ({"step": 5}, {"tokens": 0}, False)
        assert captured["store"]["screenshots"] == [
            {"data": "a", "annotation": "the header"},
            {"data": "b", "annotation": ""},
        ]
        assert captured["support"] is False
        assert captured["planning"] is None

    def test_no_click_starts_nothing(self, monkeypatch: Any) -> None:
        from spec4.callbacks.designer._wizard import on_designer_generate_mock

        captured = self._start(monkeypatch)
        store = {"step": 4, "screenshots": [{"data": "a"}]}
        out = on_designer_generate_mock(None, ["x"], store, {}, True)
        assert out == (no_update, no_update, no_update)
        assert captured == {}


class TestToolCallFollowup:
    """``_designer_tool_call_followup``, whose one caller no test drives: the tool
    turn is appended, and a web search runs with the configured search.

    No test reached it before (PHASE8_RECORD.md 1.2, P22).
    """

    def _acc(self, name: str) -> dict[int, dict[str, str]]:
        return {
            0: {"id": "call-1", "name": name, "arguments": '{"query": "pricing pages"}'}
        }

    def _assistant_turn(self, name: str) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": "thinking",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": '{"query": "pricing pages"}',
                    },
                }
            ],
        }

    def test_a_web_search_is_answered_with_the_configured_search(self) -> None:
        from spec4.agents.designer import _designer_tool_call_followup
        from spec4.websearch import SearchConfig

        cfg = SearchConfig(provider="tavily", api_key="k")
        messages: list[dict[str, Any]] = []
        with patch("spec4.agents.designer.web_search", return_value="RESULTS") as ws:
            _designer_tool_call_followup(
                messages, self._acc("web_search"), "thinking", cfg
            )
        ws.assert_called_once_with("pricing pages", cfg)
        assert messages == [
            self._assistant_turn("web_search"),
            {"role": "tool", "tool_call_id": "call-1", "content": "RESULTS"},
        ]

    def test_another_tool_gets_the_turn_but_no_search(self) -> None:
        from spec4.agents.designer import _designer_tool_call_followup

        messages: list[dict[str, Any]] = []
        with patch("spec4.agents.designer.web_search") as ws:
            _designer_tool_call_followup(messages, self._acc("other"), "thinking", None)
        ws.assert_not_called()
        assert messages == [self._assistant_turn("other")]


# ---------------------------------------------------------------------------
# Start Over clears the round's saved design, not only the store
# ---------------------------------------------------------------------------


def _store_of(layout: Any) -> dict[str, Any]:
    """The designer-session-store's initial data inside a rendered layout."""

    def walk(node: Any) -> Any:
        if getattr(node, "id", None) == "designer-session-store":
            return node.data
        kids = getattr(node, "children", None)
        if isinstance(kids, list):
            for k in kids:
                found = walk(k)
                if found is not None:
                    return found
        elif kids is not None:
            return walk(kids)
        return None

    found = walk(layout)
    assert found is not None
    return found


class TestStartOverClearsTheSavedDesign:
    """Start Over is a fresh design conversation, and ``designer_layout``
    rebuilds the wizard store from ``design/session.json`` on every render. The
    callback used to reset only the in-memory store, so answering the reopened
    gate put the discarded mock straight back on screen at the preview step.
    """

    _FILES = ("session.json", "mock.html", "manifest.json")

    def _round(self, tmp_path: Path, version: int) -> Path:
        from spec4 import project_manager

        d = project_manager.get_version_dir(str(tmp_path), version) / "design"
        d.mkdir(parents=True, exist_ok=True)
        save_session(_session(step=6, mock_html="<html>old</html>", finalized=False), d)
        save_mock("<html>old</html>", d)
        (d / "manifest.json").write_text('{"screens": ["old"]}')
        return d

    def _start_over(self, tmp_path: Path, **extra: Any) -> dict[str, Any]:
        from spec4.session import default_session

        session = default_session()
        session.update(
            {
                "phase": "designer",
                "working_dir": str(tmp_path),
                "phase_version": 1,
                "agent_llm_asked": {"designer": True},
                **extra,
            }
        )
        store = {"step": 6, "mock_html": "<html>old</html>", "_has_existing_ui": True}
        new_store, buf, disabled, updated = _dmod().on_designer_start_over(
            1, store, session
        )
        assert new_store["step"] == 2
        assert buf["text"] == ""
        assert disabled is True
        return updated

    def test_the_active_round_s_design_files_are_deleted(self, tmp_path: Path) -> None:
        d = self._round(tmp_path, 1)
        assert all((d / name).exists() for name in self._FILES)
        self._start_over(tmp_path)
        assert not any((d / name).exists() for name in self._FILES)
        assert d.is_dir()

    def test_a_prior_round_s_mock_is_left_as_the_revision_baseline(
        self, tmp_path: Path
    ) -> None:
        prior = self._round(tmp_path, 0)
        self._round(tmp_path, 1)
        self._start_over(tmp_path)
        assert all((prior / name).exists() for name in self._FILES)
        assert (prior / "mock.html").read_text() == "<html>old</html>"

    def test_answering_the_gate_lands_on_the_first_question_not_the_old_mock(
        self, tmp_path: Path
    ) -> None:
        from spec4.callbacks import on_gate_keep
        from spec4.layouts.designer import designer_layout

        self._round(tmp_path, 1)
        session = {
            **self._start_over(tmp_path),
            "active_agent": "designer",
        }
        # Before the fix this re-render found session.json and opened at the
        # preview step with the mock the developer had just discarded.
        before = _store_of(
            designer_layout({**session, "agent_llm_asked": {"designer": True}}, {})
        )
        assert before["step"] == 2
        assert "old" not in before["mock_html"]
        answered = on_gate_keep(1, session)
        after = _store_of(designer_layout(answered, {}))
        assert after["step"] == 2
        assert after["preference_text"] == ""
        assert after["screenshots"] == []

    def test_without_a_project_there_is_nothing_on_disk_to_clear(self) -> None:
        from spec4.session import default_session

        session = default_session()
        session.update({"phase": "designer", "working_dir": None})
        new_store, _, _, updated = _dmod().on_designer_start_over(
            1, {"step": 6, "mock_html": "<p/>"}, session
        )
        assert new_store["step"] == 2
        assert updated["_designer_failed_draw"] is None


# ---------------------------------------------------------------------------
# A draw outlives the page it was started from
# ---------------------------------------------------------------------------


class TestWatchdogReArmsALostDraw:
    """``render_page`` rebuilds the wizard's two memory stores on every session
    write and every browser load -- with no ``_gen_id`` and the poll off --
    while the draw's thread runs on and saves its mock to a page that never
    hears of it. The watchdog finds the round's draw and turns the poll back
    on; the poll's own delivery and acknowledgement then finish the job.
    """

    _GEN_ID = "test-watchdog-gen"

    def _session(self, tmp_path: Path) -> dict[str, Any]:
        from spec4.session import default_session

        return {
            **default_session(),
            "phase": "designer",
            "working_dir": str(tmp_path),
            "phase_version": 1,
            "agent_llm_asked": {"designer": True},
        }

    def _design_dir(self, tmp_path: Path) -> Path:
        from spec4 import project_manager

        return project_manager.get_version_dir(str(tmp_path), 1) / "design"

    def _buffer(self, tmp_path: Path, **extra: Any) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "done": False,
            "stop": threading.Event(),
            "text": "abc",
            "expected_chars": 1000,
            "design_dir": str(self._design_dir(tmp_path)),
            "started": time.monotonic(),
            **extra,
        }
        _dmod()._MOCK_BUFFERS[self._GEN_ID] = entry
        return entry

    def teardown_method(self) -> None:
        _dmod()._MOCK_BUFFERS.pop(self._GEN_ID, None)

    def test_a_rebuilt_store_is_pointed_at_the_round_s_draw(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        self._buffer(tmp_path)
        rebuilt = {"step": 2, "_has_existing_ui": True, "_is_revision": False}
        store, buf, disabled, interval = dmod.on_mock_stream_watchdog(
            1, rebuilt, True, self._session(tmp_path)
        )
        assert store["step"] == 5
        assert store["_gen_id"] == self._GEN_ID
        assert store["mock_html"] == ""
        assert store["screenshots"] == []
        assert store["refine_images"] == []
        assert store["finalized"] is False
        # The rebuilt store's own flags survive, as they do through delivery.
        assert store["_has_existing_ui"] is True
        assert buf["tokens"] == 3
        assert buf["progress"] == 0
        assert buf["error"] is None
        assert disabled is False
        assert interval == dmod.WATCHDOG_MS

    def test_a_store_already_on_the_draw_only_turns_the_poll_on(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        self._buffer(tmp_path)
        out = dmod.on_mock_stream_watchdog(
            1, {"step": 5, "_gen_id": self._GEN_ID}, True, self._session(tmp_path)
        )
        assert out == (no_update, no_update, False, dmod.WATCHDOG_MS)

    def test_a_running_poll_is_left_alone(self, tmp_path: Path) -> None:
        dmod = _dmod()
        self._buffer(tmp_path)
        out = dmod.on_mock_stream_watchdog(
            1, {"step": 2}, False, self._session(tmp_path)
        )
        assert out == (no_update, no_update, no_update, dmod.WATCHDOG_MS)

    def test_no_draw_for_this_round_is_a_no_op(self, tmp_path: Path) -> None:
        dmod = _dmod()
        session = self._session(tmp_path)
        idle = (no_update, no_update, no_update, dmod.WATCHDOG_MS)
        assert dmod.on_mock_stream_watchdog(1, {"step": 2}, True, session) == idle
        # Another round's draw is not this page's to poll.
        self._buffer(tmp_path, design_dir=str(tmp_path / "elsewhere"))
        assert dmod.on_mock_stream_watchdog(2, {"step": 2}, True, session) == idle
        # ...whereas the round's own draw is found (the pair for the two above).
        self._buffer(tmp_path)
        store, _, disabled, _ = dmod.on_mock_stream_watchdog(
            3, {"step": 2}, True, session
        )
        assert store["_gen_id"] == self._GEN_ID
        assert disabled is False

    def test_a_finished_draw_is_delivered_on_the_next_poll(
        self, tmp_path: Path
    ) -> None:
        """The reload happened after the thread finished: the rebuilt store came
        from disk at the preview step with the *saved* mock, and the buffer
        still holds the delivery. Re-arming hands it to the poll, which
        delivers it in-band as it would have on the original page."""
        dmod = _dmod()
        html = "<!DOCTYPE html><html><body>new</body></html>"
        self._buffer(tmp_path, done=True, text=html + "__DONE__", final_html=html)
        from_disk = {"step": 6, "mock_html": html, "finalized": False}
        rearmed, _, disabled, _ = dmod.on_mock_stream_watchdog(
            1, from_disk, True, self._session(tmp_path)
        )
        assert rearmed["step"] == 5
        assert disabled is False
        assert rearmed["_draw_error"] is None
        # The poll's first sight of the finished draw slows its cadence; the
        # tick after that delivers.
        dmod.on_mock_stream_poll(1, rearmed)
        buf, delivered, _, _ = dmod.on_mock_stream_poll(2, rearmed)
        assert delivered["step"] == 6
        assert delivered["mock_html"] == html
        assert delivered["_gen_id"] == self._GEN_ID
        assert buf["progress"] == 100

    def test_a_draw_is_findable_until_the_poll_acknowledges_it(
        self, tmp_path: Path
    ) -> None:
        """Delivered but unacknowledged, the draw is still this page's to poll;
        only the acknowledging tick pops it, and then nothing is found."""
        dmod = _dmod()
        html = "<!DOCTYPE html><html><body>ok</body></html>"
        entry = self._buffer(
            tmp_path, done=True, text=html + "__DONE__", final_html=html
        )
        design_dir = self._design_dir(tmp_path)
        store = {"step": 5, "_gen_id": self._GEN_ID}
        assert dmod.find_live_draw({}, design_dir) == (self._GEN_ID, entry)
        assert dmod.find_live_draw(store, None) == (self._GEN_ID, entry)
        # Without a round there is nothing to look a nameless store's draw up by.
        assert dmod.find_live_draw({}, None) is None
        dmod.on_mock_stream_poll(1, store)  # slows the cadence, delivers nothing
        assert dmod.find_live_draw({}, design_dir) == (self._GEN_ID, entry)
        _, delivered, _, _ = dmod.on_mock_stream_poll(2, store)
        assert delivered["step"] == 6
        assert dmod.find_live_draw({}, design_dir) == (self._GEN_ID, entry)
        _, _, disabled, _ = dmod.on_mock_stream_poll(3, delivered)
        assert disabled is True
        assert dmod.find_live_draw(delivered, design_dir) is None
        assert dmod.find_live_draw({}, design_dir) is None

    def test_elapsed_is_zero_for_a_buffer_with_no_start_time(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        entry = self._buffer(tmp_path)
        del entry["started"]
        assert dmod.stream_progress(entry)["elapsed"] == 0
        entry["started"] = time.monotonic() - 125
        assert dmod.stream_progress(entry)["elapsed"] >= 125

    def test_idle_counts_from_the_last_chunk(self, tmp_path: Path) -> None:
        """The pause notice's input: 0 until a chunk has arrived, then the
        seconds since the latest one."""
        dmod = _dmod()
        entry = self._buffer(tmp_path)
        assert dmod.stream_progress(entry)["idle"] == 0
        entry["last_chunk_at"] = time.monotonic() - 40
        assert dmod.stream_progress(entry)["idle"] >= 40
        entry["last_chunk_at"] = time.monotonic()
        assert dmod.stream_progress(entry)["idle"] == 0

    def test_every_chunk_kind_stamps_the_last_chunk_time(self, tmp_path: Path) -> None:
        """Thinking chunks count too: a model reasoning between output bursts
        is not paused, and the notice must not say it is."""
        from spec4.agents.designer import THINKING_MARK
        from spec4.callbacks.designer._mock_gen import _mock_absorb_chunk

        entry = self._buffer(tmp_path)
        entry["last_chunk_at"] = time.monotonic() - 40
        _mock_absorb_chunk(entry, THINKING_MARK + "hmm")
        assert entry["last_chunk_at"] > time.monotonic() - 1
        assert entry["text"] == "abc"
        entry["last_chunk_at"] = time.monotonic() - 40
        _mock_absorb_chunk(entry, "<p>")
        assert entry["last_chunk_at"] > time.monotonic() - 1
        assert entry["text"] == "abc<p>"

    def test_the_painter_says_how_long_the_output_has_paused(self) -> None:
        """The clientside line is the only reader of ``idle``; pin that it is
        wired to the threshold the buffer module names."""
        from spec4.app import app
        from spec4.callbacks.designer._mock_gen import PAUSE_NOTICE_S

        [painter] = [
            script for script in app._inline_scripts if "mock-token-count" in script
        ]
        assert "no output for" in str(painter)
        assert f"buf.idle >= {PAUSE_NOTICE_S}" in str(painter)

    def test_the_layout_mounts_it_fast_with_the_poll_off(self, tmp_path: Path) -> None:
        from spec4.callbacks.designer._mock_gen import DELIVERY_MS
        from spec4.layouts.designer import POLL_MS, WATCHDOG_FIRST_MS, designer_layout

        dmod = _dmod()
        layout = designer_layout(self._session(tmp_path), {})
        watchdog = _component(layout, "mock-stream-watchdog")
        assert watchdog.interval == WATCHDOG_FIRST_MS
        assert WATCHDOG_FIRST_MS < dmod.WATCHDOG_MS
        assert not getattr(watchdog, "disabled", False)
        # The rebuild itself never arms the poll; that is the watchdog's job.
        poll = _component(layout, "mock-stream-interval")
        assert poll.disabled is True
        # Mounted at the running cadence, which the poll's own ack restores
        # after a delivery; the delivery cadence is the slower of the two.
        assert poll.interval == POLL_MS
        assert POLL_MS < DELIVERY_MS


class TestRetryAfterAModelChangeKeepsItsDraw:
    """The retry writes ``session`` in the response that starts the draw, so
    the page is rebuilt around a draw the rebuilt store does not name. The
    watchdog's first tick on that page re-arms the same draw."""

    def test_the_rebuilt_page_re_arms_the_draw_the_retry_started(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        from spec4.callbacks.designer._refine import _rerun_failed_draw
        from spec4.layouts.designer import designer_layout
        from spec4.session import default_session

        dmod = _dmod()
        monkeypatch.setattr(dmod._mock_gen.threading, "Thread", _NoThread)
        session = {
            **default_session(),
            "phase": "designer",
            "working_dir": str(tmp_path),
            "phase_version": 1,
            "project_mode": "new",
            "provider": "openai",
            "api_key": "k",
            "llm_config": {"model": "gpt-5", "api_key": "k"},
            "agent_llm_asked": {"designer": True},
            "_designer_failed_draw": {"error": "boom", "auto_retry": True},
        }
        store = {"step": 5, "preference_text": "p", "screenshots": [], "mock_html": ""}
        try:
            new_store, _, disabled, cleared = _rerun_failed_draw(store, session, True)
            assert disabled is False
            gen_id = new_store["_gen_id"]
            assert cleared["_designer_failed_draw"] is None

            rebuilt = designer_layout(cleared, {})
            rebuilt_store = _store_of(rebuilt)
            assert "_gen_id" not in rebuilt_store
            assert _component(rebuilt, "mock-stream-interval").disabled is True

            rearmed, _, rearmed_disabled, _ = dmod.on_mock_stream_watchdog(
                1, rebuilt_store, True, cleared
            )
            assert rearmed["_gen_id"] == gen_id
            assert rearmed["step"] == 5
            assert rearmed_disabled is False
        finally:
            dmod._MOCK_BUFFERS.clear()


class TestDesignerDrawTimeout:
    """The draw's time-to-first-token can run past LiteLLM's 600 s fallback, so
    the call carries its own, longer stall bound."""

    def _chunk(self, text: str) -> Any:
        from types import SimpleNamespace

        choice = SimpleNamespace(
            delta=SimpleNamespace(content=text, tool_calls=None), finish_reason=None
        )
        return SimpleNamespace(choices=[choice])

    def _draw(self, monkeypatch: Any, chunks: list[Any]) -> dict[str, Any]:
        import spec4.agents.designer as agent_mod

        captured: dict[str, Any] = {}

        def fake_stream(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return iter(chunks)

        monkeypatch.setattr(agent_mod.llm, "stream_completion", fake_stream)
        monkeypatch.setattr(agent_mod, "build_mock_prompt", lambda *a, **k: [])
        list(generate_mock_streaming(_session(), "m", "k", [], False))
        return captured

    def test_the_draw_sends_its_own_stall_bound(self, monkeypatch: Any) -> None:
        from spec4 import llm

        sent = self._draw(monkeypatch, [])
        assert sent["timeout"] is llm.DESIGNER_STREAM_TIMEOUT
        assert llm.DESIGNER_STREAM_TIMEOUT.read is not None
        assert llm.DESIGNER_STREAM_TIMEOUT.read > 600
        assert llm.DESIGNER_STREAM_TIMEOUT.read > (llm.LLM_STREAM_TIMEOUT.read or 0)

    def test_time_to_first_token_is_printed_once(
        self, monkeypatch: Any, capsys: Any
    ) -> None:
        self._draw(monkeypatch, [self._chunk("a"), self._chunk("b")])
        out = capsys.readouterr().out
        assert out.count("[llm-ttft] designer: first chunk after") == 1

    def test_an_empty_stream_prints_no_time_to_first_token(
        self, monkeypatch: Any, capsys: Any
    ) -> None:
        self._draw(monkeypatch, [])
        assert "[llm-ttft]" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The 5-series thinks by default: the draw shows the thinking
# ---------------------------------------------------------------------------


class TestDrawYieldsThinkingUnderAMarker:
    """Reasoning text rides out of the draw under ``THINKING_MARK``, apart from
    the output, so the page can count it and the buffer can keep it out."""

    def _draw(self, monkeypatch: Any, deltas: list[Any]) -> list[str]:
        import spec4.agents.designer as agent_mod
        from tests._chunks import make_stream_chunk

        chunks = []
        for delta in deltas:
            chunk = make_stream_chunk()
            chunk.choices[0].delta = delta
            chunks.append(chunk)
        monkeypatch.setattr(
            agent_mod.llm, "stream_completion", lambda **kwargs: iter(chunks)
        )
        monkeypatch.setattr(agent_mod, "build_mock_prompt", lambda *a, **k: [])
        return list(generate_mock_streaming(_session(), "m", "k", [], False))

    def test_a_reasoning_delta_yields_the_mark_and_nothing_else(
        self, monkeypatch: Any
    ) -> None:
        from spec4.agents.designer import THINKING_MARK
        from tests._chunks import make_delta

        out = self._draw(monkeypatch, [make_delta(reasoning_content="plan <html>")])
        assert out == [THINKING_MARK + "plan <html>", "__DONE__"]

    def test_a_content_delta_yields_only_its_content(self, monkeypatch: Any) -> None:
        from spec4.agents.designer import THINKING_MARK
        from tests._chunks import make_delta

        out = self._draw(monkeypatch, [make_delta(content="<html>")])
        assert out == ["<html>", "__DONE__"]
        assert not any(piece.startswith(THINKING_MARK) for piece in out)

    def test_a_delta_with_both_yields_content_then_the_mark(
        self, monkeypatch: Any
    ) -> None:
        from spec4.agents.designer import THINKING_MARK
        from tests._chunks import make_delta

        out = self._draw(
            monkeypatch, [make_delta(content="a", reasoning_content="why")]
        )
        assert out == ["a", THINKING_MARK + "why", "__DONE__"]

    def test_an_empty_reasoning_field_yields_nothing(self, monkeypatch: Any) -> None:
        from tests._chunks import make_delta

        out = self._draw(monkeypatch, [make_delta(reasoning_content="")])
        assert out == ["__DONE__"]


class TestWorkerCountsThinkingSeparately:
    """The buffer counts thinking characters and never lets the text near the
    HTML: a reasoning summary can quote a whole document."""

    _HTML = "<!DOCTYPE html><html><body>real</body></html>"

    def _draw(self, monkeypatch: Any, tmp_path: Path, chunks: list[str]) -> Any:
        dmod = _dmod()
        monkeypatch.setattr(dmod._mock_gen.threading, "Thread", _SyncThread)
        monkeypatch.setattr(
            dmod._mock_gen, "generate_mock_streaming", lambda *a, **k: iter(chunks)
        )
        store, _, _ = dmod._start_gen({}, str(tmp_path), "m", "k", None, False)
        return dmod._MOCK_BUFFERS.pop(store["_gen_id"])

    def test_thinking_is_counted_and_kept_out_of_the_text(
        self, monkeypatch: Any, tmp_path: Path
    ) -> None:
        from spec4.agents.designer import THINKING_MARK

        dmod = _dmod()
        entry = self._draw(
            monkeypatch,
            tmp_path,
            [THINKING_MARK + "<html>plan", THINKING_MARK + "!", self._HTML, "__DONE__"],
        )
        assert entry["thinking_chars"] == len("<html>plan") + 1
        assert "plan" not in entry["text"]
        assert entry["text"] == self._HTML + "__DONE__"
        assert entry["final_html"] == self._HTML
        assert dmod.stream_progress(entry)["thinking"] == len("<html>plan") + 1

    def test_a_draw_without_thinking_reports_zero(
        self, monkeypatch: Any, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        entry = self._draw(monkeypatch, tmp_path, [self._HTML, "__DONE__"])
        assert entry["thinking_chars"] == 0
        assert dmod.stream_progress(entry)["thinking"] == 0
        # A buffer from before the field existed reports zero as well.
        del entry["thinking_chars"]
        assert dmod.stream_progress(entry)["thinking"] == 0


# ---------------------------------------------------------------------------
# The drawn mock is checked, and its errors go back to the model
# ---------------------------------------------------------------------------


_CLEAN_MOCK = (
    "<!DOCTYPE html><html><head><style>body{}</style></head>"
    "<body><p>hi</p><script>var a = `x`;</script></body></html>"
)


class TestCheckMockHtml:
    """Static, deterministic, advisory: the structural defects the text alone
    shows. Each rule has its positive and its negative."""

    def _check(self, html: str, **kw: Any) -> list[str]:
        from spec4.callbacks.designer._mock_gen import check_mock_html

        return check_mock_html(html, **kw)

    def test_a_clean_document_has_no_errors(self) -> None:
        assert self._check(_CLEAN_MOCK) == []

    def test_truncation_is_reported_with_the_limit(self) -> None:
        [error] = self._check(_CLEAN_MOCK, truncated=True)
        assert "cut off at 512 kB" in error
        assert self._check(_CLEAN_MOCK, truncated=False) == []

    def test_a_document_that_does_not_close_is_reported(self) -> None:
        broken = _CLEAN_MOCK.replace("</body>", "")
        assert any("</body> and </html>" in e for e in self._check(broken))
        assert not any("</body>" in e for e in self._check(_CLEAN_MOCK))

    def test_unbalanced_script_tags_are_counted(self) -> None:
        broken = _CLEAN_MOCK.replace("</script>", "")
        [error] = [e for e in self._check(broken) if "<script>" in e]
        assert "1 opened, 0 closed" in error
        assert not any("<script>" in e for e in self._check(_CLEAN_MOCK))

    def test_unbalanced_style_tags_are_counted(self) -> None:
        broken = _CLEAN_MOCK.replace("<style>", "<style><style>")
        [error] = [e for e in self._check(broken) if "<style>" in e]
        assert "2 opened, 1 closed" in error
        assert not any("<style>" in e for e in self._check(_CLEAN_MOCK))

    def test_an_odd_backtick_in_a_script_is_reported(self) -> None:
        broken = _CLEAN_MOCK.replace("`x`", "`x")
        [error] = [e for e in self._check(broken) if "template literal" in e]
        assert error.startswith("Script block 1")
        assert not any("template literal" in e for e in self._check(_CLEAN_MOCK))

    def test_an_escaped_backtick_is_not_counted(self) -> None:
        escaped = _CLEAN_MOCK.replace("`x`", "`x\\`y`")
        assert not any("template literal" in e for e in self._check(escaped))

    def test_tag_matching_ignores_case_and_attributes(self) -> None:
        odd = _CLEAN_MOCK.replace("<script>", '<SCRIPT type="module">').replace(
            "</script>", "</SCRIPT >"
        )
        assert self._check(odd) == []


class TestMockErrorMessages:
    def test_static_then_runtime_with_lines(self) -> None:
        from spec4.callbacks.designer._mock_gen import mock_error_list

        store = {"_mock_errors": ["Doc is cut off."]}
        reported = {
            "errors": [
                {"message": "x is not defined", "source": "", "line": 12},
                {"message": "Failed to load <img> a.png", "line": 0},
                "not a dict",
            ]
        }
        assert mock_error_list(store, reported) == [
            "Doc is cut off.",
            "x is not defined (line 12)",
            "Failed to load <img> a.png",
        ]
        assert mock_error_list({}, None) == []

    def test_the_instruction_has_the_header_and_a_capped_list(self) -> None:
        from spec4.callbacks.designer._mock_gen import (
            MOCK_ERROR_LIMIT,
            format_mock_errors,
        )

        text = format_mock_errors(["one", "two"])
        lines = text.splitlines()
        assert lines[0].startswith("Fix these errors in the current mock")
        assert "return the whole corrected document" in lines[1]
        assert lines[2:] == ["- one", "- two"]
        many = format_mock_errors([f"e{i}" for i in range(MOCK_ERROR_LIMIT + 3)])
        assert many.count("\n- ") == MOCK_ERROR_LIMIT
        assert many.endswith("(plus 3 more -- fix the structural issues above first)")


class TestFinaliseRecordsStaticErrors:
    def _finalise(self, accumulated: str, monkeypatch: Any, **kw: Any) -> Any:
        from spec4.callbacks.designer import _mock_gen

        for name, value in kw.items():
            monkeypatch.setattr(_mock_gen, name, value)
        entry: dict[str, Any] = {"text": accumulated}
        ds = {
            "step": 5,
            "preference_text": "",
            "screenshots": [],
            "mock_html": "",
            "finalized": False,
        }
        _mock_gen._mock_finalise_draw(accumulated, entry, ds, None, None)
        return entry

    def test_a_clean_mock_records_an_empty_list(self, monkeypatch: Any) -> None:
        entry = self._finalise(_CLEAN_MOCK + "__DONE__", monkeypatch)
        assert entry["final_html"] == _CLEAN_MOCK
        assert entry["static_errors"] == []

    def test_a_truncated_mock_is_reported_not_silently_shipped(
        self, monkeypatch: Any
    ) -> None:
        entry = self._finalise(
            _CLEAN_MOCK + "__DONE__", monkeypatch, _MAX_HTML_BYTES=40
        )
        assert "output truncated" in entry["final_html"]
        assert any("cut off" in e for e in entry["static_errors"])

    def test_a_broken_script_is_reported(self, monkeypatch: Any) -> None:
        entry = self._finalise(
            _CLEAN_MOCK.replace("</script>", "") + "__DONE__", monkeypatch
        )
        assert any("<script>" in e for e in entry["static_errors"])


class TestDeliveryCarriesTheStaticErrors:
    _GEN_ID = "test-static-errors-gen"

    def teardown_method(self) -> None:
        _dmod()._MOCK_BUFFERS.pop(self._GEN_ID, None)

    def _deliver(self, static_errors: list[str] | None) -> Any:
        dmod = _dmod()
        dmod._MOCK_BUFFERS[self._GEN_ID] = {
            "done": True,
            "stop": threading.Event(),
            "text": _CLEAN_MOCK + "__DONE__",
            "final_html": _CLEAN_MOCK,
            "slowed": True,
            **({"static_errors": static_errors} if static_errors is not None else {}),
        }
        _, new_store, _, _ = dmod.on_mock_stream_poll(
            1, {"step": 5, "_gen_id": self._GEN_ID, "_mock_errors": ["stale"]}
        )
        return new_store

    def test_the_step6_store_lists_the_errors(self) -> None:
        assert self._deliver(["Doc is cut off."])["_mock_errors"] == ["Doc is cut off."]

    def test_a_clean_or_older_buffer_delivers_none_and_drops_stale_ones(
        self,
    ) -> None:
        assert self._deliver([])["_mock_errors"] == []
        assert self._deliver(None)["_mock_errors"] == []

    def test_a_new_draw_and_a_rearmed_page_start_clean(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        dmod = _dmod()
        monkeypatch.setattr(dmod.threading, "Thread", _NoThread)
        store, _, _ = dmod._start_gen(
            {"_mock_errors": ["old"]}, None, "m", "k", None, False
        )
        assert store["_mock_errors"] == []
        dmod._MOCK_BUFFERS.pop(store["_gen_id"], None)
        from spec4 import project_manager
        from spec4.session import default_session

        dmod._MOCK_BUFFERS[self._GEN_ID] = {
            "done": False,
            "stop": threading.Event(),
            "text": "",
            "design_dir": str(
                project_manager.get_version_dir(str(tmp_path), 1) / "design"
            ),
            "started": time.monotonic(),
        }
        session = {
            **default_session(),
            "phase": "designer",
            "working_dir": str(tmp_path),
            "phase_version": 1,
            "agent_llm_asked": {"designer": True},
        }
        rearmed, _, _, _ = dmod.on_mock_stream_watchdog(
            1, {"step": 6, "_mock_errors": ["old"]}, True, session
        )
        assert rearmed["_mock_errors"] == []


class TestFixErrorsButton:
    """One click, one refine draw with the errors quoted back; nothing else."""

    _STORE = {
        "step": 6,
        "preference_text": "warm palette",
        "screenshots": [],
        "refine_images": [],
        "mock_html": _CLEAN_MOCK,
        "finalized": False,
        "_mock_errors": ["Doc is cut off."],
    }
    _REPORTED = {"errors": [{"message": "x is not defined", "line": 12}], "ready": True}

    def _session(self) -> dict[str, Any]:
        from spec4.session import default_session

        return {
            **default_session(),
            "working_dir": None,
            "phase": "designer",
            "provider": "anthropic",
            "api_key": "k",
            "llm_config": {"model": "claude-sonnet-4-6", "api_key": "k"},
            "agent_llm_asked": {"designer": True},
        }

    def _click(self, store: Any, reported: Any, n: int | None = 1) -> Any:
        dmod = _dmod()
        with patch.object(
            dmod._refine, "_start_gen", return_value=({}, {}, False)
        ) as started:
            out = dmod.on_designer_fix_errors(n, reported, store, self._session(), True)
        return out, started

    def test_the_draw_refines_the_mock_on_screen_with_the_errors(self) -> None:
        out, started = self._click(self._STORE, self._REPORTED)
        assert out == ({}, {}, False)
        started.assert_called_once()
        updated = started.call_args.args[0]
        assert started.call_args.kwargs["existing_html"] == _CLEAN_MOCK
        pref = updated["preference_text"]
        assert pref.startswith("warm palette\n\n--- Fix render errors ---\n")
        assert "- Doc is cut off." in pref
        assert "- x is not defined (line 12)" in pref
        assert "return the whole corrected document" in pref

    def test_no_click_and_no_errors_draw_nothing(self) -> None:
        idle = (no_update, no_update, no_update)
        out, started = self._click(self._STORE, self._REPORTED, n=None)
        assert out == idle
        out, started = self._click({**self._STORE, "_mock_errors": []}, {"errors": []})
        assert out == idle
        out, started = self._click({**self._STORE, "_mock_errors": []}, None)
        assert out == idle
        assert not started.called
        # The pair: with an error from either side alone, the draw starts.
        _, started = self._click({**self._STORE, "_mock_errors": []}, self._REPORTED)
        assert started.called
        _, started = self._click(self._STORE, None)
        assert started.called

    def test_regenerate_and_fix_compose_the_same_draw(self) -> None:
        """The factoring: the two buttons differ only in the brief they add."""
        dmod = _dmod()
        store = {
            **self._STORE,
            "refine_images": [{"data": "img", "annotation": ""}],
            "screenshots": [{"data": "shot", "annotation": "a"}],
        }
        with patch.object(
            dmod._refine, "_start_gen", return_value=({}, {}, False)
        ) as regen:
            dmod.on_designer_regenerate(
                1, "tighter rows", ["note"], store, self._session(), True
            )
        with patch.object(
            dmod._refine, "_start_gen", return_value=({}, {}, False)
        ) as fix:
            dmod.on_designer_fix_errors(1, self._REPORTED, store, self._session(), True)
        r_store, f_store = regen.call_args.args[0], fix.call_args.args[0]
        assert regen.call_args.args[1:] == fix.call_args.args[1:]
        assert regen.call_args.kwargs == fix.call_args.kwargs
        assert (
            r_store["preference_text"]
            == "warm palette\n\n--- Refinement ---\ntighter rows"
        )
        assert f_store["preference_text"].startswith(
            "warm palette\n\n--- Fix render errors ---\n"
        )
        # The refine's image annotation was applied; the fix draw, started
        # from the preview, has no annotations to apply and keeps the images.
        assert r_store["screenshots"][-1] == {"data": "img", "annotation": "note"}
        assert f_store["screenshots"][-1] == {"data": "img", "annotation": ""}
        assert {
            k: v
            for k, v in r_store.items()
            if k not in ("preference_text", "screenshots")
        } == {
            k: v
            for k, v in f_store.items()
            if k not in ("preference_text", "screenshots")
        }


class TestPreviewRunsTheErrorShim:
    def test_the_shim_sits_inside_the_head(self) -> None:
        from spec4.layouts.designer import MOCK_ERROR_SHIM, with_error_shim

        doc = (
            "<!DOCTYPE html>\n<html lang='en'>\n<head>\n<title>t</title></head>"
            "<body></body></html>"
        )
        shimmed = with_error_shim(doc)
        assert shimmed.startswith(
            "<!DOCTYPE html>\n<html lang='en'>\n<head>" + MOCK_ERROR_SHIM
        )
        # On the same line as <head>, so the mock's own line numbers are unchanged.
        assert shimmed.count("\n") == doc.count("\n")
        assert with_error_shim("<html><body></body></html>").startswith(
            "<html>" + MOCK_ERROR_SHIM
        )
        assert with_error_shim("<p>x</p>") == MOCK_ERROR_SHIM + "<p>x</p>"

    def test_both_preview_steps_run_it_and_offer_the_hidden_fix_button(self) -> None:
        from spec4.layouts.designer import (
            MOCK_ERROR_SHIM,
            step6_content,
            step7_content,
        )

        store = {"step": 6, "mock_html": _CLEAN_MOCK, "finalized": False}
        for content in (step6_content(store), step7_content(store, True)):
            # The check row stands above the preview, not under it.
            ids = [getattr(child, "id", None) for child in content.children]
            assert (
                ids.index("mock-iframe")
                > [
                    i
                    for i, child in enumerate(content.children)
                    if "mock-check-status" in str(child)
                ][0]
            )
            frame = _component(content, "mock-iframe")
            assert MOCK_ERROR_SHIM in frame.srcDoc
            assert frame.srcDoc.replace(MOCK_ERROR_SHIM, "") == _CLEAN_MOCK
            assert frame.sandbox == "allow-scripts"
            status = _component(content, "mock-check-status")
            assert status.children == "Checking the preview…"
            # The disclaimer's register, and no verdict colour yet.
            assert status.className == "dim-line"
            assert "color" not in (status.style or {})
            assert (
                _component(content, "btn-designer-fix-errors").style["display"]
                == "none"
            )

    def test_static_errors_show_from_the_first_render(self) -> None:
        from spec4.layouts.designer import step6_content

        content = step6_content(
            {"step": 6, "mock_html": _CLEAN_MOCK, "_mock_errors": ["a", "b"]}
        )
        from spec4.layouts.designer import MOCK_CHECK_FAIL_COLOR

        status = _component(content, "mock-check-status")
        assert status.children == "2 errors in the document"
        assert status.style == {"color": MOCK_CHECK_FAIL_COLOR}
        assert _component(content, "btn-designer-fix-errors").style["display"] != "none"

    def test_the_saved_mock_carries_no_shim(self, tmp_path: Path) -> None:
        from spec4.callbacks.designer import _mock_gen
        from spec4.layouts.designer import MOCK_ERROR_SHIM

        entry: dict[str, Any] = {"text": _CLEAN_MOCK + "__DONE__"}
        ds = {
            "step": 5,
            "preference_text": "",
            "screenshots": [],
            "mock_html": "",
            "finalized": False,
        }
        _mock_gen._mock_finalise_draw(entry["text"], entry, ds, tmp_path, None)
        saved = (tmp_path / "mock.html").read_text()
        assert saved == _CLEAN_MOCK
        assert MOCK_ERROR_SHIM not in saved

    def test_the_page_paints_the_check_line_from_the_report_store(self) -> None:
        from dash._callback import GLOBAL_CALLBACK_LIST

        from spec4.app import app

        fed = [
            spec
            for spec in [*GLOBAL_CALLBACK_LIST, *app._callback_list]
            if any(dep["id"] == "mock-render-errors" for dep in spec["inputs"])
        ]
        assert [str(spec["output"]).split("@")[0] for spec in fed] == [
            "_designer-fs-dummy.children"
        ]
        from spec4.layouts.designer import MOCK_CHECK_FAIL_COLOR, MOCK_CHECK_OK_COLOR

        [painter] = [s for s in app._inline_scripts if "mock-check-status" in s]
        assert "Rendered cleanly" in painter
        # Green on success, red on failure: the theme's own variables.
        assert f"txt.style.color = '{MOCK_CHECK_OK_COLOR}'" in painter
        assert f"txt.style.color = '{MOCK_CHECK_FAIL_COLOR}'" in painter
        assert "btn-designer-fix-errors" in painter
        assert "_mock_errors" in painter
        # The click's callback reads the same store.
        [fix] = [
            spec
            for spec in GLOBAL_CALLBACK_LIST
            if any(dep["id"] == "btn-designer-fix-errors" for dep in spec["inputs"])
        ]
        assert "mock-render-errors" in [dep["id"] for dep in fix["state"]]

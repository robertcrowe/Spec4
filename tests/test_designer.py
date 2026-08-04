import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

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
            "vision_statement": {
                "vision": {"ui_surface": "CLI tool for batch jobs"}
            }
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
            str(p.get("text", "")) for p in normal[1]["content"]  # type: ignore[index]
            if isinstance(p, dict)
        )
        capture_combined = " ".join(
            str(p.get("text", "")) for p in capture[1]["content"]  # type: ignore[index]
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
        combined = " ".join(
            str(p.get("text", "")) for p in messages[1]["content"]
        )
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
        "spec4.agents.designer.litellm.completion",
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
            "spec4.agents.designer.litellm.completion",
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

        with patch(
            "spec4.agents.designer.litellm.completion", side_effect=fake_completion
        ):
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
            store_arg, wd, model, api_key, tavily_key, support,
            planning_context=None, **kwargs
        ):
            captured["pc"] = planning_context
            captured["kwargs"] = kwargs
            return {}, {}, False

        monkeypatch.setattr(dmod, "_start_gen", fake_start_gen)
        monkeypatch.setattr(dmod, "ctx", _Ctx("btn-designer-modify-existing"))
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

    def test_capture_mode_is_still_requested(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            _dmod().project_manager, "load_ai_features", lambda wd: None
        )
        monkeypatch.setattr(
            _dmod().project_manager, "load_feature_specs", lambda wd: None
        )
        out = self._run(monkeypatch, self._session(tmp_path))
        assert out["kwargs"]["capture_mode"] is True

    def test_planning_context_is_passed(
        self, tmp_path: Path, monkeypatch
    ) -> None:
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

    def test_disk_catalog_wins_over_session(
        self, tmp_path: Path, monkeypatch
    ) -> None:
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

        monkeypatch.setattr(dmod, "ctx", _Ctx("btn-designer-create-new"))
        out = dmod.on_designer_step2_choice(None, 1, {"step": 2}, {}, True)
        assert out[0]["step"] == 3


class _Ctx:
    def __init__(self, triggered_id: str) -> None:
        self.triggered_id = triggered_id


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
            store_arg, wd, model, api_key, tavily_key, support,
            planning_context=None, **kwargs
        ):
            captured["pc"] = planning_context
            captured["kwargs"] = kwargs
            return {}, {}, False

        monkeypatch.setattr(dmod, "_start_gen", fake_start_gen)
        monkeypatch.setattr(
            dmod.project_manager, "load_ai_features", lambda wd: None
        )
        monkeypatch.setattr(
            dmod.project_manager, "load_feature_specs", lambda wd: None
        )
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

    def test_create_new_clears_a_stale_capture_flag(self, monkeypatch) -> None:
        dmod = _dmod()
        monkeypatch.setattr(dmod, "ctx", _Ctx("btn-designer-create-new"))
        out = dmod.on_designer_step2_choice(
            None, 1, {"step": 2, "_capture_mode": True}, {}, True
        )
        assert out[0]["_capture_mode"] is False


class _NoThread:
    """Stand-in for threading.Thread that never runs the generation body."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def start(self) -> None:
        pass


class TestRefinePersistsManifest:
    """D-DM9: the manifest tracks the mock that ships, not just the first draw."""

    def test_persist_is_not_gated_on_the_draw_kind(self) -> None:
        """The save path calls _persist_manifest unconditionally now."""
        import inspect

        src = inspect.getsource(_dmod()._start_gen)
        assert "_persist_manifest(" in src
        assert "if existing_html is None:" not in src

    def test_missing_manifest_leaves_the_prior_file_untouched(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        design_dir = tmp_path / "design"
        design_dir.mkdir()
        prior = design_dir / "manifest.json"
        prior.write_text('{"screens": ["kept"]}')
        dmod._persist_manifest("<html>no manifest here</html>", None, design_dir)
        assert prior.read_text() == '{"screens": ["kept"]}'


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
            store_arg, wd, model, api_key, tavily_key, support,
            planning_context=None, **kwargs
        ):
            captured["pc"] = planning_context
            return {}, {}, False

        monkeypatch.setattr(dmod, "_start_gen", fake_start_gen)
        dmod.on_designer_regenerate(1, "AI features changed", store, session, True)
        return captured["pc"]

    def test_disk_ai_features_win_over_session(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from spec4.callbacks import designer as dmod

        disk_cat = {
            "ai_features": [
                {"name": "kept", "scope": "feature", "tier": "single_call"}
            ]
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
            "step": 7, "mock_html": "<html>old</html>", "preference_text": "",
            "screenshots": [], "refine_images": [],
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
        monkeypatch.setattr(
            dmod.project_manager, "load_ai_features", lambda wd: None
        )
        session = {
            "working_dir": str(tmp_path),
            "vision_statement": {"name": "App"},
            "ai_features": sess_cat,
        }
        store = {
            "step": 7, "mock_html": "x", "preference_text": "",
            "screenshots": [], "refine_images": [],
        }
        pc = self._run(monkeypatch, session, store)
        assert pc["ai_features"] is sess_cat

from spec4.agents._manifest import MANIFEST_START  # noqa: E402


class TestManifestInstruction:
    def test_greenfield_includes_manifest_directive(self) -> None:
        parts = build_mock_prompt(_session(), [], False)[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert MANIFEST_START in combined
        assert "design manifest" in combined.lower()

    def test_capture_includes_manifest_directive(self) -> None:
        parts = build_mock_prompt(
            _session(), ["<nav/>"], False, capture_mode=True
        )[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert MANIFEST_START in combined

    def test_refine_includes_manifest_directive(self) -> None:
        """D-DM9: refinements change the mock, so they must restate the
        manifest — it used to be written once and then frozen."""
        parts = build_mock_prompt(
            _session(), [], False, existing_html="<html></html>"
        )[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert MANIFEST_START in combined

    def test_refine_adds_the_restate_note(self) -> None:
        parts = build_mock_prompt(
            _session(), [], False, existing_html="<html></html>"
        )[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "re-state the manifest for the updated mock" in combined.lower()
        assert "not a diff" in combined

    def test_refine_note_covers_purely_visual_changes(self) -> None:
        parts = build_mock_prompt(
            _session(), [], False, existing_html="<html></html>"
        )[1]["content"]
        combined = " ".join(str(p.get("text", "")) for p in parts)
        assert "re-state it anyway" in combined

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
        parts = build_mock_prompt(
            _session(), ["<nav/>"], False, capture_mode=True
        )[1]["content"]
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
# on_mock_stream_poll — acknowledgement-based completion delivery
# ---------------------------------------------------------------------------


class TestMockDeliveryAck:
    """The completion payload is re-delivered until the browser's own poll
    request — its designer-session-store State — proves the store moved off
    step 5. The previous fixed re-delivery window counted requests sent, not
    deliveries applied, and could expire before the first response ever
    reached the browser, stranding the UI at step 5 with the interval off.
    """

    _GEN_ID = "test-ack-gen"
    _HTML = "<!DOCTYPE html><html><body>ok</body></html>"

    def _buffer(self) -> Any:
        dmod = _dmod()
        dmod._MOCK_BUFFERS[self._GEN_ID] = {
            "done": True,
            "stop": threading.Event(),
            "text": "",
            "final_html": self._HTML,
        }
        return dmod

    def teardown_method(self) -> None:
        _dmod()._MOCK_BUFFERS.pop(self._GEN_ID, None)

    def test_delivers_step6_payload_while_store_is_at_step_5(self) -> None:
        from dash import no_update

        dmod = self._buffer()
        buf, new_store, disabled = dmod.on_mock_stream_poll(
            1, {"step": 5, "_gen_id": self._GEN_ID}
        )
        assert new_store["step"] == 6
        assert new_store["mock_html"] == self._HTML
        assert buf["progress"] == 100
        # Keep polling until the browser acknowledges; the buffer must
        # survive so a dropped response can be re-delivered.
        assert disabled is no_update
        assert self._GEN_ID in dmod._MOCK_BUFFERS

    def test_redelivers_far_beyond_the_old_fixed_window(self) -> None:
        dmod = self._buffer()
        new_store: Any = None
        for _ in range(20):
            _, new_store, _ = dmod.on_mock_stream_poll(
                1, {"step": 5, "_gen_id": self._GEN_ID}
            )
        assert new_store["step"] == 6
        assert new_store["mock_html"] == self._HTML
        assert self._GEN_ID in dmod._MOCK_BUFFERS

    def test_ack_pops_buffer_and_disables_interval(self) -> None:
        from dash import no_update

        dmod = self._buffer()
        dmod.on_mock_stream_poll(1, {"step": 5, "_gen_id": self._GEN_ID})
        buf, new_store, disabled = dmod.on_mock_stream_poll(
            1, {"step": 6, "_gen_id": self._GEN_ID}
        )
        assert new_store is no_update
        assert disabled is True
        assert buf["progress"] == 100
        assert self._GEN_ID not in dmod._MOCK_BUFFERS

    def test_refine_click_between_ticks_is_not_bounced_back(self) -> None:
        from dash import no_update

        dmod = self._buffer()
        _, new_store, disabled = dmod.on_mock_stream_poll(
            1, {"step": 7, "_gen_id": self._GEN_ID}
        )
        assert new_store is no_update
        assert disabled is True

    def test_runaway_valve_reports_the_saved_mock(self) -> None:
        dmod = self._buffer()
        dmod._MOCK_BUFFERS[self._GEN_ID]["delivered"] = dmod._MAX_DELIVERY_TICKS
        buf, new_store, disabled = dmod.on_mock_stream_poll(
            1, {"step": 5, "_gen_id": self._GEN_ID}
        )
        assert "Refresh the page" in buf["error"]
        assert disabled is True
        assert self._GEN_ID not in dmod._MOCK_BUFFERS


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

    def _implement_prior(
        self, tmp_path: Path, with_manifest: bool = True
    ) -> None:
        from spec4 import project_manager

        design_dir = project_manager.get_version_dir(str(tmp_path), 0) / "design"
        design_dir.mkdir(parents=True, exist_ok=True)
        (design_dir / "mock.html").write_text(self._MOCK, encoding="utf-8")
        if with_manifest:
            (design_dir / "manifest.json").write_text(
                self._MANIFEST, encoding="utf-8"
            )
        project_manager.get_version_dir(str(tmp_path), 0).joinpath(
            "IMPLEMENTED"
        ).write_text("")

    def test_default_without_working_dir(self) -> None:
        dmod = _dmod()
        assert dmod._expected_stream_chars(None) == dmod._DEFAULT_EXPECTED_CHARS

    def test_default_when_no_prior_mock(self, tmp_path: Path) -> None:
        dmod = _dmod()
        expected = dmod._expected_stream_chars(str(tmp_path))
        assert expected == dmod._DEFAULT_EXPECTED_CHARS

    def test_sized_from_prior_mock_and_manifest_plus_ten_percent(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        self._implement_prior(tmp_path)
        expected = dmod._expected_stream_chars(str(tmp_path))
        assert expected == int((len(self._MOCK) + len(self._MANIFEST)) * 1.1)

    def test_sized_from_mock_alone_when_manifest_missing(
        self, tmp_path: Path
    ) -> None:
        dmod = _dmod()
        self._implement_prior(tmp_path, with_manifest=False)
        expected = dmod._expected_stream_chars(str(tmp_path))
        assert expected == int(len(self._MOCK) * 1.1)

    def test_start_gen_stashes_expected_chars_in_buffer(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        dmod = _dmod()
        self._implement_prior(tmp_path)
        monkeypatch.setattr(
            dmod, "generate_mock_streaming", lambda *a, **kw: iter(())
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
            buf, _, _ = dmod.on_mock_stream_poll(
                1, {"step": 5, "_gen_id": gen_id}
            )
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
            buf, _, _ = dmod.on_mock_stream_poll(
                1, {"step": 5, "_gen_id": gen_id}
            )
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

        monkeypatch.setattr(dmod, "generate_mock_streaming", boom)
        store, _, _ = dmod._start_gen({}, None, "m", "key", None, False)
        gen_id = store["_gen_id"]
        try:
            entry = self._wait_done(dmod, gen_id)
            assert "__GENERATION_ERROR__: RuntimeError" in entry["text"]
            assert entry["done"] is True
            # The poll turns the sentinel into the error alert + Retry button.
            buf, _, disabled = dmod.on_mock_stream_poll(
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

        monkeypatch.setattr(dmod, "generate_mock_streaming", fake_stream)
        monkeypatch.setattr(
            dmod.project_manager, "active_version", raise_oserror
        )
        store, _, _ = dmod._start_gen(
            {}, str(tmp_path), "m", "key", None, False
        )
        gen_id = store["_gen_id"]
        try:
            entry = self._wait_done(dmod, gen_id)
            # Persistence failed, but delivery must still happen.
            assert entry.get("final_html") == html
            assert "__GENERATION_ERROR__" not in entry["text"]
            _, new_store, _ = dmod.on_mock_stream_poll(
                1, {"step": 5, "_gen_id": gen_id}
            )
            assert new_store["step"] == 6
            assert new_store["mock_html"] == html
        finally:
            dmod._MOCK_BUFFERS.pop(gen_id, None)
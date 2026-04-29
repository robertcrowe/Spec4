import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from spec4.agents.designer import (
    DesignerSession,
    build_mock_prompt,
    clear_session,
    collect_ui_source_files,
    detect_greenfield,
    detect_no_ui,
    generate_mock_streaming,
    load_session,
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


# ---------------------------------------------------------------------------
# detect_greenfield
# ---------------------------------------------------------------------------


class TestDetectGreenfield:
    def test_true_when_only_spec4_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".spec4").mkdir()
        assert detect_greenfield(tmp_path) is True

    def test_false_when_other_files_exist(self, tmp_path: Path) -> None:
        (tmp_path / ".spec4").mkdir()
        (tmp_path / "main.py").write_text("x = 1")
        assert detect_greenfield(tmp_path) is False

    def test_false_when_empty_directory(self, tmp_path: Path) -> None:
        assert detect_greenfield(tmp_path) is False

    def test_false_when_only_non_spec4_dir(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        assert detect_greenfield(tmp_path) is False


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

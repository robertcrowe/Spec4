"""The chat-input keydown asset: Shift+Enter = line break, Enter = submit.

The behavior itself is browser-side; these guards pin the load-bearing pieces
of the script so a refactor can't silently drop them.
"""

from pathlib import Path

ASSET = (
    Path(__file__).parent.parent / "src" / "spec4" / "assets" / "chat_input.js"
)


class TestChatInputAsset:
    def test_asset_exists_where_dash_serves_it(self) -> None:
        assert ASSET.is_file()

    def test_targets_only_the_chat_input(self) -> None:
        src = ASSET.read_text()
        assert '"chat-input"' in src

    def test_shift_enter_stops_propagation_without_preventing_the_newline(
        self,
    ) -> None:
        src = ASSET.read_text()
        assert "event.shiftKey" in src
        assert "stopPropagation" in src
        # The Shift branch must NOT preventDefault — that is what lets the
        # browser insert the line break.
        shift_branch = src.split("event.shiftKey")[1].split("else")[0]
        assert "preventDefault" not in shift_branch

    def test_plain_enter_prevents_the_stray_newline(self) -> None:
        src = ASSET.read_text()
        assert "preventDefault" in src

    def test_listener_runs_in_the_capture_phase(self) -> None:
        # Must fire before React's delegated listener at the app root; a
        # bubble-phase listener on document would run after it.
        src = ASSET.read_text()
        assert src.rstrip().rstrip(";").endswith("true\n)")

    def test_ime_composition_enter_is_ignored(self) -> None:
        src = ASSET.read_text()
        assert "isComposing" in src

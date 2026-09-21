"""The mock-preview error collector asset (``assets/mock_errors.js``).

The behaviour is browser-side (``tests/integration/test_mock_check_e2e.py``
exercises it); these guards pin the pieces the Python side depends on so a
refactor can't silently drop one.
"""

from pathlib import Path

ASSET = Path(__file__).parent.parent / "src" / "spec4" / "assets" / "mock_errors.js"


class TestMockErrorsAsset:
    def test_asset_exists_where_dash_serves_it(self) -> None:
        assert ASSET.is_file()

    def test_it_writes_the_store_the_fix_button_reads(self) -> None:
        src = ASSET.read_text()
        assert 'set_props("mock-render-errors"' in src
        assert "errors:" in src
        assert "ready:" in src

    def test_it_understands_the_shims_three_messages(self) -> None:
        from spec4.layouts.designer import MOCK_ERROR_SHIM

        src = ASSET.read_text()
        for kind in ("mock-loaded", "mock-error", "mock-ready"):
            assert f'"{kind}"' in src
            assert f'"{kind}"' in MOCK_ERROR_SHIM

    def test_only_the_preview_frame_is_listened_to(self) -> None:
        src = ASSET.read_text()
        assert 'getElementById("mock-iframe")' in src
        assert "event.source !== frame.contentWindow" in src

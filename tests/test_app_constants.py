from spec4.app_constants import DARK_THEME, GOOGLE_FONTS, PATH_TO_PHASE


class TestPathToPhase:
    def test_root_maps_to_landing(self) -> None:
        assert PATH_TO_PHASE["/"] == "landing"

    def test_dir_maps_to_working_dir(self) -> None:
        assert PATH_TO_PHASE["/dir"] == "working_dir"

    def test_setup_maps_to_setup(self) -> None:
        assert PATH_TO_PHASE["/setup"] == "setup"

    def test_agents_maps_to_agent_select(self) -> None:
        assert PATH_TO_PHASE["/agents"] == "agent_select"

    def test_chat_maps_to_chat(self) -> None:
        assert PATH_TO_PHASE["/chat"] == "chat"

    def test_all_phases_covered(self) -> None:
        expected = {"landing", "working_dir", "setup", "agent_select", "chat", "done"}
        assert set(PATH_TO_PHASE.values()) == expected


class TestDarkTheme:
    def test_primary_color_is_blue(self) -> None:
        assert DARK_THEME["primaryColor"] == "blue"

    def test_has_dark_palette(self) -> None:
        assert "dark" in DARK_THEME["colors"]

    def test_has_blue_palette(self) -> None:
        assert "blue" in DARK_THEME["colors"]

    def test_dark_palette_has_ten_shades(self) -> None:
        assert len(DARK_THEME["colors"]["dark"]) == 10

    def test_blue_palette_has_ten_shades(self) -> None:
        assert len(DARK_THEME["colors"]["blue"]) == 10

    def test_font_family_includes_inter(self) -> None:
        assert "Inter" in DARK_THEME["fontFamily"]

    def test_monospace_font_includes_jetbrains(self) -> None:
        assert "JetBrains Mono" in DARK_THEME["fontFamilyMonospace"]


class TestGoogleFonts:
    def test_is_https_url(self) -> None:
        assert GOOGLE_FONTS.startswith("https://")

    def test_references_googleapis(self) -> None:
        assert "fonts.googleapis.com" in GOOGLE_FONTS

    def test_includes_inter(self) -> None:
        assert "Inter" in GOOGLE_FONTS

    def test_includes_jetbrains_mono(self) -> None:
        assert "JetBrains+Mono" in GOOGLE_FONTS

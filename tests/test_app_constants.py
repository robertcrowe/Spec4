from spec4.app_constants import DARK_THEME, GOOGLE_FONTS, PATH_TO_PHASE


class TestPathToPhase:
    def test_root_maps_to_landing(self):
        assert PATH_TO_PHASE["/"] == "landing"

    def test_dir_maps_to_working_dir(self):
        assert PATH_TO_PHASE["/dir"] == "working_dir"

    def test_setup_maps_to_setup(self):
        assert PATH_TO_PHASE["/setup"] == "setup"

    def test_agents_maps_to_agent_select(self):
        assert PATH_TO_PHASE["/agents"] == "agent_select"

    def test_chat_maps_to_chat(self):
        assert PATH_TO_PHASE["/chat"] == "chat"

    def test_all_five_phases_covered(self):
        expected = {"landing", "working_dir", "setup", "agent_select", "chat"}
        assert set(PATH_TO_PHASE.values()) == expected


class TestDarkTheme:
    def test_primary_color_is_blue(self):
        assert DARK_THEME["primaryColor"] == "blue"

    def test_has_dark_palette(self):
        assert "dark" in DARK_THEME["colors"]

    def test_has_blue_palette(self):
        assert "blue" in DARK_THEME["colors"]

    def test_dark_palette_has_ten_shades(self):
        assert len(DARK_THEME["colors"]["dark"]) == 10

    def test_blue_palette_has_ten_shades(self):
        assert len(DARK_THEME["colors"]["blue"]) == 10

    def test_font_family_includes_inter(self):
        assert "Inter" in DARK_THEME["fontFamily"]

    def test_monospace_font_includes_jetbrains(self):
        assert "JetBrains Mono" in DARK_THEME["fontFamilyMonospace"]


class TestGoogleFonts:
    def test_is_https_url(self):
        assert GOOGLE_FONTS.startswith("https://")

    def test_references_googleapis(self):
        assert "fonts.googleapis.com" in GOOGLE_FONTS

    def test_includes_inter(self):
        assert "Inter" in GOOGLE_FONTS

    def test_includes_jetbrains_mono(self):
        assert "JetBrains+Mono" in GOOGLE_FONTS

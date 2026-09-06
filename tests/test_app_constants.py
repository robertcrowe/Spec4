from spec4.app_constants import (
    DARK_THEME,
    GOOGLE_FONTS,
    PATH_TO_PHASE,
    PHASE_DIRECTORY_PICKER,
    PHASE_PROJECT_VIEW,
    PHASE_ROOT,
    ROOT_PATH,
    SPEC4_GREEN,
)


class TestPathToPhase:
    def test_the_root_has_no_fixed_phase(self) -> None:
        """The root is resolved by the router, not looked up in the table.

        An entry here would give it a destination decided before the
        remembered directory is known — which is exactly the landing page
        this round retired.
        """
        assert ROOT_PATH == "/"
        assert ROOT_PATH not in PATH_TO_PHASE

    def test_dir_maps_to_working_dir(self) -> None:
        assert PATH_TO_PHASE["/dir"] == "working_dir"

    def test_setup_maps_to_setup(self) -> None:
        assert PATH_TO_PHASE["/setup"] == "setup"

    def test_agents_maps_to_agent_select(self) -> None:
        assert PATH_TO_PHASE["/agents"] == "agent_select"

    def test_chat_maps_to_chat(self) -> None:
        assert PATH_TO_PHASE["/chat"] == "chat"

    def test_all_phases_covered(self) -> None:
        expected = {
            "working_dir",
            "setup",
            "agent_select",
            "chat",
            "designer",
        }
        assert set(PATH_TO_PHASE.values()) == expected

    def test_no_phase_is_named_landing(self) -> None:
        assert "landing" not in set(PATH_TO_PHASE.values())


class TestRootDestinations:
    """The root resolves to one of two phases, and to nothing else."""

    def test_the_project_view_is_a_routable_phase(self) -> None:
        assert PATH_TO_PHASE["/agents"] == PHASE_PROJECT_VIEW

    def test_the_directory_picker_is_a_routable_phase(self) -> None:
        assert PATH_TO_PHASE["/dir"] == PHASE_DIRECTORY_PICKER

    def test_the_unresolved_phase_renders_nothing(self) -> None:
        """``PHASE_ROOT`` is not a screen — no path may map to it."""
        assert PHASE_ROOT not in set(PATH_TO_PHASE.values())


class TestDarkTheme:
    def test_primary_color_is_the_registered_accent(self) -> None:
        """D-LR2: the accent is named once, here, and inherited everywhere."""
        assert DARK_THEME["primaryColor"] == "spec4-green"

    def test_the_primary_color_is_a_key_of_theme_colors(self) -> None:
        """Mantine resolves ``primaryColor`` as a key of ``theme.colors``.

        Handing it a raw hex value instead throws while the theme is merged,
        which surfaces as a blank page rather than a readable error — so the
        registration is asserted rather than eyeballed.
        """
        assert DARK_THEME["primaryColor"] in DARK_THEME["colors"]

    def test_accent_palette_has_ten_shades(self) -> None:
        assert len(DARK_THEME["colors"]["spec4-green"]) == 10

    def test_the_dark_scheme_renders_the_accent_exactly(self) -> None:
        """``primaryShade`` picks which shade actually draws in dark mode."""
        shade = DARK_THEME["primaryShade"]["dark"]
        assert DARK_THEME["colors"]["spec4-green"][shade] == SPEC4_GREEN
        assert SPEC4_GREEN == "#39FF14"

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

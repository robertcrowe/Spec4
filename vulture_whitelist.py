"""Vulture whitelist for decorator-registered Dash callbacks.

Every function below is registered with Dash via ``@app.callback`` /
``@callback`` and is invoked by the Dash dispatcher, never by name from
Python, so vulture reports it as unused. This file is not imported by the
application; it exists only so that

    uvx vulture src/ tests/ vulture_whitelist.py --min-confidence 60

is quiet about callbacks and only surfaces real candidates. Regenerate it
when callbacks are added or renamed (see CLEANUP_INVENTORY.md, Dead code).

Generated for the Phase 0 baseline of SPEC4_CLEANUP_PLAN.md.
"""

# ruff: noqa
# mypy: ignore-errors


# src/spec4/app.py
render_page
on_version_check

# src/spec4/callbacks/__init__.py
on_status_bar
on_status_bar_dir
on_status_bar_setup
on_round_tree
on_round_tree_line
on_artifact_round
on_artifact_pane
on_artifact_download
on_round_cost
on_browser_navigate
on_dir_select
on_dir_up
on_dir_path_enter
on_subdir_click
on_create_folder
on_provider_hint
on_setup_connect
on_setup_clear
on_setup_back_provider
on_setup_effort_options
on_setup_model_continue
on_setup_back_model
on_search_provider_hint
on_setup_search_connect
on_setup_search_skip
on_init_turn
on_chat_submit
on_fast_forward
on_gate_provider_change
on_gate_effort_options
on_gate_use_default
on_gate_keep
on_gate_pick
on_gate_chip
on_chat_retry_model
on_gate_back
on_gate_connect
on_gate_continue
on_chat_retry
on_ff_info
on_breadth_submit
on_breadth_try_again
on_breadth_change
on_stream_poll
on_agent_pill_click
on_project_mode_choice
on_rescan_project
on_review_to_brainstormer
on_brainstormer_to_designer
on_brainstormer_to_agentifier
on_agentifier_to_designer
on_stack_to_phaser
dl_vision
dl_stack
dl_code_review
dl_features
dl_phases
on_phaser_to_deployer
on_deployer_new_project
dl_deployment

# src/spec4/callbacks/designer.py
render_designer_step
on_designer_add_gui
on_designer_skip_1
on_designer_skip_2
on_designer_step2_choice
on_designer_carry_forward
on_designer_preferences_next
on_designer_screenshot_upload
on_designer_screenshot_delete
on_designer_generate_mock
on_mock_stream_poll
on_designer_approve
on_designer_continue_stack
on_designer_step_back
on_designer_start_over
on_designer_refine
on_designer_refine_cancel
on_designer_refine_upload
on_designer_refine_image_delete
on_designer_regenerate
on_designer_revise_stale
on_designer_retry_model
on_designer_retry
on_designer_auto_retry

# Dash app attributes set in src/spec4/app.py that vulture reports as unused
# attributes; they are read by Dash itself.
_.suppress_debug_info
_.index_string

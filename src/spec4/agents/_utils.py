"""Compatibility facade over the four modules Phase 4a split this file into.

The helpers that used to live here now live in siblings, one per concern:

* ``_turn_flow`` -- conversation-history surgery for the shared turn loop.
* ``_reask`` -- the artifact re-ask protocol and the stream wrappers.
* ``_feature_context`` -- feature / AI-feature seed blocks per consumer.
* ``_stack_context`` -- stack, phase, NFR and manifest digests, plus the
  style renderers.

Nothing is defined here. The split kept every import path working: the new
modules use public names, and this module re-exports each one under both that
name and the underscore alias it had before, so no importer in ``src/``,
``tests/``, ``evals/`` or ``scripts/`` changed when the code moved. Sub-phase
4j retires the aliases and moves importers onto the public names; until then,
import from here or from the owning module -- both resolve to the same object.

``__all__`` is load-bearing rather than decorative: ``[tool.mypy] strict``
implies ``no_implicit_reexport``, so without it a re-exported name could not be
imported from this module at all.
"""

from __future__ import annotations

from spec4.agents._feature_context import (
    TIER_ORDER_FOR_SUMMARY,
    VISION_FRAMING_FIELDS,
    ai_features_for_deployer,
    ai_features_for_designer,
    ai_features_for_phaser,
    ai_features_for_stack,
    ai_served_feature_ids,
    designer_affordance_hints,
    excluded_feature_ids,
    explicitly_rejected_lines,
    feature_relationship_lines,
    feature_specs_for_designer,
    feature_specs_for_phaser,
    feature_specs_for_stack,
    project_feature_for_stack,
    served_product_feature_ids,
    short_text,
    slim_vision_framing,
    slug,
)
from spec4.agents._reask import (
    DEV_MODE,
    abandon_reask,
    artifact_fallback,
    artifact_reask_prompt,
    artifact_reask_status,
    drain_stream,
    reask_for_artifact,
    set_status,
    stream_counting,
    stream_suppressing_json,
    suppressed_as_artifact,
)
from spec4.agents._stack_context import (
    STYLE_LEAF_KEYS,
    design_manifest_for_stack,
    load_design_manifest,
    manifest_for_phaser,
    nfr_goals_for_deployer,
    phases_for_deployer,
    render_coding_style,
    render_one_style,
    render_references,
    stack_digest_for_phaser,
    stack_for_deployer,
)
from spec4.agents._turn_flow import (
    AGENT_DELIVERABLE,
    build_revision_context,
    drop_orphan_or_route_to_fresh_start,
    drop_orphan_trailing_user,
    extract_json_block,
    last_assistant_text,
    maybe_inject_resume_summary,
    maybe_inject_staleness_question,
    replay_last_assistant,
    stale_phrase,
)

# Pre-4a spellings. Every name this module exported before the split, bound
# to the object the owning module now defines. Retired in 4j.
_AGENT_DELIVERABLE = AGENT_DELIVERABLE
_DEV_MODE = DEV_MODE
_STYLE_LEAF_KEYS = STYLE_LEAF_KEYS
_TIER_ORDER_FOR_SUMMARY = TIER_ORDER_FOR_SUMMARY
_VISION_FRAMING_FIELDS = VISION_FRAMING_FIELDS
_abandon_reask = abandon_reask
_ai_features_for_deployer = ai_features_for_deployer
_ai_features_for_designer = ai_features_for_designer
_ai_features_for_phaser = ai_features_for_phaser
_ai_features_for_stack = ai_features_for_stack
_ai_served_feature_ids = ai_served_feature_ids
_artifact_fallback = artifact_fallback
_artifact_reask_prompt = artifact_reask_prompt
_artifact_reask_status = artifact_reask_status
_build_revision_context = build_revision_context
_design_manifest_for_stack = design_manifest_for_stack
_designer_affordance_hints = designer_affordance_hints
_drain_stream = drain_stream
_drop_orphan_or_route_to_fresh_start = drop_orphan_or_route_to_fresh_start
_drop_orphan_trailing_user = drop_orphan_trailing_user
_explicitly_rejected_lines = explicitly_rejected_lines
_extract_json_block = extract_json_block
_feature_relationship_lines = feature_relationship_lines
_feature_specs_for_designer = feature_specs_for_designer
_feature_specs_for_phaser = feature_specs_for_phaser
_feature_specs_for_stack = feature_specs_for_stack
_last_assistant_text = last_assistant_text
_load_design_manifest = load_design_manifest
_manifest_for_phaser = manifest_for_phaser
_maybe_inject_resume_summary = maybe_inject_resume_summary
_maybe_inject_staleness_question = maybe_inject_staleness_question
_nfr_goals_for_deployer = nfr_goals_for_deployer
_phases_for_deployer = phases_for_deployer
_project_feature_for_stack = project_feature_for_stack
_reask_for_artifact = reask_for_artifact
_render_coding_style = render_coding_style
_render_one_style = render_one_style
_render_references = render_references
_replay_last_assistant = replay_last_assistant
_served_product_feature_ids = served_product_feature_ids
_set_status = set_status
_short_text = short_text
_slim_vision_framing = slim_vision_framing
_stack_digest_for_phaser = stack_digest_for_phaser
_stack_for_deployer = stack_for_deployer
_stale_phrase = stale_phrase
_stream_counting = stream_counting
_stream_suppressing_json = stream_suppressing_json
_suppressed_as_artifact = suppressed_as_artifact

__all__ = [
    "AGENT_DELIVERABLE",
    "DEV_MODE",
    "STYLE_LEAF_KEYS",
    "TIER_ORDER_FOR_SUMMARY",
    "VISION_FRAMING_FIELDS",
    "_AGENT_DELIVERABLE",
    "_DEV_MODE",
    "_STYLE_LEAF_KEYS",
    "_TIER_ORDER_FOR_SUMMARY",
    "_VISION_FRAMING_FIELDS",
    "_abandon_reask",
    "_ai_features_for_deployer",
    "_ai_features_for_designer",
    "_ai_features_for_phaser",
    "_ai_features_for_stack",
    "_ai_served_feature_ids",
    "_artifact_fallback",
    "_artifact_reask_prompt",
    "_artifact_reask_status",
    "_build_revision_context",
    "_design_manifest_for_stack",
    "_designer_affordance_hints",
    "_drain_stream",
    "_drop_orphan_or_route_to_fresh_start",
    "_drop_orphan_trailing_user",
    "_explicitly_rejected_lines",
    "_extract_json_block",
    "_feature_relationship_lines",
    "_feature_specs_for_designer",
    "_feature_specs_for_phaser",
    "_feature_specs_for_stack",
    "_last_assistant_text",
    "_load_design_manifest",
    "_manifest_for_phaser",
    "_maybe_inject_resume_summary",
    "_maybe_inject_staleness_question",
    "_nfr_goals_for_deployer",
    "_phases_for_deployer",
    "_project_feature_for_stack",
    "_reask_for_artifact",
    "_render_coding_style",
    "_render_one_style",
    "_render_references",
    "_replay_last_assistant",
    "_served_product_feature_ids",
    "_set_status",
    "_short_text",
    "_slim_vision_framing",
    "_stack_digest_for_phaser",
    "_stack_for_deployer",
    "_stale_phrase",
    "_stream_counting",
    "_stream_suppressing_json",
    "_suppressed_as_artifact",
    "abandon_reask",
    "ai_features_for_deployer",
    "ai_features_for_designer",
    "ai_features_for_phaser",
    "ai_features_for_stack",
    "ai_served_feature_ids",
    "artifact_fallback",
    "artifact_reask_prompt",
    "artifact_reask_status",
    "build_revision_context",
    "design_manifest_for_stack",
    "designer_affordance_hints",
    "drain_stream",
    "drop_orphan_or_route_to_fresh_start",
    "drop_orphan_trailing_user",
    "excluded_feature_ids",
    "explicitly_rejected_lines",
    "extract_json_block",
    "feature_relationship_lines",
    "feature_specs_for_designer",
    "feature_specs_for_phaser",
    "feature_specs_for_stack",
    "last_assistant_text",
    "load_design_manifest",
    "manifest_for_phaser",
    "maybe_inject_resume_summary",
    "maybe_inject_staleness_question",
    "nfr_goals_for_deployer",
    "phases_for_deployer",
    "project_feature_for_stack",
    "reask_for_artifact",
    "render_coding_style",
    "render_one_style",
    "render_references",
    "replay_last_assistant",
    "served_product_feature_ids",
    "set_status",
    "short_text",
    "slim_vision_framing",
    "slug",
    "stack_digest_for_phaser",
    "stack_for_deployer",
    "stale_phrase",
    "stream_counting",
    "stream_suppressing_json",
    "suppressed_as_artifact",
]

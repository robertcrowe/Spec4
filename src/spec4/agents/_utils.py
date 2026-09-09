"""Retired facade. The helpers that used to live here live in four siblings.

Phase 4a split this module by concern and left a compatibility layer behind so
that no importer had to change while the code was moving; Phase 4j moved every
importer onto the owning module and removed that layer. Nothing is defined,
imported or re-exported here any more:

* ``_turn_flow`` -- conversation-history surgery for the shared turn loop.
* ``_reask`` -- the artifact re-ask protocol and the stream wrappers.
* ``_feature_context`` -- feature / AI-feature seed blocks per consumer,
  including ``slug``.
* ``_stack_context`` -- stack, phase, NFR and manifest digests, plus the
  style renderers.

The file is kept only so that 4j is an import-only change: deleting a module is
a Phase 2-style removal, logged in ``CLEANUP_INVENTORY.md`` §25 rather than done
here.
"""

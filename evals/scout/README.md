# Tier-coverage vision suite (Scout diagnostic)

Nine product visions, one per tier. Each describes an honest product whose
*natural* central architecture sits at the target tier. The tier is never named
and the architecture is never prescribed in the vision text — Scout must
surface it (or fail to).

## How to use

1. `uv run python evals/run_scout_probe.py --runs 3` — dump Scout's raw
   candidates for every vision. Read: does the central candidate below appear, and
   is it described so the Analyst could tier it at the target (esp. tiers 5—9,
   where the loop/coordination is the capability)?
2. Hand-label the surfaced candidates into a tier fixture and run
   `run_tier_eval.py --show-rationale` to see where each lands.

## The hypothesis this suite tests

Per the D1 finding, the failure is expected to be tier-dependent: the low tiers
(deterministic—rag) should surface cleanly as single candidates, while the
agent tiers (tool_agent and up) get shredded into lower-tier pieces or
de-agentified — no candidate ever represents the coordinating whole. This
suite is meant to locate exactly where on the ladder that break begins.

## Briefs

| # | file | target tier | central candidate to look for |
|---|------|-------------|-------------------------------|
| 01 | `01_deterministic_farebox.json` | `deterministic` | fare calculation |
| 02 | `02_embeddings_shelf.json` | `embeddings` | meaning-based search over saved items |
| 03 | `03_single_call_threadline.json` | `single_call` | email-thread summary |
| 04 | `04_rag_handbook.json` | `rag` | policy question answering with citations |
| 05 | `05_tool_agent_orderly.json` | `tool_agent` | conversational order-help assistant |
| 06 | `06_chained_calls_clipwright.json` | `chained_calls` | recording-to-article production |
| 07 | `07_planning_agent_digger.json` | `planning_agent` | open-ended data investigation |
| 08 | `08_orchestrated_subagents_decksmith.json` | `orchestrated_subagents` | coordinated pitch-deck build |
| 09 | `09_multi_agent_collaboration_haggle.json` | `multi_agent_collaboration` | cross-owner represented negotiation |

## Note on neutrality

Each vision describes a product and what it does for users, not an architecture.
No vision says 'agent', 'pipeline', 'retrieval', or names a tier. The target tier
is an emergent property of the honest product, so a correct Agentifier should reach
it on its own — the same discipline used for the tier-eval fixtures.
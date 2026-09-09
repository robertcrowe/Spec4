### Feature 1/3: `smart_search` — tier: **agentic**

**Purpose:** Answer policy questions with citations.

**Invocation:**
- user asks in chat
- nightly digest

**Inputs:**
- name: question, type: text
- name: policy_set, type: ids

**Outputs:** answer with citations

**Decision authority:**
- autonomous: cite
- escalates: refuse

**Success criteria:**
- citation resolves
- answer under 200 words

**Eval approach:**
- offline: golden set
- online: thumbs; latency

**Budgets:**
- cost_usd_per_call: 0.02
- latency_p95_s: 4

**Privacy / safety:** Redact PII before the call.

**Knowledge sources:**
- policy library
- glossary

**Tool access:**
- tool: search_policies, scope: read

**Topology:** single agent with retrieval tool

**Mechanisms:**
- **RAG**: grounding
- reranking

**References:**
- https://example.com/rag

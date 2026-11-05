---
name: graph-retrieval
description: Retrieve grounded wiki context using semantic search plus explicit entity linking and bounded typed graph traversal. Use for knowledge lookup, relational evidence, exceptions and conflicts during gathering or specification work. Does not build indexes, infer requirement confirmation, or execute arbitrary graph queries.
---

# Graph retrieval

Run from the repository root:

```bash
python3 scripts/graph_retrieval.py "<question>" --top 5 --max-hops 2 --direction both --relation-type EXCEPTION_TO --relation-type CONTRADICTS
```

The deterministic implementation is `scripts/graph_retrieval.py`; existing embeddings/index
remain authoritative for the first stage. Paths come from `knowledge-config.json`.
Use `scripts/cag_context.py` when the caller needs existing FR-011 consultation/log fields.

Inspect `semantic_status` separately from `graph_status`. Missing index is not no match;
runtime errors are not absence of knowledge. Missing/invalid/stale graph means explicit
semantic fallback. Never rebuild in a lookup. Cite note title/path, and for each relationship
its evidence document/section, edge ID, status and path. Only the packed `context` contains
budgeted evidence; do not expand it by reading source files or dumping a whole graph.

Keep direct notes first. Inferred relations remain hypotheses; disputed relations remain
conflicts. Model confidence is not human confirmation. Surface exception and conflicting
passages together; missing provenance becomes a gap. Suggest clarification questions to the
caller, which retains interview and confirmation responsibility. No subagent delegation.

See [the data and CLI contract](../../../docs/graphrag.md) when building explicit inputs,
interpreting limits, or diagnosing fallback. Never join entities on title or filename.

---
name: wiki-semantic-search
description: Build and query index/index.json, a lexical chunk index over graphify-out/wiki/, entirely inside Claude Code — no external embedding model, no VS Code extension. Use when a command or agent needs to check whether the project's knowledge base already covers a topic before asking the user or inventing an answer. Triggers: "search the wiki", "check the knowledge base", "regenerate the semantic index", "does the KB know about X".
---

# Wiki Semantic Search

Natively builds and queries `index/index.json` (path from `semantic_index` in
`knowledge-config.json`) — both halves run as local Python scripts with no network call
and no API key, no external extension or indexing tool required.

**This skill is the single source of rules for this domain.** The `knowledge-searcher` subagent
and any command that queries the knowledge base delegate to it and must not restate these rules.

## Why lexical, not vector

`index/index.json` chunks are plain text (`rawText`), not embeddings. This was a deliberate,
confirmed trade-off, not an oversight:

- True cosine-similarity search requires generating a query vector with the **same** embedding
  model used to build the index. That model is unknown here and no LLM API key is configured in
  this repo.
- A locally-available model (e.g. via `ollama`) would live in an **incompatible vector space** —
  comparing its vectors to a different model's vectors produces meaningless scores. It is not a
  drop-in substitute.
- Lexical/keyword scoring over the actual chunk text is fully local, has zero external
  dependency, and is still grounded in the real content of the wiki — not a downgrade in honesty,
  a downgrade in recall for paraphrased queries only.

## Index schema

```json
{
  "version": 1,
  "generated_at": "<ISO 8601 UTC>",
  "source_bundle": "<bundle_root>",
  "items": [
    {
      "id": "<sha1 of sourcePath#chunkIndex>",
      "docTitle": "<note title>",
      "sourcePath": "<path relative to bundle_root>",
      "chunkIndex": 0,
      "totalChunks": 3,
      "rawText": "<chunk text, ~250 words>"
    }
  ]
}
```

No `vector` / `norm` fields — nothing in this skill computes or consumes them.

## Build the index

```bash
python3 .opencode/skills/wiki-semantic-search/scripts/build_index.py
```

Reads `bundle_root` (`graphify-out/wiki/`) and writes `semantic_index` (`index/index.json`) from
`knowledge-config.json` — never hard-code either path. Chunks every `.md` file in the
bundle (including `index.md`, `log.md`, `_COMMUNITY_*.md`) into ~250-word segments, stripping
YAML frontmatter but keeping the note title. Full rebuild every run — this is deterministic and
cheap (no LLM call), so there is no incremental mode to maintain.

Run this whenever `graphify-out/wiki/` changes materially — the same trigger point the old
"regenerate the index" step in `/generate-llm-wiki` used, just native now.

## Query the index

```bash
python3 .opencode/skills/wiki-semantic-search/scripts/query_index.py "<question or topic>" --top 5
```

Tokenizes the query, scores each chunk by term overlap (title matches weighted 3× body matches),
and prints JSON: `{"query": ..., "results": [...]}`. An empty `results` array means **no match** —
this is the signal the no-fabrication rule below keys off, not an error.

## No-fabrication rule

This is the same discipline `gather-requirements.md`'s Golden Rule 3 already applies to the
business user's own words — it extends here to what the knowledge base says:

- If `query_index.py` returns one or more results, reflect the finding back to the user
  (cite `docTitle` / `sourcePath`) and ask them to confirm, correct, or extend it — do not present
  it as settled fact.
- If `results` is empty, say so plainly and ask the plain open question instead. **Never** infer an
  answer from general knowledge and present it as if it came from the wiki.
- Never read `raw/` directly to work around an empty result — `raw/` is immutable source material,
  not a search index; querying it defeats the purpose of having a chunked index and bypasses the
  citation trail (`sourcePath` points into `graphify-out/wiki/`, not `raw/`).

## Boundaries

- **Does not duplicate `second-brain-keeper`.** That agent owns extraction, graph, and OKF bundle
  generation (phases 1–5 of `/generate-llm-wiki`). This skill only builds/queries the *search*
  index on top of the bundle it produces, phase order: `second-brain-keeper` runs first, then
  `build_index.py`.
- **Does not touch `graphify-out/graph.json` or `graphify query`** — that is the structural graph
  layer (see `CLAUDE.md`'s three knowledge layers), a different tool for a different kind of
  question. This skill answers "does the wiki already say something about X", not "what depends on
  Y".

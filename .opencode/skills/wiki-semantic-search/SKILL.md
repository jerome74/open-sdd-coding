---
name: wiki-semantic-search
description: Build and query index/index.json, the vector (semantic) chunk index over graphify-out/wiki/. Use when a command or agent needs to check whether the project's knowledge base already covers a topic before asking the user or inventing an answer. Triggers: "search the wiki", "check the knowledge base", "rebuild the index", "does the KB know about X".
---

# Wiki Semantic Search

Natively builds and queries the **semantic (vector) index** at `index/index.json` (path from
`semantic_index` in `knowledge-config.json`). Both halves run as local Python scripts: embeddings
are computed in-process by a local model — no query-time network call, no external indexing tool.

**This skill is the single source of rules for this domain.** The `knowledge-searcher` subagent
and any command that queries the knowledge base delegate to it and must not restate these rules.

## Why vector, not lexical

Earlier this domain used a **lexical** index (`rawText` only, scoring by term overlap). That was a
deliberate trade-off at the time: true similarity search needs a query vector from the *same*
model that built the index, and no embedding model was available. That premise no longer holds —
the project ships the local model `intfloat/multilingual-e5-small` (see `knowledge-config.json`,
`embedding`) — so the index is now **vectorial** and search is by **meaning**, which is what lets a
reworded question find the right note.

- **Same model for build and query.** Vectors from different models live in incompatible spaces
  (BR-11). The build records the embedding service/model in the index; at query time a mismatch
  stops the search and asks to regenerate the index — it never compares across spaces.
- **Local-first.** The model runs in-process; indexing and querying the knowledge base need no API
  key. Content leaves the machine only later, in the CAG step (spec 05), by user decision.

## Index schema (v2)

```json
{
  "version": 2,
  "generated_at": "<ISO 8601 UTC>",
  "source_bundle": "<bundle_root>",
  "status": "generato | generato con errori | fallito",
  "embedding": { "service": "local", "model": "intfloat/multilingual-e5-small", "dimension": 384 },
  "errors": [],
  "items": [
    {
      "id": "<sha1 of sourcePath#chunkIndex>",
      "docTitle": "<note title>",
      "sourcePath": "<path relative to bundle_root>",
      "chunkIndex": 0,
      "totalChunks": 3,
      "rawText": "<chunk text, ~250 words>",
      "vector": [0.0]
    }
  ]
}
```

Large indices are stored as `manifest.json` + `parts/*.json.gz` (threshold in
`knowledge-config.json`, `index.part_threshold_mb`). Both layouts are resolved transparently by the
query script. `rawText` is kept for extended retrieval (spec 04) and debugging.

## Build the index

```bash
python3 .opencode/skills/wiki-semantic-search/scripts/build_index.py
```

Reads `bundle_root` (`graphify-out/wiki/`) and writes `semantic_index` (`index/index.json`) from
`knowledge-config.json` — never hard-code either path. Chunks every `.md` file in the bundle
(stripping YAML frontmatter, keeping the note title) into ~250-word segments, embeds each with the
configured local model, and writes atomically (a failed build never replaces a valid index).
Chunk size, overlap, the size threshold and the model are all configuration. `--status` prints the
last index status. Run it whenever `graphify-out/wiki/` changes materially.

## Query the index

```bash
python3 .opencode/skills/wiki-semantic-search/scripts/query_index.py "<question or topic>" --top 5
```

Embeds the query with the same local model and prints JSON
`{"query": ..., "esito": ..., "results": [...]}`, each result carrying `score` (cosine, `[-1,1]`),
`docTitle`, `sourcePath`, `chunkIndex`, `rawText` and `expanded` (`false` for a direct hit). `esito`
is one of:

- `conRisultati` — one or more results at/above `search.min_score`;
- `nessunRisultato` — a valid empty result (the signal for the no-fabrication rule below);
- `erroreModello` — index and configured embedding differ (regenerate the index);
- `erroreRuntime` — index missing or the local embedding model unavailable.

`top_k` and `min_score` come from `knowledge-config.json` (`search`).

## Extended retrieval (QACE)

With `retrieval.strategy = "esteso"` in `knowledge-config.json`, each result is expanded with the
`chunkIndex ± retrieval.neighbor_width` blocks of the **same note** (default 1 → the previous and
next block), so the caller gets more context around a hit. Expansion is bounded: the total returned
never exceeds `retrieval.max_extended_blocks` (default 15) and out-of-range values are clamped
(width 0–3, max 5–30). Expanded blocks are flagged `"expanded": true` and keep the origin's score.
The default `"standard"` strategy leaves results unchanged.

## No-fabrication rule

- If `esito` is `conRisultati`, reflect the finding back to the user (cite `docTitle` /
  `sourcePath`) and ask them to confirm, correct, or extend it — do not present it as settled fact.
- If `esito` is `nessunRisultato`, say so plainly and ask the plain open question instead.
  **Never** infer an answer from general knowledge and present it as if it came from the wiki.
- Never read `raw/` directly to work around an empty result — `raw/` is immutable source material,
  not a search index; querying it bypasses the citation trail (`sourcePath` points into
  `graphify-out/wiki/`, not `raw/`).

## Boundaries

- **Does not duplicate `second-brain-keeper`.** That agent owns extraction, graph, and OKF bundle
  generation (phases 1–5 of `/generate-llm-wiki`). This skill only builds/queries the *search*
  index on top of the bundle it produces: `second-brain-keeper` runs first, then `build_index.py`.
- **Does not touch `graphify-out/graph.json` or `graphify query`** — that is the structural graph
  layer, a different tool for a different kind of question. This skill answers "does the wiki
  already say something about X", not "what depends on Y".

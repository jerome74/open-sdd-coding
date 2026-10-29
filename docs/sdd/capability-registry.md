# Capability Registry

Mappa degli asset del framework SDD per ruolo. È il fallback di discovery quando il frontmatter non
basta: lega gli asset ai ruoli, non ai filename. Aggiornarlo quando si aggiunge o rinomina un asset.

## Pipeline knowledge base — due percorsi separati

| | graphify | compass |
|---|---|---|
| Config | `knowledge-config.json` | `knowledge-config.compass.json` |
| Comando generatore | `/generate-llm-wiki` | `/generate-llm-wiki-compass` |
| Agente esecutore | `second-brain-keeper` | `compass-keeper` |
| Comando publish | `/publish-llm-wiki` | `/publish-llm-wiki-compass` |
| Esecutore grafo | graphify CLI | `compass` CLI (≥ `compass_min_version`) |
| Grafo consumato | `graphify-out/graph.json` | `compass-out/adapted/graph.json` |
| Bundle | `graphify-out/wiki` | `compass-out/obsidian` |
| Indice semantico | `index/index.json` | `index-compass/index.json` |
| Branch publish | `{name}_llm_wiki` | `{name}_compass_wiki` |
| Stato/seal | `graphify-out/.source-manifest.json` | `compass-out/.source-manifest.json` |
| Checkpoint | `graphify-out/.pipeline_state.json` | `compass-out/.pipeline_state.json` |

Contratto comune: bundle Markdown conforme OKF v0.1, validato dallo stesso
`okf_validate_script` prima di publish e seal.

### KB attiva (una sola)

I consumatori (`scripts/cag_context.py`, indice semantico, `knowledge-searcher`) leggono la config di
default `knowledge-config.json`. La chiave attiva è composta da `graph_json`, `bundle_root`,
`semantic_index`.

- `python3 scripts/kb_active.py status` — KB attiva e puntatori.
- `python3 scripts/kb_active.py set graphify|compass [--dry-run]` — ripunta **solo** quelle tre
  chiavi, con backup.
- Ogni pipeline chiama `set` da sola come ultimo passo della Fase 5, dopo gate PASS e seal.
- La KB inattiva si interroga **solo** con `--config` esplicito; mai due KB in lettura implicita.

## Script di supporto

| Script | Ruolo |
|---|---|
| `scripts/source_watch.py` | Change detection e seal; accetta `--config` |
| `scripts/publish_gate.py` | Gate di overwrite in publish; accetta `--config` |
| `scripts/cag_context.py` | Risoluzione KB e contesto; accetta `--config` |
| `scripts/search_log.py` | Log delle query; path da config |
| `scripts/kb_active.py` | Selezione della KB attiva (ripuntamento config) |
| `scripts/compass_config_gen.py` | Genera `.compass/config.toml` dalla config compass |
| `scripts/compass_graph_adapter.py` | Adatta `compass-out/graph.json` al contratto consumatori |
| `scripts/compass_graph_check.py` | Verifica contratto del grafo adattato (bloccante) |

## Skill condivise

| Skill | Ruolo |
|---|---|
| `okf-open-knowledge-format` | Regole OKF v0.1 + `validate.sh` (gate) |
| `wiki-to-okf` | Conversione del vault in bundle OKF |
| `wiki-semantic-search` | `build_index.py` / `query_index.py` (`--config`) |
| `document-to-markdown` | Solo pipeline graphify: pre-pass conversione documenti |
| `sdd-guardrail` | Micro-Spec e disciplina spec-driven |

## Model matrix

| Asset | Model |
|---|---|
| Primary agent (comandi) | `deepseek/deepseek-flash` (da `opencode.json`) |
| `second-brain-keeper` | `deepseek/deepseek-flash` |
| `compass-keeper` | `deepseek/deepseek-flash` |
| `knowledge-searcher` | `deepseek/deepseek-flash` |
| `planner`, `sdd-governor`, `micro-spec-author`, `specification`, `prd` | vedi frontmatter |

## Note

- `docs/specs/constitution.md` è assente in questo checkout: la `## Roadmap` non è inizializzata.
- `raw/` è immutabile per entrambe le pipeline.
- Verifica della CLI compass e dello schema del grafo: `docs/sdd/compass-verification.md`.

# Verifica compass — evidenza misurata

Data: 2026-10-29. Ambiente: macOS arm64. Nessuna installazione persistente; tutto eseguito in una
directory scratch esterna al repo. Nessuna scrittura nel repo.

## Versione

| Voce | Valore |
|---|---|
| Release | `compass-v0.4.2` |
| Asset | `compass-aarch64-apple-darwin.tar.gz` |
| SHA-256 | `a85a8cd7201e1b91d22029bb954ad477c2f42b2189b507a97e0e65ce8d160c7c` (verificato) |
| `compass --version` | `compass 0.4.2` |

`cargo` non è presente sulla macchina: l'installazione prevista è da release asset, non da sorgente.

## Superficie CLI verificata

Comandi disponibili in 0.4.2:

- build: `init`, `ensure`, `update`, `extract`, `document`, `models`, `watch`, `cluster-only`,
  `label`, `merge-graphs`, `cache-check`, `merge-chunks`, `merge-semantic`, `store`;
- explore: `ask`, `search`, `callers`, `callees`, `impact`, `explore`, `node`, `context`,
  `call-graph`, `query`, `program`, `path`, `explain`, `affected`, `benchmark`, `output`,
  `hotspots`, `community`;
- history: `history`, `diff`, `review`;
- visualize: `tree`, `architecture`, `export`;
- integrate: `serve`, `global`, `clone`, `add`, `prs`, `hook`, `install`.

**Assente**: `diagnose`. Il controllo di salute del grafo non può essere delegato a compass: è
implementato nel progetto (`scripts/compass_graph_check.py`).

Flag usati/verificati:

- `compass init [PATH] --include <p> --exclude <g> --store <json|sqlite> --inference-level <lvl>
  --yes --force`;
- `compass update [PATH] --out <DIR> --store <…> --inference-level <…> --no-cluster --no-viz
  --no-gitignore --exclude … --force`;
- `compass export obsidian --dir <PATH> [--graph] [--labels]` (default `compass-out/obsidian`);
- `compass export wiki` **senza** flag `--dir`.

## Config `.compass/config.toml`

Schema minimo, accettato da `compass update` (exit 0) anche scritta a mano, senza `compass init`:

```toml
version = 1

[build]
include = ["docs/", "src/"]
exclude = []
```

## Build e layout output

Fixture in scratch: 2 file Markdown, 2 file Python. `init --store json` → **15 nodi, 16 link,
4 community**.

Layout prodotto in `compass-out/`:

```text
graph.json
GRAPH_REPORT.md
graph.html
graph-overview.json
orientation.json
community-hierarchy.json
community-quality.json
manifest.json
current-snapshot
snapshots/
cache/
store/store.sqlite3
state-events.jsonl
```

Note:

- `--out` è relativo alla radice del progetto: `--out compass-out` produce
  `compass-out/compass-out/`. L'output di default è già `compass-out`, quindi **non passare
  `--out`** se si vuole quel layout.
- `compass update` su corpus invariato: 0 file estratti, 4 in cache. Incrementalità funzionante.
- Con `--store json` viene comunque creato `store/store.sqlite3` (sidecar).

## Schema `graph.json` misurato

Top-level: `directed`, `multigraph`, `graph`, `nodes`, `links`.

Nodo (campi osservati): `id`, `kind`, `name`, `qualifiedName`, `language`,
`source{file,startByte,endByte,startLine,startColumn,endLine,endColumn}`, `details`, `evidence`,
`community`.

Link (campi osservati): `id`, `key`, `source`, `target`, `kind`, `relationshipSite`, `evidence`,
`weight`, `occurrenceRule`, `context`.

Misure sulla fixture:

| Check | Esito |
|---|---|
| Nodi totali | 15 |
| Link totali | 16 |
| Nodi senza `id` | 0 |
| Link con `source`/`target` non stringa | 0 |
| Link con endpoint inesistenti | 0 |
| Nodi senza `label` | **15 / 15** |
| Nodi senza `source_file` | **15 / 15** |

Conclusione: compass **non** emette `label` né `source_file`, che sono i campi usati da
`scripts/cag_context.py` per selezionare il sotto-grafo. Serve un **adattatore esplicito**
(`scripts/compass_graph_adapter.py`).

## Export

- `export obsidian --dir <PATH>` funziona e scrive le note più `graph.canvas` (fixture: 19 note).
  Produce note per simbolo e note di paragrafo.
- `export wiki` esiste ma non accetta `--dir`: destinazione non parametrizzabile.
- In scratch il comando stampa `Graph freshness unknown: graph has no valid build commit` perché
  la fixture non è un repo git. Da riverificare su repo reale.

## Corpus vuoto

`compass init . --include docs` su directory senza file eleggibili:

- messaggio: `include rule(s) matched no eligible files: docs`;
- exit code: **2**.

Conseguenza: sul repo attuale (`raw/` e `docs/specs/` contengono solo `.gitkeep`) `init` fallisce.
La config va scritta a mano (o generata) e il run va bloccato con un preflight esplicito.

## `compass install`

`compass install --project --all --dry-run` (exit 0) dichiara che scriverebbe:

- `.agents/skills/compass/SKILL.md`
- `AGENTS.md`
- `.cursor/rules/compass.mdc`
- `.trae/skills/compass/SKILL.md`, `.trae-cn/...`

Nessun file scritto con `--dry-run`. Confermata la regola: **mai** `compass install` dentro il repo.

## Domande residue

1. Il warning `graph snapshot is missing or invalid` compare anche dopo un `init` riuscito. Non
   blocca build/export; da monitorare, non da correggere in questa pipeline.
2. `export wiki` non parametrizzabile: non usare per il bundle; usare `export obsidian --dir`.
3. `compass install` non testato senza `--dry-run` (vietato per policy).

# AGENTS.md — OpenCode SDD Framework (DeepSeek)

Project instructions auto-loaded by OpenCode. Process rules live here; mission, tech stack e roadmap in `docs/specs/constitution.md` (**Costituzione SDD**, via `/init-new-project`) — questo file vi rimanda, non lo duplica.

## 0. Costituzione SDD — fonte unica
`docs/specs/constitution.md` (generata da `/init-new-project`) è la fonte autorevole per **Mission** e **principi non negoziabili**, **Tech Stack**, e **`## Roadmap`** (checklist, unica autorità su stato e ordine — cfr. §4).
Se manca → roadmap non inizializzata: eseguire `/init-new-project`.
Questo file = regole di processo SDD; non duplica la Costituzione (dubbio su *cosa* costruire → vince la Costituzione).

### 0.1 General agent guidelines
- **Think before coding** — leggi spec e Costituzione pertinenti; requisito non documentato → fermati e segnala, non inventare.
- **Simplicity first** — YAGNI: nessun componente, entità o dipendenza speculativa.
- **Surgical changes** — modifica solo ciò che il compito richiede; preserva tutto il resto.
- **Goal-driven execution** — lavoro tracciato da voce di `## Roadmap` o Micro-Spec; chiusura solo a ciclo completo (§4).
- **Consult before answering** — consulta la knowledge base (ricerca semantica + grafo, `scripts/cag_context.py`) e **cita le note usate**; senza risultati dichiara l'assenza e **non inventa**; non legge `raw/` (FR-011, BR-1).

### 0.2 Convenzioni di progetto (dal Tech Stack)
- **Linguaggio:** Python 3 per script locali (`build_index.py`, `query_index.py`, `source_watch.py`); type hints + gestione esplicita degli errori.
- **Configurazione:** percorsi/parametri da `knowledge-config.json` — mai hard-coded.
- **Embedding:** `intfloat/multilingual-e5-small` in-process, locale (nessuna API key).
- **Grafo:** `graphify` → `graphify-out/graph.json` (dipendenza esterna deliberata — §1, Costituzione Principio 8).
- **Assistente:** DeepSeek (default) + GitHub Copilot (`opencode.json`).
- **Pubblicazione:** Git, ramo `<name>_llm_wiki` via `/publish-llm-wiki`.
- Lingua di spec e Costituzione: **italiano** (§6).

## 1. What this project is
Non è una codebase applicativa: niente build o test suite. I "programmi" sono OpenCode **commands**, **subagents** e **skills** che guidano una pipeline: **Specification-Driven Development (SDD)**.

`docs/input/*.md` → `docs/specs/*.spec.md` → `docs/specs/constitution.md` (principi + `## Roadmap`) → deliverables (code, docs, config, …)

Flusso comandi (in ordine): `/gather-requirements` → `/spec-brainstorm <file>` → `/init-new-project <root>` → `/SDD-implement <spec|N|-all>` ⇄ `/micro-spec <descrizione>`.

- `/gather-requirements` → `docs/input/functional-requirements.md` · `/spec-brainstorm <file>` → `docs/specs/*.spec.md` · `/init-new-project <root>` → `constitution.md` + `AGENTS.md` · `/SDD-implement <spec|N|-all>` → deliverable · `/micro-spec <descrizione>` → patch spec + item di roadmap.

### Knowledge pipeline (graph-first)
Trasforma le sorgenti in knowledge graph → artefatto Obsidian + bundle OKF v0.1:
`raw/ + docs/specs/` → `graphify-out/graph.json` → `graphify-out/wiki/` → `index/index.json`
- `/generate-llm-wiki` `update|check|all|okf|validate|query "<q>"|report` — Phase 0 (change detect, `scripts/source_watch.py`) sul primary; fasi 1–5 in `@second-brain-keeper`.
- `/publish-llm-wiki <name>` — commit `graphify-out/` + `index/` su branch `<name>_llm_wiki` e push.

**Prerequisito:** `graphify` nel PATH — `uv tool install graphifyy` (0.9.25); dipendenza esterna deliberata (Costituzione Principio 8). Percorsi/lever da `knowledge-config.json` (mai hard-coded). `raw/` immutabile (negata da `opencode.json` `permission.edit`). A pipeline eseguita, `@knowledge-searcher` interroga `index/index.json` invece di `NO_INDEX`.

## 2. Conductor = primary agent, non subagent
`/SDD-implement` gira come **primary agent** e adotta il ruolo **Conductor**: orchestra il ciclo plan → produce → validate → publish, un item di roadmap alla volta. Delega **solo** checkpoint specialistici — mai l'orchestrazione — via Task. Un subagent non può generare subagent: per questo l'orchestrazione resta sul primary agent.

## 3. Runtime capability discovery — per ruolo, mai per filename
`/SDD-implement` Phase 0 legge il **frontmatter** sotto `.opencode/` (`agents/*.md`, `commands/*.md`, `skills/*/SKILL.md`, `opencode.json`) e lega le capability per **ruolo dichiarato**, non per nome. Nessun comando nomina un asset per filename. **Aggiungere un asset sotto `.opencode/` non deve mai richiedere di editare un comando.**
**Fallback.** Se il runtime non espone il frontmatter, usa la **Capability Registry** in §7 (per ruolo); tienila sincronizzata.

## 4. `## Roadmap` = single source of truth dello stato SDD
La checklist `## Roadmap` (`- [ ]` pending, `- [x]` done) è l'**unica** autorità su stato e ordine. `/SDD-implement` processa in ordine e spunta **solo a ciclo Plan → Produce → Validate → Publish completo**. Mai tracciare lo stato altrove; mai inventare roadmap.

## 5. `raw/` immutabile — imposto, non convenzionale
Se `raw/` esiste: mai modificare, rinominare, spostare o cancellare sotto di essa — solo aggiungere. Una nuova versione è un **nuovo file** (`contract-v2.docx`), mai overwrite. Enforcement: `opencode.json` → `permission.edit` nega ogni scrittura su `raw/**` (garanzia harness, non CI).

## 6. Convenzione lingua
- `README.md` — **italiano**.
- Commands, agents, skills — **inglese**.
- `/gather-requirements`, `/spec-brainstorm`, `/micro-spec` — lingua dell'utente (default **italiano**).
- Specs e `constitution.md` — **italiano**.
- Segui la lingua del file che modifichi.

## 7. Capability Registry (fallback per §3)
Risolto per **ruolo**; i filename sono solo riferimento umano.

### Commands (`.opencode/commands/`) — entrypoint umani, mai auto-invocati
| Ruolo | Asset |
|---|---|
| Intervista business → functional requirements | `gather-requirements.md` |
| Requisiti funzionali → spec tecniche (+ roadmap se constitution esiste) | `spec-brainstorm.md` |
| Specs → `constitution.md` + `AGENTS.md` | `init-new-project.md` |
| Conductor: roadmap un item alla volta, con governance | `SDD-implement.md` |
| Bug/variazione → patch spec + un item di roadmap | `micro-spec.md` |
| *(ausiliario)* piano da `engineering/prompt/` → `engineering/plan/<name>.md` (conferma richiesta); drafting a `@planner` | `plan.md` |
| *(ausiliario)* struttura una richiesta nel template `tech-plan/the_prompt_engineering.md` | `prompt-engineering.md` |
| Knowledge pipeline: change-detect → Graphify → Obsidian → OKF → index (Phase 0 sul primary, fasi 1–5 delegate) | `generate-llm-wiki.md` |
| Pubblica bundle (`graphify-out/` + `index/`) su branch dedicato | `publish-llm-wiki.md` |

### Subagents (`.opencode/agents/`)
| Ruolo | Asset | Accesso |
|---|---|---|
| Authoring spec AI-ready standalone (fuori da `/spec-brainstorm`) | `specification.md` | read / write |
| PRD; issue GitHub opzionali su conferma | `prd.md` | read / write / bash / webfetch |
| Drafting piano read-only; presenta il piano, non lo scrive | `planner.md` | **read-only** |
| Control layer read-only: valida ogni artefatto contro la sua **struttura dichiarata**; non genera contenuto (delegated + embedded) | `sdd-governor.md` | **read-only** |
| Patch spec Micro-Spec + un item di roadmap; non implementa, non spunta | `micro-spec-author.md` | write solo `docs/specs/patch-*.spec.md` + `docs/specs/constitution.md` |
| Opzionale: controlla l'indice prima di una domanda; `NO_INDEX` → intervista semplice | `knowledge-searcher.md` | **read-only** |
| Fasi 1–5 knowledge pipeline (Graphify → OKF → deepen → gate). Scrive solo sotto `graphify-out/` + `index/` | `second-brain-keeper.md` | read / write / bash |

### Skills (`.opencode/skills/`)
| Ruolo | Asset |
|---|---|
| Regole Micro-Spec: guardrail (rifiuta edit da chat → `/micro-spec`), template 4 campi, patch-spec skeleton, Append-Only, Error-to-Spec | `sdd-guardrail/SKILL.md` |
| Compila il template Prompt Engineering; grounding + escalation; mai inferire in silenzio | `prompt-engineering/SKILL.md` |
| Spec OKF v0.1 — frontmatter, filename riservati, tre regole di conformità; `scripts/validate.sh` | `okf-open-knowledge-format/SKILL.md` |
| Workflow wiki → OKF su `graphify-out/wiki/` | `wiki-to-okf/SKILL.md` |
| Build/query `index/index.json`; embedding locale, no API key; `scripts/build_index.py` + `query_index.py` | `wiki-semantic-search/SKILL.md` |

### Config
| Ruolo | Asset |
|---|---|
| Provider (DeepSeek), modello default, `permission` (incl. `raw/**` deny), `instructions` | `opencode.json` |
| Knowledge pipeline: sorgenti, path grafo/bundle, versione OKF, lever, validator | `knowledge-config.json` |

### Model → role matrix
| Ruolo | Modello |
|---|---|
| **Tutti** — default, primary, commands, subagents | `deepseek/deepseek-flash` |

Impostato una volta come `model` in `opencode.json`; ogni agente e `spec-brainstorm` pinnano lo stesso id.
> **Fallback:** se `deepseek-flash` non è disponibile, sostituisci con un modello DeepSeek da `/models` (default `opencode.json` + un frontmatter per agente / `spec-brainstorm`).

### Knowledge index location
Default `index/index.json`; assenza → `NO_INDEX`, intervista con domande aperte.

## 8. Lifecycle
`/init-new-project` può riscrivere questo file; se OpenCode lo carica una volta per sessione, riapri la sessione.

# RTK Token Optimization Rules
**Plugin di progetto (primario):** l'integrazione RTK gira da `.opencode/plugins/rtk.ts` (auto-caricato da OpenCode all'avvio, versionato nel repo). Riscrive automaticamente i comandi shell in `rtk …` via `rtk rewrite`; se `rtk` non è nel PATH → pass-through (nessun blocco). Richiede **riavvio di OpenCode** per essere attivo.

**Fallback manuale:** prefissa con `rtk` i comandi shell idonei (comprime l'output, -60/90% token) [citation:14]. Gruppi principali (`rtk --help`, v0.50.0): file (`ls`/`tree`/`read`) · ricerca (`grep`/`rg`/`find`/`ast-grep`) · git (`git`/`gh`/`glab`) · utilità (`diff`/`log`/`wc`/`json`/`env`/`deps`/`err`/`test`/`summary`) · build/test toolchain (`cargo`/`npm`/`npx`/`bun`/`pnpm`/`docker`/`kubectl`/`tsc`/`jest`/`vitest`/`playwright`/`pytest`/`mypy`/`ruff`) · raw (`run`/`pipe`/`proxy`).

**Misura del risparmio:** `rtk gain -p` (scope progetto: token/percentuale/numero comandi).

**Eccezioni (no RTK):** output già in pipe (`grep x | head`) [citation:1]; comandi senza output (`cd`, `mkdir`, `rm`); `rtk` non installato (`rtk --version`).

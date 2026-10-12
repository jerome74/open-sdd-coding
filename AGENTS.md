# AGENTS.md — OpenCode SDD Framework (DeepSeek)

Nucleo minimo delle regole di processo, caricato a ogni richiesta: tutto il resto si legge **solo quando serve**.

## 0. Fonti
- **Costituzione SDD** `docs/specs/constitution.md` — Mission, principi non negoziabili, Tech Stack, `## Roadmap`. **Non** è auto-caricata: leggila prima di lavoro SDD o in caso di dubbio su *cosa* costruire (vince lei). Assente → roadmap non inizializzata: `/init-new-project`.
- **Capability Registry** `docs/sdd/capability-registry.md` — asset per ruolo + model matrix; fallback di `/SDD-implement` Fase 0.
- **Config** — `opencode.json` (provider, modello, permessi), `knowledge-config.json` (percorsi e leve della knowledge pipeline: mai hard-coded).
- **Knowledge base** — prima di rispondere su contenuti di progetto consulta `python3 scripts/cag_context.py "<q>"` e **cita le note**; nessun risultato → dichiaralo, non inventare; non leggere `raw/` come fonte di risposta (FR-011, BR-1).

## 1. Regole generali
Pensa prima di agire (requisito non documentato → fermati e segnala) · YAGNI · modifiche chirurgiche · ogni lavoro tracciato da una voce di `## Roadmap` o da una Micro-Spec (`/micro-spec`).

## 2. Stile di output — caveman mode
Risposte in chat **telegrafiche**: niente articoli, riempitivi, cautele, preamboli né narrazione dei passi; frammenti OK; termini tecnici esatti.
- **Esenti:** contenuto dei file scritti (spec, roadmap, doc, codice, commenti) e l'intervista di `/gather-requirements`.
- Formati di output fissi restano verbatim. Mai perdere significato: path, ID, comandi, errori, numeri, negazioni, condizioni esatti.

## 3. Pipeline SDD
`/gather-requirements` → `docs/input/*.md` → `/spec-brainstorm <file>` → `docs/specs/*.spec.md` → `/init-new-project <root>` → `constitution.md` → `/SDD-implement <spec|N|-all>` ⇄ `/micro-spec <descrizione>`. Knowledge pipeline: `/generate-llm-wiki`, `/publish-llm-wiki <name>` (prerequisito `graphify`).
- **Conductor** — `/SDD-implement` gira come primary agent e orchestra; delega via Task solo i checkpoint specialistici (un subagent non genera subagent).
- **Discovery per ruolo** — gli asset sotto `.opencode/` si legano dal frontmatter, mai per filename; aggiungere un asset non richiede di editare un comando. Asset aggiunto/rinominato → aggiorna il Registry.
- **`## Roadmap` = unica fonte di stato** — ordine e `- [ ]`/`- [x]`; si spunta solo a ciclo Plan → Produce → Validate → Publish completo. Mai stato altrove, mai roadmap inventate.
- **Una voce per contesto** — tra una voce e la successiva: `/compact` o nuova sessione; alla ripresa si rilegge la `## Roadmap`.

## 4. `raw/` immutabile
Mai modificare, rinominare, spostare o cancellare sotto `raw/`: solo aggiungere (nuova versione = nuovo file). Imposto da `opencode.json` `permission.edit`.

## 5. Lingua
`README.md`, spec e `constitution.md` in **italiano**; commands, agents, skills in **inglese**; `/gather-requirements`, `/spec-brainstorm`, `/micro-spec` nella lingua dell'utente (default italiano). Altrimenti segui la lingua del file.

## 6. RTK e lifecycle
- Il plugin `.opencode/plugins/rtk.ts` riscrive i comandi shell in `rtk …`; senza `rtk` nel PATH lascia passare il comando invariato. Misura: `rtk gain -p`.
- `/init-new-project` può riscrivere questo file: deve restare un nucleo minimo. Dopo modifiche, riapri la sessione.

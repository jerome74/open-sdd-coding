# Piano 01 — Agent Runtime (fondazione)

- **Voce roadmap:** `01 — Agent Runtime (fondazione)` (non spuntata)
- **Spec:** [01-agent-runtime.spec.md](../specs/01-agent-runtime.spec.md), Stato `Implemented` (2026-10-21)
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack
- **Data piano:** 2026-10-21
- **Stato piano:** approvato 2026-10-21; eseguito (T0–T14)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | Package runtime Python, componenti C-01…C-13 + wiring applicativo; `errors.py` e `retry.py` sono supporto trasversale (non componenti) | codice | `src/agente/` (`config.py`, `errors.py`, `retry.py`, `logging_setup.py`, `role_guard.py`, `llm.py`, `device.py`, `tools.py`, `notifications.py`, `history.py`, `scheduler.py`, `execution.py`, `telegram_gateway.py`, `supervisor.py`, `app.py`) |
| D-02 | Schema SQLite iniziale e migrazione versionata | schema / migrazione | `src/agente/storage/migrations/001_init.sql`, `src/agente/storage/db.py` |
| D-03 | Repository tipizzati per entità | codice | `src/agente/storage/repositories.py` |
| D-04 | Config di esempio e template segreti (nessun valore reale) | config | `config/config.example.toml`, `config/secrets.example.env` |
| D-05 | Dipendenze pinned + setup ambiente | config | `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` (metadata + pytest), `.deps/` (install con `pip --target`, ignorata da git) |
| D-06 | Script di boot e avvio con wake-lock e loop di riavvio | script operativi | `scripts/boot/start-agent.sh`, `scripts/boot/90-agent.sh` |
| D-07 | Test suite pytest mappata su AC-01…AC-05 + unit per tutti i componenti | test | `tests/` (`conftest.py`, `test_config.py`, `test_logging.py`, `test_storage.py`, `test_role_guard.py`, `test_llm.py`, `test_device_gate.py`, `test_notifications.py`, `test_history.py`, `test_scheduler.py`, `test_execution.py`, `test_retry.py`, `test_bootstrap.py`, `test_telegram_gateway.py`, `test_supervisor.py`, `test_boundaries.py`) |
| D-08 | Documento architettura con diagrammi Mermaid (contesto, componenti, 5 sequenze dei flussi, ER, data flow) | documentazione | `docs/architecture/01-agent-runtime.md` |
| D-09 | Aggiornamento stato spec e versioni/registro nel Tech Stack | documentazione | `docs/specs/01-agent-runtime.spec.md`, `docs/specs/constitution.md` |
| D-10 | Aggiornamento `.gitignore` (`.venv/`, `.deps/`, `token.sh`, `config/secrets*.env`, eccezione `!config/secrets.example.env`) | config | `.gitignore` |
| D-11 | Delivery history della voce | documentazione | `docs/delivery-history.md` |

Fuori scope di questa voce (dichiarato, non inventato):

- Gate C-27/C-28: non definiti in spec 01; C-07 accetta solo il flag `approved: bool`. Il gate completo arriva con spec 06.
- Esecuzione end-to-end dei compiti: C-09 qui è solo scheletro con lock/timeout/retry; il flusso completo è spec 03.
- Handler delle feature FR-001…FR-010: spec 02–11.
- Validazione su dispositivo reale (wake-lock, kill di Android): resta rischio, non verificabile in questo ambiente.
- Vista di deployment nei diagrammi: la spec non la dichiara → omessa, gap registrato.
- Evento di ripartenza verso C-10: contenuto e formato sono di spec 11; follow-up registrato.
- Tasto «Autorizza» e flusso di autorizzazione utenti: spec 08.
- `web_search`: provider e strumento sono di spec 06; non registrato in C-08.

> **Assumption (piano, non spec):** la struttura del documento D-08 è derivata dalle sezioni della spec 01, perché `docs/templates/` non contiene un template per questo tipo. Sezioni obbligatorie: Contesto, Componenti, Flussi (sequenze), Modello dati, Integrazioni. Se la spec o l'operatore indicano una struttura diversa, il documento si adegua.
>
> **Assumption (piano, non spec):** D-05 usa `pytest` come framework di test e `pyproject.toml` per metadata e configurazione di pytest; nessuno dei due è dichiarato dalla spec 01. Scelta del piano, reversibile; le versioni si fissano in T0.
>
> **Assumption (piano, non spec):** il job store APScheduler usa lo stesso DB SQLite in tabella separata `apscheduler_jobs`; la spec 01 ammette sia questa sia un file dedicato.
>
> **Assumption (piano, non spec):** il job di manutenzione (retention 30 gg, reset chat 24 h) gira ogni 24 ore dall'avvio; la spec dichiara «giornaliero» ma non un'ora.
>
> **Assumption (piano, non spec):** la soglia di stallo del watchdog C-12 è 300 s senza heartbeat; la spec non la dichiara. Da validare sul dispositivo.

## Decisioni che sbloccano il piano

Le domande in sospeso della spec 01 sono state chiuse dall'operatore:

| # | Domanda aperta (spec 01) | Decisione | Fonte / data |
|---|--------------------------|-----------|--------------|
| D1 | Meccanismo di supervisione (C-12) | Boot script `~/.termux/boot/` + wake-lock + loop di riavvio esterno; watchdog in-process che termina il processo su stallo. Niente `termux-services`. | Operatore, 2026-10-21 |
| D2 | Rilevamento offline prolungato (BR-10, spec 11) | C-07 interroga `termux-wifi-connectioninfo` a intervalli; ultimo contatto salvato in `settings`; offline = ultimo contatto > 1 h. Qui si fissa **solo il meccanismo**: l'alerting è spec 11. | Operatore, 2026-10-21 |
| D3 | Cifratura at-rest del DB | Non richiesta: solo permessi `600` su file e directory privata. | Operatore, 2026-10-21 |
| D4 | Versioni librerie (non dichiarate) | Install con `pip --target .deps` (il venv non è creabile in questo ambiente: `ensurepip` assente e il filesystem del progetto non supporta il symlink `lib64`); pin in `requirements.txt`/`requirements-dev.txt`; versioni registrate nel Tech Stack della constitution. | Operatore + deviazione T0, 2026-10-21 |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente** → Phase 0 eseguita leggendo il solo frontmatter di `.opencode/{agents,commands,skills}` e `opencode.json`. Fallback ladder: passo 1 (procedo su spec + constitution, capability ridotta) e passo 2 (nessuna skill specializzata per codice/config/test).

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01 codice Python | *nessuna* | — | nessuna skill con scope codice nel frontmatter | ladder passo 2: prodotto da spec 01 + constitution; gap registrato |
| D-02 schema/migrazione | *nessuna* | — | nessuna skill con scope SQL/schema | ladder passo 2; struttura vincolata da spec §Modello dati |
| D-03 repository | *nessuna* | — | nessuna skill con scope codice | ladder passo 2 |
| D-04 config TOML | *nessuna* | — | nessuna skill con scope config | ladder passo 2; chiavi vincolate da C-01 |
| D-05 deps/setup | *nessuna* | — | nessuna skill con scope packaging | ladder passo 2; decisione D4 |
| D-06 script boot | *nessuna* | — | nessuna skill con scope script operativi | ladder passo 2; decisione D1 |
| D-07 test | *nessuna* | — | nessuna skill con scope testing | ladder passo 2; test scritti a mano su pytest |
| D-08 diagrammi | *nessuna* | — | `drawio` valutata e **scartata**: emette file `.drawio`, mentre la spec dichiara «Diagrammi Mermaid» da generare a valle — la struttura dichiarata vince | ladder passo 2: Mermaid inline nel Markdown |
| D-09 docs spec/constitution | *nessuna* | — | nessuna skill con scope documentazione di progetto | ladder passo 2; lingua italiana |
| D-10 `.gitignore` | *nessuna* | — | nessuna skill applicabile | ladder passo 2 |
| Validazione (tutti i deliverable) | `.opencode/agents/sdd-governor.md` | agent | dichiara di governare fedeltà alla struttura dichiarata, tracciabilità e completezza; read-only, non genera contenuto | usato solo in Phase 4 (checkpoint) |

Asset valutati e non vincolati:

- `planner`: read-only, duplicherebbe il piano scritto dal Conductor; non vincolato.
- `sdd-guardrail`: veto esplicito (non è una patch, è una feature completa).
- `document-to-markdown`, `okf-open-knowledge-format`, `wiki-to-okf`, `wiki-semantic-search`, `prompt-engineering`: nessun deliverable corrispondente.
- `knowledge-searcher`, `prd`, `specification`, `micro-spec-author`: fuori fase (nessuna authoring di requisiti o spec).
- Commands: mai vincolati né invocati.

## Structure-governance checkpoint (pre-piano)

Strutture dichiarate applicabili all'item:

| Artefatto | Struttura dichiarata | Fonte | Idoneità |
|---|---|---|---|
| Schema SQLite | tabelle/colonne/vincoli elencati | spec 01 §Modello dati | adeguata, nessun template esterno |
| Interfacce componenti | firme pubbliche per C-01…C-13 | spec 01 §Progettazione componenti | adeguata |
| Oggetto `Config` | campi elencati, immutabile e tipizzato | spec 01 C-01 + constitution | adeguata |
| Diagrammi (D-08) | mappa vista → modello → tipo: contesto/componenti/data flow → `flowchart`; flussi 1–5 (avvio, messaggio in ingresso, uscita, azione modificante, manutenzione) → `sequenceDiagram`; modello dati → `erDiagram`. Vista deployment: **omessa** (non dichiarata dalla spec) → gap registrato | spec 01 §Panoramica, §Componenti, §Flussi di dati, §Modello dati, §Progettazione integrazioni | adeguata |
| Documento architettura (D-08) | nessun template in `docs/templates/` per questo tipo → sezioni obbligatorie derivate dalla spec: Contesto, Componenti, Flussi, Modello dati, Integrazioni | spec 01; scelta del piano, etichettata `> Assumption:` | adeguata con assunzione esplicita |
| Piano | sezioni richieste dal comando | `.opencode/commands/SDD-implement.md` | adeguata |

Deliverable obbligatori derivati: D-01…D-11. Dipendenze: nessuna voce a monte (item 01 è fondazione). Checkpoint delegato a `sdd-governor` prima dell'approvazione; esito registrato qui sotto.

**Checkpoint 1 (2026-10-21):** FAIL (nessun failure critico).

- M1 — D-05/D-06 senza task proprietario → **risolto**: T0.
- M2 — esito checkpoint non registrato → **risolto** con il registro dei checkpoint 2 e 3.
- M3 — `config/secrets*.env` non ignorato → **risolto** a livello di piano (D-10, R5, criterio 8); l'aggiornamento reale è obbligo di T0.
- M4 — mapping vista→tipo Mermaid incompleto e deployment non dichiarato → **risolto**: flussi 1–5 mappati, deployment omesso con gap.
- M5 — struttura D-08 non dichiarata → **risolto**: sezioni obbligatorie + `> Assumption:`.
- m1 moduli di supporto etichettati → risolto.
- m2 provenienza decisioni D1–D4 → risolto (colonna Fonte/data).
- m3 confine D2 (solo meccanismo, alerting in spec 11) → risolto.
- m4 scelta job store → risolto (assunzione: stesso DB, `apscheduler_jobs`).
- m5 confine T5 (avviso credenziali in spec 10) → risolto.
- m6 duplicati nell'ordine di consegna → risolto (sequenza lineare).
- m7 proprietario job di manutenzione → risolto (registrazione T8, logica T7).
- m8 catena criterio→deliverable e T14 → risolto (tabella di tracciabilità; T14 esteso).
- m9 versione Python → risolto (fatto d'ambiente verificato con data, non dedotto dalla spec).

**Checkpoint 2 (2026-10-21):** FAIL — riverifica: M1, M3–M5 e m1–m9 chiusi; restano M2 (placeholder), m1–m9 non enumerati, mapping flussi 3/4/5 e omissione deployment non registrati, blocchi `> Assumption:` assenti, inventario non primo blocco, T6 con AC fittizia, D-08 senza sezioni obbligatorie, D-10 duplicato. Remediation applicata.

**Checkpoint 3 (2026-10-21):** PASS WITH FINDINGS (nessun failure critico). Riverifica: M2 chiuso con questa registrazione; m1–m9 enumerati con rimedio puntuale (D-01 supporto trasversale, colonna Fonte/data, confine D2, assunzione job store, confine T5, sequenza lineare, T7/T8, tabella di tracciabilità, R1 verificato con `python3 -V`); vista deployment omessa con gap registrato e flussi 1–5 mappati a `sequenceDiagram`; tre blocchi `> Assumption:` presenti (sezioni D-08, pytest/`pyproject.toml`, `apscheduler_jobs`); inventario deliverable primo blocco; T6 senza AC fittizia; sezioni D-08 enumerate; D-10 solo in T0. Residui non bloccanti: pattern constitution C-27/C-28 vs flag `approved` riportato e non riconciliato, in attesa di spec 06; domande aperte della spec ancora presenti fino a D-09/T14. Checkpoint read-only: nessun contenuto generato dal governor.

**Checkpoint 4 — validazione deliverable (2026-10-21):** primo esito FAIL (critici: job di
manutenzione non registrati; `token.sh` con segreti fuori `.gitignore`). Remediation applicata:
job di manutenzione registrato e testato, `token.sh` ignorato, watchdog avviato su thread con
heartbeat, evento di ripartenza dichiarato fuori scope (spec 11), D-09/D-11 completati, test
gateway aggiunti, sequenza di avvio e ER corretti, deviazioni e costanti registrate. Riverifica:
**PASS WITH FINDINGS**, publish GO. Suite: 74 test verdi. Residui: rotazione chiavi a carico
dell'operatore, validazione su dispositivo, AC-05 con scheduler di produzione verificato per tipo.

## Task

| Task | Contenuto | Deliverable | AC |
|---|---|---|---|
| T0 | Setup ambiente: `.deps` (pip --target), install dipendenze, pin versioni risolte (rischio R1) | D-05, D-10 | — |
| T1 | C-01 `Config` immutabile + `load_config()` TOML, verifica campi obbligatori e permessi `600`, errori fatali senza valori segreti; `errors.py`; helper retry 3×/1 min (BR-8) | D-01, D-04 | AC-02, AC-04 |
| T2 | C-13 logging JSON line su file app + console, rotazione, nessun segreto | D-01 | — |
| T3 | C-02 connessione SQLite WAL, `chmod 600`, migrazioni versionate, retry breve su `database is locked`, transazioni; schema completo spec; job store APScheduler nello stesso DB (`apscheduler_jobs`) | D-02, D-03 | AC-01 |
| T4 | C-04 `resolve_role` ADMIN/AUTHORIZED/UNKNOWN, admin solo da config, `revoked` ≡ `UNKNOWN`, decoratori | D-01 | AC-03 |
| T5 | C-05 client DeepSeek (chat, summarize, tool calling, troncamento contesto, retry, errori credenziali come errore tipizzato — l'avviso admin è spec 10) | D-01 | AC-04 |
| T6 | C-07 device adapter (`battery_level`, `is_online`, `run_command`, file read/write/delete) con rifiuto se `approved=False`; C-08 registry con `read_only`/`requires_approval` | D-01 | — (gate coperto da `test_device_gate.py`, non è un AC della spec) |
| T7 | C-10 notifiche (invio, split messaggi lunghi, alert admin) e C-11 storico, `query`, `purge_expired()` (retention 30 gg, reset chat 24 h) | D-01 | — |
| T8 | C-06 scheduler APScheduler con job store SQLite, timezone telefono, `schedule_task`/`unschedule_task`/`next_run`, registrazione dei job di manutenzione e ricarica job all'avvio | D-01 | AC-05 |
| T9 | C-09 execution engine: lock per compito, timeout 10 min, retry, registrazione esito `ok|errore|interrotto` | D-01 | — |
| T10 | C-03 gateway Telegram: long polling, `send`, inline keyboard Approva/Rifiuta/Autorizza, filtro ruoli, retry | D-01 | AC-03 |
| T11 | `app.py` bootstrap (config → migrazione → wake-lock → polling → scheduler → evento ripartenza), C-12 watchdog, script boot | D-01, D-06 | AC-01, AC-05 |
| T12 | Test suite: unit per componente + test di accettazione AC-01…AC-05 con tmpdir e fake gateway/LLM | D-07 | AC-01…AC-05 |
| T13 | Documento architettura con diagrammi Mermaid dai soli modelli della spec | D-08 | — |
| T14 | Validazione, checkpoint `sdd-governor`, publish, aggiornamento spec/constitution, indici e cross-reference, delivery history | D-09, D-11 | tutte |

## Deviazioni d'interfaccia dichiarate

Semantica della spec preservata; firme adattate al runtime Python:

- **C-04:** i decoratori sono factory (`admin_only(guard)`), perché devono risolvere il ruolo a runtime.
- **C-01:** `load_config(path)` accetta il percorso come parametro (la spec scrive `load_config()` senza argomenti); il file è obbligatorio per l'avvio.
- **C-06:** `schedule_task(task, trigger)` riceve il trigger APScheduler già interpretato; l'interpretazione di `schedule_type`/`schedule_expr` è di spec 02 (C-16), non inventata qui.
- **C-11:** `record(*, task_id, trigger, requested_by, started_at)` e `query(*, …)` usano parametri keyword; stessi dati e stessa semantica della spec.
- **C-01:** `Config.source` e la chiave `secrets_file` sono metadati di provenienza, non campi dichiarati in C-01; nessun effetto semantico.
- **C-02:** i repository usano la funzione `execute` di `storage/db.py`, che applica il retry breve su `database is locked`; `Database.execute_with_retry` è il wrapper pubblico della stessa funzione.

## Dipendenze e rischi

- **Dipendenze interne:** nessuna voce a monte. C-09/C-10/C-11 dipendono da C-02; C-03 da C-01/C-04; C-06 da C-02/C-09.
- **R1 — Ambiente Python 3.14.4 (fatto verificato con `python3 -V`, 2026-10-21):** `python-telegram-bot`/`APScheduler` potrebbero non installarsi o non supportare 3.14. Mitigazione applicata: install in `.deps` con `pip --target` (venv non creabile: `ensurepip` assente, symlink `lib64` non permesso dal filesystem); versioni risolte: python-telegram-bot 22.8, APScheduler 3.11.3, SQLAlchemy 2.1.5, httpx 0.28.1, pytest 9.1.1. Suite verde su 3.14.4.
- **R2 — Validazione su device:** wake-lock, kill di Android e watchdog reale non sono verificabili qui. Mitigazione: test con watchdog simulato; gap dichiarato nel documento architettura.
- **R3 — SQLite `database is locked`:** mitigato con WAL + retry con backoff breve.
- **R4 — Ambiguità gate:** C-27/C-28 non esistono in spec 01. Mitigazione: C-07 impone `approved=True`; nessuna implementazione del gate oltre il flag.
- **R5 — Segreti:** nessun token reale in repo; template solo placeholder; D-10 ignora `config/secrets*.env` con eccezione per `secrets.example.env`; verifica con `git check-ignore` nei criteri di validazione.

## Criteri di validazione ("done" per la voce)

1. `pytest` verde sull'intera suite, incluso AC-01…AC-05.
2. AC-01: avvio con config valido → config caricata, schema migrato, polling e scheduler avviati senza intervento manuale (gateway/LLM finti).
3. AC-02: campo mancante o segreto illeggibile → errore fatale, nessun avvio parziale.
4. AC-03: admin/authorized/unknown/revoked risolti correttamente e permessi applicati.
5. AC-04: 3 tentativi a 1 minuto prima del fallimento (tempo simulato).
6. AC-05: riavvio → job attivi ricaricati dallo stato persistito.
7. Schema DB conforme alla tabella della spec (tabelle, colonne, vincoli di stato).
8. Nessun segreto in repo o nei log; file sensibili `600` verificati nei test; `git check-ignore config/secrets.env` positivo e `config/secrets.example.env` tracciabile.
9. Diagrammi Mermaid presenti e coerenti con i modelli della spec.
10. Checkpoint `sdd-governor`: nessun failure critico; tracciabilità completa.
11. Spec aggiornata (`Stato`, note) e voce roadmap spuntata solo a publish.

## Ordine di consegna

Code-first, sequenza lineare senza duplicati: T0 (setup `.deps`/deps) → T1 (config, errori, retry) → T2 (logging) → T3 (storage) → T4 (ruoli) → T5 (LLM) → T6 (device/tool) → T7 (notifiche/storico) → T8 (scheduler) → T9 (execution) → T10 (gateway) → T11 (bootstrap/supervisor/boot) → T12 (consolidamento test) → T13 (documentazione) → T14 (validazione e publish).

## Tracciabilità

`Roadmap 01` → `docs/specs/01-agent-runtime.spec.md` → binding (tabella sopra) → T0…T14 → D-01…D-11 → validazione → publish.

| Criterio di validazione | Deliverable / prova |
|---|---|
| 1–2 (AC-01, avvio completo) | D-01 `app.py`, D-02 schema, D-07 `test_bootstrap.py` |
| 3 (AC-02, config fatale) | D-01 `config.py`, D-07 `test_config.py` |
| 4 (AC-03, ruoli) | D-01 `role_guard.py`, D-07 `test_role_guard.py` |
| 5 (AC-04, retry) | D-01 `retry.py`, D-07 `test_retry.py` |
| 6 (AC-05, restore job) | D-01 `scheduler.py`, D-02 job store, D-07 `test_scheduler.py` |
| 7 (schema conforme) | D-02 migrazione vs spec §Modello dati |
| 8 (segreti, permessi) | D-01 `config.py`, D-10 `.gitignore`, D-07 test permessi, `git check-ignore` |
| 9 (diagrammi) | D-08 documento architettura |
| 10 (governance) | checkpoint `sdd-governor` (sezione sopra) |
| 11 (stato e publish) | D-09 spec/constitution, voce roadmap |

## Gap registrati

- `docs/sdd/capability-registry.md` assente: discovery eseguita da frontmatter; nessun asset specializzato per codice, schema, config, script, test.
- Nessun governance agent alternativo: `sdd-governor` unico candidato per il checkpoint.
- Validazione su dispositivo reale non eseguibile in questo ambiente.
- Vista di deployment omessa: la spec 01 non la dichiara; nessun diagramma inventato.
- Struttura del documento D-08 e framework di test: scelte del piano, etichettate come assunzioni.
- `token.sh` in radice contiene segreti reali (segnalato dal checkpoint): aggiunto a `.gitignore`; **rotazione delle chiavi a carico dell'operatore** (non eseguibile qui). Prima del publish l'operatore verifica `git ls-files token.sh` e `git log --all -- token.sh`; se tracciato, purge della storia.
- Evento di ripartenza, tasto «Autorizza» e `web_search`: fuori scope, tracciati rispettivamente a spec 11, spec 08, spec 06.
- Soglia watchdog (300 s) e intervallo manutenzione (24 h): assunzioni del piano, non dichiarate dalla spec.
- Costanti di implementazione non dichiarate dalla spec: heartbeat 30 s e poll watchdog 5 s, timeout HTTP LLM 30 s, stima 4 caratteri/token per il troncamento, retry lock 3×0.1 s, split messaggi 4096 (limite della Bot API).

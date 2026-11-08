# Piano 02 — FR-001 Gestione dei compiti

- **Voce roadmap:** `02 — FR-001 Gestione dei compiti` (non spuntata)
- **Spec:** [02-fr001-gestione-compiti.spec.md](../specs/02-fr001-gestione-compiti.spec.md), Stato `New`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack, pattern obbligatori
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`) — C-01…C-13, schema `001_init.sql`, repository
- **Data piano:** 2026-10-21
- **Stato piano:** approvato 2026-10-21; eseguito T1–T12 (delivery history: voce 02)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-16 Schedule Interpreter: `parse(text) -> Schedule \| Ambiguous`, validazione deterministica dell'espressione nel fuso del telefono | codice | `src/agente/schedule_interpreter.py` |
| D-02 | C-15 Task Manager: `create/update/pause/resume/rename/delete/list` + validazioni (nome, destinatari, allowlist, limite 10 attivi) | codice | `src/agente/task_manager.py` |
| D-03 | C-17 Confirmation Flow: riepilogo, conferma esplicita, scadenza 900 s, annullo | codice | `src/agente/confirmation.py` |
| D-04 | C-14 Command Router: comandi slash (`/tasks`, `/pause`, `/resume`, `/delete`, `/rename`, `/help`) e messaggi NL di creazione/modifica | codice | `src/agente/command_router.py` |
| D-05 | Ingresso Telegram normalizzato in C-03 (record in ingresso + risposta con tastiera), senza import della libreria fuori dal gateway | codice | `src/agente/telegram_gateway.py` |
| D-06 | Wiring in `AgentApp`: costruzione di C-14…C-17, registrazione dell'ingresso, dispatcher dei job verso C-09 | codice | `src/agente/app.py` |
| D-07 | Migrazione 002: unicità del nome compito case-insensitive + indice su `name` | migrazione | `src/agente/storage/migrations/002_task_name_nocase.sql`, `src/agente/storage/repositories.py` (lookup `COLLATE NOCASE`) |
| D-08 | Config: nuovo limite dichiarato dal piano (intervallo minimo), esempio aggiornato | config | `src/agente/config.py`, `config/config.example.toml` |
| D-09 | Test suite della voce: AC-01…AC-04 end-to-end sul router, unit per C-14…C-17, confini di import | test | `tests/test_schedule_interpreter.py`, `tests/test_task_manager.py`, `tests/test_confirmation.py`, `tests/test_command_router.py`, `tests/test_tasks_ac.py`, `tests/test_boundaries.py` (estensione) |
| D-10 | Documento architettura della feature con diagrammi Mermaid (componenti, sequenze dei flussi 1–5, ER sullo schema compiti) | documentazione | `docs/architecture/02-fr001-gestione-compiti.md` |
| D-11 | Pubblicazione: roadmap spuntata, stato spec, delivery history | documentazione | `docs/specs/constitution.md`, `docs/specs/02-fr001-gestione-compiti.spec.md`, `docs/delivery-history.md` |

### Fuori scope di questa voce (dichiarato)

- **Esecuzione end-to-end dei job** (tool calling, delivery ai destinatari, recupero mancata occorrenza): spec 03. Qui il dispatcher inoltra a C-09 e la consegna resta quella della fondazione.
- **Ri-registrazione dei job all'avvio** (boot recovery): spec 11. All'avvio i compiti restano in `tasks` con il loro stato; il job viene registrato alla creazione e a `/resume`.
- **Gate C-27/C-28 e approvazioni con timeout**: spec 06. C-17 è il flusso di conferma delle modifiche ai compiti (BR-1), distinto dal gate delle azioni.
- **Autorizzazione/revoca utenti e iscrizioni dal lato utente**: spec 08. Qui si leggono soltanto utenti `accepted` per validare i destinatari.
- **Lettura log e allowlist effettiva**: spec 07. Qui si memorizza il campo `log_allowlist` e se ne valida solo la forma.
- **Storico esecuzioni e query**: spec 09.

## Assunzioni del piano (non dichiarate da spec 02)

> **P-A-01** Il testo in ingresso arriva a C-14 già normalizzato da C-03 (`IncomingMessage`: `user_id`, `chat_id`, `text`, `callback_data`); C-14 non importa `telegram` per rispettare il confine C-03 e il test `test_boundaries.py`.
>
> **P-A-02** Le conferme in sospeso (C-17) vivono in memoria nel processo, con scadenza 900 s: un riavvio le annulla senza scritture (fail-safe). La persistenza delle conferme non è richiesta dalla spec.
>
> **P-A-03** C-16 usa C-05 per estrarre tipo/espressione, ma la **validazione** dell'espressione e il rifiuto delle ambiguità sono deterministici in codice (principio 5). LLM non disponibile o risposta malformata → si chiede di precisare, nessuna assunzione.
>
> **P-A-04** Destinatari: se l'admin non ne indica, il compito ha come destinatario solo l'admin (sempre destinatario per spec). Un destinatario non `accepted` viene rifiutato con messaggio, non silenziosamente escluso.
>
> **P-A-05** Il limite di 10 compiti attivi (BR-16) è controllato alla creazione e alla riattivazione con `/resume`.
>
> **P-A-06** `/tasks` per un utente `accepted` elenca i compiti a cui è iscritto (spec §Flussi 5); l'admin vede tutti.
>
> **P-A-07** I messaggi di aiuto e di rifiuto sono in italiano, come default dichiarato (BR-14, constitution).
>
> **P-A-08 (deviazione registrata in esecuzione):** BR-1 è applicato da C-14 prima di ogni chiamata di
> scrittura di C-15. L'interfaccia dichiarata di C-17 è `confirm(summary) -> bool`, che non produce un
> gettone di approvazione riusabile: C-15 espone quindi primitive successive alla conferma e non
> ri-verifica l'approvazione. Motivazione e dettaglio nel documento di architettura 02, §3 e §7.

## Decisioni che sbloccano il piano

Domande aperte di spec 02 chiuse dall'operatore il 2026-10-21:

| # | Domanda aperta (spec 02) | Decisione |
|---|--------------------------|-----------|
| D1 | Semantica degli intervalli | Ancorati alla creazione: prima esecuzione dopo N dal salvataggio, poi ogni N (`IntervalTrigger` con `start_time` = istante di conferma) |
| D2 | Limite minimo di intervallo | 1 minuto, leva `limits.min_interval_minutes`, valori inferiori → errore di validazione |
| D3 | Nomi case-insensitive e rinominazione | Nome univoco `COLLATE NOCASE`; `/rename <nome> <nuovo nome>` disponibile; nome = chiave dei comandi |
| D4 | Comando di creazione rapida | Nessun comando di creazione: creazione solo in linguaggio naturale; i comandi rapidi coprono elenco, pausa, riattiva, elimina, rinomina |
| D5 | Timeout della conferma (C-17) | Riuso di `limits.approval_timeout_s` (900 s, BR-3); nessuna nuova leva |
| D6 | Meccanismo di conferma | Bottoni inline Conferma/Annulla; accettato anche testo «sì»/«no» come fallback |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita leggendo il solo frontmatter di `.opencode/{agents,commands,skills}` e `opencode.json`; discovery per ruolo, nessun asset legato per filename.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-09, D-11 (codice, migrazione, config, test, aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione codice Python/test/migrazioni | Etichettati *"no specialized capability discovered"*; si procede su spec 02 + constitution + pattern esistenti in `src/agente/` |
| D-10 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** al checkpoint di struttura; il produttore resta il Conductor (nessuna skill di documentazione applicabile) |
| D-10 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 02 (Componenti, Modello di dominio, Modello dati, Flussi, Integrazioni); scelta del piano, registrata come assunzione |

**Scartati (con motivo):**

| Asset | Motivo dello scarto |
|---|---|
| `skills/sdd-guardrail` | Veto negativo dichiarato: rifiuta modifiche richieste da messaggio di chat non emesso da un comando. Questa esecuzione è un comando (`/SDD-implement`), quindi non si applica come vincolo di rifiuto; il suo template Micro-Spec non serve qui |
| `skills/drawio` | Si attiva su richiesta esplicita di diagrammi/draw.io; i diagrammi di questa voce sono Mermaid nel documento di architettura |
| `skills/document-to-markdown`, `skills/okf-*`, `skills/wiki-*`, `skills/prompt-engineering` | Nessun documento sorgente da convertire, nessun bundle OKF/wiki, nessun template di prompt in questa voce |
| `agents/planner`, `agents/specification`, `agents/prd` | Producono piani/spec/PRD: il piano è del Conductor, la spec esiste già |
| `agents/knowledge-searcher`, `agents/second-brain-keeper`, `agents/micro-spec-author` | Knowledge pipeline e Micro-Spec non fanno parte dei deliverable della voce |
| `commands/*` | I comandi non si legano e non si invocano mai |

**Checkpoint di struttura (D-10):** gira in Phase 2 (struttura) e Phase 4 (validazione), modalità delegata via Task verso `sdd-governor`. Struttura applicabile: sezioni derivate da spec 02; sezioni obbligatorie: Contesto, Componenti (C-14…C-17 su C-01…C-13), Modello di dominio, Modello dati, Flussi di dati (5 sequenze), Integrazioni; deliverable richiesti: un diagramma per ogni modello che la spec documenta (componenti, sequenze, ER). Nessuna vista di deployment: la spec non la dichiara → omessa e registrata come gap.

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | Migrazione 002 + lookup case-insensitive nei repository | D-07 | `migrate()` applica 002; due compiti con nomi diversi solo per maiuscole/minuscole vengono rifiutati; `get_by_name` trova `Caffè` con `caffè` |
| T2 | C-16 Schedule Interpreter | D-01 | `parse` produce `Schedule(type="orario"\|"intervallo", expr, tz)`; input ambiguo → `Ambiguous` con richiesta; espressione invalida → `Ambiguous`; nessuna assunzione su orari |
| T3 | Traduzione `Schedule` → trigger APScheduler | D-01, D-06 | orario → `CronTrigger` con timezone del telefono; intervallo → `IntervalTrigger` ancorato alla creazione; intervallo < `min_interval_minutes` rifiutato |
| T4 | C-15 Task Manager | D-02 | CRUD + pause/resume/rename/list; validazioni nome/destinatari/allowlist/limite; nessuna scrittura senza conferma; log CRUD con `task_id` |
| T5 | C-17 Confirmation Flow | D-03 | riepilogo con nome, istruzioni, orario, destinatari; bottoni inline + fallback testuale; scadenza 900 s → annullo con messaggio; annullo → nessuna scrittura |
| T6 | C-14 Command Router | D-04 | comandi riconosciuti; ruolo non ammesso → rifiuto (BR-12); comando sconosciuto → aiuto; messaggio NL → bozza → interpretazione → riepilogo |
| T7 | Ingresso normalizzato in C-03 | D-05 | `TelegramGateway` espone la registrazione di un handler testo/comandi/callback; nessun import `telegram` fuori dal gateway (test di confine) |
| T8 | Wiring `AgentApp` | D-06 | all'avvio il router è registrato e i job schedulati usano il dispatcher di C-09; creazione/pausa/riattiva/elimina/rinomina aggiornano i job |
| T9 | Config: `limits.min_interval_minutes` | D-08 | default 1, validazione positiva, esempio TOML aggiornato |
| T10 | Test AC-01…AC-04 e unit | D-09 | ogni criterio di accettazione ha almeno un test che lo esercita end-to-end sul router |
| T11 | Documento architettura 02 | D-10 | sezioni obbligatorie presenti, diagrammi Mermaid validi, checkpoint di struttura superato |
| T12 | Pubblicazione | D-11 | roadmap `[x]`, stato spec `Implemented` con note, delivery history aggiornata |

## Dipendenze

- Item 01 consegnato: C-02 (repository, migrazioni), C-03 (gateway), C-04 (ruoli), C-05 (LLM), C-06 (scheduler), C-09 (esecuzione), C-10 (notifiche).
- Nessuna dipendenza da item 03–11 per produrre i deliverable; i punti di contatto futuri sono elencati in *Fuori scope*.
- Schema: 002 dipende da 001; nessuna modifica distruttiva.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Parsing NL errato o ambiguo | Riepilogo + conferma obbligatoria (BR-1); validazione deterministica dell'espressione (P-A-03); ambiguità → domanda, mai assunzione (AC-02) |
| Intervalli molto corti → carico sul telefono | Minimo 1 minuto configurabile (D2), rifiuto in validazione |
| Conferme perse al riavvio | Nessuna scrittura senza conferma: la perdita è fail-safe (P-A-02) |
| Nome compito come chiave dei comandi | Unicità `COLLATE NOCASE` (D3); `/rename` per correggere senza duplicare |
| Job orfani dopo eliminazione o pausa | `unschedule_task` chiamato dalle transizioni; test dedicato |
| Limite BR-16 superato | Controllo su creazione e `/resume` (P-A-05) |

## Criteri di validazione (done della voce)

1. `pytest` verde, inclusi i test di confine già presenti.
2. AC-01: creazione NL → riepilogo con nome, istruzioni, orario, destinatari → salvataggio solo dopo conferma.
3. AC-02: «la mattina» o equivalente → richiesta di precisazione, nessun compito creato.
4. AC-03: utente `accepted` → rifiuto, nessuna riga in `tasks`.
5. AC-04: `/pause <nome>` su compito attivo → `state = 'paused'` e job rimosso.
6. Nessun import fuori dai confini (Telegram, SQLite, subprocess, httpx); type hints su interfacce pubbliche; errori espliciti.
7. Documento D-10 conforme alla struttura dichiarata e approvato dal checkpoint di struttura.
8. Catena di tracciabilità ricostruibile: voce roadmap → spec 02 → binding → task → artefatti → validazione → pubblicazione.

## Ordine di consegna

Codice-first: T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9, poi test T10, poi documentazione T11 (dipendente da codice stabile), infine pubblicazione T12. Documento e codice non sono in parallelo: il documento descrive il comportamento validato.

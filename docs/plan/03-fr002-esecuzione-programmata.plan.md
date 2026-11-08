# Piano 03 — FR-002 Esecuzione programmata

- **Voce roadmap:** `03 — FR-002 Esecuzione programmata` (non spuntata)
- **Spec:** [03-fr002-esecuzione-programmata.spec.md](../specs/03-fr002-esecuzione-programmata.spec.md), Stato `New`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack, `## Roadmap`
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`: C-01…C-13, schema `001_init.sql`, repository) e item 02 (`02-fr001-gestione-compiti`: C-14…C-17, migrazione 002, `trigger_for()`, dispatcher in `app.py`)
- **Data piano:** 2026-10-24
- **Stato piano:** approvato 2026-10-24; eseguito T1–T14 (delivery history: voce 03).

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-18 Schedule Registrar: `register(task)`, `update(task)`, `unregister(task_id)`; traduzione `Schedule`→trigger via C-16, persistenza marcatore `next_run`, delega meccanica a C-06 | codice | `src/agente/schedule_registrar.py` |
| D-02 | C-19 Recovery Handler: `recover_missed() -> list[ExecutionResult]`; rilevamento occorrenze mancate dall'ultimo `next_run`, esecuzione della sola ultima, marcatura delle precedenti come `saltata`; watcher connettività | codice | `src/agente/recovery.py` |
| D-03 | C-20 Delivery Service: `deliver(task, result)`; destinatari = admin + iscritti `accepted` filtrati al momento dell'invio | codice | `src/agente/delivery.py` |
| D-04 | Estensione C-09: loop tool-calling read-only, consegna del risultato a C-20, esito `errore` + avviso admin quando il fallimento persiste dopo i retry | codice | `src/agente/execution.py` |
| D-05 | Estensione C-06: avvio in pausa, `resume()`, lettura job persistiti; nessun cambio di semantica dei trigger | codice | `src/agente/scheduler.py` |
| D-06 | Wiring `AgentApp`: C-18/C-19/C-20, sequenza di avvio `gateway → scheduler(paused) → seed marcatori → recupero → resume`, dispatcher con controllo online e refresh `next_run`, job watcher connettività | codice | `src/agente/app.py` |
| D-07 | Riallineamento C-15: creazione/update/pausa/riattiva/elimina passano da C-18 invece che da C-06 diretto | codice | `src/agente/task_manager.py` |
| D-08 | Migrazione 003: ricostruzione tabella `executions` con esito ammesso `saltata`; `ExecutionRepository.finish` e `HistoryService` accettano/marcano `saltata` | migrazione | `src/agente/storage/migrations/003_execution_skipped.sql`, `src/agente/storage/repositories.py`, `src/agente/history.py` |
| D-09 | Config: nuova leva `limits.connectivity_check_s` (default 60), esempio aggiornato | config | `src/agente/config.py`, `config/config.example.toml` |
| D-10 | Test suite della voce: unit C-18/C-19/C-20, estensione C-09, AC-01…AC-03 end-to-end; aggiornamento fixture e test esistenti toccati dal rebind C-15→C-18 | test | `tests/test_schedule_registrar.py`, `tests/test_recovery.py`, `tests/test_delivery.py`, `tests/test_execution.py`, `tests/test_scheduled_ac.py`, `tests/conftest.py`, `tests/test_task_manager.py`, `tests/test_tasks_ac.py`, `tests/test_boundaries.py` |
| D-11 | Documento architettura della feature con diagrammi Mermaid (componenti, sequenze dei flussi 1–4, ER `executions`; `settings` descritta a testo) | documentazione | `docs/architecture/03-fr002-esecuzione-programmata.md` |
| D-12 | Emendamento BR-15: esito `saltata` aggiunto al modello di dominio e ai vincoli (constitution §9, spec 01 §Modello dati, spec 09 §Modello di dominio), tracciato come decisione D1 del 2026-10-24 | documentazione | `docs/specs/constitution.md`, `docs/specs/01-agent-runtime.spec.md`, `docs/specs/09-fr008-storico-esecuzioni.spec.md` |
| D-13 | Pubblicazione: roadmap `[x]`, stato spec `Implemented` + note, delivery history, allineamento del piano | documentazione | `docs/specs/constitution.md`, `docs/specs/03-fr002-esecuzione-programmata.spec.md`, `docs/delivery-history.md`, questo piano |

### Fuori scope di questa voce (dichiarato)

- **Riavvio e liveness (FR-010, spec 11):** messaggio di ripartenza, segnale di vita, watchdog dell'avvio, ri-registrazione esplicita dei job. I job restano persistiti nello job store di C-06; spec 11 orchestra il boot e deve **delegare** il recupero a C-19, non reimplementarlo.
- **Gate C-27/C-28 e azioni modificanti (spec 06):** nessuno strumento modificante viene eseguito. Richiesta dal LLM di uno strumento non read-only → esito `errore` + avviso admin (fail-safe, principio 1). `web_search` non è registrato: provider a spec 06.
- **Lettura log e semantica dell'allowlist (spec 07):** C-09 inoltra `task.log_allowlist` al tool `read_logs`; la validazione dei percorsi resta di C-07/spec 07.
- **Politica degli avvisi (spec 10):** qui si emettono solo gli avvisi richiesti dai flussi 3 e 4 di spec 03 (`alert_admin`); soglie e formati restano a spec 10.
- **Lock persistente per compito (C-22, spec 04):** il lock di C-09 resta in memoria; il rischio residuo è dichiarato in §Rischi.
- **Query dello storico (spec 09):** l'esito `saltata` è scritto e interrogabile con i filtri esistenti; presentazione e query per ruolo a spec 09.
- **Chat e domande libere (spec 05), gestione utenti (spec 08).**

## Decisioni che sbloccano il piano

Domande aperte di spec 03 chiuse dall'operatore il 2026-10-24. Ogni decisione è A (raccomandazione) e vale come vincolo di esecuzione.

| # | Domanda aperta / conflitto | Decisione | Impatto |
|---|----------------------------|-----------|---------|
| D1 | C-19 prescrive di registrare le occorrenze come `saltate`, ma BR-15, constitution §9 e CHECK di `executions` ammettono solo `ok\|errore\|interrotto` | Nuovo esito **`saltata`** in `executions`, una riga per occorrenza saltata, `trigger='scheduled'`, `started_at = finished_at =` istante dell'occorrenza, summary esplicito | Migrazione 003 (ricostruzione tabella + CHECK esteso), emendamento D-12 di BR-15/spec 01, nota in spec 03; deviazione dichiarata in architettura |
| D2 | Definizione di «offline» e perimetro AC-02 («quando l'agente riparte») | Offline = **rete assente** (C-07 `is_online()`). C-19 recupera sia al rientro online durante il processo sia **all'avvio**; messaggio di ripartenza e liveness restano a spec 11, che dovrà delegare a C-19 | Sequenza di avvio in D-06; riparto di responsabilità C-19/C-39 in §Riparto |
| D3 | Tool calling richiesto dal flusso 1, ma gate spec 06 e allowlist spec 07 non consegnati | Loop tool-calling **solo read-only**; strumento modificante richiesto → `errore` + avviso admin; `web_search` assente | C-09 esteso (D-04); nessuna anticipazione di spec 06/07 |
| D4 | Nessun intervallo di verifica connettività dichiarato | Nuova leva **`limits.connectivity_check_s`**, default **60 s** | Config D-09, watcher in D-06, assunzione P-A-05 |
| D5 | Dove applicare gli 3 tentativi a 1 minuto (BR-8) | **Nessun retry esterno**: i 3×1 min restano dentro C-05 (LLM) e C-10/C-03 (Telegram). Fallimento persistente → esito `errore` + avviso admin; consegna parziale fallita → `errore` con elenco destinatari non raggiunti, nessuna nuova esecuzione del ragionamento | C-09 (D-04), C-20 (D-03), assunzione P-A-06 |

## Riparto di responsabilità tra componenti (anti-duplicazione)

| Componente spec 03 | Possiede | Delega a | Non duplica perché |
|---|---|---|---|
| C-18 Schedule Registrar | Politica di registrazione: traduzione `Schedule`→trigger (C-16), persistenza del marcatore `next_run`, refresh dopo ogni occorrenza | C-06 per l'operazione meccanica `add_job`/`remove_job`/`next_run` | C-06 è il meccanismo APScheduler; C-18 è il livello che rende il job recuperabile. C-15 smette di chiamare C-06 direttamente (D-07) |
| C-19 Recovery Handler | Rilevamento delle occorrenze mancate, semantica «una sola volta, ultima occorrenza», marcatura `saltata` | C-09 per l'esecuzione, C-11 per lo storico, C-07 per lo stato online | C-39 (spec 11) orchestrerà l'avvio e chiamerà C-19; il marcatore avanzato rende l'operazione idempotente |
| C-20 Delivery Service | Calcolo dei destinatari (admin implicito + iscritti `accepted` al momento dell'invio), esito per destinatario | C-10 per l'invio e lo split/retry del trasporto | C-10 è trasporto e messaggistica; C-20 è politica dei destinatari del risultato |
| C-09 Execution Engine | Lock, contesto, loop LLM/tool, timeout, esito, chiamata a C-20 | C-05, C-08, C-07 (tramite tool registry), C-11 | Restano invariati i confini già dichiarati da spec 01 |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita leggendo il solo frontmatter di `.opencode/{agents,commands,skills}` e `opencode.json`; discovery per ruolo, nessun asset legato per filename.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-10, D-12, D-13 (codice, migrazione, config, test, emendamento e aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione di codice Python, test o migrazioni | Etichettati *"no specialized capability discovered"*; si procede su spec 03 + constitution + pattern esistenti in `src/agente/` |
| D-11 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** (Phase 2 struttura e Phase 4 validazione); il produttore resta il Conductor |
| D-11 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 03 + blocco metadata e stile di `docs/architecture/02-fr001-gestione-compiti.md`; scelta registrata come assunzione P-A-10 |

**Scartati (con motivo):**

| Asset | Motivo dello scarto |
|---|---|
| `skills/sdd-guardrail` | Veto negativo dichiarato: rifiuta modifiche richieste da messaggio di chat non emesso da un comando. Questa esecuzione è `/SDD-implement`; il suo template Micro-Spec non serve |
| `skills/drawio` | Si attiva su richiesta esplicita di diagrammi/draw.io; qui i diagrammi sono Mermaid nel documento di architettura |
| `skills/document-to-markdown`, `skills/okf-*`, `skills/wiki-*`, `skills/prompt-engineering` | Nessun documento sorgente da convertire, nessun bundle OKF/wiki, nessun template di prompt |
| `agents/planner`, `agents/specification`, `agents/prd` | Producono piani/spec/PRD: il piano è del Conductor, la spec esiste già |
| `agents/knowledge-searcher`, `agents/second-brain-keeper`, `agents/micro-spec-author` | Knowledge pipeline e Micro-Spec non fanno parte dei deliverable |
| `commands/*` | I comandi non si legano e non si invocano mai |

**Checkpoint di struttura (D-11) — Phase 2, modalità delegata:** eseguito il 2026-10-24 su `sdd-governor` con esito **NOT APPROVED** (8 MAJOR, 8 MINOR) sullo schema proposto. Remediation recepita in questo piano:

- blocco metadata e nota di struttura dichiarata (spec 03, nessun template) → §Inventario/§Checkpoint;
- sezioni obbligatorie aggiunte: §Domande aperte, §Rischi e assunzioni, §Fuori scope, §Riparto, §Tracciabilità BR;
- `saltata` non più risoluzione unilaterale: decisione operatore D1 + emendamento D-12 di constitution/spec 01;
- riparto C-19/C-39 e anti-doppio-recupero dichiarati;
- riparto C-18→C-06/C-15 e C-20→C-10/C-03 dichiarato;
- perimetro corretto: C-18 dipende anche da C-16 (spec 02);
- tool calling read-only e `web_search` assente dichiarati;
- per-componente con Input/Output/Sicurezza; Sicurezza e NFR tenute separate;
- diagrammi giustificati: 1 flowchart componenti, 4 sequenceDiagram, 1 erDiagram su `executions`; `settings` a testo; nessuna vista deployment (non dichiarata).

Struttura applicabile dopo remediation: Contesto e obiettivi · Metadata · Componenti C-18/C-19/C-20 su C-01…C-13 · Riparto · Modello di dominio · Modello dati · Flussi di dati (1–4) · Integrazioni · Sicurezza · Requisiti non funzionali · Rischi e assunzioni · Domande aperte · Fuori scope · Tracciabilità (AC e BR) · Deviazioni. Deliverable richiesti: i diagrammi sopra. La validazione di struttura definitiva è la Phase 4 sull'artefatto reale: la produzione resta subordinata all'approvazione del piano.

## Assunzioni del piano (non dichiarate da spec 03)

> **P-A-01** Il marcatore di recupero è persistito in `settings` con chiave `next_run:<task_id>` (ISO 8601 con offset). Spec 03 dichiara solo «`next_run` per i compiti»: il nome della chiave è scelta del piano.
>
> **P-A-02** Il periodo offline è persistito in `settings` con chiave `offline_since` («ultimo periodo offline» di spec 03). Il ritorno online aggiorna `last_contact_at` con il meccanismo già dichiarato da spec 01 (BR-10); non si introduce un secondo nome equivalente.
>
> **P-A-03** La catena delle occorrenze mancate si calcola iterando `trigger.get_next_fire_time()` dal marcatore persistito fino all'istante di recupero, con tetto di 1000 iterazioni per compito; superato il tetto si esegue l'ultima occorrenza trovata e si registra il troncamento nel log.
>
> **P-A-04** Dopo un recupero il job viene ri-registrato da C-18 con ancora «adesso» anche per gli intervalli (coerente con D1 di piano 02: ancora a creazione o ripresa). La spec non dichiara la cadenza dopo un recupero.
>
> **P-A-05** Il watcher di connettività è un job C-06 con id `connectivity:check`, intervallo `limits.connectivity_check_s`; al rientro online invoca C-19 una sola volta e in modo serializzato. `is_online()` è bloccante (subprocess Termux:API) e viene eseguito in thread.
>
> **P-A-06** Se la consegna fallisce per almeno un destinatario dopo i retry del trasporto, l'esito dell'esecuzione è `errore` con summary che elenca i destinatari non raggiunti, anche se il testo è stato generato; nessuna nuova esecuzione del ragionamento.
>
> **P-A-07** `ExecutionResult` espone anche il testo completo prodotto (`text`), usato da C-20; `summary` resta troncato per lo storico. Spec 03 elenca solo `summary` nel modello di dominio: campo aggiuntivo dichiarato come deviazione.
>
> **P-A-08** Il loop tool-calling è limitato a 5 cicli di chiamata LLM per esecuzione; l'output di ogni tool è troncato a 20.000 caratteri prima di tornare al modello. Nessuna soglia è dichiarata dalla spec.
>
> **P-A-09** Il timeout BR-4 (10 min) racchiude ragionamento, tool e consegna: allo scadere l'esito è `interrotto` e l'admin è avvisato. L'await viene abbandonato; una chiamata HTTP sincrona già in corso in thread non è interrompibile a livello di socket (limite della fondazione, dichiarato).
>
> **P-A-10** Struttura del documento di architettura derivata da spec 03 e dal documento 02, non da un template: nessun template è dichiarato nel progetto.
>
> **P-A-11** Al primo avvio dopo l'aggiornamento non esistono marcatori `next_run` per i compiti creati dall'item 02: C-18 li inizializza dai job persistiti prima del recupero, senza ri-registrare i job (l'ancora degli intervalli resta invariata).

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | Migrazione 003 (`saltata`) + repository/history | D-08 | `migrate()` applica 003; `outcome='saltata'` accettato; esiti illegali ancora rifiutati; indice `idx_executions_task_started` ricreato; dati 001/002 preservati |
| T2 | Emendamento BR-15 in constitution §9 e spec 01 §Modello dati | D-12 | I due documenti elencano `saltata` con nota della decisione D1 (2026-10-24); nessuna contraddizione residua nelle fonti |
| T3 | C-18 Schedule Registrar | D-01 | `register/update/unregister` usano C-16 e C-06; marcatore `next_run` scritto e cancellato; trigger orario/intervallo invariati rispetto a item 02; log con `next_run` |
| T4 | Rebind C-15 → C-18 | D-07 | Creazione, modifica orario, pausa, riattiva, eliminazione aggiornano job e marcatore via C-18; nessuna doppia registrazione; test 02 aggiornati |
| T5 | C-19 Recovery Handler | D-02 | Con marcatori a 08:00 e ora 09:30 esegue **una** volta l'ultima occorrenza (`trigger='recovery'`); le precedenti sono righe `saltata`; senza marcatore non recupera; marcatore finale avanzato al futuro; log del conteggio saltate |
| T6 | Watcher connettività e marcatore offline | D-02, D-09 | `is_online()` falso → `offline_since` scritto; al ritorno online → recupero, `last_contact_at` aggiornato, `offline_since` rimosso; job `connectivity:check` con intervallo da config |
| T7 | C-20 Delivery Service | D-03 | Destinatari = admin + iscritti `accepted`; revocati esclusi al momento dell'invio; split dei messaggi via C-10; report per destinatario; log destinatari ed esiti |
| T8 | Estensione C-09: tool loop read-only, consegna, avviso su errore | D-04 | Tool read-only eseguiti e risultato reinviato al modello; richiesta di tool modificante/sconosciuto → `errore` + avviso admin, nessuna azione; successo → C-20; timeout → `interrotto` + avviso; lock invariato |
| T9 | C-06 avvio in pausa e resume | D-05 | `start(paused=True)` e `resume()` disponibili; job persistiti leggibili prima del resume; comportamento esistente invariato quando non usati |
| T10 | Wiring e sequenza di avvio `app.py` | D-06 | All'avvio: gateway → scheduler in pausa → seed marcatori → recupero se online → resume → watcher; dispatcher salta l'esecuzione se offline senza avanzare il marcatore, altrimenti esegue e aggiorna `next_run` |
| T11 | Config `limits.connectivity_check_s` | D-09 | Default 60, validazione intero positivo, esempio TOML aggiornato, limite esposto in `LimitsConfig` |
| T12 | Test AC-01…AC-03 e unit | D-10 | AC-01: job attivo alle 08:00 → destinatari ricevono il risultato senza intervento; AC-02: offline alle 08:00, online alle 09:30 → una sola esecuzione di recupero; AC-03: oltre 600 s → `interrotto` + avviso admin; `pytest` verde |
| T13 | Documento architettura 03 | D-11 | Sezioni obbligatorie presenti; Mermaid validi (componenti, 4 sequenze, ER `executions`); checkpoint di struttura Phase 4 **APPROVED**; nessuna vista deployment, gap registrato |
| T14 | Pubblicazione | D-13 | Roadmap 03 `[x]`; spec 03 `Implemented` + note (incluso emendamento D1); delivery history con esito e gap; piano marcato eseguito |

## Dipendenze

- Item 01: C-02 repository/migrazioni, C-03 gateway, C-05 LLM (retry BR-8), C-06 scheduler, C-07 device, C-08 tool registry, C-09 motore, C-10 notifiche, C-11 storico.
- Item 02: C-16 espressioni canoniche, `trigger_for()`, C-15 Task Manager, dispatcher job→C-09, migrazione 002.
- Migrazione 003 dipende da 001 (e convive con 002); nessuna modifica distruttiva di dati.
- Spec 11 consumerà C-19 per il boot; spec 09 leggerà l'esito `saltata`; spec 04 porterà il lock persistente C-22.
- Nessuna dipendenza bloccante da spec 04–11 per i deliverable di questa voce.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Doppio recupero (C-19 + futuro C-39 di spec 11) | Marcatore `next_run` avanzato dopo il recupero e `offline_since` rimosso: seconda chiamata non trova occorrenze. Riparto scritto in §Riparto e vincolo per spec 11 |
| Recupero con molte occorrenze mancate | Una sola esecuzione (l'ultima); le altre `saltata`; tetto iterazioni P-A-03 |
| Retry LLM/Telegram dentro il timeout 10 min | BR-8 resta dentro C-05/C-10; allo scadere esito `interrotto` + avviso (P-A-09); nessun retry esterno (D5) |
| Consegna parziale (destinatario non raggiungibile) | Esito `errore` con elenco destinatari, avviso admin; nessuna riesecuzione del ragionamento (P-A-06) |
| Marcatore `next_run` mancante o corrotto | Nessun recupero (fail-safe); log esplicito; C-18 lo ricrea all'avvio (P-A-11) |
| Lock in memoria perso al riavvio (C-22 non consegnato) | Overlap mitigato da `max_instances=1` e `coalesce=True` di C-06; rischio residuo dichiarato, C-22 a spec 04 |
| Tool modificante richiesto dal modello | Fail-safe: nessuna esecuzione, esito `errore` + avviso; gate completo a spec 06 |
| Ora del telefono/timezone | Trigger senza timezone forzata (BR-14); istanti persistiti con offset |
| Emendamento BR-15 disallineato in spec 09 | Nota di allineamento in spec 01 e spec 03; verifica esplicita quando spec 09 sarà implementata |

## Criteri di validazione (done della voce)

1. `PYTHONPATH=src:.deps python3 -m pytest` verde (inclusi test di confine).
2. AC-01: compito attivo alle 08:00 → risultati recapitati a tutti i destinatari autorizzati, nessun intervento.
3. AC-02: offline alle 08:00, rientro alle 09:30 → una sola esecuzione di recupero; occorrenze intermedie registrate `saltata`.
4. AC-03: superamento dei 600 s → interruzione, esito `interrotto` nello storico, avviso all'admin.
5. BR-4/5/8/14 verificati: timeout, recupero singolo, retry interni, timezone del telefono.
6. BR-2/12/13/16 rispettati: nessuna azione modificante senza gate, risultati solo a destinatari autorizzati, allowlist passata al tool, limite 10 compiti attivi invariato.
7. Nessun import fuori dai confini (Telegram, SQLite, subprocess, httpx); type hints su interfacce pubbliche; errori espliciti; italiano di default.
8. Migrazione 003 reversibile nei dati (copia integrale di `executions`) e verificata su DB con righe preesistenti.
9. Documento D-11 conforme alla struttura dichiarata e approvato dal checkpoint Phase 4.
10. Catena di tracciabilità ricostruibile: voce roadmap 03 → spec 03 → binding → task → artefatti → validazione → pubblicazione.

## Tracciabilità attesa (compilata a Publish)

| Requisito / criterio | Test previsto |
|---|---|
| AC-01 esecuzione programmata con consegna | `tests/test_scheduled_ac.py::test_scheduled_task_delivers_to_all_recipients` |
| AC-02 recupero una sola volta dopo offline | `tests/test_scheduled_ac.py::test_offline_missed_occurrence_recovered_once`, `tests/test_recovery.py` |
| AC-03 timeout 600 s → interrotto + avviso | `tests/test_scheduled_ac.py::test_timeout_marks_interrupted_and_alerts_admin`, `tests/test_execution.py` |
| BR-4 timeout esecuzione | `tests/test_execution.py` |
| BR-5 recupero / occorrenze saltate | `tests/test_recovery.py` |
| BR-8 retry (delegati a C-05/C-10) | `tests/test_llm.py`, `tests/test_notifications.py`, `tests/test_delivery.py` |
| BR-14 timezone del telefono | `tests/test_schedule_registrar.py` |
| BR-2/12/13/16 sicurezza e limiti | `tests/test_execution.py`, `tests/test_delivery.py`, `tests/test_boundaries.py` |

## Ordine di consegna

Codice-first: T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10 → T11, poi test T12, poi documentazione T13 (dipendente da codice stabile), infine pubblicazione T14. Documento e codice non in parallelo: il documento descrive il comportamento validato.

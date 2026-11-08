# Delivery history

Registro delle voci di roadmap completate. La fonte di stato resta la `## Roadmap` della
[constitution](specs/constitution.md); questo file conserva l'esito della validazione.

## 01 — Agent Runtime (fondazione) — 2026-10-21

**Spec:** [01-agent-runtime.spec.md](specs/01-agent-runtime.spec.md) (Stato: Implemented)
**Piano:** [01-agent-runtime.plan.md](plan/01-agent-runtime.plan.md)
**Architettura:** [01-agent-runtime.md](architecture/01-agent-runtime.md)

### Deliverable

- `src/agente/` — C-01 Config, C-02 Storage, C-03 Telegram Gateway, C-04 Role Guard,
  C-05 LLM Client, C-06 Scheduler, C-07 Device Adapter, C-08 Tool Registry, C-09 Execution
  Engine, C-10 Notification Service, C-11 History & Retention, C-12 Supervisor, C-13 Logging.
- `src/agente/storage/migrations/001_init.sql` — 8 tabelle della spec + indici.
- `config/config.example.toml`, `config/secrets.example.env`.
- `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`.
- `scripts/boot/start-agent.sh`, `scripts/boot/90-agent.sh` — wake-lock e loop di riavvio.
- `tests/` — 74 test: AC-01…AC-05, unit per componente, confini di integrazione.
- `docs/architecture/01-agent-runtime.md` — Mermaid: contesto, componenti, 5 sequenze, data flow, ER.

### Validazione

- Suite: `PYTHONPATH=.deps python3 -m pytest` → **74 passed** su Python 3.14.4.
- AC-01 avvio completo, AC-02 config fatale, AC-03 ruoli, AC-04 retry 3×/1 min (LLM e
  Telegram), AC-05 ricarica job: coperti da test.
- Schema conforme a spec §Modello dati; confini Telegram/DeepSeek/SQLite/subprocess verificati
  da `tests/test_boundaries.py`.
- Segreti: nessun valore reale nei file versionati; `config/secrets*.env` e `token.sh` ignorati.
- Governance: checkpoint `sdd-governor` finale **PASS WITH FINDINGS** (2026-10-21). Residui non
  bloccanti: costanti non dichiarate dalla spec annotate nel piano; `token.sh` da ruotare;
  validazione su dispositivo reale; AC-05 verificato con `BackgroundScheduler` più controllo del
  tipo `AsyncIOScheduler` di produzione.
- `token.sh`: non tracciato da git e mai comparso nella storia (`git ls-files`, `git log --all`);
  la rotazione delle chiavi resta consigliata perché i valori sono in chiaro nel file.

### Gap e follow-up

- Evento di ripartenza → spec 11; tasto «Autorizza» → spec 08; `web_search` e gate C-27/C-28 →
  spec 06.
- Validazione su dispositivo reale (wake-lock, kill di Android, watchdog) non eseguibile in
  questo ambiente.
- Assunzioni non dichiarate dalla spec: soglia watchdog 300 s, manutenzione ogni 24 h,
  `search` opzionale.
- `token.sh` contiene segreti reali: rotazione delle chiavi a carico dell'operatore.

## 02 — FR-001 Gestione dei compiti — 2026-10-21

**Spec:** [02-fr001-gestione-compiti.spec.md](specs/02-fr001-gestione-compiti.spec.md) (Stato: Implemented)
**Piano:** [02-fr001-gestione-compiti.plan.md](plan/02-fr001-gestione-compiti.plan.md)
**Architettura:** [02-fr001-gestione-compiti.md](architecture/02-fr001-gestione-compiti.md)

### Deliverable

- `src/agente/schedule_interpreter.py` — C-16 Schedule Interpreter: forme italiane deterministiche,
  espressioni canoniche `HH:MM`, `HH:MM@LUN,MAR`, `Nm`/`Nh`, ambiguità mai assunte.
- `src/agente/task_manager.py` — C-15 Task Manager: CRUD, validazioni, nomi univoci
  case-insensitive, destinatari autorizzati, limite 10 compiti attivi (BR-16).
- `src/agente/confirmation.py` — C-17 Confirmation Flow: riepilogo, bottoni inline, fallback
  testuale «sì»/«no», scadenza 900 s, annullo.
- `src/agente/command_router.py` — C-14 Command Router: comandi slash, comandi e modifiche in NL,
  rifiuto per ruolo, creazione con bozza LLM.
- `src/agente/telegram_gateway.py` — ingresso normalizzato (`IncomingMessage`) e handler in
  background: l'attesa di conferma non blocca il polling.
- `src/agente/scheduler.py` — `trigger_for()`: `CronTrigger` per orari, `IntervalTrigger` ancorato
  alla registrazione per intervalli.
- `src/agente/app.py` — wiring di C-14…C-17 e dispatcher job C-06 → C-09.
- `src/agente/storage/migrations/002_task_name_nocase.sql` — unicità del nome `COLLATE NOCASE`.
- `src/agente/config.py`, `config/config.example.toml` — `limits.min_interval_minutes` (default 1).
- `tests/` — 139 test: AC-01…AC-04 end-to-end sul router, unit per C-14…C-17, confini di import.

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **139 passed** su Python 3.14.4.
- AC-01 riepilogo e salvataggio solo dopo conferma; AC-02 ambiguità chiesta e mai assunta; AC-03
  rifiuto all'utente autorizzato senza effetti né chiamate LLM; AC-04 `/pause` sospende e rimuove
  il job — coperti da `tests/test_tasks_ac.py`.
- BR-1 conferma/annullo/scadenza, BR-12 ruoli, BR-14 fuso del telefono, BR-15 stati, BR-16 limite:
  coperti da test dedicati.
- Confini: nessun import Telegram/SQLite/APScheduler fuori dai rispettivi componenti
  (`tests/test_boundaries.py`).
- Governance: checkpoint `sdd-governor` in due passate. Prima passata **NOT APPROVED** (2 MAJOR:
  flusso 2 non mappato, garanzia di scrittura non veritiera). Remediation applicata; seconda passata
  **APPROVED**, 0 CRITICAL, 0 MAJOR, 10 MINOR, pubblicazione sbloccata.

### Decisioni registrate (operatore, 2026-10-21)

- D1 intervalli ancorati alla creazione (o ripresa); D2 intervallo minimo 1 minuto; D3 nomi
  case-insensitive + `/rename`; D4 nessun comando di creazione; D5 scadenza conferma 900 s; D6
  bottoni inline con fallback testuale.
- P-A-08 approvata: BR-1 applicato da C-14; C-15 espone primitive post-conferma.
- Lacuna flusso 2 di spec 02 (creazione da comando rapido) accettata e dichiarata.

### Gap e follow-up

- Esecuzione end-to-end, delivery ai destinatari e recupero della mancata occorrenza → spec 03.
- Ri-registrazione dei job all'avvio (boot recovery) → spec 11.
- Gate C-27/C-28 e approvazioni con timeout → spec 06; C-17 resta il flusso BR-1 delle modifiche ai
  compiti.
- Autorizzazione/revoca utenti e consenso privacy → spec 08; lettura log e allowlist → spec 07;
  storico esecuzioni → spec 09.
- Registro capability `docs/sdd/capability-registry.md` assente: discovery eseguita leggendo il solo
  frontmatter di `.opencode/`; nessuna skill specializzata per codice/test/migrazioni (fallback
  ladder, passo 2). Rilevante per la manutenzione del processo, non per il risultato.
- Vista di deployment assente nei diagrammi: non dichiarata da spec 02.

## 03 — FR-002 Esecuzione programmata — 2026-10-24

**Spec:** [03-fr002-esecuzione-programmata.spec.md](specs/03-fr002-esecuzione-programmata.spec.md) (Stato: Implemented)
**Piano:** [03-fr002-esecuzione-programmata.plan.md](plan/03-fr002-esecuzione-programmata.plan.md)
**Architettura:** [03-fr002-esecuzione-programmata.md](architecture/03-fr002-esecuzione-programmata.md)

### Deliverable

- `src/agente/schedule_registrar.py` — C-18 Schedule Registrar: `register/update/unregister`,
  `refresh/sync/next_run`, marcatore `next_run:<task_id>` in `settings`; C-15 non chiama più C-06
  direttamente.
- `src/agente/recovery.py` — C-19 Recovery Handler: `recover_missed()` e `check_connectivity()`,
  recupero della sola ultima occorrenza, marcatura `saltata` delle precedenti, periodo offline in
  `settings`, recupero all'avvio con scheduler in pausa.
- `src/agente/delivery.py` — C-20 Delivery Service: admin implicito + iscritti `accepted` filtrati
  al momento dell'invio, report per destinatario, consegna via C-10.
- `src/agente/execution.py` — C-09 esteso: tool loop read-only (max 5 cicli, output 20.000
  caratteri), consegna dentro il timeout BR-4, avviso admin su errore o consegna parziale, log di
  avvio/fine/durata; strumenti modificanti rifiutati (fail-safe).
- `src/agente/scheduler.py` — avvio in pausa, `resume()`, job `connectivity:check`; entry point job
  come coroutine function (eseguita da `AsyncIOScheduler`).
- `src/agente/app.py` — wiring C-18/C-19/C-20, sequenza gateway → scheduler in pausa → seed
  marcatori → recupero → resume, dispatcher con controllo rete e refresh `next_run`.
- `src/agente/task_manager.py` — rebind da C-06 a C-18.
- `src/agente/tools.py` — schemi degli strumenti, handler `(task, arguments)`, allowlist passata a
  `read_logs`.
- `src/agente/storage/migrations/003_execution_skipped.sql` — CHECK di `executions` esteso a
  `saltata`, copia integrale delle righe e ricreazione dell'indice.
- `src/agente/config.py`, `config/config.example.toml` — `limits.connectivity_check_s` (default 60).
- `docs/specs/constitution.md`, `docs/specs/01-agent-runtime.spec.md`,
  `docs/specs/09-fr008-storico-esecuzioni.spec.md` — emendamento BR-15 per l'esito `saltata`
  (decisione D1 del 2026-10-24).
- `tests/` — 175 test raccolti: AC-01…AC-03 in `tests/test_scheduled_ac.py`, unit
  `test_schedule_registrar.py`, `test_recovery.py`, `test_delivery.py`, estensioni a
  `test_execution.py`, `test_scheduler.py`, `test_storage.py`, `test_bootstrap.py`.

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **175 test, exit 0** su Python 3.14.4.
- AC-01: job alle 08:00 → risultato recapitato ad admin e utente iscritto, esito `ok`, nessun
  intervento.
- AC-02: offline alle 08:00 e recupero alle 09:30 → una sola esecuzione `recovery`; recupero anche
  all'avvio prima del resume; seconda chiamata senza effetti (marcatore avanzato).
- AC-03: superamento dei 600 s → esito `interrotto`, avviso all'admin.
- BR-4 timeout, BR-5 una sola occorrenza + `saltata`, BR-8 retry delegati a C-05/C-10, BR-14
  trigger nel fuso del telefono (`test_trigger_uses_the_phone_timezone`), BR-2 strumenti modificanti
  rifiutati, BR-12 destinatari autorizzati, BR-13 allowlist, BR-16 limite compiti: coperti da test.
- Migrazione 003 verificata su DB con righe preesistenti; indice `idx_executions_task_started`
  ricreato; esito illegale ancora rifiutato.
- Governance: checkpoint di struttura `sdd-governor` in Phase 2 **NOT APPROVED** (8 MAJOR) →
  remediation nel piano → Phase 4 **APPROVED** (2026-10-24), con soli residui minor chiusi prima
  della pubblicazione.

### Gap e follow-up

- Riavvio completo, messaggio di ripartenza e liveness → spec 11; C-39 dovrà delegare a C-19 e non
  reintrodurre un secondo meccanismo di recupero.
- Gate C-27/C-28, `web_search` e approvazioni con timeout → spec 06; fino ad allora gli strumenti
  modificanti sono rifiutati con esito `errore`.
- Semantica allowlist e riassunto log → spec 07; lock persistente C-22 → spec 04; query storico →
  spec 09 (già emendata per `saltata`).
- Divergenza di naming `last_contact_at` (spec 01) / `last_online_at` (spec 10/11): riportata, da
  riconciliare in spec 10/11.
- `docs/input/functional-requirements.md` conserva BR-15 con tre esiti: è un documento di input,
  non una fonte di implementazione; la fonte vincolante è constitution + spec 01.
- Validazione su dispositivo reale (rete che cade, Termux:API, job con telefoni in sleep) non
  eseguibile in questo ambiente.

## 04 — FR-003 Lancio manuale — 2026-10-24

**Spec:** [04-fr003-lancio-manuale.spec.md](specs/04-fr003-lancio-manuale.spec.md) (Stato: Implemented)
**Piano:** [04-fr003-lancio-manuale.plan.md](plan/04-fr003-lancio-manuale.plan.md)
**Architettura:** [04-fr003-lancio-manuale.md](architecture/04-fr003-lancio-manuale.md)

### Deliverable

- `src/agente/task_lock.py` — C-22 Task Lock: `acquire/release/held`, lock in memoria, unico per
  tutti gli inneschi (decisione D1); rilascio garantito in `finally` anche su errore e timeout.
- `src/agente/run_dispatcher.py` — C-21 Run Dispatcher: `run(...)` asincrona, admin su qualsiasi
  compito, utente autorizzato solo sugli iscritti con stato `accepted` ri-verificato; rifiuti
  tipizzati `RunRefused` con elenco dei compiti visibili quando il nome non esiste; compito sospeso
  lanciabile dall'admin e rifiutato all'utente (D2).
- `src/agente/errors.py` — `RunRefused` con codice `reason` stabile.
- `src/agente/execution.py` — C-09 usa C-22 al posto del lock interno, propaga il richiedente fino a
  C-20, `is_running()` delegato a C-22.
- `src/agente/delivery.py` — C-20 `deliver_text(..., requested_by=...)`: risultato manuale solo al
  richiedente, rifiuto se non più `accepted`; percorso programmato invariato.
- `src/agente/command_router.py` — C-14: `/run <nome>`, NL `lancia <nome>` (solo verbo
  documentato, D3), precedenza sul ramo di creazione, messaggi di rifiuto e riga di stato su esito
  negativo (P-A-06), aiuto aggiornato.
- `src/agente/app.py` — wiring di C-22 e C-21, lock condiviso con C-09, dispatcher iniettato in C-14.
- `tests/` — 209 test raccolti: `test_task_lock.py`, `test_run_dispatcher.py`,
  `test_manual_run_ac.py` (AC-01…AC-03), estensioni a `test_execution.py`, `test_delivery.py`,
  `test_command_router.py`, `tests/conftest.py`.
- `docs/architecture/03-fr002-esecuzione-programmata.md` — nota di continuità su `requested_by`
  (V-03 di quella voce).

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **209 test, exit 0** su Python 3.14.4.
- AC-01: utente iscritto, `/run` → risultato solo a lui, riga `trigger='manual'` con
  `requested_by` = richiedente; l'admin che lancia non notifica gli iscritti.
- AC-02: utente non iscritto, `/run log` → rifiuto, nessuna esecuzione, nessuna riga in `executions`.
- AC-03: lock detenuto da un'esecuzione programmata, lancio manuale → rifiuto senza seconda
  esecuzione; il lock viene rilasciato anche dopo errore.
- BR-4: timeout verificato sul percorso `manual`; BR-8: retry restano dentro C-05/C-10 (invariati);
  BR-12: iscrizioni, revoca al lancio e destinatario unico coperti da test.
- Governance: checkpoint di struttura Phase 2 **NOT APPROVED** (6 MAJOR, 9 MINOR) → remediation nel
  piano → Phase 4 **APPROVED** (2026-10-24), con soli residui minor chiusi prima della pubblicazione.

### Gap e follow-up

- Gate C-27/C-28, `web_search` e approvazioni con timeout → spec 06; fino ad allora gli strumenti
  modificanti restano rifiutati con esito `errore`.
- Avvisi all'admin e soglie → spec 10; la riga di stato al richiedente su esito negativo è
  un'assunzione di questa voce (P-A-06), non un requisito dichiarato.
- Lock persistente escluso per decisione D1: nessun coordinamento tra processi, escluso dal Tech
  Stack; un riavvio termina comunque l'esecuzione in corso.
- Deroga a spec 02 AC-04 (compito sospeso lanciabile dall'admin) registrata in spec 04 e nel
  documento di architettura; spec 02 non è emendata.
- Query e presentazione dello storico (spec 09); gestione utenti e iscrizioni (spec 08); chat
  (spec 05); riavvio/liveness (spec 11).
- Validazione su dispositivo reale (Telegram, DeepSeek, Termux) non eseguibile in questo ambiente.

## 05 — FR-004 Domande libere — 2026-10-24

**Spec:** [05-fr004-domande-libere.spec.md](specs/05-fr004-domande-libere.spec.md) (Stato: Implemented)
**Piano:** [05-fr004-domande-libere.plan.md](plan/05-fr004-domande-libere.plan.md)
**Architettura:** [05-fr004-domande-libere.md](architecture/05-fr004-domande-libere.md)

### Deliverable

- `src/agente/chat_memory.py` — C-24: contesto per utente con finestra di 24 h su silenzio (ultimo
  messaggio dell'utente) e età del messaggio, troncamento al budget di contesto, `reset` totale,
  `purge_idle`, `messages` per la rilettura admin.
- `src/agente/progress.py` — C-25: soglia configurabile, invio di «sto cercando…», cancellazione in
  background alla risposta, stato per `chat_id` con generazione e annullamento del timer.
- `src/agente/chat.py` — C-23: `ChatReply`, unico punto di invio, contesto da C-24, `llm.chat` in
  `asyncio.to_thread`, tool loop read-only (3 cicli, output troncati a 20.000 caratteri), `/reset`,
  rilettura admin, serializzazione per `user_id`, generazione anti-resurrezione dopo `/reset`.
- `src/agente/command_router.py` — C-14: testo libero degli autorizzati → chat; per l'admin bozza
  completa → creazione, altrimenti chat; bozza completa dell'autorizzato → rifiuto (spec 02 AC-03);
  `/reset`; `/chat <telegram_id>` (senza argomento elenca gli utenti `accepted`); aiuto aggiornato.
- `src/agente/telegram_gateway.py` — C-03: `send` restituisce l'id dell'ultimo messaggio;
  `delete_message` con retry BR-8.
- `src/agente/storage/migrations/004_chat_without_user_fk.sql` — tabelle chat senza FK verso `users`,
  dati, id, `sqlite_sequence` e indice preservati.
- `src/agente/storage/repositories.py` — `messages_for_user`, `delete_all_for_user`, `delete_idle`.
- `src/agente/scheduler.py` — job di manutenzione come coroutine nell'event loop (D8), callback
  sincroni o coroutine.
- `src/agente/app.py` — wiring di C-23/C-24/C-25; manutenzione `purge_expired` + `purge_idle`.
- `src/agente/config.py`, `config/config.example.toml` — `limits.chat_progress_s` (default 2).
- `src/agente/llm.py` — `assistant_message()` condiviso da C-09 e C-23; `execution.py` lo usa.
- Test: 271 raccolti — `test_chat_memory.py`, `test_progress.py`, `test_chat.py`, `test_chat_ac.py`,
  più estensioni a `test_storage.py`, `test_scheduler.py`, `test_telegram_gateway.py`,
  `test_config.py`, `test_command_router.py`, `test_tasks_ac.py`, `tests/conftest.py`,
  `tests/test_scheduled_ac.py`.
- `docs/specs/01-agent-runtime.spec.md` e `docs/architecture/01-agent-runtime.md` — note di
  continuità su C-03, migrazione 004, ripartizione retention e job di manutenzione.

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **271 test, exit 0** su Python 3.14.4.
- AC-01: due domande consecutive → la seconda porta in contesto la prima; l'admin vede il proprio
  storico.
- AC-02: 24 h di silenzio o messaggio fuori finestra → contesto vuoto (orologio iniettato).
- AC-03: `/reset` → messaggi cancellati e riga di conversazione rimossa; un `/reset` durante una
  risposta in volo non fa rientrare i turni in memoria (generazione).
- AC-04: admin `/chat <id>` → ultimi 50 messaggi dell'utente `accepted`; un autorizzato riceve il
  rifiuto; bersaglio sconosciuto o revocato → messaggio dedicato.
- AC-05: risposta semplice senza indicatore; C-23 non ha un timeout complessivo (verifica
  strutturale), C-05 mantiene il timeout HTTP per tentativo.
- AC-06: con una risposta oltre soglia l'indicatore viene inviato e poi eliminato; `web_search` non
  esiste ancora → AC-06 parzialmente validato, gap dichiarato.
- Migrazione 004 applicata su DB con dati: id e contenuti preservati, indice ricreato,
  `sqlite_sequence` riparte dopo l'id massimo.
- Concorrenza: due domande dello stesso utente → scambi ordinati; cancellazione lenta dell'indicatore
  non ritarda la risposta (< 0,1 s nel test con cancellazione da 0,2 s).
- Job di manutenzione: eseguito come coroutine nell'event loop con callback sincrono e asincrono
  (corretto un difetto preesistente di item 01/03: il job sincrono girava in un thread del pool con
  una connessione SQLite non thread-safe).
- Governance: Phase 2 **NOT APPROVED** (11 MAJOR, 10 MINOR) → piano riscritto → **APPROVED**;
  Phase 4 **NOT APPROVED** (3 MAJOR) → remediation su indicatore non bloccante, reset concorrente,
  flusso 2 e tracciabilità → **APPROVED**.

### Gap e follow-up

- **AC-06 senza ricerca web:** `web_search` e il gate C-27/C-28 arrivano con spec 06; il tool loop
  read-only è coperto con uno strumento finto e in chat l'allowlist dei log è vuota (spec 07).
- **Latenza reale:** 30 s / 2 min sono limiti-obiettivo (D7, nota interpretativa in constitution);
  la misura va fatta sul dispositivo. I retry BR-8 di C-05 e di C-03 possono estenderli.
- **Migrazione 004:** perde `ON DELETE CASCADE` verso `users`; gli utenti non vengono mai cancellati,
  solo revocati.
- **`/reset` durante una risposta:** i turni in volo non vengono registrati, ma il testo della
  risposta già richiesta viene comunque inviato.
- **Privacy e consenso:** informativa e gestione utenti a spec 08; i messaggi restano sul telefono.
- **Vista di deployment:** non dichiarata da spec 05, gap registrato.
- **Validazione su dispositivo reale** (Telegram, DeepSeek, Termux) non eseguibile in questo ambiente.

## 06 — FR-005 Ricerca web e conferma — 2026-10-25

**Spec:** [06-fr005-ricerca-web-conferma.spec.md](specs/06-fr005-ricerca-web-conferma.spec.md) (Stato: Implemented)
**Piano:** [06-fr005-ricerca-web-conferma.plan.md](plan/06-fr005-ricerca-web-conferma.plan.md)
**Architettura:** [06-fr005-ricerca-web-conferma.md](architecture/06-fr005-ricerca-web-conferma.md)

### Deliverable

- `src/agente/web_search.py` — C-26: `Result`, `WebSearchAdapter`, provider Tavily, retry BR-8,
  normalizzazione, `format_results`; provider assente/non supportato → `SearchError` esplicito.
- `src/agente/gate.py` — C-27: `ToolAction`, `Gate`, `classify`, `execute_if_allowed`, `run`;
  read-only senza conferma, modificanti solo con approvazione valida, strumento sconosciuto rifiutato,
  handler in `asyncio.to_thread`, output troncato a 20.000 caratteri.
- `src/agente/approvals.py` — C-28: creazione riga, invio tramite C-10, attesa, timeout BR-3,
  risoluzione solo admin, `is_executable`, `recover_pending`; cancellazione e errore di invio →
  `rejected`.
- `src/agente/notifications.py` — `send_approval` e `create_approval` con scadenza esplicita;
  `request_approval` mantenuto come wrapper.
- `src/agente/tools.py` — handler con `approved`, regola di registrazione, `web_search` con schema
  `query`/`k`, `default_registry(device, *, search=None)`.
- `src/agente/execution.py` / `src/agente/chat.py` — strumenti modificanti via gate, rifiuto e
  `SearchError` come esiti di tool, `reason`/`requested_by` (P-A-05), prompt di chat aggiornato.
- `src/agente/command_router.py` — callback `approval:<id>:approve|reject`, solo admin, messaggi di
  esito.
- `src/agente/storage/repositories.py` — `ApprovalRepository.reject_pending`.
- `src/agente/config.py`, `config/config.example.toml` — `search.provider` default `tavily`.
- `src/agente/app.py` — wiring di C-26/C-27/C-28, gate a C-09/C-23, `recover_pending` in `start()`.
- Test: 334 raccolti — `test_web_search.py`, `test_approvals.py`, `test_gate.py`,
  `test_approval_ac.py`, `test_tools.py`, più estensioni a execution, chat, command_router, config,
  storage, notifications, bootstrap, device_gate, boundaries, conftest, scheduled_ac.
- Note di continuità: spec 01/03/05 e architetture 01/03/04/05; constitution §Tech Stack e nota
  BR-17.

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **334 test, exit 0** su Python 3.14.4.
- AC-01: richiesta di `delete_file` → messaggio all'admin con Approva/Rifiuta, file intatto; dopo
  Approva il file è cancellato.
- AC-02: nessuna risposta entro il timeout → `rejected`, azione non eseguita; in esecuzione BR-4
  interrompe e scarta la richiesta pendente.
- AC-03: `web_search` eseguita senza alcuna richiesta di conferma e senza bottoni.
- AC-06 di spec 05: chat con `web_search`, indicatore inviato e rimosso, risultati nella risposta.
- Solo admin: un utente autorizzato che preme il bottone riceve un rifiuto e la richiesta resta
  pendente; C-28 riverifica il ruolo.
- Riavvio: le righe `pending` diventano `rejected` in `AgentApp.start()`.
- Fail-safe: strumento sconosciuto e metadati contraddittori non eseguono nulla; provider assente →
  errore esplicito senza eccezione fatale.
- Retry: provider 5xx/429 ritentato, 401 non ritentato; chiave mai nei log; query e latenza registrate.
- Governance: Phase 2 `sdd-governor` **NOT APPROVED** al primo e al secondo giro (10 MAJOR, poi
  residui su registrazione/BR-4/C-28) → piano riscritto → **APPROVED** al terzo; Phase 4
  **APPROVED** con finding minor recepiti (timeout condiviso C-17/C-28, attribuzione log, keyword-only,
  troncamento del gate, ramo errore di invio, diagramma 7.4, fonte V-15, wiring).

### Gap e follow-up

- **`install` (A4):** nessuno strumento di installazione è dichiarato da C-08; il gate coprirebbe un
  tool futuro marcato modificante.
- **Latenza BR-17:** obiettivo, non timeout; l'attesa di approvazione (15 min) e i retry della ricerca
  possono estenderlo (V-14). Misura reale solo su dispositivo.
- **BR-4 e handler in thread:** il timeout interrompe l'attesa, non un handler già avviato in
  `asyncio.to_thread` (P-A-19); l'esecuzione resta `interrotta` ma l'effetto può completare.
- **Provider:** solo Tavily implementato; Brave/Google CSE/SerpAPI sono estensioni del registry.
- **Invio parziale:** un errore di invio dei bottoni marca `rejected`; il messaggio parziale resta
  best effort (P-A-20).
- **Lock di chat:** l'attesa di approvazione può bloccare per lo stesso utente fino a 15 minuti
  (P-A-17).
- **Installazione reale:** validazione su dispositivo (Telegram, DeepSeek, Termux) non eseguibile in
  questo ambiente.

## 07 — FR-006 Lettura e riassunto dei log — 2026-10-29

**Spec:** [07-fr006-riassunto-log.spec.md](specs/07-fr006-riassunto-log.spec.md) (Stato: Implemented)
**Piano:** [07-fr006-riassunto-log.plan.md](plan/07-fr006-riassunto-log.plan.md)
**Architettura:** [07-fr006-riassunto-log.md](architecture/07-fr006-riassunto-log.md)

### Deliverable

- `src/agente/log_reader.py` — C-29: `read(paths, allowlist) -> LogContent` con `LogEntry`,
  `refused`, `notes`, `rendered`; file inesistente/vuoto/illeggibile segnalati senza eccezione;
  cartella non ricorsiva con sottocartelle e symlink contati; budget 20.000 caratteri con nota.
- `src/agente/log_allowlist.py` — C-30: `is_allowed(path, task)`, normalizzazione `expanduser` +
  `resolve` (`..` e symlink), solo percorsi assoluti, allowlist vuota = tutto negato.
- `src/agente/device.py` — C-07: `inspect_path` (`PathInfo`), `read_file_tail` (`FileTail`, ultimi N
  caratteri, budget 4 byte/carattere, UTF-8 `errors="replace"`), `list_files` (`DirectoryListing`,
  non ricorsivo, conteggio sottocartelle e symlink). `read_file` invariata.
- `src/agente/errors.py` — `LogAccessError` con `refused` e `rendered`.
- `src/agente/tools.py` — `read_logs` accetta file o cartella, passa da C-29, `log_reader`
  iniettabile, payload del rifiuto limitato a `MAX_TOTAL_CHARS - 200`.
- `src/agente/execution.py` — C-09: `LogAccessError` come esito di tool in entrambi i rami, avviso
  all'admin, rifiuti accumulati per esecuzione, nota deterministica anteposta al risultato.
- `src/agente/app.py` — invariato: C-29 è costruito dentro `default_registry`.
- Test: 386 raccolti — `test_log_allowlist.py`, `test_log_reader.py`, `test_log_ac.py`, più
  estensioni a `test_device_gate.py`, `test_tools.py`, `test_execution.py`, `test_chat.py`,
  `test_boundaries.py`.
- Note di continuità: spec 01/03/05 e architettura 05.

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **386 test, exit 0** su Python 3.14.4.
- AC-01: cartella autorizzata con log contenenti un errore → il modello riceve i log e il risultato
  consegnato contiene il riassunto.
- AC-02: percorso fuori allowlist → non letto, avviso `Log non autorizzati per il compito …`
  all'admin, nota anteposta al risultato, compito `ok`.
- AC-03: compito con `paths.logs` autorizzato → il modello riceve `esecuzione conclusa`/
  `esecuzione fallita` e l'errore, e il riassunto viene consegnato.
- Troncamento: file oltre 8.000 caratteri → coda, dimensione e flag; UTF-8 multibyte non spezzato;
  cap complessivo 20.000 verificato anche contro `gate.MAX_OUTPUT_CHARS`.
- Directory: non ricorsiva, massimo 20 file, symlink ignorati e contati, cartella vuota segnalata.
- Rifiuti: `../`, symlink che esce, percorso relativo, allowlist vuota e voci non valide; nessuna
  lettura del contenuto non autorizzato.
- Illeggibile: `PathInfo.readable=False`, `DeviceError` e `GateError` dell'adapter diventano note,
  mai guasti del compito.
- Chat: `read_logs` reale resta rifiutato con allowlist vuota.
- Confini: asserzione AST che `log_reader.py` e `log_allowlist.py` non aprono file né usano
  `pathlib` per I/O.
- Governance: Phase 2 `sdd-governor` **NOT APPROVED** al primo giro (7 MAJOR, 15 MINOR: contratto
  C-07 non implementabile, unità byte/caratteri, «illeggibile», conteggio symlink, passaggio di
  `LogAccessError` attraverso C-27, nota AC-02 non garantita dal codice, percorsi relativi, C-02)
  → piano riscritto → **APPROVED** al secondo giro con 11 minor recepiti; Phase 4 **APPROVED** con
  finding minor recepiti (cartella `paths.logs`, osservabilità C-30, symlink, `GateError` da
  elenco, tre estensioni, soglia 500 e riserva 300, margine 200 con test, test reali in chat, stile
  del wiring, riferimenti del piano).

### Gap e follow-up

- **Storico strutturato (item 09):** AC-03 legge il file C-13; la tabella `executions` non è
  esposta come strumento.
- **Chat (D6):** la lettura dei log resta non disponibile in chat, anche per l'admin.
- **Loop di tool esaurito dopo un rifiuto:** l'avviso all'admin è già partito, ma il compito chiude
  `errore` senza consegnare la nota AC-02.
- **Coda e budget:** un errore molto vecchio può restare fuori dalla coda; con molti file il budget
  si esaurisce e i successivi non vengono letti (nota esplicita in `LogContent.notes`).
- **Dispositivo:** permessi reali del filesystem Termux e latenza non verificabili in questo
  ambiente.

## 08 — FR-007 Gestione degli utenti — 2026-11-01

**Spec:** [08-fr007-gestione-utenti.spec.md](specs/08-fr007-gestione-utenti.spec.md) (Stato: Implemented)
**Piano:** [08-fr007-gestione-utenti.plan.md](plan/08-fr007-gestione-utenti.plan.md)
**Architettura:** [08-fr007-gestione-utenti.md](architecture/08-fr007-gestione-utenti.md)

### Deliverable

- `src/agente/user_manager.py` — C-31: `authorize`, `revoke`, `subscribe`, `unsubscribe`,
  `list_users`; transizioni `pending → accepted|revoked`, `accepted → revoked`, `revoked → pending`
  con `consent_at=None`; admin non gestibile; pre-check BR-16; `UserAccessError` con `reason`.
- `src/agente/consent.py` — C-32: `send_consent`, `accept`, `decline` (async); testo
  `PRIVACY_NOTICE` approvato; `consent_at` all'accettazione; avvisi all'admin su rifiuto e tetto.
- `src/agente/authorization_notifier.py` — C-33: `notify_unknown` con pulsante `authorize:<id>`,
  finestra di 24 h in memoria, `username_for` per il callback.
- `src/agente/user_state.py` — contratto condiviso: `UserView`, `UserResult`,
  `MAX_AUTHORIZED_USERS` (nessun ciclo C-31 ↔ C-32).
- `src/agente/notifications.py` — C-10: `notify`/`alert_admin` con tastiera opzionale sull'ultimo chunk.
- `src/agente/telegram_gateway.py` — C-03: `IncomingMessage.username` per messaggi e callback.
- `src/agente/command_router.py` — C-14: `/adduser`, `/removeuser`, `/users`, `/subscribe`,
  `/unsubscribe`; callback `authorize:`/`consent:` prima del rifiuto `UNKNOWN`; rifiuto esplicito a
  sconosciuto/revocato; `HELP_TEXT` aggiornato; testi di errore per `reason`.
- `src/agente/errors.py` — `UserAccessError`.
- `src/agente/app.py` — wiring di C-31/C-32/C-33; `AgentApp` espone `user_manager`, `consent`,
  `notifier`. Nessuna migrazione.
- Test: 451 raccolti — `test_user_manager.py`, `test_consent.py`, `test_authorization_notifier.py`,
  `test_users_ac.py`, più estensioni a `test_command_router.py`, `test_telegram_gateway.py`,
  `test_notifications.py`, `test_role_guard.py`.
- Note di continuità: spec 01 (C-03/C-10), spec 02 (C-14), spec 06 (registro callback).

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **451 test, exit 0** su Python 3.14.4.
- AC-01: sconosciuto → rifiuto, nessuna risposta utile, avviso all'admin con nome/id e pulsante
  Autorizza.
- AC-02: pulsante Autorizza → `pending` + informativa; accettazione → `accepted` con `consent_at`;
  `/tasks` risponde come utente autorizzato.
- AC-03: rifiuto → `revoked`, admin avvisato.
- AC-04: revoca → l'utente è trattato come sconosciuto.
- AC-05: utente autorizzato `/adduser` → rifiuto, nessun utente creato.
- BR-16: sesto utente rifiutato; riapertura `revoked → pending` rifiutata al tetto; reinvio a
  `pending` ammesso; un già autorizzato non incappa nel limite.
- Anti-spam: un solo avviso per utente nella finestra di 24 h; il rifiuto all'utente resta; un avviso
  fallito non consuma la finestra.
- Transizioni e integrità: `consent_at` azzerato solo in `revoked → pending`, `username` preservato,
  revoca che conserva le iscrizioni, riattivazione dichiarata.
- Callback: `authorize:` solo admin; `consent:` solo destinatario `pending`; `confirm:` e `approval:`
  invariati.
- Nessuna migrazione: schema 001 invariato.
- Governance: Phase 2 `sdd-governor` **NOT APPROVED** per tre passate (9 major/11 minor: C-33 senza
  tastiera, `username` assente al callback, transizioni non definite, esito «già autorizzato»
  assente, iscrizioni in conflitto con C-15, sequenze 3 e 6 mancanti; 3 major/11 minor: `accept`
  sincrono, costante circolare, codici errore; 2 major/8 minor: ownership `UserResult`, codici
  incoerenti) → **APPROVED** alla quarta con minor recepiti. Phase 4 **APPROVED** alla seconda
  passata (prima: «storico» non consegnato, nota del reinvio corrotta da `replace`, dipendenze nel
  flowchart, sequenze senza C-10/C-03, comportamento del `pending`, riga Governance).

### Gap e follow-up

- **Rilettura chat dei revocati:** C-23 accetta target admin e soli `accepted`; i dati restano (D3) ma
  la rilettura di un revocato non è disponibile. Nessuna modifica a C-23 in questa voce.
- **Anti-spam in memoria:** un riavvio può produrre un avviso in più; il nome Telegram si perde se il
  processo si riavvia fra avviso e pulsante (resta l'id).
- **Silenzio:** un `pending` non ha scadenza e non genera avvisi automatici (V-08/V-10); è visibile in
  `/users` e revocabile.
- **Tetto BR-16:** con cinque `accepted` la riapertura di un revocato è rifiutata fino a una revoca.
- **Storico e avvisi di sistema:** item 09/10; il riavvio (item 11) non è trattato.

## 09 — FR-008 Storico delle esecuzioni — 2026-11-02

**Spec:** [09-fr008-storico-esecuzioni.spec.md](specs/09-fr008-storico-esecuzioni.spec.md) (Stato: Implemented)
**Piano:** [09-fr008-storico-esecuzioni.plan.md](plan/09-fr008-storico-esecuzioni.plan.md)
**Architettura:** [09-fr008-storico-esecuzioni.md](architecture/09-fr008-storico-esecuzioni.md)

### Deliverable

- `src/agente/history_query.py` — C-34: `parse_filter` (deterministico e puro),
  `parse_window_with_llm` (unico punto C-05), `resolve_task`, `build_filter` (clamp e
  `degenerate`), `query` (visibilità admin/autorizzato), `render` (una riga, 120 caratteri,
  massimo 20 righe, `saltata`, esiti NULL, newline, istanti non parsabili).
- `src/agente/history.py` — C-11: normalizzazione a UTC in `record`/`record_skipped`/`finish`,
  cutoff di retention/reset in UTC, log dei conteggi, `record_skipped` con nota conservata.
- `src/agente/storage/migrations/005_executions_started_index.sql` — normalizzazione degli istanti
  con `strftime` e guardia `NOT NULL`, indice `idx_executions_started`.
- `src/agente/storage/db.py` — helper `commit()` (errori SQLite → `StorageError`); usato dai
  `DELETE` di retention in `repositories.py`.
- `src/agente/app.py` — wiring di C-34 (`history_query`, `tz` opzionale) e `_maintenance` con
  retention e `purge_idle` isolati.
- `src/agente/command_router.py` — C-14: `/history [periodo] [compito]`, riconoscimento NL prima
  dell'elenco compiti e della chat, veto sulle schedulazioni, `HELP_TEXT`.
- Test: 518 raccolti — `test_history_query.py`, `test_history_ac.py`, `test_history.py`,
  `test_command_router.py`, `test_storage.py`, `test_bootstrap.py`, `conftest.py`.
- Note di continuità: spec 01 (C-02/C-11), spec 02 (C-14).

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **518 test, exit 0** su Python 3.14.4.
- AC-01: admin «cosa hai fatto ieri?» → elenco con esito e riassunto.
- AC-02: utente iscritto solo a `news` → vede solo `news`.
- AC-03: esecuzione di 31 giorni fa + `purge_expired()` + `/history 30g` → solo la recente; clamp
  con nota per finestre più ampie.
- Periodo: insieme chiuso (`oggi`, `ieri`, settimana/mese corrente e precedente, `ultimi N giorni`/
  `Ng`, `GG/MM`, `GG/MM/AAAA`), punteggiatura e prefissi, cifra iniziale → `AmbiguousPeriod`,
  fallback LLM validato, `llm=None`/errore → domanda.
- Visibilità: admin tutto, autorizzato solo iscritti, compito altrui indistinguibile, `UNKNOWN` → `[]`.
- Formato: massimo 20 righe, riassunto 120 caratteri, `saltata`, `outcome` NULL → `—`, `compito
  #id`, newline sanitizzati, istante non parsabile `??/?? ??:??`.
- Migrazione 005: offset `+02:00` → UTC, istanti naive = UTC, riga non parsabile tollerata, indice
  presente; nessuna tabella o colonna nuova.
- Normalizzazione e cutoff: ordinamento misto corretto, purge/reset in UTC, log dei conteggi.
- Callback e comandi preesistenti invariati; confini `tests/test_boundaries.py` verdi.
- Governance: Phase 2 `sdd-governor` **NOT APPROVED** per dodici passate (critical iniziale
  `started_at` misto UTC/locale; poi guardia migrazione, clamp, thread SQLite, pattern NL,
  `render`/label, formato `strftime`, precedenza LLM/nome, cutoff UTC, esiti NULL, test e
  tracciabilità) → **APPROVED** con minor recepiti. Phase 4 **NOT APPROVED** per tre passate
  (C-35 Input/Output, filtro `trigger`, edge C-11→C-10, prefissi, elisione apostrofica, cifra
  iniziale, firma di `query`, BR-16) → **APPROVED** alla quarta con minor recepiti.

### Gap e follow-up

- **Compiti eliminati:** il cascade su `executions.task_id` elimina lo storico insieme al compito
  (V-08); nessun cambio di modello dati.
- **Istanti non parsabili:** restano fuori contratto; non si garantisce l'esclusione dalle query né
  la sopravvivenza alla retention (P-A-25).
- **Nomi non filtrabili:** un compito chiamato come parola generica (`storico`, `compiti`) o che
  inizia con una cifra non è filtrabile per nome; l'ordine «compito prima del periodo» non è
  supportato.
- **BR-16:** dimensionamento atteso, non misurato con test di carico.
- **Avvisi di sistema e riavvio:** item 10/11.

## 10 — FR-009 Avvisi all'amministratore — 2026-11-03

**Spec:** [10-fr009-avvisi-admin.spec.md](specs/10-fr009-avvisi-admin.spec.md) (Stato: Implemented)
**Piano:** [10-fr009-avvisi-admin.plan.md](plan/10-fr009-avvisi-admin.plan.md)
**Architettura:** [10-fr009-avvisi-admin.md](architecture/10-fr009-avvisi-admin.md)

### Deliverable

- `src/agente/alerts.py` — C-36: `alert` (composizione, dedup batteria a scaglioni, dedup credenziali
  a 1 h, invio fuori lock), `alert_threadsafe`/`bind_loop`/`close`, testi e log.
- `src/agente/device_monitor.py` — C-37: batteria, connettività, `offline_since`, `last_online_at`,
  `last_contact_at`, avvisi batteria/offline.
- `src/agente/credential_monitor.py` — C-38: classificazione 401/402/403 e inoltro.
- `src/agente/llm.py`, `src/agente/errors.py` — callback `on_credentials_error`,
  `LLMCredentialsError.status`, corpo troncato e non loggato.
- `src/agente/execution.py` — `task_failed`/`task_timeout` via C-36; credenziali senza `task_failed`.
- `src/agente/recovery.py` — C-19 con `monitor`, senza `settings`; `recover_missed` in sola lettura.
- `src/agente/scheduler.py` — `schedule_battery` (`battery:check`), errori isolati.
- `src/agente/config.py`, `config/config.example.toml` — `limits.battery_check_s = 300`.
- `src/agente/app.py` — wiring C-10→C-36→C-38→C-37→C-05, `bind_loop` prima di `recover_missed`,
  `stop` con `close()`, job batteria.
- Test: 596 raccolti — `test_alerts.py`, `test_device_monitor.py`, `test_credentials.py`,
  `test_alerts_ac.py`, `test_execution.py`, `test_llm.py`, `test_recovery.py`, `test_scheduler.py`,
  `test_config.py`, `test_bootstrap.py`, `test_scheduled_ac.py`, `test_storage.py`.
- Note di continuità: spec 01 (C-05/C-07/C-10/C-01), spec 03 (C-19), spec 09 (avvisi di sistema),
  arch 01 (§2/§8), arch 03 (§2/§5/§6.2/§14).

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **596 test, exit 0** su Python 3.14.4.
- AC-01: compito fallito → avviso admin con nome e motivo.
- AC-02: batteria 14% → avviso; 15% nessun avviso.
- AC-03: offline 2 h → avviso con periodo al rientro; 30 min nessun avviso.
- AC-04: DeepSeek 402 → avviso specifico, una volta per finestra.
- Dedup: batteria 14→9→4; reset sopra soglia; credenziali a 1 h; fallimenti per esecuzione.
- Marcatori: `offline_since`, `last_online_at`, `last_contact_at`, `battery_last_alert`,
  `credential_last_alert`; `liveness_last_sent` non toccata.
- C-19: un solo scrittore di `offline_since`; recupero invariato; nessun avviso al boot.
- Migrazioni: nessuna nuova (schema 005).
- Governance: Phase 2 **NOT APPROVED** per sette passate (soglia batteria, offline marker, lock,
  arch 03, `last_online_at`, AC-01/D-06, ordine `bind_loop`, DB/thread, log, `Alert`, test) →
  **APPROVED** all'ottava. Phase 4 **NOT APPROVED** per tre passate (Governance anticipata,
  `Alert`/`sent_at`, ordine `offline_since`, C-10 nei diagrammi, flowchart, lettori dei marcatori,
  formato durata, test lock) → **APPROVED** alla quarta.

### Gap e follow-up

- **Invio offline fallito:** il periodo è concluso e non viene ritentato oltre BR-8; coperto dalla
  liveness di spec 11.
- **Oscillazione batteria:** 14→15→14 azzera e ricrea il marcatore, con un nuovo avviso a ogni
  campionamento (nessuna isteresi).
- **`LLMClient` iniettato:** non riceve il callback di C-38; i test usano C-38 o un client reale.
- **BR-16:** avvisi occasionali, nessun test di carico.
- **Riavvio e segnale di vita:** restano a spec 11.

## 11 — FR-010 Riavvio e liveness — 2026-11-04

**Spec:** [11-fr010-riavvio-liveness.spec.md](specs/11-fr010-riavvio-liveness.spec.md) (Stato: Implemented)
**Piano:** [11-fr010-riavvio-liveness.plan.md](plan/11-fr010-riavvio-liveness.plan.md)
**Architettura:** [11-fr010-riavvio-liveness.md](architecture/11-fr010-riavvio-liveness.md)

### Deliverable

- `src/agente/boot.py` — C-39: `on_start`, `RecoverySummary`, `OfflinePeriod`, periodo da
  `last_online_at` con fallback, segnale mancato, scrittura `last_start_at`.
- `src/agente/liveness.py` — C-40: `send_liveness`, testo con `liveness_at`, `liveness_last_sent`
  solo dopo invio riuscito.
- `src/agente/restart.py` — C-41: `notify_restart`, testo con periodo e recuperati, riga del segnale
  mancato con finestra quando pertinente.
- `src/agente/recovery.py` — C-19: `RecoveryStats`/`last_summary` additivi, reset all'ingresso.
- `src/agente/scheduler.py` — C-06: `schedule_liveness` (`liveness:send`, cron con timezone dello
  scheduler, `misfire_grace_time=None`).
- `src/agente/config.py` — C-01: validazione stretta di `limits.liveness_at`.
- `src/agente/alerts.py` — C-36: `human_duration` pubblica.
- `src/agente/app.py` — wiring C-39/C-40/C-41, `schedule_liveness` prima di `on_start`, log del
  fallimento gateway, `notify_restart` dopo `on_start`.
- Test: 646 raccolti — `test_boot.py`, `test_liveness.py`, `test_restart.py`, `test_restart_ac.py`,
  estensioni a recovery/scheduler/config/bootstrap/scheduled_ac/alerts.
- Note di continuità: spec 01 (C-01/C-06/C-12), spec 03 (C-19 `last_summary`), spec 10
  (`liveness_last_sent`, `human_duration`), arch 01/03/10.

### Validazione

- Suite: `PYTHONPATH=src:.deps python3 -m pytest` → **646 test, exit 0** su Python 3.14.4.
- AC-01: avvio con `last_start_at` precedente → messaggio con periodo e recuperati.
- AC-02: alle `liveness_at` → segnale all'admin e marcatore aggiornato.
- AC-03: segnale delle 8:00 non inviato → riga nel messaggio, con finestra se l'occorrenza è nel
  periodo.
- AC-04: due avvii con marcatore seminato → un messaggio per avvio, un solo recupero per occorrenza.
- Marcatori: `last_start_at`, `liveness_last_sent`, `last_online_at`, `offline_since`; nessuna
  migrazione (schema 005).
- Governance: Phase 2 **NOT APPROVED** per dieci passate (ordine di avvio, semantica assenza,
  segnale mancato, job liveness, AC-04, deviazioni, tracciabilità, API APScheduler, log) →
  **APPROVED** all'undicesima. Phase 4 **APPROVED** alla prima con minor recepiti (testo del segnale
  mancato, riferimento V-11, wording C-39, BR-16, job store, righe di tracciabilità).

### Gap e follow-up

- **Dispositivo:** riavvio reale, autostart e limitazioni OEM da validare sul dispositivo; soak test
  AC-04 non eseguito.
- **Invio ripartenza fallito:** non ritentato oltre BR-8; l'assenza non viene ripetuta.
- **Segnale mancato con processo vivo:** riportato solo al prossimo avvio, non al rientro di rete.
- **Perdita di un'occorrenza:** se `next_run` avanza prima di un rientro `resumed`.
- **Crash-loop:** un messaggio per ogni avvio, nessuna soglia di silenzio.

## patch-readme-uso-app — README guida operativa — 2026-11-07

**Spec:** [patch-readme-uso-app.spec.md](specs/patch-readme-uso-app.spec.md) (Micro-Spec)
**Piano:** [patch-readme-uso-app.plan.md](plan/patch-readme-uso-app.plan.md)

### Deliverable

- `README.md` riscritto come guida operativa dell'app Agente Personale Telegram, in italiano:
  Prerequisiti, Setup, Configurazione, Avvio, Comandi (uso da Telegram), Accesso da un altro
  telefono, Sicurezza, Troubleshooting essenziale.
- Contenuti: Termux/Termux:API/Termux:Boot, `.deps` senza venv, `config.toml` e `secrets.env` con
  permessi `600`, token BotFather e chiave DeepSeek, avvio manuale e automatico, log applicativo e
  del supervisore, comandi e ruoli, creazione compiti in linguaggio naturale, lettura log via
  `read_logs` con percorso assoluto, accesso da altro telefono (stesso account o `/adduser` +
  consenso), sicurezza, troubleshooting.
- Il precedente README del framework SDD è sostituito (scelta dell'operatore); il contenuto
  precedente resta recuperabile dalla cronologia git.

### Validazione

- 16 comandi Telegram documentati e coerenti con `HELP_TEXT` + `/help`/`/start`; nessun comando
  inventato; ruoli verificati su router, dispatcher, task manager, history query, chat,
  role guard.
- `grep -R "sk-" README.md` → 0; nessun comando `/log`; nessun segreto o token reale.
- Sezioni richieste presenti; percorsi, `.deps`, boot, log e liveness coerenti con il codice.
- `README.md` tracciato (`git ls-files --error-unmatch`) e modificato (`git diff --stat HEAD`,
  258 inserzioni / 163 rimozioni alla validazione); `git status --porcelain` limitato ai path
  ammessi.
- Governance: Phase 2 **NOT APPROVED** per dodici passate (setup, boot, config, ruoli, scope,
  AC-01, log) → **APPROVED** alla tredicesima. Phase 4 **NOT APPROVED** per tre passate
  (`LOG_DIR`, troubleshooting, `read_logs`, prerequisiti, creazione admin, ricerca web, avviso
  24 h, wake-lock, URL, `termux-tools`, avvio preventivo del bot) → **APPROVED** alla quarta con
  note opzionali recepite.

### Gap e follow-up

- **`90-agent.sh`:** nel repo invoca `start-agent.sh` direttamente; il README istruisce la modifica
  del file copiato in `~/.termux/boot/` (`bash "$SCRIPT_DIR/start-agent.sh"`, `chmod 700/600`).
  Modifica degli script fuori scope: follow-up aperto.
- **Autostart/OEM:** installazione reale di Termux:Boot e limitazioni batteria del produttore non
  testate su dispositivo.
- **AC-01:** interpretata come riferita ai soli comandi Telegram slash (P-A-12); i comandi shell non
  sono verificati contro il router.

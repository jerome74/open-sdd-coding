# Specifica 03 — Esecuzione programmata dei compiti (FR-002)

- **ID:** `03-fr002-esecuzione-programmata`
- **Stato:** Implemented (2026-10-24)
- **Requisiti collegati:** FR-002; BR-4, BR-5, BR-8, BR-14
- **Dipendenze:** `01-agent-runtime`, `02-fr001-gestione-compiti`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

Ogni compito attivo deve essere **eseguito automaticamente** all'orario o intervallo previsto
(fuso orario del telefono). All'esecuzione l'agente ragiona tramite DeepSeek, usa gli strumenti
necessari (es. ricerca web), invia il risultato su Telegram a tutti i destinatari e registra
l'esecuzione nello storico.

Casi particolari: telefono offline all'orario previsto → recupero **una sola volta** al rientro
(BR-5); esecuzione oltre **10 minuti** → interruzione + avviso all'admin (BR-4); DeepSeek/Telegram
non raggiungibili → **3 tentativi a 1 minuto** (BR-8).

## Panoramica architetturale

Riutilizza: Scheduler (C-06), Execution Engine (C-09), LLM Client (C-05), Tool Registry (C-08),
Device Adapter (C-07), Notification Service (C-10), History & Retention (C-11), Storage (C-02).

Componenti specifici:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-18 | Schedule Registrar | Registra/aggiorna i job dei compiti attivi |
| C-19 | Recovery Handler | Recupera i compiti saltati (una volta) al rientro online |
| C-20 | Delivery Service | Determina e invia il risultato ai destinatari |

## Progettazione componenti

### C-18 — Schedule Registrar
- **Responsabilità:** tradurre lo `Schedule` di un compito in un job APScheduler, con timezone del
  telefono; persistenza del `next_run`.
- **Interfaccia pubblica:** `register(task)`, `update(task)`, `unregister(task_id)`.
- **Dipendenze:** C-06, C-02, C-16.
- **Input:** `Task`. **Output:** job attivo.
- **Error handling:** schedule non valido → errore al momento della creazione (spec 02).
- **Osservabilità:** log job registrato con `next_run`.
- **Sicurezza:** nessuna esecuzione privilegiata autonoma; il job invoca solo C-09.

### C-19 — Recovery Handler
- **Responsabilità:** al ritorno online dopo un periodo offline, rilevare le occorrenze mancate e
  **recuperarle una sola volta**, riferite all'**ultima occorrenza mancata** (BR-5, decisione #8).
- **Interfaccia pubblica:** `recover_missed() -> list[ExecutionResult]`.
- **Dipendenze:** C-02, C-06, C-09, C-07 (`is_online`).
- **Input:** `next_run` persistiti e timestamp dell'ultimo periodo offline. **Output:** esecuzioni
  di recupero + marcature delle occorrenze saltate.
- **Error handling:** più occorrenze mancate → si esegue solo l'ultima; le precedenti vengono
  registrate come `saltate` (non rilanciate).
- **Osservabilità:** log recupero con conteggio occorrenze saltate.

### C-20 — Delivery Service
- **Responsabilità:** calcolare i destinatari del compito (admin + utenti iscritti) e inviare il
  risultato (C-10).
- **Interfaccia pubblica:** `deliver(task, result)`.
- **Dipendenze:** C-02, C-10. **Input:** compito + risultato. **Output:** invii.
- **Error handling:** invio fallito a un destinatario → retry BR-8; risultati troppo lunghi → split.
- **Osservabilità:** log destinatari ed esiti invio.

## Modello di dominio

- **Esecuzione:** `id`, `task_id`, `requested_by` (null per programmata), `trigger`, `started_at`,
  `finished_at`, `outcome`, `summary`.
- **Innesco:** `scheduled` | `recovery`.
- **Esito:** `ok` | `errore` | `interrotto` | `saltata` (BR-15, emendato dalla decisione D1 del
  2026-10-24: `saltata` marca un'occorrenza mancata).

## Modello dati

Tabella `executions` (vedi spec 01). `settings` conserva i marcatori di stato (ultimo periodo
offline, `next_run` per i compiti per il recupero).

## Flussi di dati

1. **Esecuzione programmata:** C-06 scatta all'orario → C-09 carica il compito → C-05 ragiona e
   pianifica i tool → C-08 esegue gli strumenti (read-only diretti; modificanti con gate, spec 06)
   → C-20 invia ai destinatari → C-11 registra l'esito.
2. **Recupero:** al rientro online (rilevato da C-07) → C-19 confronta `next_run` mancati → esegue
   **una volta** l'ultima occorrenza → C-11 registra anche le occorrenze saltate.
3. **Timeout:** C-09 avvia un timer di 10 min → allo scadere interrompe, registra `interrotto` →
   C-10 avvisa l'admin (spec 10).
4. **Retry:** C-05/C-10 ricevono errore → ritentano 3× a 1 min → se persiste, esito `errore` →
   avviso admin (spec 10).

## Progettazione integrazioni

- **APScheduler:** trigger temporali e persistenza job.
- **DeepSeek:** ragionamento e tool calling.
- **Tool esterni:** ricerca web, lettura log (spec 06/07).
- **Telegram:** invio risultati.

## Requisiti di sicurezza

- Gli strumenti modificanti usano il gate di approvazione (BR-2, spec 06).
- Le letture log rispettano l'allowlist del compito (BR-13).
- I risultati vanno solo ai destinatari autorizzati (BR-12).

## Requisiti non funzionali

- **Durata massima esecuzione:** 10 minuti (BR-4).
- **Retry:** 3 tentativi a 1 minuto (BR-8).
- **Recupero:** una sola occorrenza (BR-5).
- **Volume:** ≤ 10 compiti attivi (BR-16).
- **Osservabilità:** ogni esecuzione registrata nello storico (FR-008).

## Rischi e assunzioni

- **Rischio:** overlap se un'esecuzione dura vicino al successivo trigger → mitigato da lock per
  compito (spec 04) e timeout 10 min.
- **Rischio:** recupero erroneo se più occorrenze mancano → semantica esplicita "ultima occorrenza".
- **Assunzione:** il telefono riporta correttamente lo stato di connettività (Termux:API).

## Domande tecniche aperte

- Definizione precisa di "offline": assenza di rete vs processo non attivo (impatta anche spec 11).
- Come marcare le occorrenze intermedie mancate nello storico (nuovo esito `saltata`? stato
  separato?). BR-15 elenca solo `ok|errore|interrotto`.

**Risposte (operatore, 2026-10-24 — decisioni D1/D2 del piano 03):** offline = assenza di rete
rilevata da C-07, con recupero anche all'avvio; il processo spento e il messaggio di ripartenza
restano di spec 11, che delegherà a C-19. Le occorrenze intermedie si registrano con il nuovo esito
`saltata`; BR-15 e il modello dati di spec 01 sono stati emendati di conseguenza.

## Criteri di accettazione

- **AC-01** Dato un compito attivo programmato alle 8:00, quando arrivano le 8:00, allora i
  destinatari ricevono il risultato su Telegram senza alcun intervento.
- **AC-02** Dato il telefono offline alle 8:00 che torna online alle 9:30, quando l'agente riparte,
  allora esegue il compito saltato una sola volta.
- **AC-03** Dato un compito che supera 10 minuti, quando scade il limite, allora viene interrotto,
  registrato come "interrotto" e l'amministratore viene avvisato.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-002, BR-4/5/8/14, §8 (journey 1), §12.

## Assunzioni

- **A-01** Scheduler APScheduler in-process con `next_run` persistito (decisione #4).
- **A-02** Semantica recupero = una volta, ultima occorrenza (decisione #8).

## Domande in sospeso

- Definizione di "offline" e rappresentazione delle occorrenze saltate: **chiuse** il 2026-10-24
  (D1/D2 del piano 03; vedi sopra).

## Valutazione di confidenza

**Alta** — FR-002 documentato con regole e criteri di accettazione; residui solo dettagli di
rappresentazione non funzionali.

## Note di implementazione

- C-18 `src/agente/schedule_registrar.py`: `register/update/unregister` + `refresh/sync/next_run`;
  marcatore `next_run:<task_id>` in `settings`; C-15 ora passa da C-18 (V-08).
- C-19 `src/agente/recovery.py`: `recover_missed()` asincrona e `check_connectivity()`; recupera
  solo l'ultima occorrenza mancata, marca le precedenti `saltata`; recupero anche all'avvio con
  scheduler in pausa (D2), marcatore avanzato per idempotenza.
- C-20 `src/agente/delivery.py`: admin implicito + iscritti `accepted` filtrati al momento
  dell'invio; consegna via C-10 con split e retry.
- C-09 `src/agente/execution.py`: loop tool-calling read-only (max 5 cicli), consegna dentro il
  timeout BR-4, esito `errore` + avviso admin su fallimento persistente o consegna parziale;
  strumenti modificanti rifiutati finché il gate C-27/C-28 non esiste (D3).
- Migrazione `003_execution_skipped.sql`: CHECK di `executions` esteso a `saltata` con copia
  integrale dei dati; BR-15 e il modello dati di spec 01/09 emendati il 2026-10-24.
- Config: `limits.connectivity_check_s` (default 60, D4).
- Test: 175 raccolti, tutti verdi (`PYTHONPATH=src:.deps python3 -m pytest`), inclusi AC-01…AC-03
  in `tests/test_scheduled_ac.py`.
- Documento: [03-fr002-esecuzione-programmata.md](../architecture/03-fr002-esecuzione-programmata.md),
  checkpoint di struttura `sdd-governor` APPROVED (2026-10-24).

## Nota di continuità (2026-10-25, voce 06)

Il gate C-27/C-28 è stato consegnato. Gli strumenti modificanti non sono più rifiutati a priori:
C-09 espone al modello anche i loro schemi e li esegue tramite C-27 solo dopo approvazione
dell'admin. Un rifiuto o un timeout è un esito di tool e l'esecuzione prosegue (V-08/V-10 della voce
06); `SearchError` è anch'esso un esito di tool (V-12). BR-4 resta invariato e racchiude l'attesa
dell'approvazione: al timeout l'esecuzione è `interrotta` e la richiesta pendente è `rejected`
(V-05). Il comportamento «modificante = errore» descritto nelle note del 2026-10-24 è quindi
superato.

## Nota di continuità (2026-10-29, voce 07)

`LogAccessError` (percorso di log fuori dall'allowlist del compito) è un **esito di tool** e non un
guasto: C-09 avvisa l'admin con i percorsi rifiutati, restituisce il contenuto parziale al modello e
antepone al testo consegnato la nota `Log non autorizzati: <percorsi>`. Tutti gli altri errori di
tool restano fatali come in item 03/06. BR-4 resta invariato e racchiude anche la lettura dei log.

## Nota di continuità (2026-11-03, voce 10)

C-19 non scrive più `offline_since` né `last_contact_at`: il periodo offline e il rientro sono
tracciati da C-37 (voce 10), che C-19 invoca con `monitor.check_online()`. `recover_missed` usa
`await monitor.is_online()` in sola lettura, quindi un riavvio non duplica l'avviso di rientro.
`OFFLINE_SINCE` resta riesportato da `recovery.py` per compatibilità; il costruttore di C-19 non
riceve più `settings` e riceve `monitor`. Recupero, BR-5 e idempotenza restano invariati.

## Nota di continuità (2026-11-04, voce 11)

C-19 espone in aggiunta `last_summary` (`RecoveryStats`: recuperate, fallite, saltate, rinviate,
mancate) azzerato all'ingresso di `recover_missed`/`check_connectivity`; il ritorno
`list[ExecutionResult]`, BR-5 e l'idempotenza sul marcatore `next_run` restano invariati. C-39
consuma il riepilogo per il messaggio di ripartenza; un `AgenteError` dal recupero di avvio fa
fallire l'avvio e il loop esterno riavvia il processo.

# Specifica 01 — Agent Runtime (fondazione)

- **ID:** `01-agent-runtime`
- **Stato:** Implemented (2026-10-21)
- **Requisiti collegati:** nessun FR diretto — fondazione architetturale che abilita FR-001…FR-010
- **Dipendenze:** nessuna
- **Priorità:** Must (fondazione)
- **Data:** 2026-10-07

## Contesto funzionale

L'Agente Personale Telegram è un processo sempre attivo che gira su uno smartphone Samsung S24 in
Termux, senza permessi di root. Questa specifica definisce la **fondazione tecnica condivisa** su
cui si appoggiano tutte le altre feature: bootstrap del processo, configurazione, persistenza,
gateway Telegram, controllo dei ruoli, client LLM, accesso al device, scheduler, logging e
retention.

Non implementa da sola alcun requisito funzionale osservabile dall'utente finale; è il prerequisito
comune. Ogni altra specifica (02–11) presuppone i componenti qui definiti e **non li ridefinisce**.

## Panoramica architetturale

Processo **singolo** in Python 3 su Termux. Architettura a componenti in-process, senza servizi
separati (coerente con i volumi previsti da BR-16: fino a 5 utenti, 10 compiti).

- **Runtime:** asyncio event loop; `python-telegram-bot` in long polling; `APScheduler`
  (`AsyncIOScheduler`) per i compiti programmati e i job di manutenzione.
- **Persistenza:** un unico file **SQLite** in directory privata dell'applicazione; il job store di
  APScheduler usa lo stesso database (tabelle separate) o un file dedicato nella stessa directory.
- **Device:** un unico *device adapter* incapsula Termux:API e l'esecuzione di comandi/file via
  subprocess; nessun altro componente accede direttamente al sistema operativo.
- **LLM:** un unico *client DeepSeek* incapsula le chiamate API e la gestione del contesto.
- **Tool:** un *tool registry* espone gli strumenti (`web_search`, `read_logs`, azioni device) con
  la relativa policy di conferma.

Diagrammi Mermaid non inclusi: generati a valle in `/SDD-implement`.

### Componenti

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-01 | Config Loader | Carica config file e segreti |
| C-02 | Storage | Accesso SQLite, migrazioni, transazioni |
| C-03 | Telegram Gateway | Long polling, invio messaggi, inline keyboard |
| C-04 | Role Guard | Identità e autorizzazione per ruolo |
| C-05 | LLM Client | Chiamate DeepSeek, budget contesto, tool calling |
| C-06 | Scheduler | Job compiti + manutenzione, wake-lock, boot |
| C-07 | Device Adapter | Termux:API + subprocess, gate azioni |
| C-08 | Tool Registry | Strumenti disponibili e policy conferma |
| C-09 | Execution Engine | Esecuzione compito, lock, timeout, retry |
| C-10 | Notification Service | Invio risultati, avvisi, conferme |
| C-11 | History & Retention | Storico esecuzioni, retention, reset conversazioni |
| C-12 | Supervisor | Watchdog di processo, self-heal |
| C-13 | Logging | Log strutturato applicativo |

## Progettazione componenti

### C-01 — Config Loader
- **Responsabilità:** caricare configurazione e segreti; validare i campi obbligatori all'avvio.
- **Interfaccia pubblica:** `load_config() -> Config` (immutabile, tipizzato).
- **Dipendenze:** filesystem.
- **Input:** config file TOML (es. `~/.config/agente/config.toml`, `chmod 600`) e file segreti
  separati (`chmod 600`) o variabili d'ambiente.
- **Output:** oggetto `Config` con: `admin_telegram_id`, `deepseek.model` (default
  `deepseek-flash`), `deepseek.api_base`, `deepseek.max_context_tokens`, `telegram.token`,
  `deepseek.api_key`, `search.provider`, `search.api_key`, `paths.db`, `paths.logs`,
  `limits.*` (10 min, 3 retry/1 min, 15 min conferma, 30 gg storico, 24 h chat, batteria 15%,
  offline 1 h, liveness 08:00).
- **Error handling:** campo obbligatorio mancante o segreto illeggibile → errore fatale in avvio,
  nessuna esecuzione parziale; errore loggato senza stampare valori segreti.
- **Scalabilità:** N/A (config statica).
- **Osservabilità:** log "config caricata" con elenco chiavi non segrete.
- **Sicurezza:** segreti mai loggati; permessi `600` verificati; nessun segreto in git.

### C-02 — Storage
- **Responsabilità:** unico punto di accesso a SQLite; schema e migrazioni; transazioni.
- **Interfaccia pubblica:** repository per entità (tasks, users, subscriptions, executions,
  conversations, approvals, settings) + `migrate()`.
- **Dipendenze:** SQLite (`sqlite3` stdlib); C-01.
- **Input/Output:** operazioni CRUD tipizzate.
- **Error handling:** errori transazionali → rollback e propagazione; `database is locked` →
  retry breve con backoff.
- **Scalabilità:** `WAL` mode; indici su `executions(task_id, started_at)`, `messages(user_id,
  created_at)`.
- **Osservabilità:** log di migrazione versione schema.
- **Sicurezza:** file DB `chmod 600`; nessuna copia esterna (FR §10).

### C-03 — Telegram Gateway
- **Responsabilità:** ricezione update via long polling; invio messaggi, risultati, avvisi;
  inline keyboard Approva/Rifiuta/Autorizza.
- **Interfaccia pubblica:** `send(chat_id, text, keyboard=None)`, handler registrati dai consumer.
- **Dipendenze:** `python-telegram-bot`; C-01, C-04.
- **Input:** update Telegram; Output: messaggi Telegram.
- **Error handling:** errori rete/API → BR-8 (3 tentativi, 1 min); messaggi troppo lunghi → split.
- **Scalabilità:** N/A volumi BR-16.
- **Osservabilità:** log invio/errore; conteggio messaggi.
- **Sicurezza:** token `600`; update da mittenti non autorizzati passano da C-04 prima di qualsiasi
  risposta utile.

### C-04 — Role Guard
- **Responsabilità:** determinare il ruolo effettivo di ogni mittente e applicare i permessi
  (BR-12/BR-18).
- **Interfaccia pubblica:** `resolve_role(telegram_id) -> ADMIN | AUTHORIZED | UNKNOWN`;
  decoratori `@admin_only`, `@authorized_or_admin`.
- **Dipendenze:** C-01 (admin id), C-02 (utenti e stati).
- **Input:** `telegram_id`. **Output:** ruolo + stato utente.
- **Error handling:** mittente non risolvibile → trattato come `UNKNOWN`.
- **Osservabilità:** log decisioni di autorizzazione.
- **Sicurezza:** admin **solo** da config (non modificabile da chat); utente `revoked` equivale a
  `UNKNOWN`; autorizzazione utenti riservata all'admin.

### C-05 — LLM Client
- **Responsabilità:** chiamate a DeepSeek; costruzione contesto entro budget; tool calling.
- **Interfaccia pubblica:** `chat(messages, tools=None) -> Response`, `summarize(text) -> str`.
- **Dipendenze:** C-01; API DeepSeek (compatibile OpenAI).
- **Input:** messaggi + tool schema. **Output:** testo e/o tool call.
- **Error handling:** timeout/rete/HTTP → BR-8 (3 tentativi, 1 min); chiave invalida/senza credito →
  evento di avviso (FR-009) e fallimento dell'operazione; risposta malformata → errore controllato.
- **Scalabilità:** contesto troncato ai turni più recenti entro `max_context_tokens` (~8k).
- **Osservabilità:** log latenza, esito, token stimati.
- **Sicurezza:** chiave `600`; nessun log del contenuto dei segreti; contenuto transita da DeepSeek
  per natura (informativa privacy, FR-007).

### C-06 — Scheduler
- **Responsabilità:** job dei compiti attivi (orario/intervallo, timezone telefono) + job di
  manutenzione (retention, reset chat, liveness).
- **Interfaccia pubblica:** `schedule_task(task)`, `unschedule_task(id)`, `next_run(id)`.
- **Dipendenze:** APScheduler; C-02; C-09.
- **Input:** definizione compito. **Output:** trigger di esecuzione.
- **Error handling:** job fallito → registrato, non blocca gli altri job; `next_run` persistito per
  il recupero post-riavvio (BR-5).
- **Scalabilità:** 10 compiti attivi (BR-16).
- **Osservabilità:** log trigger, esecuzioni, drift.
- **Sicurezza:** nessuna azione privilegiata autonoma: il job invoca solo C-09.

### C-07 — Device Adapter
- **Responsabilità:** unico punto di lettura stato device e di esecuzione azioni che modificano il
  telefono.
- **Interfaccia pubblica:** `battery_level() -> int`, `is_online() -> bool`,
  `run_command(cmd, approved: bool)`, `read_file(path, allowlist, approved)`,
  `write_file(...)`, `delete_file(...)`.
- **Dipendenze:** Termux:API (`termux-battery-status`, `termux-wifi-connectioninfo`); subprocess
  Python; C-02/C-08.
- **Input:** richieste di lettura/azione. **Output:** dati o esito azione.
- **Error handling:** tool Termux:API assente → errore esplicito; comando non approvato → rifiuto.
- **Osservabilità:** log di ogni azione proposta/eseguita.
- **Sicurezza:** **nessuna** azione modificante eseguita senza approvazione admin (BR-2, FR-005);
  lettura log solo da allowlist del compito (BR-13).

### C-08 — Tool Registry
- **Responsabilità:** elenco strumenti disponibili per l'agente con metadati e policy di conferma.
- **Interfaccia pubblica:** `tools() -> list[Tool]`, con flag `read_only` / `requires_approval`.
- **Dipendenze:** C-05, C-07.
- **Policy:** `web_search` e letture = read-only (no conferma); comandi/file/install = richiedono
  approvazione (A4, BR-2).
- **Osservabilità:** log tool invocato e decisone di gate.

### C-09 — Execution Engine
- **Responsabilità:** eseguire un compito end-to-end: lock, contesto, LLM, tool, timeout, retry,
  registrazione esito.
- **Interfaccia pubblica:** `execute(task, trigger, requester) -> ExecutionResult`.
- **Dipendenze:** C-05, C-06, C-07, C-08, C-10, C-11.
- **Input:** compito + innesco (`scheduled` | `manual` | `recovery`).
- **Output:** risultato, destinatari, esito `ok|errore|interrotto`.
- **Error handling:** superamento 10 min → interruzione + avviso (BR-4, FR-009); LLM/Telegram →
  BR-8; lock già detenuto → rifiuto overlap.
- **Scalabilità:** un'esecuzione per compito alla volta.
- **Osservabilità:** log inizio/fine, durata, esito.
- **Sicurezza:** delega ogni azione modificante a C-07 con gate.

### C-10 — Notification Service
- **Responsabilità:** invio risultati ai destinatari, avvisi admin, richieste di conferma, messaggi
  di sistema (ripartenza, liveness).
- **Interfaccia pubblica:** `notify(recipients, text)`, `alert_admin(text)`,
  `request_approval(...)`.
- **Dipendenze:** C-03, C-04. **Error handling:** BR-8.
- **Osservabilità:** log invii e fallimenti.

### C-11 — History & Retention
- **Responsabilità:** registrazione esecuzioni, query storico, retention 30 gg, reset conversazioni
  24 h.
- **Interfaccia pubblica:** `record(execution)`, `query(user, filter)`, `purge_expired()`.
- **Dipendenze:** C-02. **Job:** giornaliero per retention e reset.
- **Osservabilità:** log conteggi purgati.

### C-12 — Supervisor
- **Responsabilità:** mantenere il processo vivo; riavvio del processo dopo crash.
- **Interfaccia pubblica:** script di boot `~/.termux/boot/` + `termux-wake-lock`; watchdog interno.
- **Dipendenze:** sistema Termux. **Error handling:** riavvio con backoff; stato persistito in DB.
- **Osservabilità:** log avvio/riavvio; evento di ripartenza verso C-10 (FR-010, spec 11).

### C-13 — Logging
- **Responsabilità:** log strutturato applicativo (JSON line) su file in directory app + console.
- **Interfaccia pubblica:** logger condiviso.
- **Sicurezza:** nessun segreto nei log; i log applicativi sono leggibili come compito log
  (spec 07).
- **Retention:** rotazione per dimensione/tempo.

## Modello di dominio

Entità concettuali (dettaglio nello schema dati):

- **Compito** — attività ricorrente o su richiesta definita dall'admin.
- **Utente** — persona abilitata; l'admin è definito in config, non è un record.
- **Iscrizione** — relazione utente ↔ compito.
- **Esecuzione** — singola corsa di un compito, con innesco ed esito.
- **Conversazione / Messaggio** — memoria di chat per utente.
- **RichiestaConferma** — azione proposta in attesa di approvazione admin.
- **Impostazioni/Stato** — parametri e marcatori di stato (ultima liveness, ultimo online).

Relazioni: Utente 1→N Messaggio; Utente N↔N Compito (via Iscrizione); Compito 1→N Esecuzione;
RichiestaConferma N→1 Utente richiedente.

## Modello dati (SQLite)

| Tabella | Colonne principali |
|---------|--------------------|
| `tasks` | `id` PK, `name` UNIQUE, `instructions`, `schedule_type`, `schedule_expr`, `state` (`active`/`paused`), `log_allowlist` (JSON), `created_by`, `created_at`, `updated_at` |
| `users` | `telegram_id` PK, `username`, `state` (`pending`/`accepted`/`revoked`), `consent_at`, `created_at`, `updated_at` |
| `subscriptions` | `user_id`, `task_id`, PK(`user_id`,`task_id`) |
| `executions` | `id` PK, `task_id` FK, `requested_by`, `trigger` (`scheduled`/`manual`/`recovery`), `started_at`, `finished_at`, `outcome` (`ok`/`errore`/`interrotto`/`saltata`), `summary` |
| `conversations` | `user_id` PK, `updated_at` |
| `messages` | `id` PK, `user_id` FK, `role`, `content`, `created_at` |
| `approvals` | `id` PK, `action`, `reason`, `requested_by`, `status` (`pending`/`approved`/`rejected`), `created_at`, `expires_at`, `resolved_at` |
| `settings` | `key` PK, `value` |
| `apscheduler_jobs` | job store APScheduler (gestito dalla libreria) |

Vincoli: `state` solo valori ammessi (BR-15); `outcome` solo `ok|errore|interrotto|saltata`
(`saltata` introdotto da spec 03, decisione D1 del 2026-10-24, per le occorrenze mancate: non è
prodotto da C-09 e non conta come esecuzione avvenuta); retention
applicata da C-11.

## Flussi di dati

1. **Avvio:** C-01 carica config → C-02 migra schema → C-12 acquisisce wake-lock e avvia il
   processo → C-03 inizia polling → C-06 carica job attivi → evento di ripartenza (spec 11).
2. **Messaggio in ingresso:** Telegram → C-03 → C-04 risolve ruolo → handler competente (spec
   feature).
3. **Messaggio in uscita:** componente → C-10 → C-03 → Telegram.
4. **Azione modificante:** C-08 rileva `requires_approval` → C-10 richiede conferma all'admin →
   esito → C-07 esegue solo se approvato (spec 06).
5. **Manutenzione:** C-06 → C-11 `purge_expired()` (retention 30 gg, reset chat 24 h).

## Progettazione integrazioni

| Integrazione | Direzione | Protocollo |
|--------------|-----------|-----------|
| Telegram Bot API | both | HTTPS, long polling |
| DeepSeek API | both | HTTPS, compatibile OpenAI |
| Web search provider | receive | HTTPS (adapter pluggable, spec 06) |
| Termux:API | receive | comando locale |
| Android (subprocess/file) | both | locale |

Contratti: Telegram e DeepSeek incapsulati in C-03/C-05; il resto dell'app non li usa direttamente.

## Requisiti di sicurezza

- Admin identificato **solo** da config; nessun percorso per promuovere admin da chat (BR-12).
- Utenti sconosciuti/revocati ignorati; primo contatto → avviso admin (BR-18/spec 08).
- Nessuna azione modificante senza approvazione admin (BR-2).
- Segreti (Telegram token, DeepSeek key, search key) `chmod 600`, mai in git, mai nei log.
- Dati solo sull'S24, nessuna copia esterna (FR §10).
- Log applicativi trattati come dato locale, accessibili solo via allowlist (BR-13).

## Requisiti non funzionali

- **Volume:** ≤ 5 utenti autorizzati, ≤ 10 compiti attivi (BR-16).
- **Disponibilità:** 24/7 finché S24 acceso e connesso; ripartenza automatica (spec 11).
- **Affidabilità:** retry 3× a 1 min su DeepSeek/Telegram (BR-8); timeout esecuzione 10 min (BR-4).
- **Prestazioni:** risposta chat 30 s; 2 min con ricerca web (BR-17).
- **Osservabilità:** log strutturato; liveness giornaliero (spec 11).
- **Manutenzione:** retention 30 gg, reset chat 24 h (BR-7, BR-6).

## Rischi e assunzioni

- **Rischio:** kill del processo da parte di Android (battery optimization) → mitigato da wake-lock,
  autostart e Supervisor (C-12); validare su dispositivo reale.
- **Rischio:** perdita del file SQLite → nessuna copia per requisito (FR §10); recovery/ripartenza
  ricostruisce lo stato da zero, compiti persi.
- **Rischio:** dipendenza da Termux:API non installato → errore esplicito.
- **Assunzione A1:** S24 sempre acceso e connesso (FR §6).

## Domande tecniche aperte

- Meccanismo esatto di supervisione (watchdog in-process vs `termux-services`/script boot
  con reinvocazione): da validare su dispositivo.
- Modalità di rilevamento "stato offline prolungato" (assenza di connessione vs processo non
  attivo): impatta BR-10/spec 11.
- Necessità di cifratura at-rest del DB (non richiesta da FR; oggi solo permessi `600`).

> **Risolte (2026-10-21, vedi Note di implementazione):** supervisione = D1 (boot script +
> watchdog su thread); offline prolungato = D2 (`termux-wifi-connectioninfo` + timestamp);
> cifratura = D3 (nessuna, solo permessi `600`). Resta la validazione sul dispositivo reale.

## Criteri di accettazione

- **AC-01** Dato un config valido, quando l'app parte, allora carica config, migra lo schema,
  avvia polling e scheduler senza intervento manuale.
- **AC-02** Dato un config con campo obbligatorio mancante o segreto illeggibile, quando l'app
  parte, allora termina con errore esplicito e senza avviarsi a metà.
- **AC-03** Dato un mittente admin, autorizzato, sconosciuto o revocato, quando invia un messaggio,
  allora C-04 risolve il ruolo corretto e applica i permessi di BR-12.
- **AC-04** Data una chiamata DeepSeek/Telegram che fallisce, quando l'operazione viene ritentata,
  allora effettua 3 tentativi a 1 minuto prima di dichiarare fallimento.
- **AC-05** Dato il riavvio del processo, quando riparte, allora ricarica i job attivi dallo stato
  persistito.

## Fonti documentali

- `docs/input/functional-requirements.md` §2, §5, §6 (A1–A5), §7, §9, §10, §11, §12, §13, §15.

## Assunzioni

- **A-01** Stack Python 3 su Termux (`python-telegram-bot` + APScheduler + SQLite) — confermata
  dall'utente (decisione #2).
- **A-02** Config in TOML `chmod 600` con segreti separati — confermata (decisione #11).
- **A-03** Scheduler APScheduler in-process + wake-lock + autostart boot — confermata (#4).
- **A-04** Device adapter basato su Termux:API + subprocess — confermata (#5).
- **A-05** Model id `deepseek-flash` configurabile — confermata (#10).

## Domande in sospeso

- Supervisione processo e rilevamento offline prolungato (vedi Domande tecniche aperte).
- Cifratura at-rest non richiesta: confermare che i soli permessi `600` siano sufficienti.

> **Risolte (2026-10-21):** vedi D1/D2/D3 nelle Note di implementazione.

## Valutazione di confidenza

**Media** — feature derivata dall'architettura, non da un requisito funzionale esplicito;
le scelte tecniche sono state confermate dall'utente, ma i dettagli di supervisione su Termux
restano da validare sul dispositivo.

## Note di implementazione (2026-10-21)

- **Decisioni che chiudono le domande aperte:** D1 supervisione = boot script `~/.termux/boot/`
  + wake-lock + loop di riavvio esterno e watchdog in-process su thread separato; D2 offline =
  `termux-wifi-connectioninfo` + `last_contact_at` in `settings` (alerting in spec 11); D3 nessuna
  cifratura at-rest, solo permessi `600`; D4 versioni librerie fissate e registrate nella
  constitution (Tech Stack).
- **Deliverable:** `src/agente/` (C-01…C-13), migrazione `001_init.sql`, repository tipizzati,
  script di boot, test pytest (AC-01…AC-05 + unit), documento
  `docs/architecture/01-agent-runtime.md`, config di esempio.
- **Deviazioni d'interfaccia** (semantica invariata): C-04 decoratori come factory
  `admin_only(guard)`; C-06 `schedule_task(task, trigger)` con trigger interpretato da spec 02;
  C-11 parametri keyword. Dettaglio nel piano `docs/plan/01-agent-runtime.plan.md`.
- **Follow-up tracciati:** evento di ripartenza (spec 11), tasto «Autorizza» (spec 08),
  `web_search` (spec 06), gate C-27/C-28 (spec 06), validazione su dispositivo reale.
- **Assunzioni non dichiarate dalla spec:** soglia watchdog 300 s; job di manutenzione ogni 24 h
  dall'avvio; `search` opzionale finché spec 06 non fissa il provider.

## Note di implementazione (2026-10-24, voce 05)

- **C-03 (V-04 della voce 05):** `send(...)` restituisce l'id dell'ultimo messaggio inviato e nasce
  `delete_message(chat_id, message_id)` con retry BR-8. Servono a C-25 per rimuovere l'indicatore
  «sto cercando…». I chiamanti esistenti ignorano il valore di ritorno: semantica invariata.
- **Modello dati (V-06 della voce 05):** la migrazione `004_chat_without_user_fk.sql` ricostruisce
  `conversations` e `messages` **senza FK verso `users`**, perché l'admin non è un record `users`
  (decisione #7) ma deve poter avere una conversazione (FR-004). Dati, id, `sqlite_sequence` e
  indice `idx_messages_user_created` sono preservati.
- **C-11 e C-24:** la retention dei messaggi per età resta di C-11 (`purge_expired`, finestra
  `chat_memory_hours`); la semantica della conversazione (silenzio, `reset`, `purge_idle`) è di
  C-24 (spec 05). Il job di manutenzione chiama entrambe le operazioni, con la stessa soglia.
- **C-06 (V-10 della voce 05):** `_run_maintenance_job` è una coroutine eseguita nell'event loop,
  dove vive la connessione SQLite (`check_same_thread=True`); accetta callback sincroni e
  coroutine. La firma di `schedule_maintenance(callback)` non cambia.

## Nota di continuità (2026-10-25, voce 06)

- **C-08:** gli handler modificanti accettano `approved` con default `False`; la registrazione rifiuta
  anche i metadati contraddittori (`read_only=True` + `requires_approval=True`) e `web_search` è nel
  catalogo della fondazione (read-only). Il contratto resta `handler(context, arguments)` per i
  read-only.
- **C-10:** nasce `send_approval(approval)` per inviare i bottoni di una richiesta già creata;
  `request_approval` resta come wrapper di compatibilità. Il ciclo di vita è di C-28.
- **C-01:** `search.provider` ha default `tavily` (D2 della voce 06); `search.api_key` resta da
  `SEARCH_API_KEY`.
- **C-02:** `ApprovalRepository.reject_pending(resolved_at)` scarta le richieste aperte all'avvio;
  nessuna migrazione, la tabella `approvals` è invariata.

## Nota di continuità (2026-10-29, voce 07)

- **C-07:** nuove primitive per i log — `inspect_path` (`PathInfo`: esiste, file, cartella,
  dimensione, leggibile), `read_file_tail` (ultimi N caratteri con budget di 4 byte per carattere) e
  `list_files` (file regolari, non ricorsivo, symlink e sottocartelle contati). Tutte applicano
  l'allowlist; `read_file` resta invariata.
- **C-08:** `read_logs` accetta un file **o una cartella** autorizzata, passa da C-29 e il registry
  accetta un `log_reader` iniettabile; resta read-only e senza conferma.
- **C-13:** la cartella `paths.logs` (`agente.jsonl` e rotazioni) è leggibile come compito log quando
  l'amministratore la autorizza; il contenuto resta testo, senza parsing.

## Nota di continuità (2026-11-01, voce 08)

- **C-03:** `IncomingMessage` espone `username`, popolato da `effective_user.username` per i messaggi
  e da `query.from_user.username` per i callback; serve all'avviso di C-33. Nessun altro campo cambia.
- **C-10:** `notify` e `alert_admin` accettano una tastiera opzionale, applicata all'ultimo chunk, così
  C-33 invia il pulsante «Autorizza» senza parlare direttamente con C-03.
- **C-04:** invariato; `pending` e `revoked` continuano a valere `UNKNOWN`.

## Nota di continuità (2026-11-02, voce 09)

- **C-02:** la migrazione `005_executions_started_index.sql` normalizza gli istanti esistenti a UTC e
  crea `idx_executions_started`; nessuna tabella o colonna nuova. Il nuovo helper `commit()` converte
  gli errori di commit in `StorageError`, così nessun altro layer importa `sqlite3`.
- **C-11:** `record`/`record_skipped`/`finish` normalizzano gli istanti a UTC (C-09 scrive UTC, C-19
  l'offset locale); i cutoff di retention e reset sono calcolati in UTC; `purge_expired` logga i
  conteggi e resta l'unico `DELETE` esplicito sulle esecuzioni. C-35 è assorbito da C-11.
- **C-06:** job di manutenzione invariato; `AgentApp._maintenance` isola retention e `purge_idle`.

## Nota di continuità (2026-11-03, voce 10)

- **C-05:** `LLMClient` accetta `on_credentials_error(status, body)` e lo invoca su 401/402/403 prima
  di `LLMCredentialsError`, che espone `.status`; il corpo è troncato a 500 caratteri e non è
  loggato. Il comportamento senza callback resta invariato.
- **C-07:** `battery_level`, `is_online` e `record_last_contact` restano invariati; `last_contact_at`
  è scritto per compatibilità, `last_online_at` e `offline_since` sono di C-37 (voce 10).
- **C-10:** `alert_admin` resta l'unico canale di invio degli avvisi; C-36 compone e deduplica.
- **C-01:** nuova chiave `limits.battery_check_s = 300` (D2), validata come gli altri limiti.

## Nota di continuità (2026-11-04, voce 11)

- **C-06:** nuovo job `schedule_liveness(callback, *, at)` con id `liveness:send`, `CronTrigger`
  nella timezone dello scheduler, `replace_existing=True` e `misfire_grace_time=None`; errori del
  callback isolati.
- **C-01:** `limits.liveness_at` è validato in modo stretto come `HH:MM` (ora 0–23, minuti 0–59);
  resta l'unica sorgente dell'orario del segnale.
- **C-12 e script di boot:** invariati; wake-lock, autostart e loop di riavvio restano in
  `scripts/boot/`. C-39 non chiama C-07.
- **C-10:** invariato; ripartenza e segnale di vita usano `alert_admin`, con il retry BR-8 del
  gateway C-03.

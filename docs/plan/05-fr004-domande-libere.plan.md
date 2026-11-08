# Piano 05 — FR-004 Domande libere (chat)

- **Voce roadmap:** `05 — FR-004 Domande libere` (non spuntata)
- **Spec:** [05-fr004-domande-libere.spec.md](../specs/05-fr004-domande-libere.spec.md), Stato `New`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack, `## Roadmap`
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`: C-02 con `conversations`/`messages`, C-03, C-04, C-05, C-06, C-08, C-10, C-11, migrazioni 001–003), item 02 (C-14 router, forme NL, C-17), item 03 (C-20, timeout e retry del motore), item 04 (C-21/C-22, precedenza del lancio sul ramo di creazione)
- **Dipendenze non consegnate:** item 06 (FR-005): `web_search` non è registrato in C-08 e il gate C-27/C-28 non esiste
- **Data piano:** 2026-10-24
- **Stato piano:** approvato 2026-10-24; eseguito T1–T12 (delivery history: voce 05)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-24 Conversation Memory: `get_context(user_id)`, `append(user_id, message)`, `reset(user_id)`, `purge_idle()`, `messages(user_id, limit=50)`; finestra doppia (silenzio dall'ultimo messaggio utente + età del singolo messaggio) su `limits.chat_memory_hours`; troncamento dei turni più vecchi entro il budget | codice | `src/agente/chat_memory.py` |
| D-02 | Estensioni C-02 `ConversationRepository`: lettura messaggi per utente con `since`/`limit`, cancellazione totale per utente (reset), cancellazione delle conversazioni inattive e dei loro messaggi (purge); nessuna nuova tabella | codice | `src/agente/storage/repositories.py` |
| D-03 | Migrazione 004: ricostruzione di `conversations` e `messages` **senza FK verso `users`** (D2), dati preservati, `sqlite_sequence` e indice `idx_messages_user_created` ricreati | migrazione | `src/agente/storage/migrations/004_chat_without_user_fk.sql` |
| D-04 | C-25 Progress Indicator: `start(chat_id)`, `finish(chat_id)`; soglia `limits.chat_progress_s` (default 2 s, D5), invio di «sto cercando…», cancellazione best-effort; stato per `chat_id` con contatore di generazione e annullamento del timer di soglia se `finish` arriva prima dello scatto, così non compare un indicatore tardivo e un `finish` non cancella l'indicatore di una richiesta successiva | codice | `src/agente/progress.py` |
| D-05 | Estensione C-03: `send(...)` restituisce l'id dell'ultimo messaggio inviato; nuovo `delete_message(chat_id, message_id)` con retry BR-8 e classificazione degli errori | codice | `src/agente/telegram_gateway.py` |
| D-06 | C-23 Chat Handler: `handle(user_id, chat_id, text) -> ChatReply` asincrona; serializzazione per `user_id`, contesto da C-24, prompt di sistema, tool loop read-only su C-08 con `llm.chat` eseguito in `asyncio.to_thread`, C-25 durante l'attesa, append dopo la risposta, `/reset`, gestione `LLMError`; **unico punto di invio** della risposta (via C-03) | codice | `src/agente/chat.py` |
| D-07 | Estensione C-14: testo libero degli utenti autorizzati → C-23; per l'admin prima la bozza di compito completa, altrimenti C-23 (D1); comando `/reset` → C-23; comando admin `/chat <telegram_id>` per la rilettura (D3); aiuto aggiornato | codice | `src/agente/command_router.py` |
| D-08 | Config: nuova leva `limits.chat_progress_s` con default 2 (D5), validata come gli altri limiti; esempio aggiornato | configurazione | `src/agente/config.py`, `config/config.example.toml` |
| D-09 | Wiring `AgentApp`: costruzione di C-24, C-25, C-23; manutenzione giornaliera con un callback unico che chiama `history.purge_expired()` e `chat_memory.purge_idle()`; correzione del job di manutenzione perché giri nell'event loop (D8), accettando sia callback sincroni sia coroutine | codice | `src/agente/app.py`, `src/agente/scheduler.py` |
| D-10 | Test della voce: unit C-24/C-25/C-23, AC-01…AC-06 end-to-end sul router, migrazione 004 con dati, `/reset` e `/chat`, concorrenza per utente, tool modificante rifiutato, manutenzione a runtime, aggiornamento delle fixture e dei test toccati dal nuovo costruttore di C-14 e dal valore di ritorno di `send` | test | `tests/test_chat_memory.py`, `tests/test_progress.py`, `tests/test_chat.py`, `tests/test_chat_ac.py`, `tests/conftest.py`, `tests/test_command_router.py`, `tests/test_storage.py`, `tests/test_scheduler.py`, `tests/test_boundaries.py`, `tests/test_config.py` |
| D-11 | Documento architettura della feature con diagrammi Mermaid (flowchart componenti, sequenze dei flussi 1–4 di spec 05, ER `conversations`/`messages`) | documentazione | `docs/architecture/05-fr004-domande-libere.md` |
| D-12 | Pubblicazione: roadmap `[x]`, stato spec `Implemented` + note, delivery history, piano allineato, nota interpretativa in constitution per BR-17 (D7) | documentazione | `docs/specs/constitution.md`, `docs/specs/05-fr004-domande-libere.spec.md`, `docs/delivery-history.md`, questo piano |
| D-13 | Note di continuità sulle fonti modificate a monte: interfaccia C-03 (`send` con id, `delete_message`) e modello dati senza FK per chat, con rinvio alle deviazioni V-04/V-06 e a D2 | documentazione | `docs/specs/01-agent-runtime.spec.md`, `docs/architecture/01-agent-runtime.md` |

Nessuna tabella nuova oltre alla ricostruzione della migrazione 004. La leva `chat_progress_s` è l'unica
nuova configurazione: 30 s e 2 minuti restano limiti-obiettivo (D7) e non diventano timeout rigidi.

### Fuori scope di questa voce (dichiarato)

- **`web_search` e gate C-27/C-28 (spec 06):** C-23 espone al modello i soli strumenti read-only già
  registrati in C-08; `web_search` non esiste ancora. AC-06 resta **parzialmente validato** (indicatore e
  comportamento in attesa sì, ricerca web no): il gap è registrato in D-11/D-12 e si chiude con item 06.
  Nessuna azione modificante viene eseguita o approvata da questa voce.
- **Policy di allowlist dei log in chat (spec 07):** il contesto passato ai tool in chat ha allowlist vuota;
  `read_logs` resta quindi sempre rifiutato finché spec 07 non definirà un'autorizzazione per la chat.
- **Gestione utenti e consenso privacy (spec 08):** C-23 legge lo stato `accepted` e non lo modifica; la
  base della rilettura admin è l'informativa privacy di spec 08, qui solo richiamata.
- **Storico esecuzioni (spec 09):** `/chat` legge i messaggi, non le esecuzioni.
- **Avvisi e soglie (spec 10), riavvio/liveness (spec 11).**
- **Retention dei messaggi oltre le 24 ore:** esclusa per decisione D4.

## Decisioni che sbloccano il piano

Chiuse dall'operatore il 2026-10-24. Le domande tecniche aperte di spec 05 sono chiuse da D4 (retention
della rilettura) e D5 (soglia dell'indicatore); le altre risolvono conflitti con spec 01/02 o dipendenze.

| # | Domanda aperta / conflitto | Decisione | Impatto |
|---|----------------------------|-----------|---------|
| D1 | Testo libero dell'admin: spec 05 lo vuole in chat, spec 02 D4 impone la creazione solo in linguaggio naturale | **Bozza completa prima, chat come fallback.** C-14 tenta l'estrazione della bozza: se nome, istruzioni e testo di schedulazione sono tutti presenti → flusso di creazione di spec 02 (riepilogo + conferma); altrimenti → C-23. Nessun nuovo comando di creazione | D-07, V-07; rischio: una richiesta di creazione incompleta riceve una risposta di chat invece di «Indica quando…» (§Rischi) |
| D2 | L'admin non è un record `users` (spec 01) ma `conversations`/`messages` hanno FK verso `users`: la memoria chat dell'admin fallirebbe | **Migrazione 004 senza FK.** Si ricostruiscono le due tabelle senza il vincolo verso `users`, preservando dati, sequenza e indice. Gli utenti non vengono mai cancellati (solo revocati), quindi la perdita di `ON DELETE CASCADE` non ha effetti pratici | D-03, D-13, V-06 |
| D3 | Comando di rilettura admin non dichiarato da spec 05 (flusso 4) | **`/chat <telegram_id>`**: mostra gli ultimi messaggi di quell'utente; `/chat` senza argomento elenca gli utenti `accepted` con id. Solo admin | D-07, V-11; testi in P-A-03, limite in P-A-04 |
| D4 | Retention dei messaggi per la rilettura admin (domanda aperta di spec 05) | **24 ore, la stessa finestra della memoria** (`limits.chat_memory_hours`): un messaggio è in memoria se è più recente della finestra **e** la conversazione non è silente da più di 24 h. `/reset` cancella subito tutto. Nessuna nuova leva | D-01, D-02, V-09; rilettura admin = ciò che è ancora in memoria (P-A-09) |
| D5 | Soglia di «sto cercando…» e comportamento alla risposta (domanda aperta di spec 05) | **2 secondi**, configurabile con `limits.chat_progress_s`; alla risposta il messaggio indicatore viene **eliminato** (best effort) | D-04, D-05, D-08, V-04, V-12 |
| D6 | AC-06 richiede `web_search`, che arriva con spec 06 | **Procedere**: C-23 implementa il tool loop read-only e C-25; AC-06 è validato per indicatore e attesa, non per la ricerca web. Gap in delivery history | D-06, D-10, D-11, D-12 |
| D7 | BR-17 (30 s / 2 min, anche in constitution §Limiti operativi) e BR-8 (3 tentativi a 1 minuto) non possono valere insieme | **30 s e 2 minuti sono limiti-obiettivo, non timeout rigidi.** Nessun abort: C-05 applica i retry BR-8 e C-25 copre l'attesa; in caso di guasto l'utente riceve un messaggio di errore. La constitution **non viene modificata nei valori**: D-12 aggiunge una nota interpretativa che lascia BR-17 come obiettivo e dichiara che i retry possono estenderlo. AC-05/AC-06 valgono sul percorso senza guasti | D-06, D-12, V-08 |
| D8 | Il job di manutenzione attuale è una funzione sincrona eseguita da APScheduler in un thread del pool, mentre la connessione SQLite nasce nel thread principale (`check_same_thread=True`): a runtime il purge fallirebbe | **Job di manutenzione come coroutine**: `_run_maintenance_job` diventa `async`, invoca il callback nell'event loop e lo attende se è una coroutine. La composizione `purge_expired` + `purge_idle` resta un unico callback sincrono in `AgentApp`; la firma di `schedule_maintenance` non cambia. La mancata esecuzione nel thread va riprodotta in T8 e registrata in delivery history | D-09, D-10; difetto preesistente di item 01/03, registrato in delivery history |

## Riparto di responsabilità tra componenti (anti-duplicazione)

| Componente spec 05 | Possiede | Delega a | Non duplica perché |
|---|---|---|---|
| C-23 Chat Handler | Contesto conversazionale, prompt, tool loop read-only, `/reset` come operazione, messaggio di errore, **invio della risposta** | C-24 per la memoria, C-05 per la risposta, C-08 per gli strumenti, C-25 per l'indicatore, C-03 per l'invio, C-04 (tramite C-14) per il ruolo | C-14 riconosce comando/NL e sceglie il ramo; C-23 non verifica iscrizioni né gestisce compiti. C-14 non invia nulla della chat: un solo punto di invio |
| C-24 Conversation Memory | Persistenza e lettura dei messaggi per utente, finestra di 24 h (silenzio + età messaggio), troncamento dei turni, reset, purge | C-02 per SQLite | C-11 conserva lo storico esecuzioni e applica la retention dei messaggi per età; C-24 possiede la semantica della conversazione (silenzio, reset, contesto) |
| C-25 Progress Indicator | Soglia, invio di «sto cercando…», cancellazione alla risposta | C-03 per invio e cancellazione | C-23 non conosce soglie né id dei messaggi dell'indicatore |
| C-14 Command Router | Riconoscimento di `/reset`, `/chat`, testo libero; precedenza della creazione completa (D1) | C-23, C-15/C-16/C-17 per la creazione, C-21 per `/run` | Il router non costruisce contesto, non chiama il LLM per la chat e non invia la risposta |
| C-03 Telegram Gateway | Invio, id del messaggio, cancellazione | Telegram Bot API | C-25 non importa la libreria Telegram |

**Doppia proprietà sulla retention dei messaggi — risolta per criterio.** C-11 elimina i messaggi più
vecchi della finestra per `created_at` (retention di spec 01); C-24 applica la stessa finestra al contesto e
cancella le conversazioni silenti (`updated_at`) con i loro messaggi. I due criteri coincidono sulla stessa
soglia: un messaggio fuori finestra non è mai in memoria, e una conversazione senza messaggi recenti è
inattiva. Il job resta uno solo e chiama entrambe le operazioni (P-A-07).

**`/reset` e `HistoryService.reset_conversation`.** Il metodo esistente cancella i messaggi più vecchi
della finestra, non l'intera conversazione: non è la semantica di AC-03. C-24 implementa il reset vero
(cancellazione totale per utente) e diventa l'unico punto usato da `/reset`; il metodo di C-11 resta per
compatibilità con spec 01 e non viene chiamato da C-23.

**Troncamento del contesto — due punti, responsabilità diverse.** Spec 05 assegna a C-24 la costruzione del
contesto «entro il budget»; C-24 tronca i turni della conversazione usando `deepseek.max_context_tokens`.
C-05 continua ad applicare il proprio troncamento globale come rete di sicurezza (include il prompt di
sistema e i tool schema). Non è una duplicazione di politica: C-24 limita la **conversazione**, C-05 limita
la **richiesta al modello**. Se il budget scende sotto il prompt, vince il taglio di C-05.

## Deviazioni pre-dichiarate (numerazione stabile per il documento 05)

| # | Deviazione | Fonte modificata | Motivo |
|---|---|---|---|
| V-01 | `ChatHandler.handle(user_id, chat_id, text)` è asincrona e riceve anche `chat_id`; restituisce `ChatReply(kind, text)` | spec 05 C-23 | servono l'invio e la cancellazione via C-03; la firma `handle(user_id, text)` non dice dove rispondere né il contesto async. L'invio avviene **dentro** C-23: C-14 riceve solo l'esito |
| V-02 | C-24 espone anche `messages(user_id, limit=50)` oltre a `get_context`/`append`/`reset`/`purge_idle` | spec 05 C-24 | serve al flusso 4 (rilettura admin), che la spec attribuisce a C-24 senza dichiararne l'interfaccia; `limit` e ordine cronologico vengono da P-A-04 |
| V-03 | C-25 `start`/`finish` sono asincrone e ricevono `chat_id` | spec 05 C-25 | invio e cancellazione sono operazioni di rete; la spec non dichiara il contesto |
| V-04 | C-03 `send` restituisce l'id dell'ultimo messaggio e nasce `delete_message` | **spec 01 C-03** | senza id non si può eliminare l'indicatore come chiede spec 05 («rimuoverlo/aggiornarlo alla risposta»). Nota di continuità in D-13 |
| V-05 | `/reset` è riconosciuto da C-14 e inoltrato a C-23 | spec 05 C-23 | C-14 è il punto unico di parsing; C-23 possiede l'operazione |
| V-06 | Migrazione 004: `conversations`/`messages` senza FK verso `users` | **spec 01 §Modello dati e `001_init.sql`** | l'admin non è un record `users` (spec 01) ma deve avere memoria chat (FR-004). Nota di continuità in D-13 |
| V-07 | Per l'admin il testo libero va in chat solo se la bozza di compito non è completa (D1) | spec 02 D4 + spec 05 | concilia creazione solo NL e chat per messaggi non riconosciuti |
| V-08 | Nessun timeout rigido a 30 s / 2 min | spec 05 / constitution (BR-17) | BR-17 e BR-8 non sono compatibili; i retry restano attivi (D7), nota interpretativa in D-12 |
| V-09 | Il contesto è filtrato per età del messaggio **e** per silenzio della conversazione, entrambi sulla finestra di `chat_memory_hours` | spec 05 C-24 | allinea la semantica di «silenzio» (assunzione di spec 05) alla retention dei messaggi di C-11, senza due finestre divergenti |
| V-10 | Il job di manutenzione diventa una coroutine eseguita nell'event loop | spec 01 C-06 (implementazione) | il job sincrono girava in un thread del pool e avrebbe fallito sulla connessione SQLite (D8) |
| V-11 | Nuovo comando admin `/chat <telegram_id>` (con `/chat` senza argomento per l'elenco) | spec 05 flusso 4 | la spec richiede la rilettura ma non ne dichiara il comando; D3 |
| V-12 | Nuova leva `limits.chat_progress_s` (default 2 s) | spec 05 C-25 | la soglia è dichiarata come domanda aperta; D5 la fissa e la rende configurabile |
| V-13 | Il budget di contesto di C-24 viene da `deepseek.max_context_tokens` (C-01), non da una chiamata a C-05 | spec 05 C-24 | il valore esiste già in configurazione; C-05 resta la rete di sicurezza globale con la stessa stima |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita leggendo il solo frontmatter di
`.opencode/{agents,commands,skills}` e `opencode.json`; discovery per ruolo, nessun asset legato per filename.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-10, D-12, D-13 (codice, migrazione, config, test, aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione di codice Python, test o migrazioni SQL | Etichettati *"no specialized capability discovered"*; si procede su spec 05 + constitution + pattern esistenti in `src/agente/` |
| D-11 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** (Phase 2 struttura e Phase 4 validazione); il produttore resta il Conductor |
| D-11 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 05 e dai documenti 02–04; assunzione P-A-01 |

**Scartati (con motivo):**

| Asset | Motivo dello scarto |
|---|---|
| `skills/sdd-guardrail` | Veto negativo dichiarato: rifiuta modifiche richieste da messaggio di chat non emesso da un comando. Questa esecuzione è `/SDD-implement`; il suo template Micro-Spec non serve |
| `skills/drawio` | Si attiva su richiesta esplicita di diagrammi/draw.io; qui i diagrammi sono Mermaid nel documento di architettura |
| `skills/document-to-markdown`, `skills/okf-*`, `skills/wiki-*`, `skills/prompt-engineering` | Nessun documento sorgente da convertire, nessun bundle OKF/wiki, nessun template di prompt |
| `agents/planner`, `agents/specification`, `agents/prd` | Producono piani/spec/PRD: il piano è del Conductor, la spec esiste già |
| `agents/knowledge-searcher`, `agents/second-brain-keeper`, `agents/micro-spec-author` | Knowledge pipeline e Micro-Spec non fanno parte dei deliverable |
| `commands/*` | I comandi non si legano e non si invocano mai |

## Checkpoint di struttura (D-11) — Phase 2

Eseguito in modalità delegata su `sdd-governor` il 2026-10-24 sulla **prima** versione del piano e della
struttura proposta: esito **NOT APPROVED** (nessun critical, 11 MAJOR, 10 MINOR). Remediation recepita in
questa versione:

- **Interfaccia C-23 e invio unico:** definito `ChatReply(kind, text)`; la risposta è inviata da C-23, non da C-14 (D-06, V-01, §Riparto).
- **Contratto dei tool in chat:** C-23 espone i soli `read_only`; gli handler ricevono un contesto chat con allowlist vuota; `read_logs` è quindi sempre rifiutato; un tool sconosciuto o non read-only produce un esito di tool, non un guasto della risposta (P-A-08, T6).
- **Concorrenza:** serializzazione per `user_id` in C-23, `asyncio.to_thread` per `llm.chat` (pattern di C-09), stato dell'indicatore per `chat_id` con contatore di generazione, nuova sezione §7 nel documento (P-A-16, T6, T9).
- **Fonti modificate a monte:** V-04 e V-06 rietichettate come deviazioni da **spec 01**; nuovo deliverable D-13 con note di continuità in spec 01 e architettura 01.
- **BR-17 vs BR-8:** D7 dichiara la constitution non modificata nei valori; D-12 aggiunge la nota interpretativa in §Limiti operativi.
- **Struttura documento 05:** aggiunte «Estensioni di componenti esistenti» e «Componenti riusati»; flusso 2 etichettato «dichiarato da spec 06, non consegnato»; aggiunta §7 Concorrenza.
- **Troncamento contesto:** C-24 limita la conversazione, C-05 resta la rete di sicurezza globale; P-A-06 corretto (il prompt di sistema è conteggiato da C-05).
- **Retention:** criterio unico (silenzio + età messaggio sulla stessa finestra), scope di `purge_idle` definito, D4/P-A-05/P-A-07/T3 allineati (V-09).
- **Job di manutenzione:** correzione a coroutine (D8, V-10) e test dedicato.
- **Riferimenti e testi corretti:** D1 spiega quali domande di spec 05 chiude; D3 rimanda a P-A-03/P-A-04; D5 elenca i deliverable giusti; `/chat` e `chat_progress_s` entrano in V-11/V-12; T6 allineato a «sconosciuti/revocati ignorati»; AC-05 dichiara che la latenza è strutturale e non misurabile con LLM finto.
- **Tracciabilità estesa:** BR-2 (rifiuto dei tool modificanti), troncamento (V-09), migrazione con dati e `sqlite_sequence`, concorrenza, `purge_idle`, job di manutenzione a runtime.

Struttura applicabile dopo remediation: Metadata · Contesto e obiettivi · Componenti C-23/C-24/C-25 +
Estensioni di componenti esistenti + Componenti riusati (con flowchart) · Riparto · Modello di dominio ·
Modello dati (migrazione 004, ER) · Flussi 1–4 (sequenze; flusso 2 «dichiarato da spec 06, non consegnato») ·
Concorrenza e serializzazione (regola anti-duplicazione: la sezione descrive solo il «come» — lock per
utente, generazione dell'indicatore, offload del LLM — e rinvia a §Riparto per la proprietà e a §NFR per i
requisiti) · Integrazioni · Sicurezza · Requisiti non funzionali · Rischi e assunzioni ·
Domande aperte (chiuse da D4/D5) · Fuori scope · Deviazioni (V-01…V-13) · Tracciabilità (AC-01…AC-06 e BR).
Diagrammi: 1 flowchart componenti, 4 `sequenceDiagram`, 1 `erDiagram` su `conversations`/`messages`; nessuna
vista deployment (non dichiarata → gap registrato). La validazione definitiva è la Phase 4 sull'artefatto
reale: la produzione resta subordinata all'approvazione del piano.

## Assunzioni del piano (non dichiarate da spec 05)

> **P-A-01** Struttura del documento di architettura derivata da spec 05 e dai documenti 02–04, non da un
> template: nel progetto esistono `docs/templates/template.spec.md` e `template.constitution.md`, **nessun
> template per documenti di architettura**.
>
> **P-A-02** Prompt di sistema della chat: italiano come default, risposta nella lingua dell'utente se
> diversa (BR-14), nessuna affermazione presentata come fatto senza fonte, nessuna azione sul telefono
> (le modificanti restano al gate di spec 06).
>
> **P-A-03** Testi dei messaggi: indicatore «sto cercando…»; reset «Conversazione azzerata.»; `/reset` senza
> conversazione «Nessuna conversazione da azzerare.»; errore LLM «Non riesco a rispondere in questo momento:
> riprova tra poco.»; `/chat` senza argomento elenca «Utenti autorizzati: <id> (<username>)»; `/chat` con id
> sconosciuto o non `accepted` «Utente non autorizzato o sconosciuto.»; nessun messaggio «Nessun messaggio
> nelle ultime 24 ore.»; `/chat` da non admin «Solo l'amministratore può rileggere le chat.».
>
> **P-A-04** La rilettura admin mostra al massimo gli ultimi 50 messaggi della finestra di 24 ore, in ordine
> cronologico, con ruolo (`utente`/`agente`), istante e testo; nessun filtro per parola chiave; `/chat`
> senza argomento elenca solo gli utenti `accepted` ordinati per id.
>
> **P-A-05** La finestra di silenzio si misura dall'ultimo **messaggio dell'utente** (assunzione di spec 05):
> `conversations.updated_at` viene aggiornato quando si registra il turno dell'utente, non quello
> dell'assistente. Il contesto include i messaggi con `created_at` dentro la finestra **e** la conversazione
> non silente da più della finestra (V-09). Una conversazione senza riga in `conversations` o con
> `updated_at` illeggibile è trattata come silente: contesto vuoto (comportamento conservativo).
>
> **P-A-06** Il budget di contesto per C-24 è `deepseek.max_context_tokens` (A-01: ~8k, ultimi turni); il
> troncamento toglie i messaggi più vecchi per primi con la stessa stima di 4 caratteri/token di C-05. C-05
> continua a contare anche il prompt di sistema e i tool schema nel proprio troncamento globale: se il
> budget non basta, è C-05 a tagliare per ultimo.
>
> **P-A-07** Il job di manutenzione resta uno solo e chiama in ordine `history.purge_expired()` (esecuzioni
> 30 giorni e messaggi oltre la finestra per `created_at`) e `chat_memory.purge_idle()` (conversazioni
> silenti per `updated_at` e loro messaggi). Soglia unica `limits.chat_memory_hours`; operazioni idempotenti;
> il job gira nell'event loop (D8).
>
> **P-A-08** C-23 espone al modello solo gli strumenti `read_only` di C-08, con schema; gli handler ricevono
> un `ChatToolContext` (`user_id`, `log_allowlist` vuota, nessun compito). Con il registry attuale l'unico
> read-only è `read_logs`, che in chat non ha allowlist e viene sempre rifiutato da C-07. Un tool sconosciuto,
> non read-only o con handler mancante produce un messaggio di esito negativo al modello (`role=tool`), non un
> guasto della risposta. I modificanti non vengono **mai** eseguiti: l'approvazione resta al gate di spec 06.
>
> **P-A-09** Con D4 la rilettura admin vede solo i messaggi ancora in memoria: dopo `/reset` o dopo 24 ore di
> silenzio non c'è nulla da mostrare. Non è una perdita rispetto a BR-6, che fissa la memoria a 24 ore.
>
> **P-A-10** `/reset` cancella messaggi e riga di conversazione dell'utente; non tocca `executions`,
> iscrizioni o compiti.
>
> **P-A-11** La migrazione 004 crea le tabelle nuove senza FK, copia i dati (inclusi gli id), elimina le
> vecchie, rinomina e ricrea l'indice; `sqlite_sequence` resta coerente col massimo id copiato. Le tabelle
> non hanno riferimenti entranti, quindi l'ordine drop/rename è sicuro anche con `foreign_keys=ON`. Nessun
> `PRAGMA` dentro la transazione di `db.migrate`.
>
> **P-A-12** La cancellazione dell'indicatore è best effort e parte in background: se fallisce, la risposta
> viene inviata comunque e l'errore è loggato (spec: il fallimento dell'indicatore non blocca la risposta).
> I retry BR-8 di C-03 possono durare fino a due minuti e non devono ritardare la risposta.
>
> **P-A-13** Il comando `/chat` è distinto da `/run`, `/tasks` e dai comandi di spec 08; nessun altro
> comando è introdotto da questa voce.
>
> **P-A-14** L'admin può rileggere anche la propria conversazione con `/chat <admin_id>`; nessun dato di
> altri admin esiste (l'admin è uno solo, da configurazione).
>
> **P-A-15** Il messaggio dell'utente e quello dell'assistente vengono registrati **dopo** una risposta
> riuscita del modello e **prima** dell'invio Telegram, come nel flusso 1 di spec 05; una domanda fallita
> non entra in memoria. Il turno utente viene registrato prima di quello assistente, nell'ordine
> cronologico. Se l'invio C-03 fallisce, il turno resta in memoria (la risposta esiste) e l'errore è
> loggato dal gateway: nessun doppio invio, nessuna riscrittura della memoria.
>
> **P-A-16** Le richieste di chat dello stesso utente sono serializzate da un `asyncio.Lock` per `user_id`:
> due messaggi ravvicinati producono due scambi ordinati (domanda, risposta, domanda, risposta) e non
> interlacciati. Utenti diversi procedono in parallelo. Lo stato dell'indicatore è per `chat_id` e usa un
> contatore di generazione per non cancellare il messaggio di una richiesta successiva.
>
> **P-A-17** Numero massimo di cicli di tool calling in chat: 3 (valore proprio della chat, più stretto dei
> 5 di C-09 perché una risposta conversazionale deve restare breve e non deve trasformarsi in un'esecuzione);
> superato il limite la risposta è un errore esplicito («troppi cicli di tool calling»), come in C-09.
>
> **P-A-18** La latenza di BR-17 non è misurabile in unit test con LLM finto: AC-05 verifica che non esista
> un timeout rigido e che la risposta arrivi; la misura dei 30 s resta validazione su dispositivo (gap
> dichiarato in delivery history).
>
> **P-A-19** La regola di D1 vale anche per l'utente autorizzato: una bozza completa è un tentativo di
> creazione e riceve il rifiuto di spec 02 AC-03; solo una bozza incompleta apre la chat. Conseguenza
> dichiarata: ogni messaggio di un utente autorizzato costa un'estrazione di bozza prima della chat, e un
> falso positivo (domanda interpretata come bozza completa) produce un rifiuto invece di una risposta.

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | Migrazione 004 | D-03 | `conversations`/`messages` senza FK verso `users`; dati, id, `sqlite_sequence` e indice preservati; migrazione applicata su DB con dati e su DB vuoto; `schema_version()` = `004_chat_without_user_fk`; test in `tests/test_storage.py` (`test_chat_tables_have_no_user_fk`, `test_migration_004_preserves_ids_and_index`, `test_migration_004_keeps_sqlite_sequence`) |
| T2 | Estensioni repository | D-02 | `messages_for_user(user_id, since, limit)`, `delete_all_for_user`, `delete_idle` funzionanti e testati; nessuna modifica alle altre repository |
| T3 | C-24 Conversation Memory | D-01 | `get_context` applica silenzio e età messaggio, tronca i più vecchi al budget; `append` aggiorna `updated_at` solo sul turno utente; `reset` svuota tutto per l'utente; `purge_idle` elimina conversazioni silenti e loro messaggi; `messages` per la rilettura con limite |
| T4 | C-03 id e cancellazione | D-05 | `send` restituisce l'id dell'ultimo chunk; `delete_message` invia la cancellazione con retry BR-8 e solleva `TelegramError` sugli errori non ritentabili; test con gateway finto e `python-telegram-bot` simulato |
| T5 | C-25 Progress Indicator | D-04 | Sotto soglia nessun messaggio; oltre soglia invio di «sto cercando…»; `finish` cancella l'indicatore; `finish` prima dello scatto annulla il timer (nessun indicatore tardivo); una richiesta successiva non cancella l'indicatore della precedente (generazione); errore di invio/cancellazione non propaga; soglia da configurazione |
| T6 | C-23 Chat Handler | D-06 | Contesto da C-24, risposta C-05 con `llm.chat` in `asyncio.to_thread` (il loop resta nell'event loop), append dei due turni, tool loop read-only con esito negativo per tool non disponibili/modificanti, `/reset`, errore LLM con messaggio all'utente, log con latenza, serializzazione per utente, invio unico della risposta; ruolo `UNKNOWN`/revocato non arriva a C-23 (C-14 esce prima) |
| T7 | C-14 routing e comandi | D-07 | Utente autorizzato: testo libero → chat, salvo bozza completa → rifiuto (P-A-19); admin: bozza completa → creazione invariata, bozza incompleta → chat; `/reset` → C-23; `/chat <id>` solo admin con rilettura o elenco; aiuto aggiornato; `/run`, `/pause`, `/resume`, `/delete`, `/rename`, `/tasks` invariati |
| T8 | Config, wiring e manutenzione | D-08, D-09 | `limits.chat_progress_s` validata (intero > 0), esempio aggiornato; C-23/C-24/C-25 costruiti una volta in `AgentApp`; manutenzione: `_maintenance()` chiama `purge_expired` e `purge_idle`; `_run_maintenance_job` è una coroutine eseguita nell'event loop e attende il callback se è una coroutine; avvio e job esistenti invariati |
| T9 | Test AC-01…AC-06 e unit | D-10 | AC-01 memoria fra due domande; AC-02 silenzio/età → contesto vuoto; AC-03 `/reset` → contesto vuoto; AC-04 admin rilegge, non admin rifiutato; AC-05 risposta senza indicatore e senza timeout rigido (verifica strutturale: nessun `wait_for` in C-23); AC-06 indicatore inviato e rimosso con risposta lenta, `web_search` assente → gap dichiarato; concorrenza, tool modificante rifiutato, `purge_idle`, migrazione e manutenzione coperte; `pytest` verde |
| T10 | Documento architettura 05 | D-11 | Sezioni obbligatorie presenti; Mermaid validi (1 flowchart, 4 sequenze, 1 ER); flusso 2 etichettato non consegnato; checkpoint Phase 2 e Phase 4 **APPROVED**; nessuna vista deployment, gap registrato |
| T11 | Note di continuità su spec 01 | D-13 | Spec 01 e architettura 01 riportano la nota 2026-10-24 su `send`/`delete_message` e sulle tabelle chat senza FK, con rinvio a V-04/V-06 e D2 |
| T12 | Pubblicazione | D-12 | Roadmap 05 `[x]`; spec 05 `Implemented (2026-10-24)` + note (D1–D8); nota interpretativa in constitution §Limiti operativi per BR-17; delivery history con esito, gap AC-06 e correzione D8; piano marcato eseguito |

## Dipendenze

- Item 01: C-02 (`conversations`, `messages`, indice), C-03, C-04, C-05 (retry BR-8, troncamento), C-06, C-08, C-11, C-12.
- Item 02: C-14 (parsing comandi e NL), C-15/C-16/C-17 (creazione compiti, usata dal ramo admin di D1).
- Item 03: nessuna dipendenza diretta; il timeout BR-4 non si applica alla chat.
- Item 04: precedenza di `lancia <nome>` e `/run` sul ramo di creazione, da preservare nell'ordine di C-14.
- **Item 06 (non consegnato):** fornisce `web_search`; senza di esso AC-06 resta parzialmente validato (D6).
- **Item 07 (non consegnato):** definirà l'allowlist dei log; in chat resta vuota e `read_logs` è rifiutato.
- Item 08 (non consegnato): fornisce la gestione utenti e l'informativa privacy richiamata dalla sicurezza.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Domanda scambiata per creazione (o viceversa) con D1/P-A-19 | La creazione richiede nome+istruzioni+schedulazione e passa comunque da riepilogo e conferma (BR-1); il fallback a chat è deterministico. Rischi residui dichiarati: una richiesta di creazione incompleta riceve una risposta di chat; una domanda interpretata come bozza completa riceve un rifiuto (P-A-19). In entrambi i casi nessun compito viene creato senza conferma |
| Memoria chat dell'admin impossibile per la FK | Migrazione 004 (D2), con test su DB con dati e su DB vuoto (P-A-11) |
| Indicatore orfano, duplicato o mai rimosso | Serializzazione per utente, generazione per `chat_id`, cancellazione best effort con log (P-A-12, P-A-16); test dedicati |
| Due messaggi dello stesso utente in parallelo | Lock per `user_id` in C-23 (P-A-16); test di concorrenza |
| LLM bloccante che impedisce la soglia dell'indicatore | `asyncio.to_thread` per `llm.chat`, come in C-09 (P-A-16) |
| Doppia retention messaggi (C-11 e C-24) | Criterio unico sulla stessa finestra, operazioni idempotenti, un solo job (P-A-07); documentato nel riparto |
| Job di manutenzione in thread con SQLite non thread-safe | Correzione D8: job come coroutine nell'event loop; test dedicato |
| Retry BR-8 oltre i 30 s dichiarati da BR-17 | Deviazione V-08 approvata (D7): i retry restano, la latenza è un obiettivo; C-25 copre l'attesa e la constitution riceve una nota interpretativa |
| Contesto troppo grande o conversazione senza fine | Troncamento a `deepseek.max_context_tokens` (P-A-06) e purge a 24 h |
| Tool modificante chiamato in chat | Solo `read_only` esposti; i modificanti producono esito negativo e non vengono eseguiti (P-A-08); il gate di spec 06 resta l'unico punto di approvazione |
| `read_logs` senza allowlist genera errori rumorosi | Esito di tool esplicito al modello, risposta non bloccata (P-A-08); policy di allowlist a spec 07 |
| `send` che cambia valore di ritorno rompe i chiamanti | Il valore è aggiuntivo: i chiamanti esistenti lo ignorano; i gateway finti dei test vengono aggiornati in D-10 |
| AC-05/AC-06 non verificabili end-to-end senza dispositivo e senza web_search | Gap dichiarato (D6, P-A-18): indicatore, assenza di timeout rigido e percorso normale testati; ricerca web a item 06, latenza reale su dispositivo |

## Criteri di validazione (done della voce)

1. `PYTHONPATH=src:.deps python3 -m pytest` verde (inclusi i test di confine).
2. AC-01: due domande consecutive dello stesso utente → la seconda riceve il contesto della prima.
3. AC-02: oltre 24 ore dall'ultimo messaggio → contesto vuoto (orologio iniettato).
4. AC-03: `/reset` → messaggi cancellati, la domanda successiva riparte da zero.
5. AC-04: admin `/chat <id>` → messaggi dell'utente; utente autorizzato riceve rifiuto.
6. AC-05: domanda semplice → risposta, nessun indicatore sotto soglia; assenza di timeout rigido verificata; obiettivo 30 s dichiarato come validazione su dispositivo.
7. AC-06: risposta lenta → «sto cercando…» inviato e poi eliminato; `web_search` assente → gap registrato.
8. Concorrenza: due domande ravvicinate dello stesso utente → scambi ordinati; nessun indicatore orfano.
9. Nessun import fuori dai confini; type hints sulle interfacce pubbliche; errori espliciti; italiano di default.
10. Migrazione 004 applicata su DB con dati; schema finale senza FK verso `users`; `sqlite_sequence` coerente.
11. Documento D-11 conforme alla struttura dichiarata e approvato dal checkpoint Phase 4.
12. Catena di tracciabilità ricostruibile: voce roadmap 05 → spec 05 → binding → task → artefatti → validazione → pubblicazione.

## Tracciabilità attesa (compilata a Publish)

| Requisito / criterio | Test previsto |
|---|---|
| AC-01 memoria della conversazione | `tests/test_chat_ac.py::test_ac01_second_question_uses_the_previous_turn` |
| AC-02 silenzio di 24 ore | `tests/test_chat_ac.py::test_ac02_silence_resets_the_context`, `tests/test_chat_memory.py::test_context_excludes_messages_older_than_the_window` |
| AC-03 `/reset` | `tests/test_chat_ac.py::test_ac03_reset_starts_from_scratch`, `tests/test_chat_memory.py::test_reset_deletes_every_message_of_the_user`, `tests/test_chat.py::test_reset_during_an_answer_does_not_resurrect_the_memory` |
| AC-04 rilettura admin | `tests/test_chat_ac.py::test_ac04_admin_reads_an_authorized_user_chat`, `::test_ac04_authorized_user_cannot_read_chats` |
| AC-05 risposta semplice (latenza: validazione su dispositivo, P-A-18) | `tests/test_chat_ac.py::test_ac05_simple_question_gets_an_answer_without_indicator` |
| AC-06 indicatore (ricerca web: gap spec 06) | `tests/test_chat_ac.py::test_ac06_slow_answer_shows_and_removes_the_indicator`, `tests/test_progress.py` |
| BR-2 nessuna azione modificante senza gate | `tests/test_chat.py::test_modifying_tool_is_never_executed` |
| BR-6 memoria 24 h e reset | `tests/test_chat_memory.py::test_purge_idle_removes_idle_conversations`, `::test_context_excludes_messages_older_than_the_window` |
| BR-8 retry LLM e Telegram | `tests/test_llm.py`, `tests/test_telegram_gateway.py` |
| BR-12 permessi chat e rilettura | `tests/test_chat_ac.py::test_ac04_authorized_user_cannot_read_chats`, `tests/test_command_router.py::test_revoked_user_is_ignored` |
| BR-14 lingua e fuso | `tests/test_chat.py::test_system_prompt_follows_user_language`; istanti UTC ISO come nella fondazione |
| BR-17 latenza-obiettivo | `tests/test_chat_ac.py::test_ac05_simple_question_gets_an_answer_without_indicator`, `::test_ac06_slow_answer_shows_and_removes_the_indicator`; misura reale su dispositivo (gap P-A-18) |
| Troncamento del contesto (V-09, P-A-06) | `tests/test_chat_memory.py::test_context_is_truncated_to_the_budget` |
| Migrazione 004 e memoria admin | `tests/test_storage.py::test_chat_tables_have_no_user_fk`, `::test_migration_004_preserves_ids_and_index`, `::test_migration_004_keeps_sqlite_sequence`, `tests/test_chat_memory.py::test_admin_can_have_a_conversation` |
| Concorrenza (P-A-16) | `tests/test_chat.py::test_two_questions_of_the_same_user_are_serialized`, `::test_reset_during_an_answer_does_not_resurrect_the_memory`, `tests/test_progress.py::test_new_request_closes_the_previous_indicator`, `::test_finish_does_not_wait_for_a_slow_delete` |
| Precedenza creazione/chat (D1/P-A-19) | `tests/test_command_router.py::test_admin_incomplete_draft_falls_back_to_chat`, `::test_admin_complete_draft_still_creates_a_task`, `::test_authorized_user_incomplete_draft_goes_to_chat` |
| Manutenzione a runtime (D8) | `tests/test_scheduler.py::test_maintenance_job_runs_in_the_event_loop`, `tests/test_chat_ac.py::test_app_wiring_answers_a_chat_and_runs_maintenance` |
| Confini di integrazione | `tests/test_boundaries.py` |

## Ordine di consegna

Codice-first: T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8, poi test T9, poi documentazione T10 e note di
continuità T11 (dipendenti da codice stabile), infine pubblicazione T12. Il documento descrive il
comportamento validato; l'unica sequenza non consegnata (flusso 2, `web_search`) è etichettata come tale e
rinvia a spec 06.

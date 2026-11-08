# Agente Personale Telegram: Constitution

## Mission

**North Star.** Un agente personale sempre attivo sullo smartphone Samsung S24 (Termux, senza
permessi di root) che, comandato interamente via Telegram anche da un altro dispositivo, esegue in
autonomia compiti ricorrenti — rassegne informative, riassunti di log — e risponde a domande libere,
eliminando il lavoro manuale quotidiano e la dipendenza dalla disponibilità fisica dell'S24.

**Contesto e problemi.** Oggi le attività ricorrenti vengono svolte a mano: occorre ricordarsele,
avere l'S24 in mano e dedicarvi tempo. Senza un agente il lavoro resta manuale e dipende dalla
memoria e dalla disponibilità del proprietario. L'agente deve colmare questo divario restando
operativo per settimane senza interventi, consegnando risultati puntuali e consentendo la gestione
completa da Telegram. Beneficiari: l'amministratore/proprietario e fino a 5 utenti autorizzati
(BR-16), con permessi distinti.

### Principi non negoziabili (in ordine di precedenza)

1. **Controllo umano sulle modifiche.** Nessuna azione che modifica il telefono — eseguire comandi,
   scrivere/cancellare file, installare — è eseguita senza approvazione esplicita
   dell'amministratore (BR-2, A4). La conferma va sempre e solo all'admin, anche quando la richiesta
   nasce da un utente autorizzato (A5); nessuna risposta entro 15 minuti equivale a rifiuto (BR-3).
   In caso di dubbio sulla classificazione, il gate richiede conferma (fail-safe).
2. **Un solo amministratore, definito in configurazione.** L'admin è identificato esclusivamente
   dalla config e non è promuovibile da chat né rappresentato come record utente (BR-12, decisione
   #7). Solo l'admin crea/modifica compiti, autorizza/revoca utenti e fornisce conferme.
3. **Conferma esplicita prima dell'effetto.** Creazione, modifica ed eliminazione di un compito
   richiedono riepilogo e conferma dell'admin prima di essere persistenti (BR-1). Le ambiguità —
   in particolare gli orari — non si assumono mai: si chiede di precisare (FR-001, BR-14).
4. **Singola fonte di verità.** SQLite nella directory privata dell'app è l'unico stato persistente
   per compiti, utenti, iscrizioni, esecuzioni, conversazioni, approvazioni e impostazioni
   (spec 01). Ogni accesso passa da C-02. Nessuna copia esterna dei dati: tutto resta sull'S24
   (FR §10).
5. **Affidabilità deterministica.** Le regole di sicurezza, permessi, soglie e transizioni di stato
   sono applicate dal codice, mai delegate al LLM. Retry 3 tentativi a 1 minuto (BR-8), timeout di
   esecuzione 10 minuti (BR-4), recupero una sola volta dell'ultima occorrenza mancata (BR-5), una
   sola esecuzione per compito alla volta (C-22), ripartenza automatica e segnale di vita alle 8:00
   (BR-11).
6. **Privacy e minimizzazione.** Solo utenti autorizzati interagiscono; sconosciuti e revocati sono
   ignorati (BR-12). Un nuovo utente usa l'agente solo dopo aver accettato l'informativa privacy
   (BR-18). I log si leggono solo da percorsi in allowlist del compito (BR-13). Segreti con permessi
   `600`, mai in git e mai nei log.
7. **Semplicità adeguata al dispositivo.** Un solo processo Python su Termux, componenti
   in-process; nessun servizio separato. Il dimensionamento è quello dichiarato: fino a 5 utenti
   autorizzati e 10 compiti attivi (BR-16). YAGNI: niente astrazioni o infrastruttura oltre i
   requisiti.
8. **Fedeltà ai requisiti.** Ciò che le spec non dichiarano non si inventa: requisito, soglia,
   versione o provider mancanti si segnalano e restano domande aperte. Le decisioni confermate
   (A-01…A-05 di spec 01) sono vincolanti.
9. **Osservabilità e memoria operativa.** Log strutturato senza segreti; ogni esecuzione è
   registrata nello storico con esito `ok|errore|interrotto|saltata` e conservata 30 giorni (BR-7,
   BR-15 emendato dalla decisione D1 del 2026-10-24: `saltata` marca un'occorrenza mancata, non
   un'esecuzione avvenuta).
   La conversazione si azzera dopo 24 ore di silenzio o con `/reset` (BR-6).

## Tech Stack

| Ambito | Tecnologia / vincolo | Fonte |
|--------|----------------------|-------|
| Runtime | Python 3, processo singolo, event loop `asyncio`; Termux su Samsung S24, **senza root** | spec 01; FR §13 |
| Canale | Telegram Bot API via `python-telegram-bot`, long polling; unico punto di contatto C-03 | spec 01 |
| Scheduling | `APScheduler` con `AsyncIOScheduler` in-process; job store persistente su SQLite; timezone del telefono | spec 01, 03; BR-14 |
| Persistenza | SQLite (`sqlite3` stdlib), modalità WAL, migrazioni versionate; unico file in directory privata `chmod 600` | spec 01 |
| LLM | API DeepSeek compatibile OpenAI; modello default `deepseek-flash`, configurabile; contesto troncato entro `max_context_tokens` (~8k) | spec 01, 05 |
| Ricerca web | Adapter pluggable con provider configurabile; **default Tavily** (D2 voce 06), candidati Brave/Google CSE/SerpAPI non implementati | spec 06 |
| Device | Termux:API (`termux-battery-status`, `termux-wifi-connectioninfo`) + subprocess, esclusivamente via C-07 | spec 01, 06, 10 |
| Config | TOML `~/.config/agente/config.toml` `chmod 600`; segreti separati o variabili d'ambiente | spec 01 |
| Supervisione | Script di boot `~/.termux/boot/`, `termux-wake-lock`, watchdog/supervisor C-12 | spec 01, 11 |

**Versioni.** Le spec dichiarano solo Python 3 e il model id `deepseek-flash`; nessuna versione di
libreria è specificata. Non introdurre versioni inventate: fissarle in fase di implementazione e
registrarle qui.

| Libreria | Versione fissata | Data | Fonte |
|---|---|---|---|
| python-telegram-bot | 22.8 | 2026-10-21 | risoluzione pip (item 01) |
| APScheduler | 3.11.3 | 2026-10-21 | risoluzione pip (item 01) |
| SQLAlchemy | 2.1.5 | 2026-10-21 | risoluzione pip, job store APScheduler (item 01) |
| httpx | 0.28.1 | 2026-10-21 | risoluzione pip (item 01) |
| pytest | 9.1.1 | 2026-10-21 | risoluzione pip, solo sviluppo (item 01) |

Ambiente verificato: Python 3.14.4 su Termux. `python-telegram-bot`, `APScheduler`,
`SQLAlchemy`, `httpx` e `pytest` sono installati con `pip --target .deps` (il venv non è
creabile: `ensurepip` assente e il filesystem del progetto non supporta il symlink `lib64`);
versioni pinnate in `requirements.txt` / `requirements-dev.txt`.

### Pattern e vincoli architetturali obbligatori

- **Processo unico, componenti in-process** C-01…C-13 (spec 01). Nessun microservizio, coda o
  processo separato.
- **Confini di integrazione invalicabili:** Telegram solo tramite C-03; DeepSeek solo tramite C-05;
  SQLite solo tramite C-02; filesystem e comandi solo tramite C-07; strumenti esposti solo da C-08
  con flag `read_only` / `requires_approval`.
- **Gate centralizzato:** C-27 classifica le azioni e C-28 gestisce l'approvazione con scadenza a
  15 minuti; il gate non è aggirabile dagli altri componenti.
- **Config immutabile e tipizzata** (`load_config() -> Config`); campi obbligatori mancanti o
  segreti illeggibili producono errore fatale all'avvio, senza avvio parziale.
- **Gestione errori esplicita:** rollback transazionale, retry limitati e con backoff su
  `database is locked`, nessun fallimento silenzioso; niente segreti nei log.
- **Type hints obbligatori** su interfacce pubbliche e modelli di dominio; stati ammessi vincolati
  (BR-15).
- **Lingua e locale:** italiano come default, risposta nella lingua dell'utente se diversa; orari e
  query nel fuso orario del telefono (BR-14).
- **Limiti operativi:** esecuzione ≤ 10 min; risposta chat ≤ 30 s, ≤ 2 min con ricerca web mostrando
  "sto cercando…" (BR-17); storico 30 giorni; memoria chat 24 ore; batteria < 15%; offline > 1 ora;
  liveness 08:00.
  - *Nota interpretativa 2026-10-24 (voce 05, decisione D7):* i 30 s e i 2 minuti restano **limiti-
    obiettivo** e non timeout rigidi. I retry BR-8 (DeepSeek 3×1 min, invio Telegram 3×1 min) possono
    estenderli; C-23 non interrompe l'attesa e l'indicatore «sto cercando…» copre il ritardo. I valori
    non cambiano.
  - *Estensione 2026-10-25 (voce 06, V-14):* rientrano nella stessa nota anche l'attesa
    dell'approvazione admin (fino a BR-3, 15 minuti) e i retry del provider di ricerca (3×1 min);
    BR-17 resta un obiettivo, non un timeout complessivo.

## Roadmap

Checklist delle funzionalità derivate dagli spec in `docs/specs/`. Ordine di dipendenza; si spunta
solo a ciclo Plan → Produce → Validate → Publish completo.

- [x] **01 — Agent Runtime (fondazione)** — bootstrap, config, SQLite, gateway Telegram, ruoli, LLM,
  device adapter, scheduler, logging, retention, supervisor —
  [01-agent-runtime.spec.md](01-agent-runtime.spec.md)
- [x] **02 — FR-001 Gestione dei compiti** — CRUD da Telegram con interpretazione NL, schedule
  interpreter, conferma esplicita —
  [02-fr001-gestione-compiti.spec.md](02-fr001-gestione-compiti.spec.md)
- [x] **03 — FR-002 Esecuzione programmata** — job, esecuzione end-to-end, delivery, recupero una
  volta, timeout e retry —
  [03-fr002-esecuzione-programmata.spec.md](03-fr002-esecuzione-programmata.spec.md)
- [x] **04 — FR-003 Lancio manuale** — `/run`/NL, permessi e iscrizioni, lock per compito, risultato
  al solo richiedente —
  [04-fr003-lancio-manuale.spec.md](04-fr003-lancio-manuale.spec.md)
- [x] **05 — FR-004 Domande libere** — chat NL, memoria conversazione 24 h/`/reset`, indicatore di
  avanzamento, rilettura admin —
  [05-fr004-domande-libere.spec.md](05-fr004-domande-libere.spec.md)
- [x] **06 — FR-005 Ricerca web e conferma** — web search read-only, action gate, approvazioni con
  timeout 15 min —
  [06-fr005-ricerca-web-conferma.spec.md](06-fr005-ricerca-web-conferma.spec.md)
- [x] **07 — FR-006 Lettura e riassunto log** — log reader, allowlist per compito, riassunto ed
  errori —
  [07-fr006-riassunto-log.spec.md](07-fr006-riassunto-log.spec.md)
- [x] **08 — FR-007 Gestione utenti** — autorizzazione/revoca, consenso privacy, iscrizioni,
  antispam sconosciuti —
  [08-fr007-gestione-utenti.spec.md](08-fr007-gestione-utenti.spec.md)
- [x] **09 — FR-008 Storico esecuzioni** — query per ruolo/periodo, retention 30 giorni —
  [09-fr008-storico-esecuzioni.spec.md](09-fr008-storico-esecuzioni.spec.md)
- [x] **10 — FR-009 Avvisi all'amministratore** — fallimenti/timeout, batteria, offline prolungato,
  credenziali DeepSeek —
  [10-fr009-avvisi-admin.spec.md](10-fr009-avvisi-admin.spec.md)
- [x] **11 — FR-010 Riavvio e liveness** — boot recovery, messaggio di ripartenza, segnale di vita
  quotidiano —
  [11-fr010-riavvio-liveness.spec.md](11-fr010-riavvio-liveness.spec.md)
- [x] patch-readme-uso-app — Micro-Spec: README.md come guida operativa dell'app Telegram ([patch-readme-uso-app.spec.md](./patch-readme-uso-app.spec.md))

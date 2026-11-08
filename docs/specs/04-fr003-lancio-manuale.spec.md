# Specifica 04 — Lancio manuale di un compito (FR-003)

- **ID:** `04-fr003-lancio-manuale`
- **Stato:** Implemented (2026-10-24)
- **Requisiti collegati:** FR-003; BR-4, BR-8, BR-12
- **Dipendenze:** `01-agent-runtime`, `02-fr001-gestione-compiti`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

L'amministratore o un utente autorizzato deve poter **eseguire subito** un compito esistente
scrivendo *"lancia news"* o `/run news`. Il risultato va **solo a chi ha fatto la richiesta**. Un
utente autorizzato può lanciare solo i compiti a cui è iscritto; altrimenti riceve un rifiuto.
L'esecuzione viene registrata nello storico.

## Panoramica architetturale

Riutilizza: Command Router (C-14), Execution Engine (C-09), LLM/Tool/Lock (spec 03), Notification
Service (C-10), History (C-11), Storage (C-02), Role Guard (C-04).

Componenti specifici:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-21 | Run Dispatcher | Riconosce `/run`/NL, verifica permessi e iscrizione, invoca l'esecuzione |
| C-22 | Task Lock | Garantisce una sola esecuzione per compito alla volta |

## Progettazione componenti

### C-21 — Run Dispatcher
- **Responsabilità:** interpretare la richiesta di lancio, verificare che il compito esista e che il
  richiedente sia autorizzato a eseguirlo; invocare C-09 con `trigger=manual` e `requester`.
- **Interfaccia pubblica:** `run(requester_role, requester_id, task_name) -> ExecutionResult`.
- **Dipendenze:** C-14, C-04, C-02, C-09, C-11.
- **Input:** nome compito + richiedente. **Output:** risultato al richiedente.
- **Error handling:** compito inesistente → segnalazione e possibile elenco dei compiti disponibili
  per quel richiedente; utente non iscritto → rifiuto; compito già in esecuzione → rifiuto (C-22).
- **Osservabilità:** log lancio con `requester_id` e `task_id`.
- **Sicurezza:** l'utente autorizzato può lanciare solo i compiti a cui è iscritto (BR-12); l'admin
  può lanciare qualsiasi compito.

### C-22 — Task Lock
- **Responsabilità:** serializzare le esecuzioni per compito; una sola esecuzione attiva per
  `task_id` (decisione #9).
- **Interfaccia pubblica:** `acquire(task_id) -> bool`, `release(task_id)`.
- **Dipendenze:** C-02 (o lock in-memory con stato persistito).
- **Error handling:** lock già detenuto → rifiuto con messaggio.
- **Osservabilità:** log acquisizione/rilascio lock.
- **Sicurezza:** previene duplicati e overlap.

## Modello di dominio

- **Esecuzione manuale:** come l'esecuzione di spec 03, con `trigger = manual` e `requested_by`
  valorizzato col richiedente.
- **Iscrizione:** relazione utente ↔ compito (spec 08) usata per l'autorizzazione.

## Modello dati

Tabella `executions` (spec 01) con `trigger` e `requested_by`. L'iscrizione è in `subscriptions`.

## Flussi di dati

1. **Lancio:** messaggio *"lancia news"* / `/run news` → C-14 → C-21 verifica esistenza + permesso →
   C-22 acquisisce il lock → C-09 esegue → C-10 invia il risultato **solo al richiedente** → C-11
   registra → C-22 rilascia il lock.
2. **Compito inesistente:** C-21 risponde "compito non trovato" ed eventualmente elenca i compiti
   disponibili per il richiedente.
3. **Non iscritto:** C-21 risponde con rifiuto e non esegue nulla.

## Progettazione integrazioni

- **Telegram:** comando/NL in ingresso, risultato in uscita.
- **DeepSeek / tool:** come per l'esecuzione di spec 03 (stesso motore).

## Requisiti di sicurezza

- L'utente autorizzato esegue solo compiti a cui è iscritto (BR-12).
- Il risultato manuale va solo al richiedente (non ai destinatari del compito).
- Azioni modificanti durante l'esecuzione restano soggette al gate (BR-2, spec 06).

## Requisiti non funzionali

- Stesso limite di 10 minuti e stessi retry 3×1 min di FR-002 (BR-4, BR-8).
- Nessuna esecuzione concorrente dello stesso compito (lock).

## Rischi e assunzioni

- **Rischio:** lancio manuale mentre è in corso l'esecuzione programmata → rifiutato (decisione #9).
- **Assunzione:** il nome compito è l'identificatore usato dagli utenti (case-insensitive da
  definire, cfr. spec 02).

## Domande tecniche aperte

- Il lock deve sopravvivere a un riavvio del processo? (persistito vs in-memory)
- Messaggio esatto e comportamento quando il compito esiste ma è `sospeso`.

**Risposte (operatore, 2026-10-24 — decisioni D1/D2 del piano 04):** il lock è **solo in memoria**:
il processo è unico e un riavvio termina l'esecuzione in corso, quindi non c'è stato da serializzare.
Un compito `sospeso` è lanciabile **solo dall'admin**; l'utente autorizzato riceve un rifiuto. Lo
stato resta `paused` e continua a bloccare le sole occorrenze programmate (deroga dichiarata a spec
02 AC-04, che non è emendata).

## Criteri di accettazione

- **AC-01** Dato un utente iscritto al compito "news", quando scrive `/run news`, allora riceve il
  risultato solo lui.
- **AC-02** Dato un utente non iscritto al compito "log", quando scrive `/run log`, allora riceve un
  rifiuto e il compito non viene eseguito.
- **AC-03** Dato un compito già in esecuzione, quando arriva un lancio manuale, allora viene
  rifiutato senza avviare una seconda esecuzione.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-003, BR-4/8/12, §8 (journey 3), §9.

## Assunzioni

- **A-01** Una sola esecuzione per compito alla volta (decisione #9).

## Domande in sospeso

- Persistenza del lock; comportamento su compito sospeso: **chiuse** il 2026-10-24 (D1/D2 del piano
  04; vedi sopra).

## Valutazione di confidenza

**Alta** — FR-003 documentato con criteri di accettazione espliciti.

## Note di implementazione

- C-22 `src/agente/task_lock.py`: `acquire/release/held`, lock in memoria, unico per tutti gli
  inneschi; rilasciato in `finally` anche su errore e timeout (D1).
- C-21 `src/agente/run_dispatcher.py`: `run(requester_role, requester_id, task_name)` asincrona;
  admin su qualsiasi compito, utente autorizzato solo sugli iscritti con stato `accepted`
  ri-verificato; rifiuti tipizzati `RunRefused` (`missing_name`, `not_found`, `forbidden`, `paused`,
  `busy`); elenco dei compiti visibili nel rifiuto per compito inesistente (D2, P-A-02/P-A-04).
- C-09 `src/agente/execution.py`: usa C-22 al posto del lock interno e propaga il richiedente fino a
  C-20; il lock resta acquisito da C-09 (V-02 del documento di architettura).
- C-20 `src/agente/delivery.py`: `deliver_text(..., requested_by=...)` → risultato manuale solo al
  richiedente (V-03); percorso programmato invariato.
- C-14 `src/agente/command_router.py`: `/run <nome>` e NL `lancia <nome>` (solo verbo documentato),
  riconosciuti prima del ramo di creazione; rifiuto o riga di stato al richiedente (P-A-06).
- Config: nessuna nuova leva; nessuna migrazione.
- Test: 209 raccolti, tutti verdi (`PYTHONPATH=src:.deps python3 -m pytest`), inclusi AC-01…AC-03 in
  `tests/test_manual_run_ac.py`.
- Documento: [04-fr003-lancio-manuale.md](../architecture/04-fr003-lancio-manuale.md), checkpoint di
  struttura `sdd-governor` APPROVED (2026-10-24).

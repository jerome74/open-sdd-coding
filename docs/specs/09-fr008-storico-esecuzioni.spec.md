# Specifica 09 — Storico delle esecuzioni (FR-008)

- **ID:** `09-fr008-storico-esecuzioni`
- **Stato:** Implemented (2026-11-02)
- **Requisiti collegati:** FR-008; BR-7, BR-12, BR-15
- **Dipendenze:** `01-agent-runtime`, `02-fr001-gestione-compiti`, `03-fr002-esecuzione-programmata`, `04-fr003-lancio-manuale`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

Ogni esecuzione (programmata o manuale) deve essere **tracciata** e **consultabile da Telegram**.
Per ogni esecuzione si registrano: compito, data e ora, esito (`ok` / `errore` / `interrotto` /
`saltata`), breve riassunto. `saltata` (spec 03, decisione D1 del 2026-10-24) indica un'occorrenza
mancata e recuperata solo nell'ultima occorrenza: non è un'esecuzione avvenuta. L'utente consulta lo storico chiedendo (es. *"cosa hai fatto ieri?"*) o con
`/history`.

Le voci più vecchie di **30 giorni** vengono eliminate (BR-7). Un utente autorizzato vede solo lo
storico dei compiti a cui è iscritto; l'amministratore vede tutto (BR-12).

## Panoramica architetturale

Riutilizza: Command Router (C-14), Storage (C-02), Role Guard (C-04), History & Retention (C-11),
Scheduler (C-06, per il job di retention).

Componenti specifici:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-34 | History Query | Interpreta le richieste e filtra per ruolo/tempo |
| C-35 | Retention Job | Elimina le esecuzioni più vecchie di 30 giorni |

## Progettazione componenti

### C-34 — History Query
- **Responsabilità:** rispondere a `/history` e a richieste NL (es. *"cosa hai fatto ieri?"*)
  filtrando per periodo e per compito; applicare i permessi di visibilità.
- **Interfaccia pubblica:** `query(role, user_id, filter) -> list[Execution]`.
- **Dipendenze:** C-14, C-05 (parsing temporale), C-11, C-04.
- **Input:** richiedente + intervallo/filtro. **Output:** elenco esecuzioni.
- **Error handling:** intervallo non interpretabile → richiesta di precisazione; nessun risultato →
  messaggio "nessuna esecuzione".
- **Osservabilità:** log query e conteggio risultati.
- **Sicurezza:** l'utente autorizzato vede **solo** i compiti a cui è iscritto; l'admin vede tutto
  (BR-12).

### C-35 — Retention Job
- **Responsabilità:** eliminare giornalmente le esecuzioni più vecchie di 30 giorni (BR-7).
- **Interfaccia pubblica:** `purge()` (invocato da C-11/C-06).
- **Dipendenze:** C-02.
- **Error handling:** errore di cancellazione → log e nuovo tentativo al job successivo.
- **Osservabilità:** log conteggio voci eliminate.

## Modello di dominio

- **Esecuzione:** `task_id`, `requested_by`, `trigger`, `started_at`, `finished_at`, `outcome`,
  `summary`.
- **Esito:** `ok` | `errore` | `interrotto` | `saltata` (BR-15, emendato da spec 03).

## Modello dati

Tabella `executions` (spec 01) con indice su `(task_id, started_at)` e su `started_at` per la
retention. `trigger` distingue `scheduled`/`manual`/`recovery`.

## Flussi di dati

1. **Consultazione:** `/history` o NL → C-34 interpreta il filtro → C-11 legge da `executions` →
   filtra per ruolo → risposta Telegram.
2. **Scrittura:** ogni esecuzione (spec 03/04) chiama C-11 `record()`.
3. **Retention:** C-35 (job giornaliero) → elimina `started_at < now - 30 gg`.

## Progettazione integrazioni

- **Telegram:** comando/NL in ingresso, elenco in uscita.
- **DeepSeek:** parsing del riferimento temporale NL.

## Requisiti di sicurezza

- Visibilità filtrata per ruolo (BR-12): admin tutto, utente solo iscritti.
- Le voci eliminate non sono recuperabili (retention 30 gg).

## Requisiti non funzionali

- Retention 30 giorni (BR-7).
- Query reattiva per volumi BR-16 (≤ 5 utenti, ≤ 10 compiti).

## Rischi e assunzioni

- **Rischio:** "breve riassunto" troppo lungo per Telegram → troncamento (limite messaggio).
- **Assunzione:** il fuso orario delle query è quello del telefono (BR-14).

## Domande tecniche aperte

- Formato del "breve riassunto" (limite caratteri) e se includere il link al dettaglio.
- Interpretazione di riferimenti temporali NL (ieri, questa settimana) e loro precisione.

**Risposte (operatore, 2026-11-01 — D1/D2 del piano 09):** elenco a **una riga per esecuzione**,
riassunto troncato a **120 caratteri**, massimo **20 righe**, nessun link al dettaglio; **parser
deterministico** per un insieme chiuso di espressioni italiane con **fallback LLM validato** e
richiesta di precisazione in caso di ambiguità. Chiuse anche le questioni implicite: finestra
predefinita 24 ore (D3), sintassi `/history [periodo] [compito]` (D4), C-35 assorbito da C-11 (D5),
cascade sui compiti eliminati mantenuto (D6).

## Criteri di accettazione

- **AC-01** Dato un compito eseguito ieri, quando l'amministratore chiede *"cosa hai fatto ieri?"*,
  allora riceve l'elenco delle esecuzioni con esito e riassunto.
- **AC-02** Dato un utente iscritto solo a "news", quando scrive `/history`, allora vede solo le
  esecuzioni di "news".
- **AC-03** Data un'esecuzione di 31 giorni fa, quando si consulta lo storico, allora non compare
  più.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-008, BR-7/12/15, §8, §10, §12.

## Assunzioni

- **A-01** Le esecuzioni sono scritte da C-11 al termine di ogni corsa (spec 03/04).
- **A-02** Retention applicata da job giornaliero.

## Domande in sospeso

- Formato riassunto; parsing temporale NL (vedi sopra).

## Valutazione di confidenza

**Alta** — FR-008 documentato con criteri di accettazione; i dettagli di formato e di parsing sono
stati chiusi il 2026-11-01 (D1/D2).

## Note di implementazione (2026-11-02)

- **Componenti:** C-34 `src/agente/history_query.py` (`parse_filter`, `parse_window_with_llm`,
  `resolve_task`, `build_filter`, `query`, `render`); C-11 `src/agente/history.py` assorbe C-35
  (`purge_expired`, log dei conteggi, error handling) e normalizza gli istanti a UTC; C-14
  `command_router.py` gestisce `/history` e le richieste NL.
- **Estensioni:** C-02 con `commit()` (errori SQLite → `StorageError`) e migrazione 005;
  `AgentApp` con `history_query`, `tz` opzionale e `_maintenance` isolato.
- **Migrazione:** `005_executions_started_index.sql` normalizza `started_at`/`finished_at` con
  `strftime('%Y-%m-%dT%H:%M:%S+00:00', …)` e crea `idx_executions_started`; nessuna tabella o
  colonna nuova.
- **Decisioni:** D1 formato; D2 parser + LLM; D3 24 ore; D4 sintassi; D5 C-35 assorbito; D6 cascade
  mantenuto.
- **Deviazioni:** V-01…V-12 nel documento
  [09-fr008-storico-esecuzioni.md](../architecture/09-fr008-storico-esecuzioni.md).
- **Test:** 518 raccolti, tutti verdi (`PYTHONPATH=src:.deps python3 -m pytest`), inclusi AC-01…AC-03
  in `tests/test_history_ac.py`.
- **Gap:** lo storico di un compito eliminato sparisce (cascade); una riga con `started_at` non
  parsabile resta fuori contratto; un compito con nome che inizia con una cifra non è filtrabile per
  nome; l'ordine «compito prima del periodo» non è supportato; gli avvisi di sistema (item 10) e il
  riavvio (item 11) restano fuori.
- **Documento:** [09-fr008-storico-esecuzioni.md](../architecture/09-fr008-storico-esecuzioni.md),
  checkpoint di struttura `sdd-governor` Phase 4 **APPROVED** (2026-11-02).

## Nota di continuità (2026-11-03, voce 10)

Gli avvisi di sistema (fallimento, timeout, batteria, offline, credenziali) sono consegnati dalla
voce 10: C-09 instrada `task_failed`/`task_timeout` a C-36, C-37 gestisce batteria/offline e C-38 le
credenziali. Lo storico delle esecuzioni non cambia: un errore di credenziale resta `errore` e
l'avviso specifico non è una riga di storico.

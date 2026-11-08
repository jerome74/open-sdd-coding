# Specifica 05 — Domande libere (chat) (FR-004)

- **ID:** `05-fr004-domande-libere`
- **Stato:** Implemented (2026-10-24)
- **Requisiti collegati:** FR-004; BR-2, BR-6, BR-12, BR-17
- **Dipendenze:** `01-agent-runtime`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

L'amministratore e gli utenti autorizzati devono poter **fare domande qualsiasi** all'agente, al
volo, in linguaggio naturale. L'agente risponde usando la ricerca web se serve (spec 06) e ricorda
la conversazione in corso con quell'utente. La memoria si azzera dopo **24 ore di silenzio** o con
`/reset` (BR-6). L'amministratore può **rileggere le chat** degli utenti autorizzati (BR-12).

Tempi: risposta semplice entro **30 secondi**; con ricerca web fino a **2 minuti**, mostrando
"sto cercando…" (BR-17).

## Panoramica architetturale

Riutilizza: Telegram Gateway (C-03), Role Guard (C-04), LLM Client (C-05), Notification (C-10),
Storage (C-02), Tool Registry (C-08).

Componenti specifici:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-23 | Chat Handler | Riceve le domande, orchestra risposta e memoria |
| C-24 | Conversation Memory | Persiste e recupera i messaggi per utente, applica il reset |
| C-25 | Progress Indicator | Mostra "sto cercando…" durante il lavoro lungo |

## Progettazione componenti

### C-23 — Chat Handler
- **Responsabilità:** ricevere un messaggio NL non riconosciuto come comando, costruire il contesto
  della conversazione, invocare C-05, restituire la risposta; gestire `/reset`.
- **Interfaccia pubblica:** `handle(user_id, text) -> Response`.
- **Dipendenze:** C-04, C-24, C-05, C-08, C-25, C-03.
- **Input:** messaggio utente. **Output:** risposta testuale.
- **Error handling:** errore LLM → BR-8 (3 tentativi/1 min) → messaggio di errore all'utente; se per
  rispondere serve un'azione modificante → gate di spec 06.
- **Osservabilità:** log domanda/risposta con latenza.
- **Sicurezza:** solo admin e utenti `accepted` possono usare la chat (BR-12); sconosciuti/revocati
  ignorati.

### C-24 — Conversation Memory
- **Responsabilità:** persistere i messaggi per utente; fornire gli ultimi turni entro il budget di
  contesto; azzerare la memoria dopo 24 h di silenzio o su `/reset`.
- **Interfaccia pubblica:** `get_context(user_id) -> list[Message]`, `append(user_id, msg)`,
  `reset(user_id)`, `purge_idle()`.
- **Dipendenze:** C-02, C-05 (budget token).
- **Input/Output:** messaggi (`role`, `content`, `created_at`).
- **Error handling:** contesto oltre budget → tronca i messaggi più vecchi (decisione #10).
- **Osservabilità:** log reset/purge.
- **Sicurezza:** le chat sono leggibili dall'admin (BR-12); nessuna copia esterna.

### C-25 — Progress Indicator
- **Responsabilità:** inviare "sto cercando…" quando l'elaborazione supera una soglia breve e
  rimuoverlo/aggiornarlo alla risposta.
- **Interfaccia pubblica:** `start(chat_id)`, `finish(...)`.
- **Dipendenze:** C-03. **Error handling:** fallimento invio indicatore → non blocca la risposta.
- **Osservabilità:** log soglia superata.

## Modello di dominio

- **Conversazione:** per utente, con `updated_at`.
- **Messaggio:** `role` (`user`/`assistant`/`tool`), `content`, `created_at`.

## Modello dati

Tabelle `conversations` (`user_id` PK, `updated_at`) e `messages` (`id`, `user_id`, `role`,
`content`, `created_at`), con indice su `messages(user_id, created_at)`.

## Flussi di dati

1. **Domanda semplice:** messaggio → C-04 ruolo → C-23 → C-24 contesto → C-05 risposta (entro 30 s)
   → C-24 append → risposta Telegram.
2. **Domanda con ricerca web:** C-23 avvia C-25 ("sto cercando…") → C-08 esegue `web_search`
   (read-only, senza conferma, spec 06) → C-05 compone → risposta entro 2 min → C-24 append.
3. **Reset per silenzio:** job di manutenzione (C-06) → C-24 `purge_idle()` azzera le conversazioni
   inattive da > 24 h.
4. **Rilettura admin:** comando admin su un utente → C-24 legge lo storico messaggi di quell'utente.

## Progettazione integrazioni

- **Telegram:** ricezione/invio messaggi.
- **DeepSeek:** risposta NL e gestione contesto.
- **Web search:** tramite Tool Registry (spec 06).

## Requisiti di sicurezza

- Accesso chat solo per admin e utenti `accepted` (BR-12).
- Admin può rileggere le chat degli utenti autorizzati (BR-12); ciò è coperto dall'informativa
  privacy accettata (spec 08).
- Contenuto transita da DeepSeek (informativa privacy).

## Requisiti non funzionali

- Risposta semplice ≤ 30 s; con ricerca web ≤ 2 min con "sto cercando…" (BR-17).
- Memoria azzerata a 24 h di silenzio o `/reset` (BR-6).
- Contesto entro budget token (decisione #10).

## Rischi e assunzioni

- **Rischio:** latenza DeepSeek oltre i target → mitigata da indicatore di avanzamento e retry.
- **Assunzione:** il "silenzio" è misurato dall'ultimo messaggio dell'utente.

## Domande tecniche aperte

- Soglia esatta per mostrare "sto cercando…" (es. 2 s).
- Contenuto minimo da conservare per la rilettura admin e relativa retention (oltre al reset).

**Risposte (operatore, 2026-10-24 — decisioni D4/D5 del piano 05):** la soglia è **2 secondi**,
configurabile con `limits.chat_progress_s`; alla risposta l'indicatore viene eliminato in background.
La rilettura admin vede gli **ultimi 50 messaggi della finestra di 24 ore**, la stessa della memoria
(`limits.chat_memory_hours`); `/reset` cancella subito e oltre la finestra non resta nulla da leggere.
Nessuna retention dedicata più lunga.

## Criteri di accettazione

- **AC-01** Dato un utente autorizzato, quando fa una domanda e poi una che vi fa riferimento,
  allora l'agente risponde tenendo conto della conversazione precedente.
- **AC-02** Date 24 ore dall'ultimo messaggio, quando l'utente scrive, allora l'agente non ricorda
  la conversazione precedente.
- **AC-03** Dato l'utente scrive `/reset`, quando invia un nuovo messaggio, allora la conversazione
  riparte da zero.
- **AC-04** Dato l'amministratore, quando chiede di rileggere la chat di un utente autorizzato,
  allora può consultarla.
- **AC-05** Data una domanda semplice, quando l'utente la invia, allora riceve la risposta entro 30
  secondi.
- **AC-06** Data una domanda che richiede ricerca web, quando l'utente la invia, allora vede "sto
  cercando…" e riceve la risposta entro 2 minuti.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-004, BR-2/6/12/17, §8 (journey 3), §10, §12.

## Assunzioni

- **A-01** Contesto troncato entro un budget token (~8k), ultimi turni (decisione #10).
- **A-02** Conversazioni separate per `user_id`.

## Domande in sospeso

- Soglia "sto cercando…"; retention dei messaggi per la rilettura admin: **chiuse** il 2026-10-24
  (D4/D5 del piano 05; vedi sopra).

## Valutazione di confidenza

**Alta** — FR-004 documentato con criteri di accettazione misurabili.

## Note di implementazione (2026-10-24)

- **Decisioni che chiudono le domande aperte:** D4 retention dei messaggi = 24 h (stessa finestra
  della memoria, rilettura admin sugli ultimi 50 messaggi); D5 soglia dell'indicatore = 2 s
  (`limits.chat_progress_s`), messaggio eliminato in background alla risposta. Altre decisioni
  registrate nel piano: D1 creazione vs chat, D2 migrazione 004 senza FK, D3 `/chat <telegram_id>`,
  D6 AC-06 come gap (spec 06), D7 30 s/2 min come limiti-obiettivo con retry BR-8, D8 job di
  manutenzione a coroutine.
- **Deliverable:** C-24 `src/agente/chat_memory.py`, C-25 `src/agente/progress.py`, C-23
  `src/agente/chat.py`; estensioni C-03 (`send` con id, `delete_message`), C-14 (`/reset`,
  `/chat`, precedenza della bozza completa), C-02 (`messages_for_user`, `delete_all_for_user`,
  `delete_idle`), C-06 (job di manutenzione nell'event loop); migrazione
  `004_chat_without_user_fk.sql`; `limits.chat_progress_s`; wiring in `app.py`.
- **Deviazioni:** V-01…V-13 nel documento [05-fr004-domande-libere.md](../architecture/05-fr004-domande-libere.md).
  V-04 e V-06 modificano interfaccia e modello dati di spec 01: nota di continuità in spec 01
  §Note di implementazione (2026-10-24).
- **Sicurezza:** chat solo per admin e utenti `accepted`; rilettura riservata all'admin; solo tool
  read-only esposti; in chat l'allowlist dei log è vuota (spec 07).
- **Test:** 271 raccolti, tutti verdi (`PYTHONPATH=src:.deps python3 -m pytest`), inclusi AC-01…AC-06
  in `tests/test_chat_ac.py` e la migrazione con dati in `tests/test_storage.py`.
- **Gap:** AC-06 non è verificabile end-to-end senza `web_search` (spec 06); l'indicatore e il tool
  loop read-only sono coperti con uno strumento finto. La latenza reale di BR-17 resta da misurare
  sul dispositivo.
- **Documento:** [05-fr004-domande-libere.md](../architecture/05-fr004-domande-libere.md), checkpoint
  di struttura `sdd-governor` Phase 4 **APPROVED** (2026-10-24).

## Nota di continuità (2026-10-25, voce 06)

`web_search` è stato consegnato con C-26: AC-06 è ora verificabile end-to-end e il test
`tests/test_approval_ac.py::test_ac06_web_search_closes_the_gap` lo copre (indicatore inviato e
rimosso, risultati nella risposta, nessuna conferma). La chat espone al modello anche gli strumenti
modificanti: l'esecuzione passa dal gate C-27/C-28 e solo dopo approvazione dell'admin (V-10 della
voce 06). Il prompt di sistema di C-23 è stato aggiornato di conseguenza; la frase «solo strumenti
read-only» nelle note del 2026-10-24 valeva prima del gate.

## Nota di continuità (2026-10-29, voce 07)

La nota della voce 05 («`read_logs` resta rifiutato in chat finché spec 07 non definisce
un'autorizzazione») è chiusa: spec 07 (D6/V-06) ha scelto di **non** autorizzare la lettura dei log in
chat. `ChatToolContext.log_allowlist` resta vuota, `read_logs` produce un rifiuto e C-23 lo traduce in
testo per il modello; nessuna deroga per l'admin, BR-13 vale anche in chat. C-23 non è stato
modificato.

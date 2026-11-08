# Specifica 02 — Gestione dei compiti (FR-001)

- **ID:** `02-fr001-gestione-compiti`
- **Stato:** Implemented (2026-10-21)
- **Requisiti collegati:** FR-001; BR-1, BR-12, BR-14, BR-15
- **Dipendenze:** `01-agent-runtime`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

L'amministratore deve poter **creare e gestire i compiti ricorrenti** scrivendo su Telegram, in
linguaggio naturale o con comandi rapidi, **senza aprire Termux**. Un compito definisce: nome,
istruzioni, quando eseguirlo (orario o intervallo), destinatari, eventuale percorso log autorizzato.

Creazione, modifica ed eliminazione richiedono **conferma esplicita dell'amministratore** prima di
avere effetto (BR-1). Solo l'amministratore può creare o modificare compiti; un utente autorizzato
riceve un rifiuto cortese (BR-12).

## Panoramica architetturale

Riutilizza i componenti di `01-agent-runtime`: Telegram Gateway (C-03), Role Guard (C-04), LLM
Client (C-05, per l'interpretazione in linguaggio naturale), Storage (C-02), Notification Service
(C-10), Scheduler (C-06, per registrare i job).

Componenti specifici di questa feature:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-14 | Command Router | Instrada comandi slash e messaggi NL verso le operazioni sui compiti |
| C-15 | Task Manager | CRUD e validazione dei compiti |
| C-16 | Schedule Interpreter | Interpreta orario/intervallo e rileva ambiguità |
| C-17 | Confirmation Flow | Riepilogo + conferma esplicita prima dell'effetto |

## Progettazione componenti

### C-14 — Command Router
- **Responsabilità:** riconoscere i comandi rapidi (`/tasks`, `/pause <nome>`, `/resume <nome>`,
  `/delete <nome>`, e i comandi delle altre feature) e i messaggi NL diretti alla gestione compiti.
- **Interfaccia pubblica:** `route(update, role) -> Action`.
- **Dipendenze:** C-03, C-04, C-05, C-15.
- **Input:** testo utente. **Output:** azione di dominio.
- **Error handling:** comando sconosciuto → messaggio di aiuto; comando da ruolo non ammesso →
  rifiuto (BR-12).
- **Osservabilità:** log comando riconosciuto.

### C-15 — Task Manager
- **Responsabilità:** creare, leggere, modificare, sospendere/riattivare, eliminare compiti;
  validare i campi; garantire la conferma prima dell'effetto.
- **Interfaccia pubblica:** `create(draft) -> Task` (dopo conferma), `update(id, delta)`,
  `pause(id)`, `resume(id)`, `delete(id)`, `list(role, user_id)`.
- **Dipendenze:** C-02, C-05, C-16, C-17, C-06.
- **Input/Output:** `Task` (persistito in `tasks`).
- **Error handling:** nome duplicato → richiesta nome diverso; campo mancante → richiesta di
  precisazione; errore di persistenza → nessuna modifica e messaggio di errore.
- **Scalabilità:** ≤ 10 compiti attivi (BR-16); indice su `name`.
- **Osservabilità:** log CRUD con `task_id`.
- **Sicurezza:** accessibile solo all'admin (BR-12); ogni scrittura passa da C-17.

### C-16 — Schedule Interpreter
- **Responsabilità:** ricavare dalla frase (o dal comando) il tipo di schedulazione (orario fisso
  o intervallo) e l'espressione, nel **fuso orario del telefono** (BR-14).
- **Interfaccia pubblica:** `parse(text) -> Schedule | Ambiguous`.
- **Dipendenze:** C-05, timezone di sistema.
- **Input:** testo (es. *"ogni giorno alle 8"*, *"la mattina"*, *"ogni 2 ore"*).
- **Output:** `Schedule(type, expr, tz)` oppure `Ambiguous` con richiesta di precisazione.
- **Error handling:** orario ambiguo (es. *"la mattina"*) → **non assunto**: si chiede di
  precisare prima del riepilogo (FR-001, BR-14).
- **Osservabilità:** log schedule interpretato.

### C-17 — Confirmation Flow
- **Responsabilità:** mostrare un riepilogo (nome, istruzioni, orario, destinatari) e raccogliere la
  conferma esplicita dell'admin prima di rendere effettiva creazione/modifica/eliminazione (BR-1).
- **Interfaccia pubblica:** `confirm(summary) -> bool`.
- **Dipendenze:** C-03, C-10.
- **Input:** riepilogo. **Output:** conferma/annullamento.
- **Error handling:** mancata conferma → nessun salvataggio; timeout di inattività → annullo con
  messaggio.
- **Osservabilità:** log conferma/annullo.

## Modello di dominio

- **Compito (`Task`):** `id`, `nome`, `istruzioni`, `schedule`, `destinatari`, `stato`, `allowlist_log`.
- **Schedule:** tipo `orario` (es. `08:00` giornaliero o giorni specifici) o `intervallo`
  (es. ogni N ore); timezone = telefono.
- **Destinatari:** insieme di utenti autorizzati iscritti (l'admin è sempre destinatario).
- **Stato compito:** `attivo` | `sospeso` (BR-15).

Relazioni: Compito 1→N Esecuzione (spec 03/04); Compito N↔N Utente (Iscrizione, spec 08); Compito
0/1→ allowlist log (spec 07).

## Modello dati

Usa la tabella `tasks` definita in `01-agent-runtime`: `id`, `name` (UNIQUE), `instructions`,
`schedule_type`, `schedule_expr`, `state`, `log_allowlist` (JSON), `created_by`, `created_at`,
`updated_at`. Le iscrizioni stanno in `subscriptions`.

## Flussi di dati

1. **Creazione (NL):** messaggio admin → C-14 → C-05 estrae bozza (nome, istruzioni, orario,
   destinatari) → C-16 interpreta l'orario o chiede precisazione → C-17 mostra riepilogo →
   conferma → C-15 salva `attivo` → C-06 registra il job.
2. **Creazione (comando rapido):** come sopra, con i campi dal comando.
3. **Modifica:** `/pause <nome>` o NL → C-15 propone delta → C-17 conferma → C-15 persiste → C-06
   aggiorna job.
4. **Eliminazione:** richiesta admin → C-17 conferma → C-15 elimina + C-06 rimuove job.
5. **Elenco:** `/tasks` o NL → C-15 lista per ruolo (admin: tutti; utente: iscritti).

## Progettazione integrazioni

- **Telegram:** ricezione comandi/NL e invio riepiloghi/conferme (C-03).
- **DeepSeek:** estrazione bozza compito e parsing NL (C-05).
- **APScheduler:** registrazione/aggiornamento/rimozione job (C-06).

## Requisiti di sicurezza

- Solo l'admin crea/modifica/elimina compiti (BR-12); utente autorizzato → rifiuto.
- Nessun salvataggio senza conferma esplicita (BR-1).
- Destinatari limitati a utenti autorizzati.
- Allowlist log facoltativa, definita alla creazione (BR-13, spec 07).

## Requisiti non funzionali

- Interpretazione NL ragionevole in italiano; risposta secondo i tempi di BR-17.
- Timezone del telefono, lingua italiano salvo lingua utente (BR-14).
- Fino a 10 compiti attivi (BR-16).

## Rischi e assunzioni

- **Rischio:** parsing NL ambiguo o errato → mitigato da riepilogo+conferma obbligatori (BR-1).
- **Rischio:** intervalli molto corti → carico; non documentato: valutare un minimo.
- **Assunzione:** i nomi compito sono univoci per l'admin.

## Domande tecniche aperte

- Semantica esatta degli **intervalli** (ancorati all'avvio, alla mezzanotte, o "ogni N minuti dal
  termine"): non documentata.
- Eventuale limite minimo di intervallo/frequenza.
- Gestione nomi compito case-insensitive e rinominazione (nome = chiave di `/pause`).

## Criteri di accettazione

- **AC-01** Dato l'amministratore scrive un compito NL, quando l'agente lo interpreta, allora mostra
  un riepilogo (nome, istruzioni, orario, destinatari) e lo salva solo dopo la conferma.
- **AC-02** Dato un orario ambiguo, quando l'agente riceve la richiesta, allora chiede di precisarlo
  invece di assumerlo.
- **AC-03** Dato un utente autorizzato, quando prova a creare un compito, allora riceve un rifiuto e
  nessun compito viene creato.
- **AC-04** Dato un compito attivo, quando l'amministratore invia `/pause <nome>`, allora il compito
  passa a sospeso e non viene più eseguito finché non viene riattivato.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-001, BR-1/12/14/15, §8 (journey 1–2), §10, §12.

## Assunzioni

- **A-01** Interpretazione NL delegata al LLM (C-05) con riepilogo+conferma come rete di sicurezza.
- **A-02** Il fuso orario è quello del telefono, letto a runtime.

## Domande in sospeso

- Semantica e limiti degli intervalli (vedi Domande tecniche aperte).

## Valutazione di confidenza

**Alta** — requisito funzionale documentato (FR-001) con regole e criteri di accettazione espliciti.

## Note di implementazione (2026-10-21)

- **Decisioni che chiudono le domande aperte:** D1 intervalli ancorati all'istante di creazione (o
  di ripresa); D2 intervallo minimo 1 minuto (`limits.min_interval_minutes`); D3 nomi univoci senza
  distinzione di maiuscole e `/rename` disponibile; D4 nessun comando di creazione (creazione solo
  in linguaggio naturale); D5 scadenza della conferma = `limits.approval_timeout_s` (900 s, BR-3);
  D6 conferma con bottoni inline e fallback testuale «sì»/«no».
- **Deliverable:** C-14 `command_router.py`, C-15 `task_manager.py`, C-16
  `schedule_interpreter.py`, C-17 `confirmation.py`, ingresso normalizzato in
  `telegram_gateway.py`, `trigger_for()` in `scheduler.py`, migrazione
  `002_task_name_nocase.sql`, `limits.min_interval_minutes`, test AC-01…AC-04 e documento
  `docs/architecture/02-fr001-gestione-compiti.md`.
- **Espressioni canoniche persistite:** `orario` → `HH:MM` o `HH:MM@LUN,MAR`; `intervallo` → `Nm` o
  `Nh`.
- **Deviazioni d'interfaccia** (semantica invariata): C-14 `route(message: IncomingMessage)` invece
  di `route(update, role)`; C-17 `confirm(*, requested_by, chat_id, summary)`; C-15 mantiene le
  operazioni dichiarate e aggiunge `rename`. BR-1 è applicato da C-14 (P-A-08, approvata).
- **Flusso 2** (creazione da comando rapido) non implementato per D4: lacuna dichiarata e accettata
  dall'operatore; il flusso 3 è coperto anche in linguaggio naturale con verbi imperativi.
- **Follow-up tracciati:** esecuzione end-to-end e recupero mancata occorrenza (spec 03), boot
  recovery dei job (spec 11), gate C-27/C-28 (spec 06), utenti e privacy (spec 08), allowlist log
  (spec 07), storico (spec 09).
- **Assunzioni del piano:** P-A-01…P-A-08 in `docs/plan/02-fr001-gestione-compiti.plan.md`.

## Nota di continuità (2026-11-01, voce 08)

C-14 estende il registro dei comandi (`/adduser`, `/removeuser`, `/users`, `/subscribe`,
`/unsubscribe`, tutti solo admin) e dei callback (`authorize:`, `consent:`, oltre a `confirm:` e
`approval:`). L'ordine di instradamento diventa: ruolo → **callback** → comandi → linguaggio naturale;
i callback precedono il rifiuto agli `UNKNOWN`, altrimenti un `pending` non potrebbe accettare
l'informativa e l'admin non potrebbe premere «Autorizza». I comandi e i callback preesistenti non
cambiano comportamento.

## Nota di continuità (2026-11-02, voce 09)

C-14 guadagna `/history [periodo] [compito]` e il riconoscimento delle richieste NL di storico. In
`_on_natural` l'ordine diventa: lancio → mutazioni → **storico** → elenco compiti → bozza/chat; un
testo che contiene un indizio di schedulazione (`ogni`, `tutti i giorni`, `giornalier*`, …) non è una
richiesta di storico. `HELP_TEXT` elenca il nuovo comando. Callback e comandi preesistenti non
cambiano comportamento.

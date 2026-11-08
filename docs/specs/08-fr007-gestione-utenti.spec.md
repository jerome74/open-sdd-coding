# Specifica 08 — Gestione degli utenti (FR-007)

- **ID:** `08-fr007-gestione-utenti`
- **Stato:** Implemented (2026-11-01)
- **Requisiti collegati:** FR-007; BR-12, BR-18
- **Dipendenze:** `01-agent-runtime`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

Solo l'amministratore controlla **chi può interagire** con l'agente e **a quali compiti è iscritto**.
Uno sconosciuto che scrive al bot riceve un rifiuto e genera un avviso all'amministratore con il suo
nome Telegram e il pulsante **Autorizza**. In alternativa l'admin autorizza con `/adduser`.

Dopo l'autorizzazione l'agente invia al nuovo utente un **messaggio informativo sulla privacy**: i
suoi messaggi transitano da DeepSeek e Telegram, sono conservati sull'S24 e l'admin può rileggerli.
L'utente deve **accettarlo esplicitamente**; solo dopo può usare l'agente. Se rifiuta (o non
accetta), resta non autorizzato e l'admin riceve un avviso (BR-18). L'admin può revocare un utente
(`/removeuser`), iscriverlo/disiscriverlo da un compito ed elencare gli utenti.

## Panoramica architetturale

Riutilizza: Telegram Gateway (C-03), Role Guard (C-04), Storage (C-02), Notification (C-10).

Componenti specifici:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-31 | User Manager | Gestisce utenti, stati e iscrizioni |
| C-32 | Consent Flow | Invia l'informativa privacy e registra l'accettazione |
| C-33 | Authorization Notifier | Avvisa l'admin dei nuovi contatti con pulsante Autorizza |

## Progettazione componenti

### C-31 — User Manager
- **Responsabilità:** creare/aggiornare/revocare utenti; gestire iscrizioni ai compiti; elencare
  utenti.
- **Interfaccia pubblica:** `authorize(telegram_id)`, `revoke(id)`, `subscribe(user_id, task_id)`,
  `unsubscribe(user_id, task_id)`, `list_users()`.
- **Dipendenze:** C-02, C-04, C-32.
- **Input/Output:** record utente (`telegram_id`, `username`, `state`, `consent_at`).
- **Error handling:** utente già autorizzato → messaggio informativo; operazione da non-admin →
  rifiuto (BR-12).
- **Osservabilità:** log autorizzazioni/revoche/iscrizioni.
- **Sicurezza:** solo l'admin autorizza/revoca (BR-12); un utente revocato è trattato come
  sconosciuto.

### C-32 — Consent Flow
- **Responsabilità:** inviare l'informativa privacy al nuovo utente e registrarne l'accettazione
  esplicita prima di abilitarlo (BR-18).
- **Interfaccia pubblica:** `send_consent(user_id)`, `accept(user_id)`, `decline(user_id)`.
- **Dipendenze:** C-03, C-02, C-10.
- **Input/Output:** stato `pending` → `accepted` | `revoked` (in caso di rifiuto).
- **Error handling:** rifiuto o nessuna accettazione → l'utente resta non autorizzato; l'admin
  riceve un avviso.
- **Osservabilità:** log invio/accettazione/rifiuto.

### C-33 — Authorization Notifier
- **Responsabilità:** al primo contatto di uno sconosciuto, avvisare l'admin con nome Telegram e
  pulsante **Autorizza**; limitare il contatto ripetuto.
- **Interfaccia pubblica:** `notify_unknown(telegram_id, username)`.
- **Dipendenze:** C-03, C-10, C-04.
- **Error handling:** molteplici messaggi da sconosciuti → non generare spam (aggregazione/rate
  limit).
- **Osservabilità:** log avvisi inviati.
- **Sicurezza:** lo sconosciuto non riceve risposte utili (BR-12).

## Modello di dominio

- **Utente:** `telegram_id`, `username`, `state` (`pending`/`accepted`/`revoked`), `consent_at`.
- **Iscrizione:** relazione utente ↔ compito.
- **Stato utente (BR-18):** `in attesa di accettazione` (`pending`) / `autorizzato` (`accepted`) /
  `revocato` (`revoked`).
- **Amministratore:** definito in config, **non** è un record utente.

## Modello dati

Tabelle `users` e `subscriptions` (spec 01). `consent_at` valorizzato all'accettazione.

## Flussi di dati

1. **Sconosciuto:** messaggio → C-04 `UNKNOWN` → C-33 avvisa l'admin con Autorizza → lo sconosciuto
   non ottiene risposte utili.
2. **Autorizzazione con pulsante:** admin preme Autorizza → C-31 crea `pending` → C-32 invia
   l'informativa → l'utente accetta → `accepted` → può usare l'agente.
3. **Autorizzazione con `/adduser`:** come sopra, a partire dal comando admin.
4. **Rifiuto/o silenzio:** l'utente resta `pending`/`revoked`; l'admin riceve un avviso.
5. **Revoca:** `/removeuser` → `revoked` → contatti successivi trattati come sconosciuti.
6. **Iscrizione:** admin iscrive/disiscrive un utente da un compito; aggiorna `subscriptions`, usato
   da delivery (spec 03), lancio manuale (spec 04) e storico (spec 09).

## Progettazione integrazioni

- **Telegram:** pulsanti Autorizza, invio informativa, callback di accettazione/rifiuto.
- **Storage:** `users`, `subscriptions`.

## Requisiti di sicurezza

- Solo l'admin autorizza/revoca (BR-12); un utente autorizzato che tenta `/adduser` riceve un
  rifiuto.
- Nessun uso dell'agente prima dell'accettazione dell'informativa (BR-18).
- Revoca immediata: l'utente revocato è ignorato.
- Dati utente conservati solo sull'S24 (FR §10).

## Requisiti non funzionali

- ≤ 5 utenti autorizzati (BR-16).
- Antispam sui contatti da sconosciuti.

## Rischi e assunzioni

- **Rischio:** spam da sconosciuti → mitigato da C-33 (aggregazione/rate limit).
- **Assunzione:** l'admin è sempre raggiungibile su Telegram per autorizzare.

## Domande tecniche aperte

- Strategia anti-spam esatta (debounce, soglia).
- Testo esatto dell'informativa privacy (contenuto legale da fornire).
- Cosa accade ai dati/iscrizioni di un utente revocato (conservare vs eliminare).

## Criteri di accettazione

- **AC-01** Dato uno sconosciuto scrive al bot, quando il messaggio arriva, allora lo sconosciuto non
  riceve risposte utili e l'amministratore riceve l'avviso con Autorizza.
- **AC-02** Dato l'amministratore preme Autorizza, quando l'utente accetta il messaggio informativo,
  allora l'agente gli risponde come utente autorizzato.
- **AC-03** Dato l'amministratore preme Autorizza, quando l'utente rifiuta il messaggio informativo,
  allora resta non autorizzato e l'amministratore riceve un avviso.
- **AC-04** Dato l'amministratore revoca un utente, quando quell'utente scrive, allora viene
  ignorato.
- **AC-05** Dato un utente autorizzato, quando invia `/adduser`, allora il comando viene rifiutato.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-007, BR-12/18, §8 (journey 3), §10, §12.

## Assunzioni

- **A-01** Admin definito in config; utenti in DB con stati (decisione #7).
- **A-02** Il testo dell'informativa privacy è fornito dall'operatore.

## Domande in sospeso

- Anti-spam; testo informativa; gestione dati utente revocato (vedi sopra).

**Risposte (operatore, 2026-11-01 — decisioni D1–D3 del piano 08):** anti-spam con **una finestra di
24 ore per utente** e contatore in memoria; **testo dell'informativa approvato** e riportato verbatim
in `consent.PRIVACY_NOTICE`; **revoca che conserva record e iscrizioni** (nessun `DELETE`). Le
decisioni D4–D6 chiudono i comportamenti impliciti: comandi `/users`, `/subscribe`, `/unsubscribe`;
tetto rigido di 5 utenti `accepted` (BR-16); nessun timeout dell'informativa (l'utente resta
`pending`, senza avviso automatico sul silenzio).

## Valutazione di confidenza

**Alta** — FR-007 documentato con criteri di accettazione; le domande operative sono state chiuse il
2026-11-01 (D1–D3).

## Note di implementazione (2026-11-01)

- **Componenti:** C-31 `src/agente/user_manager.py` (`authorize`, `revoke`, `subscribe`,
  `unsubscribe`, `list_users`, transizioni di stato, pre-check BR-16), C-32
  `src/agente/consent.py` (`send_consent`, `accept`, `decline`, `PRIVACY_NOTICE`, `consent_at`,
  tetto BR-16), C-33 `src/agente/authorization_notifier.py` (`notify_unknown`, pulsante
  `authorize:<id>`, finestra anti-spam di 24 h, `username_for`). Contratto condiviso in
  `src/agente/user_state.py` (`UserView`, `UserResult`, `MAX_AUTHORIZED_USERS`).
- **Estensioni:** C-03 (`IncomingMessage.username`), C-10 (`notify`/`alert_admin` con tastiera
  opzionale sull'ultimo chunk), C-14 (comandi `/adduser`, `/removeuser`, `/users`, `/subscribe`,
  `/unsubscribe`; callback `authorize:`/`consent:` instradati prima del rifiuto agli `UNKNOWN`;
  `HELP_TEXT` aggiornato), `errors.UserAccessError` con `reason`.
- **Decisioni:** D1 testo privacy approvato; D2 anti-spam 24 h in memoria; D3 revoca conservativa;
  D4 comandi di iscrizione ed elenco; D5 tetto rigido BR-16; D6 nessun timeout dell'informativa.
- **Deviazioni:** V-01…V-12 nel documento
  [08-fr007-gestione-utenti.md](../architecture/08-fr007-gestione-utenti.md). V-09 estende C-10, V-10
  rinuncia all'avviso sul silenzio, V-12 introduce il rifiuto esplicito a sconosciuto/revocato.
- **Modello dati:** nessuna tabella e nessuna migrazione; `users`/`subscriptions` invariate.
- **Sicurezza:** solo admin gestisce utenti (BR-12 e doppio controllo C-14/C-31); nessun uso prima
  dell'accettazione (BR-18); `authorize:` richiede admin, `consent:` richiede il destinatario;
  l'admin non è un target e non conta nel tetto.
- **Test:** 451 raccolti, tutti verdi (`PYTHONPATH=src:.deps python3 -m pytest`), inclusi AC-01…AC-05
  in `tests/test_users_ac.py` e i test di C-31/C-32/C-33.
- **Gap:** la chat di un utente revocato non è rileggibile da `/chat` (C-23 accetta admin e
  `accepted`); un riavvio può duplicare un avviso anti-spam; il nome Telegram si perde se il processo
  si riavvia fra avviso e pulsante; un `pending` non ha scadenza né avviso automatico sul silenzio;
  lo storico strutturato resta item 09.
- **Documento:** [08-fr007-gestione-utenti.md](../architecture/08-fr007-gestione-utenti.md),
  checkpoint di struttura `sdd-governor` Phase 4 **APPROVED** (2026-11-01).

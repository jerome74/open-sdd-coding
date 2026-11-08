# Piano 08 — FR-007 Gestione degli utenti

- **Voce roadmap:** `08 — FR-007 Gestione utenti` (non spuntata)
- **Spec:** [08-fr007-gestione-utenti.spec.md](../specs/08-fr007-gestione-utenti.spec.md), Stato `New`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack, `## Roadmap`
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`: C-02 con `users`/`subscriptions` e migrazione 001, C-03 con `send`/inline keyboard, C-04 con `Role` e stati `pending`/`accepted`/`revoked`, C-10 con `alert_admin`, C-23 con `/chat`), item 02 (`02-fr001-gestione-compiti`: C-14 con comandi e callback, C-15 con `find` per nome e destinatari solo `accepted`, C-17), item 03 (C-20 `DeliveryService` filtra gli `accepted`), item 04 (C-21 `RunDispatcher` rifiuta `UNKNOWN`), item 05 (C-23 chat per gli `accepted`), item 06 (C-27/C-28, callback `approval:`), item 07 (C-29/C-30, nessuna interazione)
- **Dipendenze non consegnate:** item 09 (storico esecuzioni), item 10 (avvisi di sistema), item 11 (riavvio)
- **Data piano:** 2026-11-01
- **Stato piano:** approvato 2026-11-01; eseguito T1–T11 (delivery history: voce 08)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-31 User Manager: `authorize(actor_id, telegram_id, *, username=None)`, `revoke(actor_id, telegram_id)`, `subscribe(actor_id, user_id, task_id)`, `unsubscribe(actor_id, user_id, task_id)`, `list_users(actor_id)`; transizioni di stato esplicite, tetto BR-16, esito `UserResult`, solo admin | codice | `src/agente/user_manager.py` |
| D-02 | C-32 Consent Flow: `send_consent(user_id)`, `accept(user_id, *, by_user_id)` (**async**), `decline(user_id, *, by_user_id)`; testo privacy approvato; `pending` → `accepted` (con `consent_at`) o `revoked`; avviso all'admin al rifiuto e al tetto; esito `UserResult`; applica `MAX_AUTHORIZED_USERS` (BR-16) | codice | `src/agente/consent.py` |
| D-03 | C-33 Authorization Notifier: `notify_unknown(telegram_id, username)` con pulsante **Autorizza**, finestra anti-spam di 24 h per utente in memoria e mappa `telegram_id → username` per il callback | codice | `src/agente/authorization_notifier.py` |
| D-04 | Estensione C-03: `IncomingMessage.username` popolato da `update.effective_user.username` (messaggi e callback) | codice | `src/agente/telegram_gateway.py` |
| D-05 | Estensione C-10: `alert_admin(text, keyboard=None)` e `notify(recipients, text, keyboard=None)` per inviare il pulsante **Autorizza** senza aggirare C-10 | codice | `src/agente/notifications.py` |
| D-06 | Estensione C-14: comandi `/adduser <telegram_id> [username]`, `/removeuser <telegram_id>`, `/users`, `/subscribe <compito> <telegram_id>`, `/unsubscribe <compito> <telegram_id>` (solo admin); callback `authorize:<id>` e `consent:accept|decline`; sconosciuto/revocato → rifiuto + C-33; `HELP_TEXT` aggiornato | codice | `src/agente/command_router.py` |
| D-07 | Errori `UserAccessError` (codici `forbidden`, `not_found`, `invalid_state`, `invalid_target`, `limit`) e contratto condiviso `UserView`/`UserResult`/`MAX_AUTHORIZED_USERS` in un modulo dati che non importa componenti (solo il tipo `User` da C-02) | codice | `src/agente/errors.py`, `src/agente/user_state.py` |
| D-08 | Wiring: C-31/C-32/C-33 costruiti in `AgentApp.build` e iniettati in C-14; `AgentApp` espone `user_manager`, `consent`, `notifier` | codice | `src/agente/app.py` |
| D-09 | Test della voce: unit C-31/C-32/C-33/C-10, estensioni a C-14/C-03/C-04, AC-01…AC-05 end-to-end, aggiornamento dei test esistenti su sconosciuto/revocato | test | `tests/test_user_manager.py`, `tests/test_consent.py`, `tests/test_authorization_notifier.py`, `tests/test_users_ac.py`, `tests/test_command_router.py`, `tests/test_telegram_gateway.py`, `tests/test_notifications.py`, `tests/test_role_guard.py`, `tests/conftest.py` |
| D-10 | Documento architettura della feature con Mermaid (1 flowchart, 6 sequenze, una per flusso di spec 08) e testo privacy verbatim | documentazione | `docs/architecture/08-fr007-gestione-utenti.md` |
| D-11 | Pubblicazione: roadmap `[x]`, stato spec 08 `Implemented` + note, delivery history, piano allineato, note di continuità su spec 01 (C-03 `username`, C-10 `keyboard`), spec 02 (C-14 ordine e registro callback), spec 06 (registro callback `approval:`) | documentazione | `docs/specs/constitution.md`, `docs/specs/08-fr007-gestione-utenti.spec.md`, `docs/specs/01-agent-runtime.spec.md`, `docs/specs/02-fr001-gestione-compiti.spec.md`, `docs/specs/06-fr005-ricerca-web-conferma.spec.md`, `docs/delivery-history.md`, questo piano |

Nessuna tabella nuova e nessuna migrazione: `users` (`telegram_id`, `username`, `state`,
`consent_at`, `created_at`, `updated_at`) e `subscriptions` (`user_id`, `task_id`) esistono dalla 001
e sono già usate da C-04, C-15, C-20 e C-21. Nessuna nuova chiave di configurazione: il testo privacy
è una costante di modulo (D1), i limiti sono `MAX_AUTHORIZED_USERS` in `user_state.py` (BR-16) e
`UNKNOWN_ALERT_WINDOW_S` in `authorization_notifier.py` (D2).

### Fuori scope di questa voce (dichiarato)

- **Timeout dell'informativa (D6):** un utente che non risponde resta `pending`; nessun job, nessuna
  scadenza e **nessun avviso automatico per il silenzio** (V-10). L'admin vede i `pending` in
  `/users` e può revocarli.
- **Eliminazione dei dati dell'utente revocato (D3):** record e iscrizioni restano; la revoca cambia
  solo lo stato. Nessun `DELETE`, nessuna cancellazione delle conversazioni.
- **Rilettura admin della chat di un utente revocato:** C-23 accetta solo `accepted`
  (`chat.py::transcript`, `list_authorized`). I dati restano, la rilettura no: **gap dichiarato**, C-23
  non viene modificato in questa voce.
- **Notifiche di sistema e storico:** item 09/10. Qui solo gli avvisi puntuali di C-33 e C-32.
- **Lettura dei log e chat:** invariati (item 07); `read_logs` resta rifiutato in chat.
- **Vista di deployment:** non dichiarata dalla spec 08 e non necessaria a descrivere il
  comportamento; **gap registrato** esplicitamente.
- **Modifica del testo privacy a runtime:** nessuna leva di configurazione (D1/P-A-01).

## Decisioni che sbloccano il piano

Chiuse dall'operatore il 2026-11-01. D1 risponde ad A-02, D2/D3/D6 alle tre domande tecniche aperte
di spec 08; D4 colma i comandi che la spec non nomina; D5 applica BR-16.

| # | Domanda aperta / conflitto | Decisione | Impatto |
|---|----------------------------|-----------|---------|
| D1 | Testo dell'informativa privacy (A-02, domanda aperta) | **Bozza approvata**, riportata verbatim in C-32 e nel documento: «Privacy — come funziona l'agente. I tuoi messaggi a questo bot passano dai server di DeepSeek (per generare le risposte) e di Telegram (per il trasporto). Sono conservati nella memoria dell'agente sul telefono (S24) dell'amministratore e l'amministratore può rileggerli. Puoi chiedere in ogni momento all'amministratore di revocare il tuo accesso. Premi «Accetto» per usare l'agente; «Rifiuto» per non autorizzare l'accesso.» | D-02, P-A-01, V-03; test sul testo |
| D2 | Strategia anti-spam di C-33 (domanda aperta) | **Un avviso per utente ogni 24 ore**, contatore in memoria; lo sconosciuto riceve **sempre** il rifiuto, l'admin al massimo un avviso per id nella finestra. Nessuna tabella, nessuna migrazione; un riavvio può produrre al più un avviso in più | D-03, P-A-02, V-04; test con clock iniettato |
| D3 | Dati e iscrizioni di un utente revocato (domanda aperta) | **Conservare record e iscrizioni**: `state=revoked`, `consent_at` invariato, righe di `subscriptions` intatte. C-20/C-21 ignorano già chi non è `accepted` | D-01, P-A-15, V-05; test di revoca |
| D4 | Comandi per iscrizioni ed elenco (la spec nomina solo `/adduser` e `/removeuser`) | **`/users`**, **`/subscribe <compito> <telegram_id>`**, **`/unsubscribe <compito> <telegram_id>`**, tutti e tre solo admin | D-06, P-A-07/P-A-21, V-02; test di comando |
| D5 | BR-16 «fino a 5 utenti autorizzati» | **Tetto rigido**: la sesta autorizzazione (o accettazione) è rifiutata; nessun utente viene creato o abilitato oltre 5 `accepted`. Il conteggio considera solo gli `accepted` | D-01, D-02, P-A-08, V-06; test del sesto utente |
| D6 | Utente autorizzato che non accetta né rifiuta l'informativa (domanda aperta «cosa accade in caso di silenzio») | **Nessun timeout**: resta `pending` (quindi non autorizzato), compare in `/users`, l'admin può revocarlo. Nessun avviso automatico sul silenzio (V-10); l'avviso all'admin esiste al rifiuto esplicito e — già — al momento dell'autorizzazione | D-02, P-A-09, V-08, V-10; test del silenzio |

## Transizioni di stato (regola unica, applicata da C-31 e C-32)

| Stato attuale | `authorize` | `accept` | `decline` | `revoke` |
|---|---|---|---|---|
| assente | → `pending`, `consent_at=None`, invia informativa | `not_found` | `not_found` | `not_found` |
| `pending` | resta `pending`, **rinvia** l'informativa, conserva `consent_at` | → `accepted`, `consent_at=now` (se BR-16 lo consente) | → `revoked`, `consent_at` invariato | → `revoked` |
| `accepted` | resta `accepted`, «già autorizzato», **nessuna** informativa | `invalid_state` | `invalid_state` | → `revoked` |
| `revoked` | → `pending` **se BR-16 lo consente** (altrimenti `limit`), `consent_at=None` (nuova accettazione obbligatoria), invia informativa | `invalid_state` | `invalid_state` | resta `revoked`, «già revocato» |

- `authorize` e `revoke` con `telegram_id == admin_id` → `invalid_target`: l'amministratore non è un
  record `users` (decisione #7) e non va creato né conteggiato in BR-16.
- `authorize` preserva `username` e `consent_at` esistenti quando i nuovi valori sono assenti; non usa
  `upsert` con un oggetto costruito da zero (P-A-22).
- `accept` verifica **prima** lo stato (`pending`) e **poi** il tetto BR-16: un utente già autorizzato
  non riceve un errore di limite.
- La transizione `revoked → pending` è una riautorizzazione esplicita dell'admin, non un accesso:
  l'utente resta non autorizzato finché non accetta di nuovo (BR-18).
- **Riattivazione delle iscrizioni (D3):** un revocato conserva le righe di `subscriptions`; se viene
  riautorizzato e accetta di nuovo, C-20 torna a consegnargli i compiti a cui era iscritto, senza
  che l'admin debba reiscriverlo. È l'effetto voluto di D3 ed è dichiarato qui, non un caso implicito.

## Riparto di responsabilità tra componenti (anti-duplicazione)

| Componente | Possiede | Delega a | Non duplica perché |
|---|---|---|---|
| C-31 User Manager | ciclo di vita del record utente, iscrizioni, elenco, transizioni e **pre-check** del tetto BR-16 | C-02 (persistenza), C-04 (ruolo dell'attore), C-32 (informativa) | C-04 risolve il ruolo a ogni richiesta e non scrive utenti; C-15 gestisce i destinatari di un compito, non l'anagrafica |
| C-32 Consent Flow | invio dell'informativa, accettazione, rifiuto, `consent_at`, **tetto BR-16** e relativi avvisi | C-10 (invio e avviso; C-03 raggiunto tramite C-10), C-02 (stato) | C-31 decide *chi* è autorizzato, C-32 decide *quando* l'autorizzazione diventa efficace (BR-18) |
| C-33 Authorization Notifier | avviso all'admin al primo contatto, pulsante Autorizza, anti-spam, mappa nome per il callback | C-10 (invio con tastiera), C-03 (bottoni) | C-33 **non** usa C-04, benché la spec 08 lo elenchi fra le dipendenze: chi decide se l'attore è admin è C-14 (P-A-11), e C-33 non deve risolvere ruoli per inviare un avviso | C-14 instrada, C-31 autorizza: nessuno dei due invia avvisi agli sconosciuti |
| C-10 Notification | invio con tastiera opzionale, split, retry | C-03 | C-33 decide *se* e *quando*, C-10 *come* |
| C-04 Role Guard | ruolo effettivo a ogni richiesta | C-02 | **invariato**: `pending` e `revoked` valgono `UNKNOWN` |
| C-14 Command Router | parsing, ordine di instradamento, risposte | C-31, C-32, C-33, C-17, C-23 | non scrive utenti né compone l'informativa |
| C-15 Task Manager | destinatari di un compito, solo `accepted` | C-02 | C-31 applica **la stessa politica** alle iscrizioni (P-A-13): un solo criterio, due punti di scrittura |
| C-20 Delivery / C-21 Run | destinatari e autorizzazione al lancio | C-02 | già filtrano gli `accepted`; la revoca ha effetto immediato senza modifiche |

**Un solo scrittore per stato.** Solo C-31 e C-32 scrivono `users.state` e `consent_at`; C-14 non
tocca il database e non compone messaggi di stato (li riceve in `UserResult.note`, sia da C-31 sia da
C-32).

**Un solo tetto, una sola costante.** `MAX_AUTHORIZED_USERS` vive in `user_state.py`, un modulo dati
che importa solo il tipo `User` da C-02 (nessun accesso a SQL, nessun import di C-31/C-32): C-31 e C-32 lo importano entrambi senza cicli (C-31 importa C-32 per
`send_consent`, C-32 non importa C-31). C-31 lo applica prima di creare/riaprire un `pending`, C-32
nell'istante in cui lo stato diventa `accepted`. Il criterio è identico:
`len(users.list("accepted"))`. Con cinque `accepted`: la creazione di un nuovo utente e la riapertura
`revoked → pending` sono rifiutate subito; il **reinvio** a un `pending` esistente resta possibile
(non aumenta gli `accepted`); l'accettazione è rifiutata con avviso all'admin.

**C-03 resta l'unico punto di invio.** C-32 non parla con il gateway: usa C-10, che a sua volta usa
C-03. La dipendenza C-03 elencata dalla spec 08 per C-32 è quindi soddisfatta per composizione, come
per C-33 (V-09).

**C-33 non duplica C-10.** C-33 decide *se* avvisare, compone testo e tastiera, e ricorda il nome
Telegram per il callback; l'invio, lo split e i retry restano di C-10/C-03 (D-05).

**Stessa politica sulle iscrizioni.** C-15 rifiuta destinatari non `accepted`; C-31 `subscribe`
applica la stessa regola (`invalid_state`) invece di creare righe che C-15 non creerebbe. C-31
`unsubscribe` accetta qualsiasi utente esistente, perché rimuovere un'iscrizione è sempre sicuro.

## Contratti (forma dei tipi)

```python
# user_state.py (contratto condiviso: importa solo il tipo `User` da storage.repositories,
# nessun accesso a SQL e nessun import di C-31/C-32)
MAX_AUTHORIZED_USERS = 5                # BR-16, unica definizione

@dataclass(frozen=True)
class UserView:
    user: User
    task_names: tuple[str, ...] = ()

@dataclass(frozen=True)
class UserResult:
    user: User
    changed: bool          # True se stato o iscrizioni sono cambiati su disco
    note: str              # messaggio pronto per il destinatario (admin o utente)
    notice_sent: bool = False   # True solo se questa chiamata ha inviato l'informativa

# C-31

class UserManager:
    def __init__(
        self,
        users: UserRepository,
        subscriptions: SubscriptionRepository,
        tasks: TaskRepository,
        consent: ConsentFlow,
        roles: RoleGuard,
    ) -> None: ...
    async def authorize(
        self, actor_id: int, telegram_id: int, *, username: str | None = None
    ) -> UserResult: ...
    def revoke(self, actor_id: int, telegram_id: int) -> UserResult: ...
    def subscribe(self, actor_id: int, user_id: int, task_id: int) -> UserResult: ...
    def unsubscribe(self, actor_id: int, user_id: int, task_id: int) -> UserResult: ...
    def list_users(self, actor_id: int) -> tuple[UserView, ...]: ...

# C-32
CONSENT_PREFIX = "consent"
PRIVACY_NOTICE = "..."                  # D1, verbatim

class ConsentFlow:
    def __init__(self, users: UserRepository, notifications: NotificationService, *, clock=None) -> None: ...
    async def send_consent(self, user_id: int) -> bool      # True se inviata
    async def accept(self, user_id: int, *, by_user_id: int) -> UserResult
    async def decline(self, user_id: int, *, by_user_id: int) -> UserResult

# C-33
AUTHORIZE_PREFIX = "authorize"
UNKNOWN_ALERT_WINDOW_S = 24 * 60 * 60

class AuthorizationNotifier:
    def __init__(self, notifications: NotificationService, *, clock=None, window_s: int = UNKNOWN_ALERT_WINDOW_S) -> None: ...
    async def notify_unknown(self, telegram_id: int, username: str | None) -> bool  # True se l'avviso è partito
    def username_for(self, telegram_id: int) -> str | None

# C-10 (estensione)
class NotificationService:
    async def notify(self, recipients, text: str, keyboard: Keyboard | None = None) -> None: ...
    async def alert_admin(self, text: str, keyboard: Keyboard | None = None) -> None: ...

# C-14 (estensione)
UNKNOWN_REFUSAL = "Non sei autorizzato a usare questo agente."
USER_ADMIN_REFUSAL = "Solo l'amministratore può gestire gli utenti."

# C-03 (estensione)
@dataclass(frozen=True)
class IncomingMessage:
    user_id: int
    chat_id: int
    text: str = ""
    callback_data: str | None = None
    username: str | None = None
```

- `UserAccessError(AgenteError)` con `reason` in `{"forbidden", "not_found", "invalid_state",
  "invalid_target", "limit"}`; C-14 traduce `reason` in un messaggio esplicito e non propaga
  l'eccezione al polling.
- `UserResult.note` è l'unico testo di stato: «Utente 123 in attesa: informativa inviata.», «Utente
  123 già autorizzato.», «Utente 123 revocato.», «Utente 123 era già revocato.», «Utente 123 iscritto
  al compito «news».», «Hai accettato l'informativa: ora sei autorizzato.» ecc. C-14 lo inoltra senza
  ricomporlo.
- `notice_sent` è `True` **solo** quando questa chiamata ha inviato con successo l'informativa:
  `False` per «già autorizzato», per invio fallito e per ogni operazione diversa da `authorize`. La
  `note` distingue i due casi di `False` (P-A-23).
- `authorize` è **idempotente**: un utente `accepted` resta `accepted`, non riceve una seconda
  informativa e `changed=False` con nota «già autorizzato».
- `accept`/`decline` esigono l'attore stesso (`by_user_id == user_id`) e lo stato `pending`.
- `subscribe`/`unsubscribe` esigono utente esistente e compito esistente; `subscribe` esige anche
  `accepted` (P-A-13).
- Il callback di autorizzazione porta l'id (`authorize:<telegram_id>`); il nome si legge da
  `AuthorizationNotifier.username_for`, alimentata all'invio dell'avviso. Il callback di consenso non
  porta id (`consent:accept`/`consent:decline`): l'attore è l'utente stesso e lo stato è riletto dal
  database.

## Deviazioni pre-dichiarate (numerazione stabile per il documento 08)

| # | Deviazione | Fonte modificata | Motivo |
|---|---|---|---|
| V-01 | `IncomingMessage` guadagna `username`; C-03 lo popola da `effective_user.username` | spec 01 C-03 | C-33 deve mostrare il «nome Telegram» (FR-007, AC-01); senza il dato l'avviso avrebbe solo l'id |
| V-02 | Nuovi comandi `/users`, `/subscribe`, `/unsubscribe` | spec 08 (nomina solo `/adduser` e `/removeuser`) | D4: iscrizioni ed elenco sono richiesti da FR-007 ma senza comando dichiarato |
| V-03 | Il testo privacy è una costante di modulo (`PRIVACY_NOTICE`) | spec 01 C-01 (nessuna chiave `privacy.*`) | D1/A-02: il testo è fornito dall'operatore; una chiave nuova estenderebbe C-01 senza mandato |
| V-04 | L'anti-spam di C-33 è un contatore in memoria con finestra di 24 h | spec 08 «aggregazione/rate limit» | D2: nessuna tabella nuova e nessuna migrazione; costo dichiarato: un riavvio può duplicare un avviso |
| V-05 | La revoca conserva record e iscrizioni | spec 08 domanda aperta «conservare vs eliminare» | D3: lo storico (item 09) resta leggibile per id e l'audit non perde l'anagrafica. **Non** rende rileggibile la chat del revocato: C-23 accetta solo `accepted` (gap dichiarato) |
| V-06 | Tetto rigido di 5 utenti `accepted` | BR-16 («dimensionamento previsto») e spec 08 NFR | D5: la spec 08 elenca «≤ 5 utenti autorizzati» fra i requisiti non funzionali |
| V-07 | C-31/C-32 verificano l'attore (ruolo admin, `by_user_id`) oltre al controllo di C-14 | spec 08 C-31 («operazione da non-admin → rifiuto») | difesa in profondità: BR-12 resta valido anche se un futuro chiamante salta C-14 |
| V-08 | Nessun timeout dell'informativa: `pending` resta `pending` | spec 08 flusso 4 e domanda aperta | D6: la spec non dichiara una soglia e introdurne una richiederebbe un job non previsto |
| V-09 | C-10 `notify`/`alert_admin` accettano una tastiera opzionale | spec 01 C-10 (non dichiarava il parametro) | C-33 deve inviare il pulsante **Autorizza**; estendere C-10 evita che C-33 parli direttamente con C-03 per i messaggi all'admin |
| V-10 | Nessun avviso automatico all'admin quando l'utente **non** accetta (silenzio) | spec 08 C-32 error handling e flusso 4; FR-007 alternate (`docs/input/functional-requirements.md:182`); BR-18 | D6: senza una scadenza non esiste l'istante in cui avvisare; i `pending` sono visibili in `/users` e l'admin li ha appena autorizzati. L'avviso resta al rifiuto esplicito |
| V-11 | Firme estese: C-31 con `actor_id` e `username`, C-32 con `by_user_id`, esito `UserResult` | spec 08 C-31/C-32 | il ruolo va verificato dentro il componente (V-07) e C-14 non può leggere il database per distinguere «creato» da «già autorizzato» |
| V-12 | Sconosciuto e revocato ricevono un rifiuto esplicito (`UNKNOWN_REFUSAL`) | BR-12 («sconosciuto/revocato: ignorato») | FR-007 flusso 1 e contesto: «riceve un rifiuto». «Ignorato» è interpretato come «nessun contenuto utile», non «silenzio totale» |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita leggendo il solo frontmatter
di `.opencode/agents/*.md`, `.opencode/commands/*.md`, `.opencode/skills/*/SKILL.md` e
`opencode.json`; discovery per ruolo, nessun asset legato per filename.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-09, D-11 (codice, test, aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione di codice Python, test o configurazione | Etichettati *"no specialized capability discovered"*; si procede su spec 08 + constitution + pattern esistenti in `src/agente/` |
| D-10 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** (Phase 2 struttura e Phase 4 validazione); il produttore resta il Conductor |
| D-10 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 08 e dai documenti 03–07; assunzione P-A-01 |

**Scartati (con motivo, solo asset realmente presenti in `.opencode/`):**

| Asset | Motivo dello scarto |
|---|---|
| `skills/sdd-guardrail` | Veto negativo dichiarato: rifiuta modifiche richieste da messaggio di chat non emesso da un comando. Questa esecuzione è `/SDD-implement`; il template Micro-Spec non serve |
| `skills/drawio` | Si attiva su richiesta esplicita di diagrammi/draw.io; qui i diagrammi sono Mermaid nel documento di architettura |
| `skills/document-to-markdown` | Nessun documento Word/PowerPoint/Excel/PDF da convertire |
| `skills/okf-open-knowledge-format`, `skills/wiki-semantic-search`, `skills/wiki-to-okf` | Nessun bundle OKF o wiki da creare, validare o interrogare |
| `skills/prompt-engineering` | Nessun template di prompt da compilare |
| `agents/planner`, `agents/specification`, `agents/prd` | Producono piani/spec/PRD: il piano è del Conductor, la spec esiste già |
| `agents/knowledge-searcher`, `agents/second-brain-keeper`, `agents/micro-spec-author` | Knowledge pipeline e Micro-Spec non fanno parte dei deliverable |
| `commands/*` | I comandi non si legano e non si invocano mai |

## Checkpoint di struttura (D-10) — Phase 2

Struttura applicabile proposta: **Metadata** (Spec · Voce roadmap · Piano · Constitution · Data ·
Struttura dichiarata + P-A-01) · Contesto e obiettivi · Componenti (C-31, C-32, C-33, estensioni
C-03/C-10/C-14, C-04/C-15/C-20/C-21 invariati, flowchart) · Componenti e capacità non disponibili
(rilettura chat dei revocati, timeout dell'informativa, avvisi di sistema) · Wiring di `AgentApp` ·
Riparto di responsabilità · Modello di dominio (stati e transizioni) · Modello dati (`users`,
`subscriptions`, nessuna migrazione, rimando all'ER di `01-agent-runtime`) · Testo dell'informativa
privacy (verbatim, D1) · Anti-spam (D2) · Flussi di dati: 8.1 contatto sconosciuto (flusso 1), 8.2
autorizzazione con pulsante e consenso (flusso 2), 8.3 `/adduser` (flusso 3), 8.4 rifiuto e silenzio
(flusso 4), 8.5 revoca (flusso 5), 8.6 iscrizione (flusso 6), tutte `sequenceDiagram` · Concorrenza e
ciclo di vita · Integrazioni · Sicurezza · Requisiti non funzionali (BR-16) · Rischi e assunzioni ·
Domande aperte chiuse · Fuori scope · Deviazioni (V-01…V-12) · Tracciabilità (AC-01…AC-05,
BR-12/BR-18). Per ogni componente: Responsabilità · Interfaccia · Input/Output · Dipendenze · Error
handling · Osservabilità · Sicurezza. Nessuna vista deployment e nessun ER nuovo: la spec 08 non li
dichiara e `users`/`subscriptions` sono già nella 01/02.

**Passate del 2026-11-01:** prima **NOT APPROVED** (9 major, 11 minor); seconda **NOT APPROVED**
(3 major, 11 minor); terza **NOT APPROVED** (2 major, 8 minor); quarta **APPROVED** con i minor sotto
recepiti. Remediation applicata in questa versione, in ordine di passata:

- **C-33 e tastiera:** C-10 `notify`/`alert_admin` estesi con `keyboard` (V-09, D-05, T5); la tastiera
  va sull'ultimo chunk (P-A-25).
- **`username` al callback:** mappa `AuthorizationNotifier.username_for` alimentata all'invio; dopo un
  riavvio il nome è assente e resta l'id (P-A-03, P-A-07).
- **Transizioni e integrità:** tabella completa, `revoked → pending` con `consent_at=None`,
  preservazione di `username`, niente `upsert` con oggetto vuoto (P-A-22); effetto di riattivazione
  delle iscrizioni dichiarato.
- **Esito «già autorizzato»:** nuovo `UserResult(user, changed, note, notice_sent)`; C-14 non legge il
  database e non compone testi; `notice_sent` con regola esplicita (P-A-23).
- **Iscrizioni:** `subscribe` richiede `accepted`, stessa politica di C-15 (P-A-13).
- **Silenzio:** V-10 esplicita la rinuncia all'avviso automatico, con le fonti FR-007/BR-18.
- **Struttura doc:** aggiunte «Componenti e capacità non disponibili» e «Wiring di AgentApp»; 6
  sequenze, una per flusso di spec 08.
- **Callback:** ordine prima del rifiuto `UNKNOWN`, comportamento per prefisso (P-A-11), registro
  esaustivo (P-A-19), `Action.kind` definiti (P-A-24).
- **Tetto BR-16:** costante unica in `consent.py`, applicata da C-31 (pre-check) e C-32 (accettazione);
  controllo «già autorizzato» prima del limite; `pending` non bloccato (P-A-08).
- **Admin:** `/adduser` e revoca sull'admin rifiutati, BR-16 non lo conta (P-A-10).
- **Invio e ordine:** rifiuto→avviso, entrambi best effort, finestra solo su avviso riuscito (P-A-20);
  informativa fallita gestita (P-A-12).
- **Documentazione e continuità:** note su spec 01/02/06, C-14 attribuito a spec 02, `test_role_guard`
  e `test_notifications` nei deliverable di test.

Dalla seconda passata: `accept` reso **async**; `UserView`/`UserResult`/`MAX_AUTHORIZED_USERS`
spostati in `user_state.py` (modulo dati, nessun ciclo C-31 ↔ C-32); P-A-11 riscritta con un codice
errore per caso (`invalid_state` per stato, `invalid_target` per attore sbagliato o target admin);
`UserResult.user` non opzionale e regola `notice_sent`/`changed` (P-A-23); rendering di `/users`
senza `(None)` (P-A-07); tastiera sull'ultimo chunk (P-A-25); riattivazione delle iscrizioni dopo
riautorizzazione dichiarata; V-10 estesa a FR-007/BR-18.

**Phase 4 (2026-11-01):** prima passata **NOT APPROVED** (major: «storico» citato senza item 09,
nota del reinvio corrotta da `replace`, dipendenze C-31/C-15 nel testo e nel flowchart, sequenze
8.2/8.3/8.5 senza C-10/C-03, `pending` non dichiarato, C-23 «solo accepted», «ER» improprio,
riferimento `effective_user` per i callback; minor: componenti riusati, `send_consent` async, rifiuto
«sempre inviato», riga Governance). Remediation applicata: nota composta per ramo e nuovo test sul
reinvio fallito; flowchart e dipendenze corrette; sequenze riscritte; comportamento del `pending`
dichiarato; terminologia e notazione allineate. Seconda passata **APPROVED** con minor recepiti
(edge `C31 → C15` nel flowchart, `tasks`/`subscriptions` nelle dipendenze, riga Governance, `authorize`
async, scrittura del `pending` nella sequenza 8.3, test dell'avviso da `pending`).

**Quarta passata (APPROVED):** `user_state.py` dichiarato come contratto che importa solo il tipo
`User`; C-33 senza C-04 motivato nel riparto; regola esplicita per `revoked → pending` al tetto;
tracciabilità di `changed`/`notice_sent` e dei testi di errore; numero del messaggio di limite derivato
dalla costante. La validazione definitiva resta la Phase 4 sull'artefatto reale.

## Assunzioni del piano (non dichiarate da spec 08)

> **P-A-01** Struttura del documento di architettura derivata da spec 08 e dai documenti 03–07, non
> da un template: in `docs/templates/` esistono solo `template.spec.md` e `template.constitution.md`.

> **P-A-02** Finestra anti-spam: 24 ore dall'ultimo avviso **riuscito** per lo stesso `telegram_id`,
> misurate con il clock iniettato; un avviso fallito non aggiorna la finestra. Il contatore è un
> dizionario in memoria, azzerato al riavvio.

> **P-A-03** Callback dei bottoni: `authorize:<telegram_id>` per l'avviso all'admin;
> `consent:accept` / `consent:decline` per l'informativa. Etichette: «Autorizza», «Accetto»,
> «Rifiuto». Il nome Telegram per l'autorizzazione da pulsante viene dalla mappa di C-33
> (`username_for`); se il processo è stato riavviato il nome è `None` e resta l'id.

> **P-A-04** Testo del rifiuto allo sconosciuto: `UNKNOWN_REFUSAL = "Non sei autorizzato a usare
> questo agente."` — nessuna informazione sul contenuto del messaggio ricevuto.

> **P-A-05** Testo dell'avviso all'admin: `Nuovo contatto: <@username | id> (id <telegram_id>).
> Premi «Autorizza» per inviargli l'informativa privacy.`

> **P-A-06** Testo dell'avviso di rifiuto: `L'utente <@username | id> (id <telegram_id>) ha rifiutato
> l'informativa privacy: resta non autorizzato.`

> **P-A-07** Formato di `/users`, una riga per utente: `• <telegram_id> (@<username>) — <stato> —
> compiti: <nomi o "nessuno">`; con `username` assente la riga è `• <telegram_id> — <stato> —
> compiti: …` (la parentesi sparisce, nessun `(None)` e nessun doppio separatore). `pending` e
> `revoked` compaiono con il proprio stato. Nessun utente → «Nessun utente.»

> **P-A-08** Tetto BR-16: `MAX_AUTHORIZED_USERS = 5` definita una sola volta in `user_state.py` e
> importata da C-31 e C-32, contati con `users.list("accepted")`. Ordine dei controlli in `authorize`:
> attore admin → `invalid_target` per l'admin → stato esistente (già `accepted` = nessuna informativa,
> nessun limite) → tetto. Un `pending` **non** è bloccato dal tetto: il reinvio dell'informativa non
> aumenta gli `accepted` e resta possibile anche con cinque autorizzati. Al superamento del tetto in
> creazione o in accettazione: `UserAccessError(reason="limit")`, che C-14 traduce in
> `f"Limite di {MAX_AUTHORIZED_USERS} utenti autorizzati raggiunto: revoca un utente prima di
> autorizzarne un altro."` (il numero è derivato dalla costante, non scritto a mano) e invia alla chat
> dell'attore (l'admin per `/adduser` e per il pulsante, l'utente per l'accettazione); in
> accettazione C-32 invia **anche** un avviso all'admin. La riapertura `revoked → pending` segue la
> stessa regola: rifiutata al tetto, perché porterebbe un sesto utente verso `accepted`.

> **P-A-09** `accept` registra `consent_at` in UTC ISO 8601 (secondi) e passa a `accepted`;
> `decline` passa a `revoked` senza toccare `consent_at`. Entrambi richiedono che lo stato corrente
> sia `pending` e che l'attore sia l'utente stesso.

> **P-A-10** L'amministratore non è un record `users`: `/adduser` e `authorize` con `admin_id` sono
> rifiutati (`invalid_target`), la revoca dell'admin è rifiutata, BR-16 non lo conta.

> **P-A-11** Comportamento per prefisso, indipendente dal ruolo risolto:
> - `authorize:<id>`: se l'attore non è `ADMIN` (compreso `UNKNOWN` o un `pending`) risponde
>   `USER_ADMIN_REFUSAL`; **nessun** avviso a C-33 e nessun rifiuto aggiuntivo allo sconosciuto.
> - `consent:accept|decline`: stato diverso da `pending` → `UserAccessError(reason="invalid_state")`;
>   attore diverso dal destinatario → `UserAccessError(reason="invalid_target")`. Il secondo ramo è
>   **difensivo**: il callback non porta id, quindi dal percorso bottoni `by_user_id == user_id` per
>   costruzione; resta per i chiamanti diretti e per i test. Nessun avviso a C-33.
> - `confirm:`/`approval:` invariati; un prefisso sconosciuto resta `ignored`.
> Un callback non-C-33 da un `UNKNOWN` non genera quindi mai un nuovo avviso all'admin.

> **P-A-12** Un invio dell'informativa fallito (`TelegramError`) è catturato **dentro** C-32:
> `send_consent` restituisce `False`, l'utente resta `pending`, C-32 invia un avviso all'admin con
> l'errore (best effort), C-31 compone `notice_sent=False` e una nota che lo dice; `/adduser` è
> ripetibile. L'eccezione non risale a C-14.

> **P-A-13** `subscribe` richiede utente esistente e `accepted` e compito esistente (`invalid_state`
> se `pending`/`revoked`), coerente con C-15 che rifiuta destinatari non `accepted`. `unsubscribe`
> richiede solo che utente e compito esistano: rimuovere un'iscrizione è sempre sicuro, anche per un
> revocato (D3 conserva le righe).

> **P-A-14** `HELP_TEXT` elenca i nuovi comandi nella sezione admin; è lo stesso testo per tutti i
> ruoli, come oggi.

> **P-A-15** La revoca non tocca `subscriptions`, `conversations`, `messages`, `executions`. C-20
> esclude gli iscritti non `accepted`, C-21 rifiuta `UNKNOWN`, C-23 non risponde: l'effetto è
> immediato senza pulizia dati. La chat di un revocato non è rileggibile da `/chat` (gap).

> **P-A-16** Nessuna migrazione: lo schema 001 contiene già `consent_at` e `subscriptions`.
> `Database.migrate()` resta invariato.

> **P-A-17** `AgentApp` guadagna tre campi (`user_manager`, `consent`, `notifier`) e li passa a C-14;
> nessun altro wiring cambia. Il gateway è lo stesso oggetto già condiviso.

> **P-A-18** L'ordine di C-14 diventa: ruolo → **callback** → comandi → linguaggio naturale. I
> callback precedono il rifiuto agli `UNKNOWN`, altrimenti un utente `pending` non potrebbe accettare
> l'informativa e l'admin non potrebbe premere «Autorizza». Un `UNKNOWN` senza callback riceve
> `UNKNOWN_REFUSAL` e genera l'avviso; `Action.kind` resta `"ignored"` per compatibilità con i test
> esistenti.

> **P-A-19** Il registro dei callback è esaustivo: `confirm:` (C-17), `approval:` (C-28),
> `authorize:` (C-33), `consent:` (C-32); un prefisso sconosciuto resta `ignored`.

> **P-A-20** Ordine delle due azioni su uno sconosciuto: prima il rifiuto all'utente, poi l'avviso
> all'admin. Entrambe sono best effort: un invio fallito è loggato e non impedisce l'altro; la finestra
> anti-spam avanza solo se l'avviso all'admin è riuscito (P-A-02).

> **P-A-21** Parsing di `/subscribe` e `/unsubscribe`: l'ultimo token deve essere un `telegram_id`
> numerico, tutto ciò che precede è il nome del compito (quindi i nomi con spazi funzionano). Senza
> id numerico → messaggio d'uso.

> **P-A-22** `authorize` non usa `UserRepository.upsert` con un oggetto costruito da zero: legge il
> record, compone il nuovo con `username` e `consent_at` preservati (o azzerati solo nella transizione
> `revoked → pending`) e solo dopo chiama `upsert`.

> **P-A-23** Regola di `notice_sent` e `changed`: `notice_sent=True` solo per un invio riuscito di
> questa chiamata; `False` per «già autorizzato» (nessun invio), per invio fallito (con avviso
> all'admin) e per le altre operazioni. `changed=True` solo se stato o iscrizioni cambiano su disco:
> `authorize` su un `pending` che riceve un reinvio ha `changed=False, notice_sent=True`; `revoke` su
> un già revocato ha `changed=False`; `subscribe` su un'iscrizione esistente ha `changed=False`. La
> `note` distingue i casi, quindi nessun chiamante deve dedurli dai flag.

> **P-A-24** `Action.kind` dei nuovi callback: `authorized` (autorizzazione da pulsante riuscita),
> `consent_accepted`, `consent_declined`, `rejected` (permesso negato), `error` (stato non ammesso o
> input non valido). I valori esistenti (`ignored`, `confirm_resolved`, `approval_resolved`, `error`,
> `rejected`) restano invariati.

> **P-A-25** In `NotificationService.notify` la tastiera va applicata all'**ultimo** chunk prodotto da
> `split_message`, così non viene duplicata su ogni pezzo; con un solo chunk coincide con l'unico
> messaggio (comportamento attuale di C-03).

> **P-A-26** Testi dei rifiuti di C-14 per `reason`, tutti in italiano e senza dettagli interni:
> `forbidden` → `USER_ADMIN_REFUSAL`; `not_found` → `Utente non trovato: <id>.`;
> `invalid_state` → `Operazione non ammessa per lo stato attuale dell'utente.`;
> `invalid_target` → `Operazione non ammessa su questo utente.`; `limit` → il testo di P-A-08. Un
> `reason` sconosciuto → messaggio generico `Operazione non riuscita.`.

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | C-32 Consent Flow | D-02 | `send_consent` invia il testo D1 con i bottoni Accetto/Rifiuto e restituisce l'esito; `accept` (**async**) porta a `accepted` con `consent_at` solo se `pending` e solo per l'utente stesso; `decline` porta a `revoked` e avvisa l'admin; tetto BR-16 all'accettazione con avviso e `UserResult`; log di invio/accettazione/rifiuto |
| T2 | C-31 User Manager | D-01, D-07 | transizioni della tabella rispettate (incluso `revoked → pending` con `consent_at=None` e preservazione di `username`); `authorize` idempotente su `accepted`; tetto dopo il controllo «già autorizzato»; admin rifiutato come target; `subscribe` solo `accepted`; `unsubscribe` su qualsiasi esistente; `list_users` con stato e compiti; ogni metodo rifiuta un attore non admin; `changed`/`notice_sent` secondo P-A-23; log di autorizzazione, revoca, iscrizione, disiscrizione |
| T3 | C-33 Authorization Notifier | D-03 | avviso con username/id e pulsante `authorize:<id>`; secondo contatto entro 24 h senza secondo avviso; nuovo avviso dopo la finestra; utenti diversi indipendenti; `username_for` disponibile per il callback; log degli avvisi |
| T4 | C-03 `username` | D-04 | `IncomingMessage.username` popolato da messaggi e callback; default `None`; nessun altro campo cambia |
| T5 | C-10 tastiera opzionale | D-05 | `alert_admin`/`notify` inoltrano `keyboard` a C-03 e la tastiera va sull'ultimo chunk (P-A-25); i chiamanti esistenti senza tastiera non cambiano comportamento |
| T6 | C-14 comandi e callback | D-06 | `/adduser`, `/removeuser`, `/users`, `/subscribe`, `/unsubscribe` con la sintassi dichiarata, solo admin; `authorize:`/`consent:` instradati prima del rifiuto `UNKNOWN`; sconosciuto/revocato ricevono `UNKNOWN_REFUSAL` e generano l'avviso; `Action.kind` invariato per i casi esistenti; `HELP_TEXT` aggiornato |
| T7 | Wiring | D-08 | `AgentApp.build` costruisce C-31/C-32/C-33 e li inietta in C-14; `AgentApp` espone i tre campi; nessun'altra dipendenza cambia |
| T8 | Test unit e di integrazione | D-09 | nuovi test C-31/C-32/C-33/C-10 e `username`; estensioni a `test_command_router.py` e `test_role_guard.py`; test esistenti su sconosciuto/revocato aggiornati al nuovo comportamento (rifiuto + avviso, `kind="ignored"`); `pytest` verde |
| T9 | AC-01…AC-05 end-to-end | D-09 | AC-01 sconosciuto → rifiuto + avviso con Autorizza; AC-02 pulsante + accettazione → risposta come autorizzato; AC-03 rifiuto → resta non autorizzato + avviso; AC-04 revoca → ignorato; AC-05 utente autorizzato `/adduser` → rifiuto |
| T10 | Documento architettura 08 | D-10 | sezioni obbligatorie presenti (incluse «Componenti e capacità non disponibili» e «Wiring di AgentApp»); Mermaid validi (1 flowchart, 6 sequenze 8.1–8.6); testo privacy verbatim; checkpoint Phase 2 e Phase 4 **APPROVED**; vista deployment e ER dichiarati assenti con motivo |
| T11 | Pubblicazione | D-11 | roadmap 08 `[x]`; spec 08 `Implemented (2026-11-01)` + note; delivery history con esito, gap e V-01…V-12; piano marcato eseguito; note di continuità su spec 01/02/06 |

## Dipendenze

- Item 01: C-02 (`users`, `subscriptions`, migrazione 001), C-03 (invio e bottoni), C-04 (ruoli e
  stati), C-10 (`alert_admin`), C-23 (`/chat`, invariato).
- Item 02: C-14 (comandi, callback, `HELP_TEXT`), C-15 (`find` per nome, destinatari solo `accepted`),
  C-17 (conferme; il registro callback convive con `confirm:`).
- Item 03/04: C-20 e C-21 filtrano già gli `accepted`; nessuna modifica.
- Item 05: C-23 usa `users.list("accepted")` per `/chat`; nessuna modifica (gap sui revocati).
- Item 06: C-28 usa `approval:`; il nuovo ordine dei callback non deve romperlo.
- **Item 09 (non consegnato):** lo storico userà `executions.requested_by`; conservare il record
  dell'utente revocato (D3) mantiene il dato leggibile.
- **Item 10/11 (non consegnati):** nessun avviso di sistema, nessuna gestione di riavvio qui.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Spam di avvisi da molti sconosciuti | finestra di 24 h per utente (D2); lo sconosciuto non ottiene mai contenuto utile |
| Doppio avviso dopo un riavvio | limite noto e dichiarato (V-04); il costo è un solo messaggio |
| Nome Telegram perso al riavvio fra avviso e pulsante | `authorize` accetta `username=None`; l'utente è creato con il solo id e l'admin vede l'id (P-A-03) |
| Sconosciuto che prova a premere «Autorizza» | il callback `authorize:` richiede `Role.ADMIN` (P-A-11) |
| Utente diverso che accetta al posto di un altro | `accept`/`decline` verificano `by_user_id == user_id` (P-A-09) |
| `authorize` su revocato che azzera dati utili | tabella transizioni + P-A-22: `consent_at` azzerato **solo** in `revoked → pending`, `username` preservato se assente |
| Sesto utente oltre BR-16 | tetto in C-31 e C-32, dopo il controllo «già autorizzato» (P-A-08) |
| Iscrizione di un non `accepted` che aggira C-15 | `subscribe` richiede `accepted` (P-A-13), stessa politica di C-15 |
| Informativa non recapitata | `TelegramError` catturato: resta `pending`, avviso all'admin, `/adduser` ripetibile (P-A-12) |
| Revoca che lascia accesso residuo | C-04 rilegge lo stato a ogni richiesta; C-20/C-21/C-23 escludono i non `accepted`; test AC-04 |
| Revocato non rileggibile da `/chat` | gap dichiarato (V-05/P-A-15); modifica di C-23 rimandata a una voce dedicata |
| Testo privacy modificato senza traccia | costante unica (V-03) riportata verbatim nel documento; una modifica è un cambio di codice + documento |
| Ordine dei callback che rompe `confirm:`/`approval:` | P-A-19: registro esaustivo, test di regressione su entrambi i prefissi |
| Regressione su item 02–07 | C-04, C-15, C-20, C-21, C-23 invariati; cambia solo l'atteso per sconosciuto/revocato (nuovo comportamento di spec 08) |
| Admin non raggiungibile | assunzione dichiarata dalla spec; nessun meccanismo alternativo inventato |

## Criteri di validazione (done della voce)

1. `PYTHONPATH=src:.deps python3 -m pytest` verde (inclusi i test di item 01–07).
2. AC-01: sconosciuto → rifiuto, nessuna risposta utile, avviso all'admin con nome/id e pulsante
   Autorizza.
3. AC-02: admin preme Autorizza → utente `pending` riceve l'informativa; accetta → `accepted` con
   `consent_at`; l'agente gli risponde come autorizzato.
4. AC-03: rifiuto dell'informativa → `revoked`, admin avvisato.
5. AC-04: utente revocato → trattato come sconosciuto (rifiuto, nessun contenuto utile).
6. AC-05: utente autorizzato `/adduser` → comando rifiutato, nessun utente creato.
7. Solo admin esegue `/adduser`, `/removeuser`, `/users`, `/subscribe`, `/unsubscribe`.
8. BR-16: sesto utente rifiutato con messaggio esplicito; un utente già autorizzato non incappa nel
   limite.
9. Anti-spam: un solo avviso per utente nella finestra di 24 h; il rifiuto all'utente resta sempre.
10. Transizioni: `pending → accepted|revoked`, `accepted → revoked`, `revoked → pending` con
    `consent_at=None`; nessun altro passaggio.
11. Nessuna migrazione; `users`/`subscriptions` invariate; `pending`/`revoked` senza timeout.
12. Documento D-10 conforme alla struttura dichiarata e approvato dal checkpoint Phase 4.
13. Catena di tracciabilità ricostruibile: voce roadmap 08 → spec 08 → binding → task → artefatti →
    validazione → pubblicazione.

## Tracciabilità attesa (compilata a Publish)

| Requisito / criterio | Test previsto |
|---|---|
| AC-01 sconosciuto: rifiuto + avviso con Autorizza | `tests/test_users_ac.py::test_ac01_unknown_is_refused_and_admin_is_alerted` |
| AC-02 autorizzazione + consenso | `tests/test_users_ac.py::test_ac02_authorized_user_accepts_and_uses_the_agent` |
| AC-03 rifiuto dell'informativa | `tests/test_users_ac.py::test_ac03_declined_consent_keeps_the_user_unauthorized` |
| AC-04 revoca immediata | `tests/test_users_ac.py::test_ac04_revoked_user_is_ignored` |
| AC-05 `/adduser` da non admin | `tests/test_users_ac.py::test_ac05_authorized_user_cannot_add_users` |
| BR-12 solo admin gestisce utenti | `tests/test_user_manager.py::test_non_admin_cannot_manage_users` |
| BR-18 nessun uso prima dell'accettazione | `tests/test_role_guard.py::test_pending_and_revoked_are_unknown`, `tests/test_consent.py::test_accept_enables_the_user` |
| BR-16 tetto 5 utenti | `tests/test_user_manager.py::test_sixth_user_is_refused`, `::test_already_authorized_user_does_not_hit_the_limit`, `tests/test_consent.py::test_acceptance_is_refused_when_the_limit_is_reached` |
| Transizioni e preservazione campi | `tests/test_user_manager.py::test_reauthorizing_a_revoked_user_clears_consent`, `::test_authorize_preserves_the_username` |
| Anti-spam 24 h | `tests/test_authorization_notifier.py::test_second_contact_within_the_window_is_suppressed`, `::test_alert_resumes_after_the_window` |
| Pulsante Autorizza | `tests/test_authorization_notifier.py::test_alert_has_authorize_button_and_username`, `tests/test_notifications.py::test_alert_admin_forwards_the_keyboard` |
| Callback autorizzazione | `tests/test_command_router.py::test_authorize_callback_starts_the_consent_flow` |
| Callback consenso | `tests/test_command_router.py::test_consent_callbacks_accept_and_decline` |
| Comandi di gestione | `tests/test_command_router.py::test_adduser_command`, `::test_removeuser_command`, `::test_users_command_lists_states`, `::test_subscribe_and_unsubscribe_commands`, `::test_subscribe_requires_an_accepted_user` |
| `username` in ingresso | `tests/test_telegram_gateway.py::test_username_is_carried_in_the_incoming_message` |
| Informativa non recapitata | `tests/test_consent.py::test_failed_notice_keeps_the_user_pending` |
| Registro callback invariato | `tests/test_command_router.py::test_callback_button_resolves_confirmation`, `tests/test_approval_ac.py` invariati |
| Revoca e iscrizioni conservate | `tests/test_user_manager.py::test_revoke_keeps_the_subscriptions` |
| Esiti `changed`/`notice_sent` | `tests/test_user_manager.py::test_resend_to_pending_is_not_a_change`, `::test_revoking_twice_is_not_a_change`, `::test_subscribing_twice_is_not_a_change`, `tests/test_consent.py::test_accept_reports_the_change` |
| Messaggi di errore di C-14 | `tests/test_command_router.py::test_user_errors_are_translated`, `::test_unknown_reason_has_a_generic_message` |
| Nessuna migrazione | `tests/test_storage.py` invariato; nessun file in `src/agente/storage/migrations/` aggiunto |

## Ordine di consegna

Codice-first: T1 → T2 → T3 → T4 → T5 → T6 → T7, poi test T8, poi AC end-to-end T9, poi documentazione
T10 (dipendente da codice stabile), infine pubblicazione T11. Il documento descrive il comportamento
validato.

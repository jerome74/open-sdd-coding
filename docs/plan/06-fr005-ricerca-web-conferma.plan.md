# Piano 06 — FR-005 Ricerca web e conferma

- **Voce roadmap:** `06 — FR-005 Ricerca web e conferma` (spuntata 2026-10-25; delivery history: voce 06)
- **Spec:** [06-fr005-ricerca-web-conferma.spec.md](../specs/06-fr005-ricerca-web-conferma.spec.md), Stato `Implemented (2026-10-25)`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack, `## Roadmap`
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`: C-01 con `search.provider`/`search.api_key` e `limits.approval_timeout_s`, C-02 con `approvals`, C-03 con callback, C-04, C-07, C-08, C-10 `request_approval`, migrazione 001), item 03 (`03-fr002-esecuzione-programmata`: C-09 con tool loop e BR-4, strumenti modificanti rifiutati in attesa del gate), item 05 (`05-fr004-domande-libere`: C-23 con tool loop read-only e `ChatToolContext`, C-03 `send`/`delete_message`, C-25, AC-06 lasciato come gap)
- **Dipendenze non consegnate:** item 07 (allowlist dei log), item 08 (utenti e privacy), item 10 (avvisi admin)
- **Data piano:** 2026-10-25
- **Stato piano:** approvato 2026-10-25; eseguito T1–T12 (delivery history: voce 06)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-26 Web Search Adapter: `Result(title, url, snippet)`, `search(query, k) -> list[Result]`, provider pluggable con registry, implementazione Tavily, retry BR-8, normalizzazione e formattazione per il modello, errori espliciti; log query/latenza/esito | codice | `src/agente/web_search.py` |
| D-02 | C-28 Approval Manager: crea la riga in `approvals`, invia i bottoni tramite C-10, `request` (asincrona, attende l'esito), `resolve(id, decision, by_user_id) -> bool`, `is_executable(approval) -> bool`, `recover_pending() -> int`, timeout BR-3, scarto al riavvio; log richieste, risoluzioni e tempi | codice | `src/agente/approvals.py`, `src/agente/notifications.py` (nuovo `send_approval`) |
| D-03 | C-27 Action Gate: `ToolAction`, `Gate`, `classify(action) -> Gate`, `execute_if_allowed(action, approval)`, orchestrazione `run(action)` con richiesta di conferma per le azioni modificanti; log classificazione e decisione | codice | `src/agente/gate.py` |
| D-04 | Estensione C-08: contratto degli handler con `approved` keyword-only; regola di registrazione che rifiuta sia `read_only=False, requires_approval=False` sia `read_only=True, requires_approval=True`; registrazione di `web_search` (sempre presente, schema `query` stringa obbligatoria e `k` intero opzionale con default 5 e clamp 1–10, errore esplicito se l'adapter manca); `default_registry(device, *, search=None)` | codice | `src/agente/tools.py` |
| D-05 | Estensione C-09: tutti gli strumenti esposti al modello, invocazione tramite C-27, rifiuto dell'approvazione come esito di tool (l'esecuzione prosegue), `SearchError` come esito di tool, BR-4 invariato | codice | `src/agente/execution.py` |
| D-06 | Estensione C-23: tutti gli strumenti esposti, invocazione tramite C-27 con `ChatToolContext`, `reason` e `requested_by` valorizzati, rifiuto come esito di tool, nessun `to_thread` attorno all'attesa di approvazione | codice | `src/agente/chat.py` |
| D-07 | Estensione C-14: callback `approval:<id>:approve|reject` risolti solo dall'admin; messaggi di esito; comandi e NL invariati | codice | `src/agente/command_router.py` |
| D-08 | Estensione C-02: `ApprovalRepository.reject_pending(resolved_at) -> int` per lo scarto al riavvio; `resolve` resta invariato | codice | `src/agente/storage/repositories.py` |
| D-09 | Config: `SearchConfig.provider` con default `tavily` **nel loader** (`_optional_str(..., "tavily")`), provider esplicitamente vuoto preservato; esempio aggiornato; `search.api_key` resta da `SEARCH_API_KEY` | configurazione | `src/agente/config.py`, `config/config.example.toml` |
| D-10 | Errori: `SearchError(AgenteError)` per provider assente, non supportato, non raggiungibile, credenziali rifiutate o risposta malformata | codice | `src/agente/errors.py` |
| D-11 | Wiring `AgentApp`: costruzione di C-26, C-28 (con C-04 e C-10), C-27; gate passato a C-09 e C-23; `web_search` registrato; `recover_pending` chiamato in `start()`; warning se il provider non è disponibile; nuovi campi dell'app | codice | `src/agente/app.py` |
| D-12 | Test della voce: unit C-26/C-28/C-27, AC-01…AC-03 end-to-end, chiusura di AC-06 di spec 05, estensioni a tool, execution, chat, router, config, storage, notifiche, bootstrap, confini, wiring | test | `tests/test_web_search.py`, `tests/test_approvals.py`, `tests/test_gate.py`, `tests/test_approval_ac.py`, `tests/test_tools.py` (nuovo), `tests/test_execution.py`, `tests/test_chat.py`, `tests/test_chat_ac.py`, `tests/test_command_router.py`, `tests/test_config.py`, `tests/test_storage.py`, `tests/test_notifications.py`, `tests/test_bootstrap.py`, `tests/test_device_gate.py`, `tests/test_boundaries.py`, `tests/conftest.py`, `tests/test_scheduled_ac.py` |
| D-13 | Documento architettura della feature con diagrammi Mermaid (1 flowchart, 4 sequenze, 1 stato, 1 ER `approvals`) | documentazione | `docs/architecture/06-fr005-ricerca-web-conferma.md` |
| D-14 | Pubblicazione: roadmap `[x]`, stato spec 06 `Implemented` + note, delivery history, piano allineato, note di continuità su spec 01/03/05 e architetture 01/03/04/05, constitution §Tech Stack aggiornata a Tavily e nota BR-17 estesa ad attesa di approvazione e retry della ricerca | documentazione | `docs/specs/constitution.md`, `docs/specs/06-fr005-ricerca-web-conferma.spec.md`, `docs/specs/01-agent-runtime.spec.md`, `docs/specs/03-fr002-esecuzione-programmata.spec.md`, `docs/specs/05-fr004-domande-libere.spec.md`, `docs/architecture/01-agent-runtime.md`, `docs/architecture/03-fr002-esecuzione-programmata.md`, `docs/architecture/04-fr003-lancio-manuale.md`, `docs/architecture/05-fr004-domande-libere.md`, `docs/delivery-history.md`, questo piano |

Nessuna tabella nuova: `approvals` esiste dalla migrazione 001. Nessuna nuova leva in `limits`:
`approval_timeout_s = 900` e i retry BR-8 esistono già. I valori interni introdotti (k predefinito,
timeout HTTP, limiti di troncamento) sono assunzioni P-A, non configurazione.

### Fuori scope di questa voce (dichiarato)

- **Allowlist dei log (spec 07):** `read_logs` resta rifiutato in chat e usa l'allowlist del compito
  nelle esecuzioni; nessuna policy nuova.
- **Installazione di pacchetti (A4):** nessuno strumento `install` è dichiarato da C-08. Il gate
  coprirebbe un eventuale strumento futuro purché registrato come modificante; **gap registrato**:
  A4 nomina l'installazione ma il catalogo strumenti non la include.
- **Gestione utenti, revoca e consenso privacy (spec 08):** il richiedente è solo un id; nessuna
  verifica del consenso viene aggiunta qui.
- **Avvisi di sistema su batteria/offline/credenziali (spec 10):** il gate invia solo la richiesta di
  conferma; nessun altro avviso.
- **UI di approvazione diversa dai bottoni:** nessun comando `/approva` o fallback testuale (D6).
- **Provider di ricerca multipli attivi contemporaneamente:** un solo provider per configurazione.

## Decisioni che sbloccano il piano

Chiuse dall'operatore il 2026-10-25. D1 e D2 rispondono alle domande tecniche aperte di spec 06;
D3–D5 risolvono conflitti con spec 03 e casi di ciclo di vita.

| # | Domanda aperta / conflitto | Decisione | Impatto |
|---|----------------------------|-----------|---------|
| D1 | Criterio di classificazione delle azioni modificanti (domanda aperta di spec 06) | **Whitelist dai metadati di C-08** (`read_only`, `requires_approval`) con **fail-safe**. Regola di registrazione: `read_only=False, requires_approval=False` è rifiutato (già oggi) e anche `read_only=True, requires_approval=True` è rifiutato perché contraddittorio; per un tool registrato, `modifying ⇔ not read_only`. Uno strumento sconosciuto **non viene eseguito** (rifiuto, non richiesta di conferma: non c'è nulla da autorizzare). Nessuna euristica sul testo | D-03, D-04, V-15; test di registrazione e di classificazione |
| D2 | Provider di ricerca di default (domanda aperta di spec 06; la constitution non ne dichiara uno) | **Tavily** (`provider = "tavily"`): POST `https://api.tavily.com/search`, un solo segreto `SEARCH_API_KEY`, risultati con titolo/URL/estratto. Adapter pluggable: il registry dei provider è il punto di estensione, non si implementano gli altri candidati | D-01, D-09, V-07, D-14; riga Tech Stack aggiornata |
| D3 | BR-3 (15 min) e BR-4 (10 min) non possono valere insieme per un'azione modificante dentro un'esecuzione; spec 03 dice che BR-4 racchiude anche i tool | **Vince BR-4.** L'attesa dell'approvazione resta dentro il timeout di esecuzione: al decimo minuto l'esecuzione è `interrotta`, la richiesta pendente è marcata `rejected` e nessuna azione nuova viene avviata. Un handler già partito può completare (P-A-19, limite dichiarato) | D-02, D-05, V-05, P-A-19; test di timeout con richiesta pendente |
| D4 | Una richiesta `pending` sopravvive al riavvio ma nessuno la attende più | **Scarto all'avvio:** C-28 marca `rejected` tutte le righe `pending` e registra il conteggio; un click su un bottone vecchio riceve «non valida o scaduta». Fail-safe, nessuna azione sopravvive al riavvio | D-02, D-08, D-11, V-06 |
| D5 | Comportamento con `search.provider` vuoto o non supportato | **`web_search` resta esposto** e restituisce un errore esplicito al modello («ricerca web non configurata»); warning all'avvio. Avvio non fatale: l'agente resta utilizzabile senza ricerca | D-01, D-04, V-04, V-11 |
| D6 | Risoluzione delle approvazioni | **Solo bottoni Approva/Rifiuta**, solo admin (A5). Il fallback testuale «sì»/«no» resta riservato alle conferme dei compiti (C-17); per le approvazioni non è dichiarato e non viene aggiunto | D-02, D-07, P-A-06 |

## Riparto di responsabilità tra componenti (anti-duplicazione)

| Componente spec 06 | Possiede | Delega a | Non duplica perché |
|---|---|---|---|
| C-26 Web Search Adapter | provider, HTTP, normalizzazione, retry BR-8, formattazione dei risultati | C-01 per configurazione, `httpx` per HTTP | C-08 possiede la registrazione del tool, non la ricerca; C-05 non fa rete |
| C-27 Action Gate | classificazione, attesa dell'approvazione, esecuzione condizionata, fail-safe | C-08 per il tool, C-28 per l'approvazione, C-07 (tramite l'handler) per l'effetto | C-09/C-23 non decidono se un'azione è permessa: chiedono sempre al gate |
| C-28 Approval Manager | creazione della riga, attesa, timeout, risoluzione, scarto al riavvio, verifica del ruolo e della scadenza | C-10 per l'invio (`send_approval`), C-02 per `approvals`, C-04 per il ruolo | C-10 formatta e invia; C-28 possiede l'intero ciclo di vita. Una sola riga, un solo messaggio |
| C-14 Command Router | riconoscimento del callback `approval:` e inoltro a C-28 | C-28 per la decisione | C-14 non cambia lo stato dell'approvazione né esegue azioni |
| C-08 Tool Registry | metadati `read_only`/`requires_approval`, handler, schemi | C-26 per `web_search`, C-07 per gli effetti | C-27 legge i metadati, non li duplica |
| C-09 / C-23 | loop di tool calling e contesto | C-27 per ogni invocazione | nessun filtro locale quando il gate è presente: il gate è l'unico punto di decisione |

**C-17 e C-28 restano separati.** C-17 conferma la creazione/modifica di un compito prima che sia
persistita (BR-1); C-28 autorizza un'azione sul telefono durante un'esecuzione o una chat (BR-2).
Hanno storage, chiavi dei bottoni (`confirm:`/`approval:`), timeout e destinatari diversi: unificarli
renderebbe una conferma di compito capace di sbloccare un'azione device, il che è esattamente ciò che
il gate deve impedire.

**C-28 non duplica C-10.** C-28 crea la riga in `approvals` (C-02), registra il waiter e chiede a
C-10 di inviare il messaggio con i bottoni tramite il nuovo `send_approval(approval)`. Il formato del
messaggio e il destinatario restano di C-10 (che già li implementa in `request_approval`, mantenuto
per compatibilità). La separazione permette a C-28 di marcare `rejected` anche se la cancellazione
arriva durante l'invio, quando la riga esiste già.

**C-27 non duplica C-08.** Il gate non conosce i nomi degli strumenti: legge `read_only` /
`requires_approval` dal registry e non mantiene una seconda whitelist. Aggiungere un tool modificante
non richiede modifiche a C-27.

## Contratto di C-27 (forma dei tipi)

```python
@dataclass(frozen=True)
class ToolAction:
    tool: str
    arguments: dict[str, Any]
    context: Any                 # Task in C-09, ChatToolContext in C-23
    reason: str                  # istruzioni del compito o domanda dell'utente
    requested_by: int | None     # P-A-05

@dataclass(frozen=True)
class Gate:
    kind: str                    # "read_only" | "modifying" | "unknown"
    tool: Tool | None
```

- `classify(action) -> Gate` è sincrona e non tocca la rete.
- `execute_if_allowed(action, approval)` è sincrona: esegue l'handler del tool e solleva `GateError`
  se l'azione è modificante senza un'approvazione già validata. Viene invocata da `run` dentro
  `asyncio.to_thread`, così il subprocess non blocca l'event loop.
- `run(action)` è asincrona: classifica; per un'azione read-only esegue; per una modificante chiede a
  C-28 e attende; per un'azione sconosciuta restituisce un rifiuto senza chiedere nulla. Restituisce
  il testo dell'esito (output del tool o rifiuto), così C-09/C-23 lo aggiungono come messaggio
  `role=tool`. **La rilettura di stato e scadenza avviene qui, nell'event loop**, prima dell'offload:
  `execute_if_allowed` riceve un `Approval` già validato e non apre SQLite dal thread.
- `run` intercetta `SearchError` e lo restituisce come esito di tool (V-12); gli altri errori
  propagano ai chiamanti, che mantengono il comportamento esistente.
- C-09/C-23 chiamano `await gate.run(...)` **direttamente**, senza avvolgere l'attesa in un thread:
  solo l'handler sincrono viene offloaded.

## Deviazioni pre-dichiarate (numerazione stabile per il documento 06)

| # | Deviazione | Fonte modificata | Motivo |
|---|---|---|---|
| V-01 | C-28 `request(...)` è asincrona e attende l'esito, restituendo l'`Approval` risolto | spec 06 C-28 | la spec dichiara `request(...) -> Approval` e l'output `approved`/`rejected`, ma non il contesto asincrono; l'attesa è il comportamento richiesto dal flusso 2 |
| V-02 | C-27 espone anche `run(action)` oltre a `classify`/`execute_if_allowed` | spec 06 C-27 | le due interfacce dichiarate non contengono la chiamata a C-28: l'orchestrazione è necessaria e resta dentro il gate, senza scorciatoie per i chiamanti |
| V-03 | Gli handler di C-08 accettano `approved` come keyword-only (default `False`) | spec 01 C-08 / spec 03 C-09 | senza un modo di propagare l'approvazione, C-27 non può eseguire via C-07 un'azione autorizzata; il default `False` mantiene il fail-safe per i chiamanti esistenti |
| V-04 | `web_search` è sempre registrato; provider assente o non supportato produce un errore di tool esplicito, non l'assenza dello strumento | spec 06 C-26 | D5: evita la degradazione silenziosa e rende l'errore visibile al modello e all'utente |
| V-05 | Nelle esecuzioni l'attesa dell'approvazione è dentro BR-4; al timeout la richiesta è `rejected` e non parte nessuna azione nuova | spec 06 BR-3 / spec 03 BR-4 | D3: BR-4 è un limite rigido sull'attesa e sull'avvio di nuove azioni (non su un handler già partito, P-A-19) e spec 03 lo estende ai tool; BR-3 resta integro in chat e in C-28 |
| V-06 | Le approvazioni `pending` sono marcate `rejected` all'avvio | spec 06 C-28 | D4: nessun waiter sopravvive al riavvio; lasciarle `pending` sarebbe uno stato ambiguo |
| V-07 | `SearchConfig.provider` ha default `tavily` nel loader; la constitution aggiorna la riga Tech Stack | **spec 01 C-01 e constitution §Tech Stack** | D2: la spec 06 chiede di scegliere il provider di default; la constitution diceva «nessun default dichiarato», non «vietato» |
| V-08 | C-09 non interrompe più l'esecuzione quando un'azione modificante è rifiutata: riceve un esito di tool e prosegue | **spec 03 D3 / architettura 03** | spec 06 flusso 2: «Rifiuta o timeout → azione non eseguita; l'agente prosegue senza o comunica l'impossibilità» |
| V-09 | C-14 gestisce i callback `approval:<id>:approve|reject` | spec 06 §Integrazioni | i bottoni esistono da item 01 ma nessun consumatore li risolveva; l'instradamento è indispensabile |
| V-10 | C-09 espone al modello anche gli schemi degli strumenti modificanti | **spec 03 (solo read-only)** | senza esporli il modello non può chiedere un'azione che richiede conferma; l'esecuzione passa comunque dal gate |
| V-11 | Provider non supportato o chiave assente non bloccano l'avvio: C-26 restituisce `SearchError` | spec 06 C-26 | D5: l'errore è esplicito al momento dell'uso e l'agente resta operativo per chat e compiti |
| V-12 | `SearchError` è sempre un esito di tool (chat **e** esecuzione); gli altri errori di tool restano fatali in esecuzione e testo in chat | spec 03 C-09 / spec 05 C-23 | un provider assente non deve far fallire un compito: l'agente comunica l'impossibilità e prosegue; gli errori device mantengono il comportamento validato |
| V-13 | `resolve(id, decision, by_user_id)` aggiunge il mittente all'interfaccia di C-28 | spec 06 C-28 | A5 impone che solo l'admin risolva; la verifica va fatta nel manager, non solo nel router |
| V-14 | In chat l'attesa dell'approvazione può durare fino a 15 minuti (BR-3) e i retry della ricerca possono estendere i 2 minuti di BR-17 | spec 06 BR-3 / BR-17 | BR-17 resta un obiettivo, C-25 copre l'attesa; la nota interpretativa in constitution viene estesa a **entrambe** le cause |
| V-15 | Uno strumento sconosciuto è rifiutato senza richiesta di conferma; i metadati contraddittori sono rifiutati alla registrazione | **spec 01 C-08** (registrazione) e spec 06 A-02 (unknown) | A-02 raccomanda la conferma «in dubbio»; per uno strumento ineseguibile o mal registrato la conferma non autorizzerebbe nulla: il rifiuto è più restrittivo e fail-safe. La regola di registrazione estende la policy di C-08, che già rifiutava il modificante senza approvazione |
| V-16 | C-28 espone `is_executable` e `recover_pending`; C-10 espone `send_approval` (con `request_approval` mantenuto per compatibilità) | spec 06 C-28 / spec 01 C-10 | servono a validare la scadenza nell'event loop, a scartare le richieste al riavvio e a separare creazione (C-28) da invio (C-10), evitando righe orfane se l'invio viene cancellato |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita leggendo il solo frontmatter
di `.opencode/agents/*.md`, `.opencode/commands/*.md`, `.opencode/skills/*/SKILL.md` e
`opencode.json`; discovery per ruolo, nessun asset legato per filename. Gli asset dichiarati dal
runtime ma non presenti in `.opencode/` non sono stati scansionati e non compaiono qui.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-12, D-14 (codice, config, test, aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione di codice Python, test o configurazione | Etichettati *"no specialized capability discovered"*; si procede su spec 06 + constitution + pattern esistenti in `src/agente/` |
| D-13 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** (Phase 2 struttura e Phase 4 validazione); il produttore resta il Conductor |
| D-13 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 06 e dai documenti 02–05; assunzione P-A-01 |

**Scartati (con motivo, solo asset realmente presenti in `.opencode/`):**

| Asset | Motivo dello scarto |
|---|---|
| `skills/sdd-guardrail` | Veto negativo dichiarato: rifiuta modifiche richieste da messaggio di chat non emesso da un comando. Questa esecuzione è `/SDD-implement`; il suo template Micro-Spec non serve |
| `skills/drawio` | Si attiva su richiesta esplicita di diagrammi/draw.io; qui i diagrammi sono Mermaid nel documento di architettura |
| `skills/document-to-markdown` | Nessun documento Word/PowerPoint/Excel/PDF da convertire |
| `skills/okf-open-knowledge-format`, `skills/wiki-semantic-search`, `skills/wiki-to-okf` | Nessun bundle OKF o wiki da creare, validare o interrogare |
| `skills/prompt-engineering` | Nessun template di prompt da compilare |
| `agents/planner`, `agents/specification`, `agents/prd` | Producono piani/spec/PRD: il piano è del Conductor, la spec esiste già |
| `agents/knowledge-searcher`, `agents/second-brain-keeper`, `agents/micro-spec-author` | Knowledge pipeline e Micro-Spec non fanno parte dei deliverable |
| `commands/*` | I comandi non si legano e non si invocano mai |

## Checkpoint di struttura (D-13) — Phase 2

Eseguito in modalità delegata su `sdd-governor` il 2026-10-25.

- **Prima passata:** **NOT APPROVED** — 10 MAJOR, 13 MINOR. Proprietà C-28/C-10 ambigua; regola di
  classificazione non verificabile; `P-A-03` vs `SearchError`; `D5` vs `V-12`; flusso 3 senza
  diagramma; `default_registry`/confini HTTP; pubblicazione incompleta (arch 04/05); deviazioni
  mancanti; BR-17 vs attesa; contratto C-27 sotto-specificato.
- **Seconda passata:** **NOT APPROVED** — chiusi i finding della prima; residui: enumerazione della
  regola di registrazione (D1), limite BR-4 su un handler già avviato in thread, `V-14` vs `D-14`,
  `recover_pending` non dichiarato, plumbing `reason`/`requested_by`, rilettura della scadenza fuori
  thread, cancellazione durante l'invio, schema `web_search`/`search=None`, warning all'avvio, riga
  BR-17, riferimenti incrociati, conteggio del checkpoint.
- **Remediation recepita in questa versione:** regola di registrazione esplicitata (entrambi i casi
  contraddittori rifiutati; `modifying ⇔ not read_only`); P-A-19 sul limite del thread; `V-14` e
  `D-14` allineati; `recover_pending`/`is_executable`/`send_approval` in D-02; `reason` e
  `requested_by` nel contratto di C-23/C-09; rilettura della scadenza in `run`; creazione della riga
  prima dell'invio e scarto su cancellazione; schema `web_search` e stub `search=None`; warning
  all'avvio in D-11/T9; riga BR-17; riferimenti corretti; conteggio corretto.
- **Terza passata:** **APPROVED** — nessun critical, nessun major; residui minor recepiti in questa
  versione (riferimento D1, fonte di V-15, regola di registrazione in D-04, cattura `AgenteError` in
  C-23, wrapper `request_approval`, firme di C-28, schema di `web_search`, owner del warning, invio
  parziale, wording di V-05).
- **Phase 4 (2026-10-25):** **APPROVED** — nessun critical, nessun major; finding minor recepiti
  nell'artefatto (timeout condiviso C-17/C-28, aggiornamento constitution in D-14, attribuzione del
  log di invio a C-10, `approved` keyword-only, troncamento del gate, ramo errore di invio, ramo
  riavvio, diagramma 7.4 con C-14, assenza di stato `executed`, fonte di V-15, wiring di
  `AgentApp`). La pubblicazione è avvenuta in Phase 5 (delivery history: voce 06).

Struttura applicabile dopo remediation: **Metadata** (Spec · Voce roadmap · Piano · Constitution ·
Data · Struttura dichiarata + blocco assunzione P-A-01) · Contesto e obiettivi · Componenti
C-26/C-27/C-28 + Estensioni di componenti esistenti + Componenti riusati (con flowchart) · Riparto ·
Modello di dominio · Modello dati (`approvals`, ER) · Macchina a stati dell'approvazione
(`stateDiagram-v2`) · Flussi 1–3 (quattro sequenze: read-only/ricerca web, modificante approvata,
rifiuto/timeout, richiesta da utente autorizzato) · Concorrenza e ciclo di vita · Integrazioni ·
Sicurezza · Requisiti non funzionali · Rischi e assunzioni · Domande aperte (chiuse da D1/D2) · Fuori
scope · Deviazioni (V-01…V-16) · Tracciabilità (AC-01…AC-03, AC-06 di spec 05 e BR). Per ogni
componente: Responsabilità · Interfaccia · Input/Output · Dipendenze · Error handling · Osservabilità ·
Sicurezza. Nessuna vista deployment (non dichiarata → gap registrato).

## Assunzioni del piano (non dichiarate da spec 06)

> **P-A-01** Struttura del documento di architettura derivata da spec 06 e dai documenti 02–05, non da
> un template: nel progetto esistono `docs/templates/template.spec.md` e `template.constitution.md`,
> **nessun template per documenti di architettura**.

> **P-A-02** `k` predefinito della ricerca: **5** risultati; il parametro è limitato a 1–10 lato
> adapter per non lasciare al modello un valore arbitrario. La spec dichiara `search(query, k)` ma non
> un default.

> **P-A-03** Formattazione dei risultati per il modello: una riga per risultato
> `1. <titolo> — <url>` seguita dall'estratto su una riga. Il troncamento dell'output a 20.000
> caratteri è applicato dal gate C-27 (unico punto di esecuzione in produzione) e resta in C-09/C-23
> per il percorso senza gate; C-26 non tronca. Una risposta HTTP valida senza risultati produce una
> lista vuota con log; una risposta malformata (JSON o forma inattesa) produce `SearchError`.

> **P-A-04** Testo della richiesta di approvazione: `action` = nome dello strumento + argomenti JSON
> compatti (troncati a 300 caratteri); `reason` = istruzioni del compito (esecuzione) o domanda
> dell'utente (chat), troncate a 300 caratteri. Il formato del messaggio resta quello di C-10.

> **P-A-05** `requested_by` dell'approvazione: id dell'utente in chat; `task.created_by` in
> esecuzione programmata; richiedente in lancio manuale. Il destinatario dei bottoni è sempre l'admin
> (A5).

> **P-A-06** Le approvazioni si risolvono solo con i bottoni; «sì»/«no» continuano a risolvere le
> conferme dei compiti (C-17). Un click di un non-admin riceve un rifiuto e la richiesta resta
> `pending` fino alla scadenza.

> **P-A-07** Scadenza verificata due volte: C-28 attende fino a `expires_at` e marca `rejected` al
> timeout; C-27 rilegge stato e scadenza in `run`, prima di eseguire, quindi un'approvazione arrivata
> tardi non sblocca nulla.

> **P-A-08** Timeout HTTP della ricerca: 30 secondi per tentativo, come C-05; retry BR-8 su errori di
> rete, 429 e 5xx. 401/403 producono `SearchError` senza retry.

> **P-A-09** La query di ricerca è registrata nei log come chiede la spec (osservabilità); la chiave
> del provider non compare mai. I risultati non vengono persistiti: vivono nel contesto del modello e
> nell'eventuale risposta.

> **P-A-10** In chat l'attesa dell'approvazione può durare fino a 15 minuti (V-14); D7 di item 05
> (nessun timeout rigido in C-23) resta valido. L'indicatore C-25 resta visibile durante l'attesa.

> **P-A-11** Un rifiuto dell'approvazione è un esito di tool, non un errore: C-09 e C-23 proseguono il
> loop e il modello decide se comunicare l'impossibilità. `SearchError` segue la stessa regola (V-12);
> gli altri errori di tool restano fatali in esecuzione e diventano testo per il modello in chat.

> **P-A-12** Lo scarto all'avvio è l'unico recupero delle approvazioni pendenti; nessun job periodico
> viene aggiunto. `expire_pending` resta disponibile per usi futuri ma non viene schedulato.

> **P-A-13** Nessuna migrazione: `approvals` ha già tutti i campi e i vincoli di stato dichiarati da
> spec 01/06. `reject_pending` è una query, non un cambio di schema.

> **P-A-14** Il provider è scelto dal registry `{"tavily": ...}`; un nome diverso è «non supportato»
> e produce `SearchError`. Aggiungere un provider significa aggiungere una voce al registry e il
> relativo client, senza toccare C-27 o C-09/C-23.

> **P-A-15** In assenza di gate (test o costruzione parziale) C-09 e C-23 mantengono il comportamento
> fail-safe di item 03/05: solo strumenti read-only esposti ed eseguiti. Il gate è obbligatorio nel
> wiring di produzione.

> **P-A-16** Dopo un click valido C-14 invia all'admin un messaggio breve di esito («Azione
> approvata.» / «Azione rifiutata.»); per un click non valido o scaduto invia «Richiesta non valida o
> scaduta.». Il messaggio con i bottoni non viene modificato né eliminato.

> **P-A-17** Il lock per `user_id` di C-23 resta attivo durante l'attesa dell'approvazione: i
> messaggi successivi dello stesso utente attendono, quelli degli altri utenti no. È la stessa
> serializzazione di item 05, estesa a un'attesa più lunga.

> **P-A-18** Il waiter di C-28 è per `approval_id`; una doppia risoluzione trova la riga non più
> `pending` e restituisce `False`; l'azione viene eseguita al massimo una volta perché `run` esegue
> solo dopo un esito `approved`.

> **P-A-19** BR-4 interrompe l'attesa dell'approvazione, non un handler già avviato in
> `asyncio.to_thread`: un'azione approvata pochi istanti prima del timeout può completare mentre
> l'esecuzione è registrata `interrotto`. Il caso è dichiarato nei rischi e nella §Concorrenza; non
> viene introdotto un kill del subprocess (non previsto dalle spec).
>
> **P-A-20** L'invio dei bottoni è best effort come ogni invio Telegram: se `send_approval` fallisce
> o viene cancellata dopo aver consegnato parte dei messaggi, la riga è marcata `rejected` e il
> messaggio parziale può restare nella chat dell'admin senza che l'azione sia eseguibile. È lo
> stesso comportamento di C-03/C-10 in caso di errore di invio.

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | C-26 Web Search Adapter | D-01, D-10 | `search("q", 5)` normalizza titolo/URL/estratto; provider Tavily con chiave nel corpo e URL corretti; retry su rete/429/5xx; `SearchError` per provider vuoto, non supportato, chiave assente, 401/403, risposta malformata; risposta valida senza risultati → `[]`; nessuna chiave nei log; warning di indisponibilità; test con client HTTP finto |
| T2 | C-02 `reject_pending` | D-08 | Marca `rejected` tutte le righe `pending` e restituisce il conteggio; nessuna modifica alle altre repository; test su DB con righe miste |
| T3 | C-28 Approval Manager e C-10 `send_approval` | D-02 | `request` crea la riga, registra il waiter, invia tramite C-10 e attende; `approved`/`rejected` risolvono; timeout → `rejected`; cancellazione durante invio o attesa → `rejected`; `resolve` da non-admin rifiutato (C-04); scadenza verificata; `recover_pending` scarta tutto all'avvio; doppia risoluzione rifiutata |
| T4 | C-27 Action Gate | D-03 | `classify` distingue read-only/modifying/unknown; `execute_if_allowed` esegue solo con approvazione validata e passa `approved=True`; `run` orchestra richiesta, rilettura della scadenza, esecuzione; strumento sconosciuto non esegue; handler in thread; log di classificazione e decisione |
| T5 | C-08 contratto e registrazione | D-04 | Handler accetta `approved` keyword-only; `default_registry(device, *, search=None)` registra `web_search` sempre con schema `query` (stringa, obbligatoria) e `k` (intero, opzionale, default 5, clamp 1–10); `search=None` produce `SearchError` esplicito; metadati contraddittori rifiutati; gli altri strumenti invariati |
| T6 | C-09 gate e strumenti modificanti | D-05 | Schemi di tutti gli strumenti al modello; invocazione via `await gate.run` con `reason=task.instructions` e `requested_by` da P-A-05; rifiuto → esito di tool e loop prosegue; `SearchError` → esito di tool; senza gate resta il comportamento fail-safe; BR-4 invariato |
| T7 | C-23 gate e strumenti modificanti | D-06 | Schemi di tutti gli strumenti; invocazione via `await gate.run` con `ChatToolContext`, `reason=domanda` e `requested_by=user_id`; rifiuto → esito di tool; C-23 cattura `AgenteError` attorno a `await gate.run` e lo restituisce al modello (V-12/P-A-11); nessun `to_thread` attorno all'attesa; senza gate resta il comportamento di item 05 |
| T8 | C-14 callback di approvazione | D-07 | `approval:<id>:approve|reject` risolto solo dall'admin; non-admin riceve rifiuto; id inesistente/scaduto → messaggio dedicato; `confirm:` invariato |
| T9 | Config e wiring | D-09, D-11 | Default `tavily` nel loader, provider vuoto preservato; C-26/C-28/C-27 costruiti una volta con C-04 e C-10; gate passato a C-09/C-23; `web_search` registrato; `recover_pending` chiamato in `start()`; l'unico warning di indisponibilità è emesso da C-26 alla costruzione; avvio e job esistenti invariati |
| T10 | Test AC-01…AC-03, AC-06 e unit | D-12 | AC-01 file non toccato prima dell'approvazione e cancellato dopo; AC-02 timeout → rifiuto e nessuna esecuzione; AC-03 ricerca web senza conferma; AC-06 di spec 05 chiuso con `web_search` e indicatore; fail-safe, riavvio, provider assente, cancellazione, doppia risoluzione, timeout BR-4; `pytest` verde |
| T11 | Documento architettura 06 | D-13 | Sezioni obbligatorie presenti; Mermaid validi (1 flowchart, 4 sequenze, 1 stato, 1 ER); checkpoint Phase 2 e Phase 4 **APPROVED**; nessuna vista deployment, gap registrato |
| T12 | Pubblicazione | D-14 | Roadmap 06 `[x]`; spec 06 `Implemented (2026-10-25)` + note; note di continuità su spec 01/03/05 e architetture 01/03/04/05; constitution §Tech Stack aggiornata a Tavily e nota BR-17 estesa ad attesa e retry; delivery history con esito, gap e V-01…V-16; piano marcato eseguito |

## Dipendenze

- Item 01: C-01 (`search`, `limits.approval_timeout_s`, `retry_*`), C-02 (`approvals`), C-03 (callback), C-04 (ruolo admin), C-07 (`approved`), C-08, C-10 (`request_approval`, `send_approval`).
- Item 03: C-09 con tool loop, BR-4 e consegna; il comportamento «modificante = errore» è superato da V-08/V-10.
- Item 05: C-23 con tool loop e `ChatToolContext`; AC-06 resta il riferimento per la ricerca web e viene chiuso da questa voce.
- **Item 07 (non consegnato):** allowlist dei log; `read_logs` resta invariato e rifiutato in chat.
- **Item 08 (non consegnato):** consenso privacy e gestione utenti; il gate non li verifica.
- **Item 10 (non consegnato):** avvisi di sistema; il gate invia solo la richiesta di conferma.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Classificazione errata di un'azione modificante come read-only | Whitelist C-08 + registrazione che rifiuta metadati contraddittori (D1); test dedicati |
| Un'azione modificante eseguita senza approvazione per un percorso alternativo | C-27 è l'unico punto di esecuzione quando è presente; C-09/C-23 non chiamano gli handler modificanti direttamente (P-A-15); test `test_modifying_handler_runs_only_after_approval` |
| Click di un non-admin o riuso di un bottone vecchio | C-14 verifica il ruolo, C-28 riverifica ruolo e stato `pending`; dopo il riavvio tutto è `rejected` (D4); dopo un timeout il click riceve «non valida o scaduta» |
| Richiesta approvata ma mai eseguita | Il waiter esiste solo nel processo che ha creato la richiesta; scarto all'avvio e `resolve` senza waiter → rifiuto |
| Doppia esecuzione della stessa azione | Un solo `await` per richiesta, una sola riga `pending` risolvibile; `run` esegue solo su `approved`; test di doppia risoluzione |
| Cancellazione dell'attesa o dell'invio | La riga è creata prima dell'invio; C-28 intercetta `CancelledError` e ogni errore di invio, marca `rejected` e rilancia; un invio parziale resta best effort (P-A-20); test dedicato |
| BR-3 (15 min) irraggiungibile dentro BR-4 (10 min) | Deviazione V-05 approvata (D3): il timeout di esecuzione interrompe e marca `rejected`; AC-02 verificato in chat e in C-28 |
| Handler già avviato che completa dopo l'interruzione BR-4 | P-A-19: limite dichiarato di `asyncio.to_thread`, documentato in §Concorrenza; nessun kill del subprocess inventato |
| BR-17 (30 s / 2 min) superato da approvazione o retry della ricerca | Deviazione V-14 approvata: BR-17 resta obiettivo, C-25 copre l'attesa; nota in constitution estesa a entrambe le cause |
| Admin offline → azioni modificanti bloccate | Accettato da spec 06 §Rischi; l'attesa termina con rifiuto e l'agente prosegue |
| Provider di ricerca assente o chiave mancante | Errore esplicito al modello e warning all'avvio (D5); nessuna eccezione fatale |
| Provider irraggiungibile o rate-limited | Retry BR-8 (3×1 min) e poi `SearchError` come esito di tool; nessun risultato inventato |
| Chiave del provider nei log | C-26 non registra mai l'header né la chiave; test sul contenuto dei log |
| Query dell'utente nei log | Registrata come chiede la spec (P-A-09); è l'unico dato personale aggiunto ai log, che restano locali |
| Attesa di 15 min in chat e lock per utente | P-A-10/P-A-17: l'indicatore copre l'attesa; solo i messaggi dello stesso utente sono serializzati |
| Regressione su item 03/05 | Fallback fail-safe senza gate (P-A-15), test esistenti mantenuti, note di continuità in spec 03/05 e architetture 04/05 |
| `send`/callback con id inesistente | C-14 risponde «non valida o scaduta» senza eccezioni |

## Criteri di validazione (done della voce)

1. `PYTHONPATH=src:.deps python3 -m pytest` verde (inclusi i test di confine e quelli di item 01–05).
2. AC-01: richiesta di `delete_file` → messaggio all'admin con Approva/Rifiuta, file intatto; dopo Approva il file è cancellato.
3. AC-02: nessuna risposta entro il timeout → `rejected`, azione non eseguita; in esecuzione il timeout BR-4 interrompe e scarta la richiesta.
4. AC-03: `web_search` eseguita senza alcuna richiesta di conferma e senza bottoni.
5. AC-06 di spec 05: chat con `web_search` → indicatore inviato e rimosso, risposta con i risultati.
6. Fail-safe: strumento sconosciuto e metadati contraddittori non eseguono nulla; provider assente → errore esplicito, nessuna eccezione fatale.
7. Riavvio: righe `pending` → `rejected`; un click successivo non esegue nulla.
8. Solo admin risolve: un utente autorizzato che preme il bottone riceve un rifiuto e la richiesta resta pendente.
9. Nessun segreto nei log; query registrata; risultati non persistiti.
10. Nessun import fuori dai confini (l'unica eccezione dichiarata è `httpx` in `llm.py` e `web_search.py`); type hints sulle interfacce pubbliche; errori espliciti; italiano di default.
11. Documento D-13 conforme alla struttura dichiarata e approvato dal checkpoint Phase 4.
12. Catena di tracciabilità ricostruibile: voce roadmap 06 → spec 06 → binding → task → artefatti → validazione → pubblicazione.

## Tracciabilità attesa (compilata a Publish)

| Requisito / criterio | Test previsto |
|---|---|
| AC-01 azione modificante con conferma | `tests/test_approval_ac.py::test_ac01_file_is_not_touched_before_approval`, `::test_ac01_file_is_deleted_after_approval` |
| AC-02 timeout 15 min | `tests/test_approval_ac.py::test_ac02_unanswered_request_is_rejected`, `tests/test_approvals.py::test_timeout_marks_the_request_rejected`, `tests/test_execution.py::test_pending_approval_is_rejected_when_execution_times_out` |
| AC-03 ricerca web senza conferma | `tests/test_approval_ac.py::test_ac03_web_search_needs_no_confirmation`, `tests/test_gate.py::test_read_only_action_is_executed_without_approval` |
| AC-06 di spec 05 chiuso | `tests/test_approval_ac.py::test_ac06_web_search_closes_the_gap` |
| BR-2 nessuna azione modificante senza admin | `tests/test_gate.py::test_modifying_action_requires_an_approval`, `::test_modifying_action_without_approval_is_refused`, `::test_unknown_tool_is_never_executed`, `::test_modifying_handler_runs_only_after_approval`, `tests/test_approvals.py::test_only_the_admin_can_resolve` |
| BR-3 scadenza = rifiuto | `tests/test_approvals.py::test_timeout_marks_the_request_rejected`, `tests/test_gate.py::test_expired_approval_is_not_executable` |
| BR-8 retry provider | `tests/test_web_search.py::test_retryable_error_is_retried`, `::test_permanent_error_is_not_retried` |
| BR-17 latenza-obiettivo (V-14) | `tests/test_chat_ac.py::test_ac05_simple_question_gets_an_answer_without_indicator`, `tests/test_approval_ac.py::test_ac06_web_search_closes_the_gap`; misura reale su dispositivo |
| A4 lettura/ricerca senza conferma | `tests/test_gate.py::test_read_only_action_is_executed_without_approval`, `tests/test_web_search.py::test_search_returns_normalized_results` |
| A5 conferma solo all'admin | `tests/test_approvals.py::test_request_goes_to_the_admin_with_buttons`, `::test_only_the_admin_can_resolve`, `tests/test_command_router.py::test_non_admin_cannot_resolve_an_approval` |
| Provider configurabile (A-01) | `tests/test_web_search.py::test_unconfigured_provider_raises_an_explicit_error`, `::test_unsupported_provider_raises_an_explicit_error`, `::test_unavailable_provider_logs_a_warning`, `tests/test_config.py::test_search_provider_defaults_to_tavily`, `::test_explicit_empty_provider_is_kept` |
| Fail-safe (A-02, V-15) | `tests/test_gate.py::test_unknown_tool_is_never_executed`, `::test_modifying_action_without_approval_is_refused`, `tests/test_tools.py::test_contradictory_metadata_is_rejected` |
| Riavvio senza azioni pendenti | `tests/test_approvals.py::test_recover_pending_rejects_everything`, `tests/test_storage.py::test_reject_pending_updates_only_pending_rows`, `tests/test_bootstrap.py::test_start_rejects_pending_approvals` |
| Esecuzione: rifiuto non fatale (V-08) | `tests/test_execution.py::test_rejected_approval_lets_the_execution_continue` |
| Esecuzione: SearchError non fatale (V-12) | `tests/test_execution.py::test_search_error_is_a_tool_outcome` |
| Cancellazione e doppia risoluzione | `tests/test_approvals.py::test_cancelled_wait_marks_rejected`, `::test_cancelled_send_marks_rejected`, `::test_double_resolution_is_rejected` |
| Chat: ricerca web e conferma | `tests/test_chat.py::test_web_search_tool_is_exposed_and_executed`, `::test_modifying_tool_goes_through_the_gate` |
| C-14 callback | `tests/test_command_router.py::test_admin_resolves_an_approval`, `::test_unknown_approval_is_reported` |
| C-10 `send_approval` | `tests/test_notifications.py::test_send_approval_uses_the_existing_format` |
| Schema e stub di `web_search` | `tests/test_tools.py::test_default_registry_registers_web_search`, `::test_web_search_schema_is_declared`, `::test_web_search_without_adapter_raises_an_explicit_error` |
| Osservabilità C-26/C-27/C-28 | `tests/test_web_search.py::test_query_and_latency_are_logged`, `tests/test_gate.py::test_gate_logs_the_decision`, `tests/test_approvals.py::test_resolution_is_logged` |
| Nessun segreto nei log | `tests/test_web_search.py::test_api_key_is_never_logged` |
| Confini di integrazione | `tests/test_boundaries.py` |

## Ordine di consegna

Codice-first: T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9, poi test T10, poi documentazione T11
(dipendente da codice stabile), infine pubblicazione T12. Il documento descrive il comportamento
validato.

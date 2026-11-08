# Piano 04 — FR-003 Lancio manuale

- **Voce roadmap:** `04 — FR-003 Lancio manuale` (non spuntata)
- **Spec:** [04-fr003-lancio-manuale.spec.md](../specs/04-fr003-lancio-manuale.spec.md), Stato `New`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack, `## Roadmap`
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`: C-02, C-03, C-04, C-09, C-10, C-11, schema `001_init.sql`), item 02 (`02-fr001-gestione-compiti`: C-14, C-15, C-16, C-17, ricerca per nome senza distinzione di maiuscole), item 03 (`03-fr002-esecuzione-programmata`: C-18, C-19, C-20, lock in C-09, timeout BR-4, delivery, esito `saltata`)
- **Data piano:** 2026-10-24
- **Stato piano:** approvato 2026-10-24; eseguito T1–T9 (delivery history: voce 04).

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-22 Task Lock: `acquire(task_id) -> bool`, `release(task_id)`, `held(task_id) -> bool`; serializzazione per compito, lock in memoria (D1) | codice | `src/agente/task_lock.py` |
| D-02 | C-21 Run Dispatcher: `run(requester_role, requester_id, task_name) -> ExecutionResult`; esistenza del compito, permesso/iscrizione, regola compito sospeso (D2), rifiuto se già in esecuzione | codice | `src/agente/run_dispatcher.py` |
| D-03 | Estensione C-09: usa C-22 al posto del dizionario di lock interno; propagazione del richiedente lungo la catena `execute(..., requester)` → `_work(task, requester)` → `_deliver(task, text, requested_by)`; `is_running()` delegato a C-22 | codice | `src/agente/execution.py` |
| D-04 | Estensione C-20: `deliver_text(task, text, *, requested_by=None)`; con `requested_by` i destinatari sono solo il richiedente (se admin o utente `accepted`), altrimenti politica invariata (admin + iscritti `accepted`); nota di continuità in doc 03 §13 V-03 | codice | `src/agente/delivery.py`, `docs/architecture/03-fr002-esecuzione-programmata.md` |
| D-05 | Estensione C-14: comando `/run <nome>`, forma NL `lancia <nome>` (D3), instradamento a C-21, messaggi di rifiuto/errore, aiuto aggiornato | codice | `src/agente/command_router.py` |
| D-06 | Wiring `AgentApp`: costruzione di C-22 e C-21, iniezione del lock in C-09 e del dispatcher in C-14; nessun nuovo job | codice | `src/agente/app.py` |
| D-07 | Test della voce: unit C-22 e C-21, AC-01…AC-03 end-to-end sul router, estensione C-09/C-20, aggiornamento fixture e test esistenti toccati dal nuovo costruttore di C-14 | test | `tests/test_task_lock.py`, `tests/test_run_dispatcher.py`, `tests/test_manual_run_ac.py`, `tests/conftest.py`, `tests/test_execution.py`, `tests/test_delivery.py`, `tests/test_command_router.py` |
| D-08 | Documento architettura della feature con diagrammi Mermaid (flowchart componenti, sequenze dei flussi 1–3 di spec 04, ER `executions` + `subscriptions`) | documentazione | `docs/architecture/04-fr003-lancio-manuale.md` |
| D-09 | Pubblicazione: roadmap `[x]`, stato spec `Implemented` + note, delivery history, piano allineato | documentazione | `docs/specs/constitution.md`, `docs/specs/04-fr003-lancio-manuale.spec.md`, `docs/delivery-history.md`, questo piano |

Nessuna migrazione e nessuna nuova leva di configurazione: spec 04 riusa `executions` (`trigger='manual'`,
`requested_by`) e `subscriptions`; non dichiara nuovi parametri.

### Fuori scope di questa voce (dichiarato)

- **Gate C-27/C-28 e azioni modificanti (spec 06):** il lancio manuale usa lo stesso motore di spec 03; gli strumenti modificanti restano rifiutati con esito `errore` finché il gate non esiste.
- **Avvisi all'admin (spec 10):** gli avvisi emessi sono quelli già di C-09 (timeout, errore); soglie e formati restano a spec 10. In particolare il messaggio di esito negativo al richiedente è un'assunzione di questa voce (P-A-06), non un requisito dichiarato.
- **Query dello storico (spec 09):** l'esecuzione manuale è registrata e interrogabile con i filtri esistenti; la presentazione per ruolo è di spec 09.
- **Gestione utenti e iscrizioni (spec 08):** C-21 legge iscrizioni e stato utente, non li modifica; nessun comando di autorizzazione/iscrizione.
- **Chat e domande libere (spec 05), riavvio/liveness (spec 11).**
- **Lock persistente:** escluso per decisione D1 (lock in memoria), con il rischio residuo dichiarato.

## Decisioni che sbloccano il piano

Domande chiuse dall'operatore il 2026-10-24 (le prime due sono le «Domande tecniche aperte» di spec 04).

| # | Domanda aperta / conflitto | Decisione | Impatto |
|---|----------------------------|-----------|---------|
| D1 | «Il lock deve sopravvivere a un riavvio del processo?» (spec 04) | **Lock solo in memoria.** Il processo è unico: un riavvio termina l'esecuzione in corso, quindi non esiste stato da serializzare. Nessuna tabella o chiave di lock, nessuna politica di lock scaduto | D-01; C-22 senza dipendenza da C-02 per lo stato del lock; rischio residuo in §Rischi |
| D2 | «Comportamento quando il compito esiste ma è `sospeso`» (spec 04) | **Rifiuto per gli utenti autorizzati, esecuzione consentita all'admin.** Il compito resta `paused` (nessuna transizione implicita); lo stato continua a bloccare solo le occorrenze programmate | D-02; messaggi in P-A-02; test in D-07 |
| D3 | Vocabolario NL: la spec cita solo «lancia news» | **Solo `lancia <nome>`** oltre a `/run <nome>`. Nessun sinonimo inventato («esegui», «avvia» restano fuori) | D-05; assunzione P-A-03 |

## Riparto di responsabilità tra componenti (anti-duplicazione)

| Componente spec 04 | Possiede | Delega a | Non duplica perché |
|---|---|---|---|
| C-21 Run Dispatcher | Riconoscimento della richiesta di lancio, esistenza del compito, permesso/iscrizione, regola del compito sospeso, composizione dei messaggi di rifiuto | C-09 per l'esecuzione, C-02 per iscrizioni/stato utente, C-15 per la ricerca per nome, C-14 per l'invio dei messaggi | C-14 riconosce il comando/NL e inoltra; C-21 decide se il lancio è ammesso e lo esegue |
| C-22 Task Lock | Serializzazione per `task_id`: acquisizione non bloccante, rilascio, interrogazione | — | Il lock è unico per tutti gli inneschi (`scheduled`, `manual`, `recovery`): non esistono due meccanismi di esclusione |
| C-09 Execution Engine | Contesto, loop LLM/tool, timeout, esito, chiamata a C-20, acquisizione/rilascio del lock tramite C-22 | C-05, C-08, C-11, C-20 | Il lock non è reimplementato in C-09: la politica sta in C-22, l'uso è nel punto unico di esecuzione |
| C-20 Delivery Service | Destinatari del risultato: programmato = admin + iscritti `accepted`; manuale = solo il richiedente (se admin o `accepted`) | C-10 per l'invio | C-09 non decide i destinatari; C-21 non invia il risultato |
| C-14 Command Router | Riconoscimento di `/run` e di `lancia <nome>`, inoltro a C-21, invio delle risposte di rifiuto e dell'esito negativo | C-21 | Il router non verifica iscrizioni né esegue compiti |

**Dipendenze dichiarate da spec 04 per C-21 — C-04 e C-11.** La spec elenca `C-14, C-04, C-02, C-09, C-11`.
Nel riparto sopra C-04 non compare come chiamata diretta: il ruolo è già risolto da C-14 all'ingresso del
messaggio e C-21 lo riceve come parametro (`requester_role`), senza ri-risolvere l'identità. C-11 non è
chiamato da C-21: la registrazione dell'esecuzione avviene dentro C-09 (inizio e fine), come già in spec 03;
C-21 non scrive una seconda riga. Entrambe sono deleghe dichiarate, non dipendenze perse; la ri-verifica
dello stato `accepted` usa C-02 (P-A-05).

**Punto unico del lock.** Spec 01 assegna il lock a C-09; il flusso 1 di spec 04 mostra l'acquisizione in
C-21. Le due letture convivono così: C-22 è il componente di lock, **C-09 è l'unico punto che lo
acquisisce** (vale per tutti e tre gli inneschi), C-21 traduce `LockHeldError` nel rifiuto di AC-03.
Deviazione dichiarata V-02 in architettura.

## Deviazioni pre-dichiarate (numerazione stabile per il documento 04)

| # | Deviazione dalla lettera della spec | Motivo |
|---|---|---|
| V-01 | `RunDispatcher.run(...)` è `async` e restituisce `ExecutionResult` | C-09 è asincrono; la spec non dichiara il contesto di esecuzione |
| V-02 | Il lock è acquisito da C-09 (tramite C-22), non da C-21 come nel flusso 1 | un solo punto di acquisizione per tutti gli inneschi; evita doppio lock e lascia AC-03 a C-21 come rifiuto |
| V-03 | C-20 accetta `requested_by` oltre a `(task, text)` | serve il destinatario unico del risultato manuale; l'interfaccia programmata resta invariata |
| V-04 | C-22 espone anche `held(task_id)` oltre a `acquire`/`release` | serve a `is_running()` di C-09 e ai test; nessuna nuova responsabilità |
| V-05 | C-22 non usa C-02 e non persiste lo stato del lock | decisione D1: processo unico, riavvio = nessuna esecuzione in corso |
| V-06 | Il riconoscimento di `/run` e `lancia <nome>` sta in C-14, non in C-21 | C-14 è già il punto unico di parsing di comandi e NL; C-21 riceve il nome già estratto |
| V-07 | L'admin può lanciare un compito `paused` (D2), deroga a spec 02 AC-04 | la domanda è aperta in spec 04 ed è stata chiusa dall'operatore; lo stato continua a bloccare le occorrenze programmate. Spec 02 non è emendata: la deroga vale solo per il lancio manuale dell'admin ed è registrata qui e in architettura |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita leggendo il solo frontmatter di
`.opencode/{agents,commands,skills}` e `opencode.json`; discovery per ruolo, nessun asset legato per filename.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-07, D-09 (codice, test, aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione di codice Python o test | Etichettati *"no specialized capability discovered"*; si procede su spec 04 + constitution + pattern esistenti in `src/agente/` |
| D-08 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** (Phase 2 struttura e Phase 4 validazione); il produttore resta il Conductor |
| D-08 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 04 e dai documenti 02/03; assunzione P-A-07 |

**Scartati (con motivo):**

| Asset | Motivo dello scarto |
|---|---|
| `skills/sdd-guardrail` | Veto negativo dichiarato: rifiuta modifiche richieste da messaggio di chat non emesso da un comando. Questa esecuzione è `/SDD-implement`; il suo template Micro-Spec non serve |
| `skills/drawio` | Si attiva su richiesta esplicita di diagrammi/draw.io; qui i diagrammi sono Mermaid nel documento di architettura |
| `skills/document-to-markdown`, `skills/okf-*`, `skills/wiki-*`, `skills/prompt-engineering` | Nessun documento sorgente da convertire, nessun bundle OKF/wiki, nessun template di prompt |
| `agents/planner`, `agents/specification`, `agents/prd` | Producono piani/spec/PRD: il piano è del Conductor, la spec esiste già |
| `agents/knowledge-searcher`, `agents/second-brain-keeper`, `agents/micro-spec-author` | Knowledge pipeline e Micro-Spec non fanno parte dei deliverable |
| `commands/*` | I comandi non si legano e non si invocano mai |

**Checkpoint di struttura (D-08) — Phase 2, modalità delegata:** eseguito il 2026-10-24 su `sdd-governor`
con esito **NOT APPROVED** (6 MAJOR, 9 MINOR) sullo schema proposto. Remediation recepita in questo piano:

- blocco metadata di testata (Spec, Voce roadmap, Piano, Constitution, Data, Struttura dichiarata) come nei documenti 02/03;
- sezione §Tracciabilità che mappa esplicitamente AC-01, AC-02, AC-03 e BR-4/BR-8/BR-12;
- dipendenze dichiarate da spec 04 per C-21: C-04 (ruolo già risolto da C-14) e C-11 (registrazione in C-09) contabilizzate in §Riparto;
- deviazioni pre-dichiarate con ID stabili V-01…V-07, incluse firma `async` di C-21, parametro `requested_by` di C-20 (con nota in doc 03 §13 V-03), `held()` di C-22, lock in-memory senza C-02, riconoscimento in C-14 e deroga D2 a spec 02 AC-04;
- catena di propagazione `requester` esplicitata in D-03/D-04;
- precedenza di `lancia <nome>` prima del ramo di creazione/rifiuto non-admin fissata in T5;
- test nominati aggiunti: timeout su `trigger='manual'`, revoca `accepted` al lancio, lancio manuale con lock detenuto da esecuzione programmata;
- correzione P-A-07: i template esistono per spec e constitution, non per documenti di architettura;
- sequenza del flusso 1 con acquisizione/rilascio in C-09 (V-02), altrimenti il documento contraddirebbe sé stesso.

Struttura applicabile dopo remediation: Metadata · Contesto e obiettivi · Componenti C-21/C-22 su C-01…C-20
(con flowchart) · Riparto · Modello di dominio · Modello dati · Flussi 1–3 (sequenze) · Integrazioni ·
Sicurezza · Requisiti non funzionali · Rischi e assunzioni · Domande aperte (chiuse da D1/D2) · Fuori scope ·
Deviazioni (V-01…V-07) · Tracciabilità (AC-01…AC-03 e BR). Diagrammi richiesti: 1 flowchart componenti,
3 `sequenceDiagram` (flussi 1–3), 1 `erDiagram` su `executions`/`subscriptions`; nessuna vista deployment
(non dichiarata → gap registrato). La validazione di struttura definitiva è la Phase 4 sull'artefatto reale:
la produzione resta subordinata all'approvazione del piano.

## Assunzioni del piano (non dichiarate da spec 04)

> **P-A-01** I rifiuti di C-21 sono eccezioni applicative tipizzate (`RunRefused` con `reason` e messaggio
> utente) perché l'interfaccia dichiarata `run(...) -> ExecutionResult` copre il solo percorso di successo.
> C-14 cattura l'eccezione e invia il messaggio.
>
> **P-A-02** Testi dei messaggi (la spec li dichiara solo come comportamento): compito inesistente →
> «Compito non trovato: «<nome>».» seguito, se non vuoto, dall'elenco dei compiti che il richiedente può
> lanciare; non iscritto → «Non sei iscritto al compito «<nome>»: lancio rifiutato.»; sospeso e richiedente
> non admin → «Il compito «<nome>» è sospeso: chiedi all'amministratore di riattivarlo.»; già in esecuzione
> → «Il compito «<nome>» è già in esecuzione: lancio rifiutato.»; nome assente → «Indica il compito da
> lanciare: /run <nome>.».
>
> **P-A-03** Il verbo NL riconosciuto è solo `lancia` (D3); il confronto è case-insensitive e accetta
> articoli e virgolette come le altre forme NL di spec 02 (`_clean_name`). La ricerca del compito usa
> `TaskManager.find()`, già senza distinzione di maiuscole (spec 02 D3).
>
> **P-A-04** L'elenco dei compiti disponibili per il richiedente è quello di `TaskManager.list(role, id)`
> (admin: tutti; autorizzato: quelli a cui è iscritto) e viene incluso nel messaggio di «compito non
> trovato» (la spec lo dichiara «possibile»): solo i nomi, senza stato né orario.
>
> **P-A-05** L'iscrizione è verificata su `subscriptions` al momento del lancio, non alla creazione del
> compito; per il ruolo `AUTHORIZED` si ri-verifica che l'utente sia ancora `accepted` (BR-12), anche se
> C-04 lo ha già risolto per il messaggio corrente.
>
> **P-A-06** Se l'esecuzione manuale termina con esito `errore` o `interrotto`, il richiedente riceve una
> riga di stato («Esecuzione non riuscita: …» / «Esecuzione interrotta: …») inviata da C-14; il risultato
> testuale resta solo al richiedente e l'avviso di errore all'admin resta quello di C-09. La spec non
> dichiara questo messaggio: assume valore di cortesia minima, non di nuovo requisito.
>
> **P-A-07** Struttura del documento di architettura derivata da spec 04 e dai documenti 02/03, non da un
> template: nel progetto esistono `docs/templates/template.spec.md` e `template.constitution.md`, **nessun
> template per documenti di architettura**.
>
> **P-A-08** C-21 non controlla lo stato della rete: spec 04 non lo dichiara per il lancio manuale; un
> guasto di rete produce l'esito `errore` già previsto da C-05/C-09.
>
> **P-A-09** Il lock di C-22 è un insieme di `task_id` in memoria, protetto dall'assenza di `await` tra
> controllo e inserimento (event loop singolo): acquisizione non bloccante, rilascio idempotente.
>
> **P-A-10** Un compito sospeso lanciato dall'admin non cambia stato e non viene ri-registrato: nessun job
> viene creato, l'esecuzione è una tantum (`trigger='manual'`).

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | C-22 Task Lock | D-01 | `acquire` restituisce `True` la prima volta e `False` se già detenuto; `release` idempotente; `held` coerente; log acquisizione/rilascio con `task_id` |
| T2 | C-09 su C-22 | D-03 | `execute` acquisisce il lock, lo rilascia in `finally` anche su errore/timeout; secondo avvio concorrente → `LockHeldError` senza seconda riga in `executions`; `is_running()` delega a C-22 |
| T3 | C-20 destinatario manuale | D-04 | `requested_by` valorizzato → invio al solo richiedente se admin o `accepted`; richiedente non autorizzato → nessun invio e `DeliveryError`; percorso programmato invariato |
| T4 | C-21 Run Dispatcher | D-02 | Admin: qualsiasi compito; autorizzato: solo iscritti; compito inesistente → rifiuto con elenco; sospeso → admin esegue, autorizzato rifiutato; già in esecuzione → rifiuto; esecuzione con `trigger='manual'` e `requested_by` = richiedente; log con `requester_id` e `task_id` |
| T5 | C-14 `/run` e `lancia` | D-05 | `/run <nome>` e `lancia <nome>` instradati a C-21 **prima** del ramo di creazione e del rifiuto per ruolo non admin (altrimenti «lancia news» dell'admin diventerebbe una bozza di nuovo compito); rifiuti ed esiti negativi inviati al richiedente; `/run` senza nome → messaggio d'uso; aiuto aggiornato; creazione/modifica invariata per l'admin, rifiutata per gli altri |
| T6 | Wiring `AgentApp` | D-06 | C-22 e C-21 costruiti una volta e condivisi con C-09 e C-14; avvio, job e sequenza di recupero invariati |
| T7 | Test AC-01…AC-03 e unit | D-07 | AC-01: utente iscritto, `/run news` → risultato solo a lui; AC-02: utente non iscritto, `/run log` → rifiuto, nessuna esecuzione, nessuna riga in `executions`; AC-03: lancio manuale con lock detenuto da un'esecuzione **programmata** → rifiuto senza seconda esecuzione (più il caso manuale+manuale a livello engine); timeout BR-4 verificato su `trigger='manual'`; revoca `accepted` dopo la risoluzione del ruolo → rifiuto; `pytest` verde |
| T8 | Documento architettura 04 | D-08 | Sezioni obbligatorie presenti; Mermaid validi (componenti, 3 sequenze, ER); checkpoint di struttura Phase 2 e Phase 4 **APPROVED**; nessuna vista deployment, gap registrato |
| T9 | Pubblicazione | D-09 | Roadmap 04 `[x]`; spec 04 `Implemented (2026-10-24)` + note (D1/D2/D3); delivery history con esito e gap; piano marcato eseguito |

## Dipendenze

- Item 01: C-02 repository, C-03 gateway, C-04 ruoli, C-09 motore, C-10 invio, C-11 storico.
- Item 02: C-15 ricerca per nome senza distinzione di maiuscole, C-14 router e forme NL, C-17 conferme (non usate dal lancio: nessuna modifica persistente).
- Item 03: C-09 con timeout BR-4 e consegna, C-20 destinatari, esito `errore`/`interrotto` e avviso admin, migrazione 003.
- C-21 dipende dall'iscrizione (`subscriptions`) che oggi è scritta da C-15 e letta da C-20; spec 08 la estenderà senza cambiarne il significato.
- Nessuna dipendenza bloccante da spec 05–11 per i deliverable di questa voce.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Lancio manuale durante un'esecuzione programmata (o viceversa) | C-22 unico per tutti gli inneschi; secondo innesco rifiutato con `LockHeldError` → rifiuto AC-03, nessuna seconda esecuzione |
| Lock in memoria perso al riavvio (D1) | Un riavvio termina l'esecuzione in corso: non esistono lock orfani. Rischio residuo: nessun coordinamento con un secondo processo, che il Tech Stack esclude |
| Risultato manuale inviato per errore ai destinatari del compito | C-20 applica la politica: con `requested_by` i destinatari sono solo il richiedente; test dedicato in T3/T7 |
| Utente revocato dopo la risoluzione del ruolo | Ri-verifica dello stato `accepted` al momento del lancio (P-A-05) |
| Compito sospeso eseguito da un utente | Regola D2 applicata in C-21 prima dell'esecuzione, non delegata al LLM |
| Omonimie o nome ambiguo | `TaskManager.find()` è già univoco e case-insensitive (spec 02 D3); nessuna nuova ricerca |
| Silenzio al richiedente su esito negativo | Riga di stato inviata da C-14 (P-A-06), dichiarata come assunzione |
| Testi dei messaggi non dichiarati | Assunzione P-A-02, modificabile senza impatto sul codice |

## Criteri di validazione (done della voce)

1. `PYTHONPATH=src:.deps python3 -m pytest` verde (inclusi i test di confine).
2. AC-01: utente iscritto a «news», `/run news` → risultato recapitato solo a lui, riga `trigger='manual'`, `requested_by` = richiedente.
3. AC-02: utente non iscritto a «log», `/run log` → rifiuto, compito non eseguito, nessuna riga in `executions`.
4. AC-03: compito già in esecuzione → rifiuto, una sola esecuzione registrata.
5. BR-4/BR-8 invariati: lo stesso motore di spec 03 (timeout 10 min, retry interni a C-05/C-10).
6. BR-12 rispettato: admin su tutto, utente autorizzato solo sui compiti iscritti, revocati/sconosciuti ignorati.
7. Nessun import fuori dai confini; type hints sulle interfacce pubbliche; errori espliciti; italiano di default.
8. Nessuna migrazione e nessuna nuova leva di configurazione introdotte.
9. Documento D-08 conforme alla struttura dichiarata e approvato dal checkpoint Phase 4.
10. Catena di tracciabilità ricostruibile: voce roadmap 04 → spec 04 → binding → task → artefatti → validazione → pubblicazione.

## Tracciabilità attesa (compilata a Publish)

| Requisito / criterio | Test previsto |
|---|---|
| AC-01 lancio manuale, risultato solo al richiedente | `tests/test_manual_run_ac.py::test_ac01_subscriber_gets_the_result_alone` |
| AC-02 non iscritto rifiutato, nessuna esecuzione | `tests/test_manual_run_ac.py::test_ac02_unsubscribed_user_is_refused` |
| AC-03 compito già in esecuzione rifiutato | `tests/test_manual_run_ac.py::test_ac03_manual_launch_refused_while_scheduled_runs`, `tests/test_execution.py::test_one_execution_per_task_at_a_time` |
| C-21 permessi e compito sospeso (D2) | `tests/test_run_dispatcher.py::test_admin_may_run_a_paused_task`, `::test_authorized_user_is_refused_on_a_paused_task` |
| C-22 lock (D1) | `tests/test_task_lock.py` |
| Riconoscimento `/run` e `lancia` (D3), precedenza sul ramo di creazione | `tests/test_command_router.py::test_run_command_and_natural_language_launch`, `::test_natural_launch_is_not_treated_as_creation` |
| BR-12 destinatari, iscrizioni e revoca al lancio | `tests/test_delivery.py::test_manual_result_goes_only_to_the_requester`, `tests/test_run_dispatcher.py::test_revoked_user_is_refused_at_launch` |
| BR-4/BR-8 invariati (anche su percorso manuale) | `tests/test_execution.py::test_manual_timeout_is_interrupted`, `tests/test_llm.py`, `tests/test_telegram_gateway.py` |
| Confini di integrazione | `tests/test_boundaries.py` |

## Ordine di consegna

Codice-first: T1 → T2 → T3 → T4 → T5 → T6, poi test T7, poi documentazione T8 (dipendente da codice
stabile), infine pubblicazione T9. Il documento descrive il comportamento validato.

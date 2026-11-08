# Piano 09 — FR-008 Storico delle esecuzioni

- **Voce roadmap:** `09 — FR-008 Storico esecuzioni` (non spuntata)
- **Spec:** [09-fr008-storico-esecuzioni.spec.md](../specs/09-fr008-storico-esecuzioni.spec.md), Stato `New`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack, `## Roadmap`
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`: C-02 con `executions` e indici, C-04, C-05
  `LLMClient.chat`, C-06 con job di manutenzione giornaliero, C-11 con `record`/`finish`/
  `query`/`purge_expired` e retention configurabile, C-13), item 02 (C-14 con comandi e NL, C-15
  `find` e `list(role, user_id)`), item 03 (C-19 che marca `saltata`, C-20), item 04 (C-21), item 08
  (C-14 con ordine callback/prima-del-rifiuto e `HELP_TEXT`)
- **Dipendenze non consegnate:** item 10 (avvisi), item 11 (riavvio)
- **Data piano:** 2026-11-01
- **Stato piano:** approvato 2026-11-01; eseguito T1–T12 (delivery history: voce 09)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-34 History Query: `parse_filter(text)` e `parse_window_with_llm(text)` (puri), `resolve_task(name, *, role, user_id)`, `build_filter`, `query(role, user_id, filter)`, `render(executions, *, label, degenerate=False)`; parser temporale deterministico con fallback LLM validato; visibilità per ruolo; elenco a una riga per esecuzione, riassunto 120 caratteri, massimo 20 righe; clamp alla retention; log di ogni consultazione | codice | `src/agente/history_query.py` |
| D-02 | Migrazione `005_executions_started_index.sql`: normalizza `started_at`/`finished_at` a UTC ISO con `strftime('%Y-%m-%dT%H:%M:%S+00:00', …)` e guardia `datetime(…) IS NOT NULL` per colonna; crea l'indice `idx_executions_started` su `started_at` | migrazione | `src/agente/storage/migrations/005_executions_started_index.sql` |
| D-03 | C-11: normalizzazione degli istanti a UTC in `record`/`record_skipped`/`finish` (nota del chiamante conservata), cutoff di retention e reset conversazione calcolati in UTC, log del conteggio purgato in `purge_expired` | codice | `src/agente/history.py` |
| D-04 | `AgentApp._maintenance`: retention (`purge_expired`) e `purge_idle` della chat isolati; `StorageError` catturato e loggato senza fermare il processo né `purge_idle` (C-02 converte gli errori SQLite in `commit()`); nuovo tentativo al job successivo (24 h) | codice | `src/agente/app.py` |
| D-05 | Estensione C-14: comando `/history [periodo] [compito]`, riconoscimento deterministico delle richieste NL di storico prima dell'elenco compiti e della chat (con veto sulle schedulazioni), `HELP_TEXT` aggiornato | codice | `src/agente/command_router.py` |
| D-06 | Wiring: C-34 costruito in `AgentApp.build` con C-11, C-15, C-05, `clock`, `tz` opzionale (per i test) e la retention di config; iniettato in C-14; `AgentApp` espone `history_query` | codice | `src/agente/app.py` |
| D-07 | Test della voce: unit C-34 (parsing, visibilità, formato, clamp, log), normalizzazione e log di C-11, migrazione 005, AC-01…AC-03 end-to-end, estensioni a C-14, aggiornamento delle asserzioni di migrazione | test | `tests/test_history_query.py`, `tests/test_history_ac.py`, `tests/test_history.py`, `tests/test_command_router.py`, `tests/test_storage.py`, `tests/test_bootstrap.py`, `tests/conftest.py` |
| D-08 | Documento architettura con Mermaid (1 flowchart componenti, 4 sequenze nella sezione 10: scrittura, AC-01 admin NL, AC-02 utente filtrato, AC-03 retention) e formato dell'elenco | documentazione | `docs/architecture/09-fr008-storico-esecuzioni.md` |
| D-09 | Pubblicazione: roadmap `[x]`, stato spec 09 `Implemented` + note, delivery history, piano allineato, note di continuità su spec 01 (indice `started_at`, normalizzazione, C-11 soddisfa C-35) e spec 02 (C-14 comando `/history` e riconoscimento NL) | documentazione | `docs/specs/constitution.md`, `docs/specs/09-fr008-storico-esecuzioni.spec.md`, `docs/specs/01-agent-runtime.spec.md`, `docs/specs/02-fr001-gestione-compiti.spec.md`, `docs/delivery-history.md`, questo piano |

Nessuna tabella nuova e nessuna colonna nuova: `executions` (`id`, `task_id`, `requested_by`,
`trigger`, `started_at`, `finished_at`, `outcome`, `summary`) esiste dalla 001 ed è già scritta da
C-09/C-11 (incluse le righe `saltata` di C-19). Le modifiche di schema sono l'indice su
`started_at` (richiesto da spec 09) e la **normalizzazione degli istanti esistenti a UTC** (V-10):
`ExecutionEngine` scrive in UTC, `RecoveryHandler`/`record_skipped` scrivono l'occorrenza nel fuso
locale, e `ExecutionRepository` confronta e ordina le stringhe. Senza normalizzazione ordinamento,
AC-01 e retention sarebbero errati con offset diversi. Nessuna nuova chiave di configurazione: la
retention resta `limits.history_retention_days` (BR-7, oggi 30), i limiti di presentazione sono
costanti di modulo (D1). **C-35 non viene creato:** `HistoryService.purge_expired()` è già il job
giornaliero di retention, schedulato da C-06 con soglia di configurazione (D5/V-01). Riceve il log
del conteggio e l'error handling che la spec 09 chiede a C-35.

### Fuori scope di questa voce (dichiarato)

- **Nuovo job di retention (C-35):** nessuna duplicazione; il job esistente di C-06/C-11 resta
  l'unico punto che cancella **esplicitamente** esecuzioni (D5, V-01); il cascade su `tasks` resta
  (V-08). Log ed error handling di C-35 sono assorbiti da C-11 e da `AgentApp._maintenance`.
- **Storico delle chat o riepilogo LLM dello storico:** FR-008 riguarda le esecuzioni; nessuna
  sintesi generata dal modello sull'elenco.
- **Dettaglio di una singola esecuzione / link al dettaglio:** la spec lascia aperto il punto
  («se includere il link al dettaglio»); non esiste un identificativo pubblico e non viene inventato
  (V-04).
- **Storico dei compiti eliminati:** il vincolo `ON DELETE CASCADE` di `executions.task_id` elimina
  le righe insieme al compito; comportamento esistente, **gap dichiarato** (D6/V-08), nessuna
  migrazione di modello dati.
- **Filtro per esito o per innesco:** `ExecutionRepository.list` supporta `outcome` ma **non**
  `trigger`; la spec 09 non espone filtri di questo tipo da Telegram e non viene aggiunto alcun
  parametro.
- **Storico nella chat come tool di C-08:** non dichiarato; le richieste NL di storico sono
  intercettate da C-14 prima della chat (P-A-13).
- **Vista di deployment:** non dichiarata dalla spec 09 e non necessaria; **gap registrato**. Nessun
  ER nuovo: `executions` è già nel modello dati di spec 01.

## Decisioni che sbloccano il piano

Chiuse dall'operatore il 2026-11-01. D1 e D2 rispondono alle due domande tecniche aperte di spec 09;
D3–D6 chiudono i comportamenti impliciti.

| # | Domanda aperta / conflitto | Decisione | Impatto |
|---|----------------------------|-----------|---------|
| D1 | Formato del «breve riassunto» e link al dettaglio (domanda aperta 1) | **Una riga per esecuzione**, riassunto troncato a **120 caratteri** (con «…»), massimo **20 righe**; nessun link al dettaglio. Formato: `• GG/MM HH:MM — <compito> — <esito> — <riassunto>`; riga finale `… (mostrate le <max_rows> esecuzioni più recenti)` quando ce ne sono altre | D-01, P-A-04/P-A-06, V-04; test di formato e troncamento |
| D2 | Interpretazione dei riferimenti temporali NL (domanda aperta 2) | **Parser deterministico** per un insieme chiuso (`oggi`, `ieri`, `questa settimana`/`settimana`, `settimana scorsa`, `questo mese`/`mese`, `mese scorso`, `ultimi N giorni`/`Ng`, `GG/MM`, `GG/MM/AAAA`) + **fallback LLM validato** (C-05, come C-16) per le frasi non riconosciute; la finestra proposta dal modello è ri-validata in codice; ambiguità o validazione fallita → richiesta di precisazione | D-01, P-A-03/P-A-14, V-05; test con LLM finto |
| D3 | Finestra predefinita di `/history` (non dichiarata) | **Ultime 24 ore** dal momento della richiesta | D-01, P-A-02; test del default |
| D4 | Sintassi del comando (la spec nomina solo `/history`) | **`/history [periodo] [compito]`**: prefisso di periodo riconosciuto, il resto è il nome del compito risolto con C-15; senza argomenti → ultime 24 ore e tutti i compiti visibili | D-05, P-A-08; test di comando |
| D5 | La spec dichiara C-35 Retention Job, ma C-11 ha già `purge_expired()` e il job giornaliero | **C-35 non viene creato**: C-11 soddisfa C-35 (`purge_expired`, soglia `limits.history_retention_days`, job C-06), con log del conteggio e error handling aggiunti in questa voce. Deviazione dichiarata | D-01/D-02/D-03/D-04, V-01; nessun nuovo job |
| D6 | `executions.task_id` con `ON DELETE CASCADE`: eliminare un compito cancella il suo storico | **Mantenere il cascade** (schema 001 invariato); gap dichiarato nel documento e nella delivery history | D-09, V-08; nessuna migrazione di modello dati |

## Riparto di responsabilità tra componenti (anti-duplicazione)

| Componente | Possiede | Delega a | Non duplica perché |
|---|---|---|---|
| C-34 History Query | parsing del filtro, finestra temporale, risoluzione del compito visibile, visibilità per ruolo, formato dell'elenco, log della consultazione | C-11 (lettura), C-15 (compiti), C-05 (solo fallback temporale), C-04 (ruolo, già risolto da C-14) | C-11 resta l'unico lettore/scrittore di `executions`; C-14 instrada e invia |
| C-11 History & Retention | scrittura normalizzata delle esecuzioni, query SQL, retention e reset chat, log dei conteggi purgati | C-02 | C-34 compone il filtro e presenta; non apre SQL |
| C-14 Command Router | riconoscimento di `/history` e dell'intento NL, invio della risposta, messaggi d'uso | C-34 | non legge `executions` e non compone l'elenco |
| C-15 Task Manager | compiti e visibilità per ruolo | C-02 | C-34 usa `find`/`list(role, user_id)`, non duplica la regola |
| C-05 LLM Client | proposta di finestra temporale per frasi non riconosciute | — | il valore è ri-validato in C-34; il parser deterministico non chiama il modello |
| C-06 Scheduler | esecuzione giornaliera del job di manutenzione | C-11 | invariato: C-35 non esiste come componente separato (D5) |
| C-04 Role Guard | ruolo effettivo a ogni richiesta | C-02 | invariato: `pending`/`revoked` sono `UNKNOWN` e non raggiungono C-34 |

**Un solo lettore di `executions`.** C-34 non importa `sqlite3` né `ExecutionRepository`: usa
`HistoryService.query`, che resta l'unico accesso allo storico. **Un solo punto di retention.**
`purge_expired` di C-11 è l'unico `DELETE` **esplicito** sulle esecuzioni (messaggi e conversazioni hanno i propri metodi di reset/purge; il cascade su `tasks` resta, V-08). **Un solo punto di normalizzazione.**
C-11 converte gli istanti a UTC prima di scrivere, così l'ordinamento e i confronti stringa di C-02
restano corretti; la migrazione 005 allinea le righe già presenti.

**Nessuna duplicazione della visibilità.** La regola «admin tutto, autorizzato solo iscritti» è già
in `ExecutionRepository.list(user_id=…)` (`EXISTS` su `subscriptions`) e in `TaskManager.list`; C-34
le applica passando `user_id=None` per l'admin e l'id per l'autorizzato, senza riscriverle.

**Confine dei thread.** `parse_window_with_llm` è l'unica parte che può chiamare C-05 ed è **pura**
(nessun accesso a SQLite); `parse_filter` è puro e deterministico. Fra i metodi di C-34, **solo**
questi due possono girare in `asyncio.to_thread`; C-14 lo fa sul ramo NL, mentre sul comando chiama
`parse_filter` direttamente. `resolve_task`, `query` e `render` usano C-15/C-11 e restano sul
thread dell'event loop, perché la connessione SQLite non è condivisibile fra thread
(`check_same_thread=True`).

## Contratti (forma dei tipi)

```python
# C-34 — history_query.py
MAX_HISTORY_ROWS = 20
SUMMARY_CHARS = 120

PERIOD_USAGE = (
    "Uso: /history [periodo] [compito]. Periodi: oggi, ieri, questa settimana, "
    "settimana scorsa, questo mese, mese scorso, ultimi N giorni (Ng), GG/MM, "
    "GG/MM/AAAA. Alias: settimana, mese."
)
EMPTY_HISTORY = "Nessuna esecuzione nel periodo."
EMPTY_RETENTION = (
    "Nessuna esecuzione conservata: il periodo precede la retention di "
    "{} giorni."
)  # formattato con retention_days

@dataclass(frozen=True)
class Period:
    since: datetime            # aware, nel fuso `tz` di C-34
    until: datetime            # aware, nel fuso `tz` di C-34
    label: str                 # "ultime 24 ore", "ieri (31/10)", "ultimi 7 giorni", ...

@dataclass(frozen=True)
class ParsedFilter:
    period: Period
    task_name: str | None = None
    period_found: bool = False     # True se la finestra è determinata (esplicita o via LLM); False = default 24h

@dataclass(frozen=True)
class AmbiguousPeriod:
    question: str              # richiesta di precisazione, nessun default assunto

@dataclass(frozen=True)
class HistoryFilter:
    since: str                 # UTC ISO 8601, timespec="seconds", per C-11
    until: str
    task_id: int | None = None
    label: str = "ultime 24 ore"
    degenerate: bool = False   # True se il clamp ha svuotato la finestra

class HistoryQuery:
    def __init__(
        self,
        history: HistoryService,
        tasks: TaskManager,
        *,
        retention_days: int,          # da config.limits.history_retention_days
        llm: Any = None,
        clock: Callable[[], datetime] | None = None,
        tz: tzinfo | None = None,     # fuso delle query; default = fuso del telefono
        max_rows: int = MAX_HISTORY_ROWS,
        summary_chars: int = SUMMARY_CHARS,
    ) -> None: ...
    def parse_filter(
        self, text: str
    ) -> ParsedFilter | AmbiguousPeriod: ...   # puro: nessun SQLite, nessun LLM
    def parse_window_with_llm(
        self, text: str
    ) -> Period | AmbiguousPeriod: ...            # puro: solo C-05
    def resolve_task(
        self, name: str, *, role: Role, user_id: int
    ) -> Task | None: ...                        # C-15, thread dell'event loop
    def build_filter(
        self, parsed: ParsedFilter, task: Task | None
    ) -> HistoryFilter: ...                      # ValueError se task_name senza task
    def query(
        self, role: Role, user_id: int, filter: HistoryFilter
    ) -> list[Execution]: ...
    def render(
        self, executions: list[Execution], *, label: str, degenerate: bool = False
    ) -> str: ...   # intestazione "Storico — <label>"; se degenerate -> EMPTY_RETENTION
```

```python
# C-14 (estensione)
# __init__(..., history_query: HistoryQuery)      # nuovo parametro, iniettato da AgentApp
# _on_command: name == "history" -> await self._history(message, role, argument)
# _on_natural: dopo lancio/mutazioni, PRIMA di elenco compiti e di bozza/chat -> _NL_HISTORY
#   NL: parsed = await asyncio.to_thread(self._history_query.parse_filter, rest)
#       se AmbiguousPeriod -> domanda e stop
#       task = None
#       se parsed.task_name:
#           task = self._history_query.resolve_task(...)        # event loop
#           se task is None and not parsed.period_found:
#               window = await asyncio.to_thread(
#                   self._history_query.parse_window_with_llm, rest)
#               se AmbiguousPeriod -> domanda e stop
#               parsed = ParsedFilter(window, None, True)   # il resto era un tempo, non un nome
#           altrimenti se task is None:
#               invia "Compito non trovato" e stop
#       filter = build_filter(parsed, task); query;
#       render(executions, label=filter.label, degenerate=filter.degenerate)
#   ValueError di build_filter (difensivo) -> "Operazione non riuscita." e Action("error")
# Action.kind nuovi: "history" (elenco inviato, anche vuoto), "ask_period" (precisazione NL)
```

- **`parse_filter`** traduce testo in periodo + eventuale nome di compito: prefisso di periodo
  deterministico (match più lungo), resto come nome; `period_found=True` solo per un periodo
  esplicito, `False` per il default delle 24 ore. C-14 lo porta a `True` anche dopo il fallback LLM,
  perché la finestra è ormai determinata. È **puro** (solo clock, nessun DB, nessun LLM) e deterministico.
- **`parse_window_with_llm`** è l'unico punto che chiama C-05: si usa **solo** sul ramo NL, quando il
  testo non contiene un periodo esplicito e non risolve un compito visibile (precedenza: periodo →
  compito → LLM). Se il modello interpreta il resto come tempo, il resto non era un nome di compito:
  la query copre tutti i compiti visibili in quella finestra. Un nome con periodo esplicito non
  risolto è un errore, non un'ambiguità temporale. È puro e C-14 lo esegue in thread; non può
  cambiare compito né visibilità.
- **`build_filter`** è l'unica conversione fra `ParsedFilter` e l'input di `query`: applica il clamp
  alla retention e imposta `degenerate` quando la finestra si svuota; solleva
  `ValueError` se `task_name` è valorizzato e `task` è `None`, così un errore di risoluzione non può
  diventare «tutti i compiti». C-14 risolve il compito prima di chiamarla (P-A-20).
- **`query`** chiama `HistoryService.query(user_id=…, since=…, until=…, task_id=…,
  limit=max_rows+1)` (tutti keyword-only, come la firma reale); l'extra riga serve solo a sapere che l'elenco è troncato, non viene mostrata.
- **`render`** produce il testo D1; i nomi dei compiti vengono da C-15, con fallback difensivo
  `compito #<id>` (il cascade rende il caso teorico).
- **`AmbiguousPeriod`** è restituito quando il periodo non è interpretabile con certezza: C-14
  invia `question` e non interroga lo storico (nessun default silenzioso).

## Interpretazione del periodo (regola unica)

| Testo | `since` (locale) | `until` (locale) | `label` |
|---|---|---|---|
| *(assente, `/history`)* | `now - 24h` | `now` | `ultime 24 ore` |
| `oggi` | oggi 00:00 | `now` | `oggi (GG/MM)` |
| `ieri` | ieri 00:00 | oggi 00:00 − 1s | `ieri (GG/MM)` |
| `questa settimana` / `settimana` | lunedì 00:00 | `now` | `questa settimana` |
| `settimana scorsa` | lunedì precedente 00:00 | lunedì corrente 00:00 − 1s | `settimana scorsa` |
| `questo mese` / `mese` | primo del mese 00:00 | `now` | `questo mese` |
| `mese scorso` | primo del mese precedente 00:00 | primo del mese corrente 00:00 − 1s | `mese scorso` |
| `ultimi N giorni` / `Ng` | `now - N giorni` | `now` | `ultimi N giorni` |
| `GG/MM` o `GG/MM/AAAA` | quel giorno 00:00 | giorno successivo 00:00 − 1s | `GG/MM` |
| altro | — | — | nessun periodo: il testo è provato come nome compito; se inizia con una cifra e non è un periodo valido → `AmbiguousPeriod`. Comando o periodo esplicito con nome non risolto → `Compito non trovato`; NL senza periodo esplicito → fallback LLM, poi domanda (P-A-08/P-A-20) |

- **Anno di `GG/MM`:** si usa l'anno corrente; se la data risultante è nel futuro oltre 24 ore, si
  usa l'anno precedente (P-A-19).
- **Punteggiatura, preposizioni, articoli:** prima del parsing si rimuovono spazi, punteggiatura
  finale (`? ! . , ; :`), prefissi iniziali (`su`, `di`, `del`, `della`, `dei`, `delle`, `degli`,
  `per`, `con`, `nel`, `nella`, `nelle`, `sull'`, `sul`, `sulla`, `sulle`, `nell'`, `dall'`, `all'`,
  `dello`, `dell'`, `il`, `lo`, `la`, `i`, `gli`, `le`, `l'`) e nomi generici residui (`compiti`,
  `compito`, `esecuzioni`, `esecuzione`, `storico`): «cosa hai fatto ieri?» produce `ieri`; «la
  settimana scorsa» produce `settimana scorsa`; «mostra lo storico dei compiti» non ha filtro di
  compito (P-A-21).
- **Clamp (politica unica):** `since = max(since, now - retention_days)`, applicato una sola volta
  in `build_filter` per le finestre di entrambi i percorsi (deterministico e LLM); se il taglio avviene, la `label` riceve ` (limitato
  agli ultimi <N> giorni)`, con `N` dalla stessa configurazione del job di retention. Una finestra
  oltre la retention non è un'ambiguità: viene tagliata e dichiarata. Se l'intera finestra precede
  la retention (`until <= cutoff`), il filtro degenera in un intervallo vuoto a `cutoff` e la
  `label` diventa `periodo precedente alla conservazione` e `degenerate=True`; la resa usa
  `EMPTY_RETENTION` (P-A-05): nessuna riga, nessuna ambiguità.
- **Fuso:** i confini di giorno/settimana/mese sono calcolati nel fuso `tz` (default: fuso del
  telefono, BR-14) e convertiti in UTC ISO per C-11; la resa usa lo stesso fuso. La scrittura
  normalizza comunque a UTC (V-10), così `since`/`until` e `started_at` sono confrontabili come
  stringhe.
- **Fallback LLM:** prompt che chiede **solo** un oggetto JSON
  `{"since": "ISO", "until": "ISO", "label": "..."}`; un LLM che risponde male, date non valide,
  `since > until` o `until` nel futuro oltre 60 s producono `AmbiguousPeriod`. Il modello non può
  allargare la visibilità né scegliere il compito.
- **Ambiguità:** un testo che sembra un periodo ma non è valido (es. `31/13`, `0g`) produce
  `AmbiguousPeriod` con `PERIOD_USAGE`; anche un testo che inizia con una cifra e non è un periodo
  valido (es. `3 news`) produce `AmbiguousPeriod`. Un testo che non inizia con una cifra e non è un
  periodo viene provato come nome di compito (P-A-08/P-A-20).

## Formato dell'elenco (D1)

```
Storico — ieri (31/10)
• 31/10 08:00 — news — ok — rassegna delle notizie sull'IA…
• 31/10 09:15 — log — errore — TimeoutError: …
… (mostrate le 20 esecuzioni più recenti)
```

- Intestazione `Storico — <label>`; nessun risultato → solo `Nessuna esecuzione nel periodo.`;
  filtro `degenerate` → solo `EMPTY_RETENTION` (P-A-05). Nessuna intestazione nei casi vuoti.
- Una riga per esecuzione: `• GG/MM HH:MM — <compito> — <esito> — <riassunto>`; `GG/MM HH:MM` è
  l'istante di `started_at` nel fuso `tz`. Newline nel riassunto e nel nome del compito sono
  sostituiti da uno spazio, così una voce resta una riga.
- `esito` è uno di `ok`, `errore`, `interrotto`, `saltata` (BR-15 + spec 03 D1); `saltata` compare
  come tale, non viene nascosta. `outcome` NULL → `—` (P-A-06); `finished_at` non compare nella riga.
- Riassunto assente → `—`; oltre 120 caratteri → primi 120 + `…`. Il testo in DB resta quello già
  troncato a 500 caratteri da C-09. `started_at` non parsabile → `??/?? ??:??` (P-A-06).
- Massimo 20 righe; se C-11 restituisce la `<max_rows + 1>`-esima, la coda è sostituita dalla nota di
  troncamento con `max_rows` effettivo (nessun conteggio totale inventato).
- La rilettura usa il fuso del telefono; l'ordinamento è quello di C-11 (più recenti prima).

## Deviazioni pre-dichiarate (numerazione stabile per il documento 09)

| # | Deviazione | Fonte modificata | Motivo |
|---|---|---|---|
| V-01 | C-35 Retention Job non viene creato: la retention è `HistoryService.purge_expired()`, con log del conteggio e error handling assorbiti in C-11 e `AgentApp._maintenance`; l'interfaccia si chiama `purge_expired()` e non `purge()` | spec 09 C-35 | D5: C-11 ha già il job giornaliero con soglia di configurazione; un wrapper sarebbe duplicazione senza comportamento nuovo |
| V-02 | Migrazione 005 con indice `idx_executions_started` su `started_at` | spec 01 C-02 §Scalabilità (indice su `executions(task_id, started_at)`; nessun indice su `started_at`) | spec 09 §Modello dati richiede esplicitamente l'indice per la retention |
| V-03 | C-34 espone `parse_filter`/`parse_window_with_llm`/`resolve_task`/`build_filter`/`render` oltre a `query` | spec 09 C-34 (interfaccia `query(role, user_id, filter)`) | l'interfaccia dichiarata non copre parsing del testo, risoluzione del compito e resa Telegram; restano nello stesso componente che «risponde a /history e NL». La separazione tiene l'LLM fuori dal thread con SQLite |
| V-04 | Nessun link al dettaglio nell'elenco | spec 09 domanda aperta 1 | non esiste un identificativo pubblico dell'esecuzione; inventarlo sarebbe un requisito nuovo |
| V-05 | Parser deterministico con fallback LLM validato | spec 09 domanda aperta 2 | D2: precisione e prevedibilità; il modello propone solo la finestra e non può allargarla |
| V-06 | Sintassi `/history [periodo] [compito]` e riconoscimento NL con pattern deterministici ancorati in apertura | spec 09 (nomina solo `/history` e «richieste NL») | D4 e P-A-13: senza una sintassi dichiarata il comando non è usabile; i pattern ancorati evitano che la chat o le creazioni assorbano le richieste di storico |
| V-07 | Clamp della finestra alla retention con nota nella `label` | spec 09 §Modello dati / BR-7 | una finestra più ampia non avrebbe dati: meglio dichiararlo che restituire un elenco silenziosamente incompleto |
| V-08 | Lo storico di un compito eliminato sparisce (cascade) | FR-008 «conservata 30 giorni» | D6: comportamento dello schema 001; gap dichiarato, nessun cambio di modello dati |
| V-09 | `saltata` compare nell'elenco | BR-15 / spec 03 D1 | le righe esistono in `executions` e servono a spiegare le occorrenze mancate; nasconderle renderebbe lo storico incompleto |
| V-10 | Normalizzazione degli istanti a UTC: in `HistoryService.record`/`record_skipped`/`finish` e, per le righe esistenti, nella migrazione 005; istanti naive interpretati come UTC | spec 01 C-11 (non dichiarava la normalizzazione) | `ExecutionEngine` scrive UTC, `RecoveryHandler` scrive il fuso locale e C-02 confronta stringhe: senza normalizzazione ordinamento, AC-01 e retention sono errati con offset diversi. Correzione alla radice, non nel confronto |
| V-11 | C-34 dipende anche da C-15 per risolvere il nome del compito fra quelli visibili | spec 09 C-34 (elenca C-14, C-05, C-11, C-04) | la risoluzione per nome esiste già in C-15 e riscriverla duplicherebbe la regola di visibilità; C-14 resta il chiamante |
| V-12 | `AgentApp._maintenance` cattura `StorageError`, non `sqlite3.Error`; C-02 espone `commit()` che converte gli errori SQLite | spec 01 C-02 (SQLite solo in storage) | il confine vieta `sqlite3` fuori da C-02; il `commit()` della retention traduce l'errore e il wiring resta pulito |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita in questa invocazione
leggendo il solo frontmatter di `.opencode/agents/*.md`, `.opencode/commands/*.md`,
`.opencode/skills/*/SKILL.md` e `opencode.json`; discovery per ruolo, nessun asset legato per
filename.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-07, D-09 (codice, migrazione, test, aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione di codice Python, migrazioni SQL, test o configurazione | Etichettati *"no specialized capability discovered"*; si procede su spec 09 + constitution + pattern esistenti in `src/agente/` |
| D-08 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** (Phase 2 struttura e Phase 4 validazione); il produttore resta il Conductor |
| D-08 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 09 e dai documenti 07/08; assunzione P-A-01 |

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

## Checkpoint di struttura (D-08) — Phase 2

Struttura applicabile proposta: **Metadata** (Spec · Voce roadmap · Piano · Constitution · Data ·
Struttura dichiarata + P-A-01 + Governance) · **1** Contesto e obiettivi · **2** Componenti (C-34, C-11 che
soddisfa C-35, estensione C-14, C-04/C-05/C-06/C-15 invariati in tabella, flowchart) · **3** Componenti e
capacità non disponibili (C-35 separato, dettaglio/link, storico dei compiti eliminati, vista
deployment) · **4** Wiring di `AgentApp` · **5** Riparto di responsabilità · **6** Modello di dominio (`Execution`,
esiti inclusa `saltata`) · **7** Modello dati (`executions`, migrazione 005 con normalizzazione e indice,
rimando al modello dati di spec 01) · **8** Interpretazione del periodo (tabella D2, clamp, fuso, anno,
punteggiatura) · **9** Formato dell'elenco (D1) · **10 Flussi di dati**: 10.1 scrittura di
un'esecuzione (flusso 2, C-09/C-19 → C-11 con normalizzazione), 10.2 domanda NL dell'admin (flusso 1,
AC-01), 10.3 `/history` di un utente iscritto (flusso 1, AC-02), 10.4 retention giornaliera (flusso 3,
AC-03), tutte `sequenceDiagram` · **11** Concorrenza e ciclo di vita (con il confine dei thread) ·
**12** Integrazioni · **13** Sicurezza (BR-12, filtri, dati solo su S24, voci eliminate non recuperabili) · **14** Requisiti non funzionali (BR-7, BR-16, BR-14; BR-17 non si applica: la query è locale e
immediata) · **15** Rischi e assunzioni · **16** Domande aperte chiuse · **17** Fuori scope · **18** Deviazioni (V-01…V-12) ·
**19** Tracciabilità (AC-01…AC-03, BR-7/12/15). Per ogni componente: Responsabilità · Interfaccia ·
Input/Output · Dipendenze · Error handling · Osservabilità · Sicurezza. Nessuna vista deployment e
nessun ER: la spec 09 non li dichiara e le tabelle sono già nella fondazione.

**Passate del 2026-11-01:** prima **NOT APPROVED** (1 critical: `started_at` misto UTC/locale;
8 major: normalizzazione non dichiarata, asserzioni di migrazione, log di C-34 assente, C-35
incompleto, pattern NL troppo larghi, LLM sincrono sul loop, contratto `interpret`→`query`, test
inesistenti; 8 minor); seconda **NOT APPROVED** (regressione: `interpret` in thread con SQLite;
guardia NULL nella 005; clamp vs LLM; fuso non iniettabile; punteggiatura; ordine `_NL_LIST`);
terza **NOT APPROVED** (pattern «mostra lo storico» vs `_NL_LIST`; P-A-23 errata su `started_at`;
formato SQL di normalizzazione non fissato; precedenza LLM/nome compito; cutoff non normalizzato;
esiti NULL; clamp invertito; guardia `build_filter`; formulazioni di rischio); quarta **NOT
APPROVED** (veto `settiman*` che bloccava i periodi validi; flusso LLM che scartava il nome;
«storico dei compiti» trattato come nome; riferimenti stale a `parse_filter`; `period_found` morto;
`tz` non passato da `build`; naive non etichettato; formulazioni residue). Quinta passata in corso su
questa versione, con le correzioni applicate: flusso `elif`, nomi generici residui, due parser puri,
`tz` nel wiring, P-A-25 riformulata, blocco esplicito di `UNKNOWN`, `PERIOD_USAGE` completo,
istante del formato, `llm=None`, note di `record_skipped`, firma di C-14; quinta **NOT APPROVED**
(`render` senza label, match esatto impossibile in `parse_filter`, `period_found` ambiguo, log
stale, `timespec` non fissato, nota di troncamento hardcoded, veto non raggiungibile, virgolette
spurie). Sesta passata in corso su questa versione con le correzioni: `render(executions, label)`,
limitazione dichiarata per i nomi generici, `period_found` ridefinito, `timespec="seconds"`, nota di
troncamento dinamica, messaggio dedicato per il clamp degenere, veto in `search` senza «alle N»,
`allow_llm` rimosso dalle assunzioni, riga «ieri» inserita via C-11 nei test end-to-end; sesta
**NOT APPROVED** (`EMPTY_RETENTION` in contraddizione con P-A-20, discriminante di `render` non
dichiarato, log fermo alla quinta, `render` posizionale in D-01, regex spezzate, perimetro P-A-21,
`tz` offset fisso, test di creazione non discriminante, alias mancanti in `PERIOD_USAGE`, sezioni
D-08 non numerate, BR mancanti in tracciabilità). Settima passata in corso con: campo
`HistoryFilter.degenerate`, carve-out in P-A-20, `render(..., degenerate)`, log aggiornato, D-01
keyword-only, regex su una riga, perimetro P-A-21 esteso, `tz` come zona con test DST, test di
creazione con bozza completa, alias in `PERIOD_USAGE`, sezioni numerate, righe BR-7/12/15; settima
**NOT APPROVED** (`tz` «zona fissa» contraddittorio con il test DST, default `tz` legato al clock,
alias assenti in D2, log stale, `purge_expired` accoppiato, firme posizionali, `degenerate` senza
default, ramo NL degenere implicito, harness senza `history_query`, struttura D-08 rinumerata).
Ottava passata in corso con: `ZoneInfo("Europe/Rome")`, default `tz` indipendente dal clock, alias in
D2, log aggiornato, separazione dichiarata dei DELETE, firme keyword-only, `degenerate=False` in
D-01, azione NL esplicita, `TaskHarness` con C-34, deviazione di struttura dichiarata; ottava **NOT
APPROVED** (non atomicità dei due `DELETE`, log stale, `period_found` ambiguo, confine thread,
P-A-10 «nessuna query SQL», test mancanti, ordine P-A-25/P-A-26, newline non gestiti, limiti NL non
dichiarati). Nona passata in corso con: non atomicità dichiarata, `period_found` ridefinito,
confine thread esplicitato, P-A-10 corretto, nuova riga di sicurezza, resa elenco vuoto unica,
sanitizzazione newline, preposizioni/articoli estesi, test nominati, P-A-25/P-A-26 riordinati; nona
**NOT APPROVED** (§Interpretazione non allineata a P-A-21, `period_found` post-LLM, `rest` non
definito, resa di `started_at` non parsabile, catch troppo stretto, log conteggi parziali, frase
«unico DELETE» troppo larga, log passate incompleto). Decima passata in corso con: regola unica
allineata, `period_found` ridefinito, `rest` dichiarato, fallback di resa, catch `sqlite3.Error`, log
dopo il primo `DELETE`, frase corretta, log aggiornato; decima **NOT APPROVED** (`period_found`
ancora ambiguo nel corpo, strip dei prefissi senza regola, frasi DELETE residue, resa non parsabile
senza test, clamp senza proprietario, `purge_idle` in errore non dichiarato, pattern senza flag,
P-A-26 errata, clock di C-34 non dichiarato, BR-14 mancante). Undicesima passata in corso con: regola
del prefisso più lungo, `period_found` allineato, frasi DELETE corrette, test della resa non
parsabile, clamp in `build_filter`, errore di `purge_idle`, `IGNORECASE`/`\b`, P-A-26 corretta,
clock di C-34 e BR-14; undicesima **APPROVED** con minor recepiti (frasi DELETE residue, test
maiuscole mancante, clamp formulato due volte, ordine stadi non unico, test mal collocati);
dodicesima **APPROVED** con minor recepiti (qualificazione del cascade, rimando clamp in P-A-03,
test dei nomi generici, firma reale di `HistoryService.query`, registro delle passate).

**Phase 4 (2026-11-02):** prima **NOT APPROVED** (C-35 senza Input/Output, filtro `trigger`
inesistente, edge `C11 → C10`, Governance anticipata, stato piano, tre riferimenti di test errati,
fuso/DST non sviluppati, prefissi incompleti, guardia `finished_at`, `parse_window` «puro», «ogni»,
`HistoryFilter` con ruolo); seconda **NOT APPROVED** (prefissi piano, stato T11, `build_filter` nel
razionale SQLite, elisione apostrofica, cifra iniziale, `compito #id`, attribuzione a C-14, fonte
V-12, FR-008/BR-16); terza **NOT APPROVED** (firma di `query`, regola cifra nel piano, test
prefissi/cifra, pattern `N giorni`, duplicazione del limite, BR-16); quarta **APPROVED** con minor
recepiti (T2 allineato, evidenza del periodo invalido, esempio in §10.2, log di `_maintenance`,
campo `task_id`). La validazione finale è la Phase 4 sull'artefatto reale: 518 test, exit 0.

## Assunzioni del piano (non dichiarate da spec 09)

> **P-A-01** Struttura del documento di architettura derivata da spec 09 e dai documenti 07/08, non
> da un template: in `docs/templates/` esistono solo `template.spec.md` e `template.constitution.md`.

> **P-A-02** Finestra predefinita: `now - 24h` → `now`. Il default di `clock` è
> `datetime.now(timezone.utc)`, come C-11. I confini di giorno, settimana e mese sono
> calcolati nel fuso `tz` del costruttore. Default: `datetime.now().astimezone().tzinfo`, cioè il
> fuso del telefono **indipendentemente dal `clock` iniettato** (i test possono congelare l'ora senza
> cambiare il fuso). `tz` dovrebbe essere una zona (`ZoneInfo`, es. `Europe/Rome`) per seguire l'ora
> legale; un offset fisso è accettato ma dichiarato come limite. Gli istanti scritti sono normalizzati
> a UTC (V-10). Nei test `tz=ZoneInfo("Europe/Rome")` e un caso di confine attorno al cambio DST.

> **P-A-03** Prompt del fallback LLM: sistema che chiede **solo** `{"since": "...", "until": "...",
> "label": "..."}` in ISO 8601; risposta letta con `json.loads` (tollerando i fence come C-14).
> Validazione in codice: date parsabili, `since <= until`, `until <= now + 60s`, `label` non vuota e
> massimo 40 caratteri. Una finestra oltre la retention viene **clampata** (non è un'ambiguità); il
> taglio avviene una sola volta in `build_filter` (P-A-07), non nel parser. Ogni
> altro scarto → `AmbiguousPeriod`.

> **P-A-04** Elenco: massimo `MAX_HISTORY_ROWS = 20` righe, `SUMMARY_CHARS = 120`. La ventunesima
> riga non viene mostrata e la coda è `… (mostrate le <max_rows> esecuzioni più recenti)`, con il
> valore effettivo del parametro: nessun totale calcolato.

> **P-A-05** Nessun risultato: `Nessuna esecuzione nel periodo.` (testo unico, usato sia da
> `/history` sia dalle richieste NL). Se il filtro è `degenerate` (clamp a vuoto, P-A-07) il testo è
> `EMPTY_RETENTION`. In entrambi i casi vuoti **non** viene stampata l'intestazione `Storico — …`:
> la risposta è il solo messaggio.

> **P-A-06** Formato riga: `• GG/MM HH:MM — <compito> — <esito> — <riassunto>`; intestazione
> `Storico — <label>`. Riassunto assente → `—`; troncamento con `…` a 120 caratteri. Esiti noti
> (`ok`, `errore`, `interrotto`, `saltata`) mostrati con il valore di dominio, senza traduzioni
> ambigue; `outcome` NULL (esecuzione ancora in corso o interrotta prima di `finish`) → `—`.
> `finished_at` non compare nella riga, quindi il suo NULL non ha resa dedicata. Se `started_at` non
> è parsabile (P-A-25), l'istante è reso come `??/?? ??:??` invece di sollevare.

> **P-A-07** Clamp: `since = max(since, now - retention_days)`; se il taglio avviene, la `label`
> riceve ` (limitato agli ultimi <N> giorni)` con `N = retention_days` letto dalla configurazione.
> `MAX_HISTORY_DAYS` non esiste come costante separata: una sola fonte, il valore di config. Se
> `until <= cutoff`, si imposta `since = cutoff` e `until = cutoff - 1s`: la query non può restituire
> righe e la `label` diventa `periodo precedente alla conservazione`.

> **P-A-08** Parsing di comando e NL (sulle forme prodotte da P-A-21): si cerca il **prefisso di
> periodo più lungo** nell'insieme chiuso; ciò che segue (con preposizioni, articoli e punteggiatura rimossi) è il nome del compito.
> Se nessun periodo è riconosciuto, il testo è provato come nome di compito con la finestra
> predefinita. **Precedenza dichiarata:** periodo esplicito → nome di compito → fallback LLM (solo
> NL). Sul comando `/history` il fallback LLM non esiste: nome non risolto → `Compito non trovato:
> «<nome>».` (`Action("error")`). Sulla NL il fallback LLM è ammesso **solo** quando non c'era un
> periodo esplicito (`period_found=False`): «storico news» risolve `news` senza modello; «storico
> dell'ultima ora» prova `ultima ora` come nome (dopo lo strip di `dell'`), fallisce e passa al
> modello. Un nome con
> periodo esplicito («ieri news») non risolto è `Compito non trovato`, senza chiamata al modello. Un testo che sembra un periodo ma è invalido (es. `31/13`, `0g`) →
> `AmbiguousPeriod` con `PERIOD_USAGE`. Nessun argomento → finestra predefinita e tutti i compiti
> visibili.

> **P-A-09** Visibilità dei compiti: si usa `TaskManager.find` (confronto `casefold` come C-15); per
> l'autorizzato il risultato è accettato solo se il suo `id` compare fra i `TaskView` restituiti da
> `TaskManager.list(role, user_id)` (si usa `view.task`), così un compito altrui non è distinguibile
> da uno inesistente e le differenze di maiuscole non rompono AC-02. `Role.UNKNOWN` non arriva a
> C-34 (C-14 lo rifiuta prima); C-34, in difesa, restituisce `[]` senza interrogare C-11 quando il
> ruolo è `UNKNOWN` (il filtro `user_id` non basterebbe, perché la revoca conserva le iscrizioni).
> Quel ramo logga `storico non interrogato` con `role=unknown` e non produce il log di consultazione:
> «log di ogni consultazione» vale per le richieste servite.

> **P-A-10** Nomi nell'elenco: `TaskManager.get(task_id)`; se assente (caso teorico, il cascade
> elimina le righe) si mostra `compito #<id>`. Nessuna SQL diretta in C-34: una chiamata a C-15 per
> riga mostrata (al massimo `max_rows`).

> **P-A-11** `Action.kind` nuovi: solo `"history"` (elenco inviato, anche vuoto) e `"ask_period"`
> (domanda di precisazione). `"error"`, `"rejected"`, `"ignored"` e gli altri valori esistenti non
> cambiano significato.

> **P-A-12** Nessuna chiave di configurazione nuova: `MAX_HISTORY_ROWS` e `SUMMARY_CHARS` sono
> costanti di `history_query.py`; `retention_days` è un parametro obbligatorio del costruttore,
> passato da `config.limits.history_retention_days`.

> **P-A-13** Riconoscimento NL: `rest` è il testo che segue il match del pattern, prima di
> `parse_filter`. Pattern deterministici **ancorati all'inizio** della frase, con `re.IGNORECASE` e
> confine di parola finale (`\b`); «Cosa hai fatto ieri?» è riconosciuto come «cosa hai fatto ieri?».
> (`cosa hai fatto`, `cosa ha fatto`, `che cosa hai fatto`, `che cosa ha fatto`, `mostra(?:mi)?\s+(?:lo|le)?\s*(?:storico|esecuzioni)`, `(?:lo|il)?\s*storico`, `(?:le|gli)?\s*esecuzioni`). Un testo che **contiene** un
> indizio di schedulazione — regex `\b(?:ogni|tutti\s+i\s+giorni|giornalier\w*|settimanal\w*|mensil\w*|intervall\w*)` — **non** è una richiesta di storico e prosegue verso bozza/chat: così
> «storico delle esecuzioni ogni giorno alle 8» resta una creazione; «questa settimana» e «settimana
> scorsa» restano periodi validi, perché `settimana` non matcha `settimanal\w*`. Il prezzo
> dichiarato: una richiesta di storico che contiene la parola «ogni» viene trattata come creazione.
> **Limite dichiarato:** l'ordine «compito prima del periodo» («storico news ieri») non è supportato:
> il periodo deve precedere il nome del compito. Il ramo storico è valutato **dopo** lancio e mutazioni
> ma **prima** di `_NL_LIST` e della chat, altrimenti «mostra lo storico dei compiti» diventerebbe un
> elenco compiti. Il resto viene normalizzato con P-A-21, che elimina anche i nomi generici residui
> (`compiti`, `compito`, `esecuzioni`, `esecuzione`, `storico`): «dei compiti» non è un filtro.

> **P-A-14** Un fallback LLM non disponibile (`llm is None`, `LLMError`, timeout, JSON non valido)
> non blocca la richiesta: si restituisce `AmbiguousPeriod` con la domanda di precisazione; nessun default
> silenzioso. Solo `parse_filter` e `parse_window_with_llm` (puri, senza SQLite) girano in
> `asyncio.to_thread`; `resolve_task`, `query` e `render` restano sul thread dell'event loop, perché
> la connessione SQLite ha `check_same_thread=True`.

> **P-A-15** Il comando `/history` usa **solo** `parse_filter` e non chiama mai
> `parse_window_with_llm`: una chiamata al modello per ogni comando sarebbe un costo non necessario
> e una fonte di variazione.

> **P-A-16** La query chiede `limit = max_rows + 1`; la riga in più serve solo a decidere il
> troncamento e non viene mostrata. Il log riporta `len(executions)` **mostrate** (≤ `max_rows`) e un
> flag `truncated`, non le righe lette.

> **P-A-17** I test usano un clock iniettato, un `tz` iniettato e un LLM finto; nessun test dipende
> dall'ora reale, dal fuso della macchina o dalla rete. `AgentApp.build` passa a C-34 lo stesso
> `clock` già usato dagli altri componenti.

> **P-A-18** `HELP_TEXT` elenca `/history [periodo] [compito]` senza distinzione di ruolo: il
> comando è disponibile a admin e utenti `accepted`, con visibilità diversa applicata da C-34.

> **P-A-19** `GG/MM` senza anno: anno corrente; se la data risulta nel futuro oltre 24 ore, anno
> precedente. `GG/MM/AAAA` usa l'anno indicato senza correzioni.

> **P-A-20** Esiti di comando e NL: `AmbiguousPeriod` → comando: `PERIOD_USAGE` + `Action("error")`;
> filtro `degenerate` → `EMPTY_RETENTION` + `Action("history")` (nessuna intestazione), sia sul
> comando sia sul ramo NL;
> NL: `question` + `Action("ask_period")`. Nome non risolto **con periodo esplicito** o sul comando →
> `Compito non trovato: «<nome>».` + `Action("error")`. Nome non risolto **senza** periodo esplicito
> sul ramo NL → fallback LLM; se anche il modello non produce una finestra → `question` +
> `Action("ask_period")`. Un `ValueError` difensivo di `build_filter` → `Operazione non riuscita.` +
> `Action("error")`. Elenco vuoto → `EMPTY_HISTORY` + `Action("history")`. Tutti gli altri casi con
> periodo valido → `Action("history")`.

> **P-A-21** Ordine degli stadi, unico per comando e NL: **strip → periodo → nome compito → LLM**.
> Normalizzazione del testo del filtro: `strip` degli spazi, rimozione della punteggiatura
> finale (`? ! . , ; :`), dei prefissi iniziali (`su`, `di`, `del`, `della`, `dei`, `delle`, `per`,
> `con`, `nel`, `nella`, `sull'`, `sul`, `sulla`, `sulle`, `nell'`, `dall'`, `all'`, `dello`, `dell'`, `il`, `lo`, `la`, `i`, `gli`, `le`, `l'`, `degli`, `nelle`) e
> dei nomi generici residui (`compiti`, `compito`, `esecuzioni`, `esecuzione`, `storico`). Lo strip
> usa il **prefisso più lungo** con confine di parola o apostrofo, ripetuto finché nessun prefisso
> corrisponde: `dell'ultima ora` → `ultima ora`, `della settimana scorsa` → `settimana scorsa`. La frase canonica «cosa hai fatto ieri?» produce `ieri`;
> «la settimana scorsa» produce `settimana scorsa`; «mostra lo storico dei compiti» non ha filtro di
> compito. **Limitazione dichiarata:** un compito chiamato esattamente come una parola generica
> (`storico`, `compiti`, `esecuzioni`, …) non è filtrabile per nome né da `/history` né dal ramo
> NL; resta visibile nell'elenco senza filtro. Nessun secondo tentativo è possibile in
> `parse_filter`, che non accede a C-15.

> **P-A-22** `record_skipped` conserva la `note` passata dal chiamante (che può contenere l'orario
> locale dell'occorrenza): C-11 normalizza solo gli istanti, non riscrive i testi. Il formato misto
> nella nota è intenzionale e non incide su ordinamento o retention. Se `note` è assente, il
> riassunto generato usa l'istante **normalizzato** (`occorrenza saltata: <UTC ISO>`).

> **P-A-23** `ExecutionResult.started_at` (C-09) è persistito in `executions.started_at` tramite
> `HistoryService.record` e viene normalizzato a UTC da C-11; `ExecutionResult.finished_at` non è
> persistito, perché `HistoryService.finish` usa il proprio clock. Entrambi restano nel fuso del
> chiamante nel risultato in memoria: la normalizzazione riguarda solo la scrittura.

> **P-A-24** `AgentApp._maintenance` esegue `history.purge_expired()` e `chat_memory.purge_idle()` in
> due passi separati: un errore di `purge_expired` viene loggato e non impedisce `purge_idle`; il job
> giornaliero successivo (24 h) ritenta. Anche un errore di `purge_idle` è catturato e loggato senza
> fermare il job. Nessun retry immediato. Dentro `purge_expired` i due
> `DELETE` (esecuzioni e messaggi oltre la finestra chat) restano nella stessa chiamata ma **non sono
> atomici**: ciascuno fa il proprio commit, quindi un errore sul secondo lascia il primo già
> applicato. Non viene introdotta una transazione unica in questa voce; il job successivo ritenta il
> residuo. Il log del conteggio delle esecuzioni avviene subito dopo il primo `DELETE`, così un
> fallimento del secondo non nasconde il lavoro già fatto.

> **P-A-25** Un istante senza fuso (`started_at`/`finished_at` naive) è interpretato come UTC, sia in
> C-11 sia nella migrazione 005 (SQLite `datetime`/`strftime` assumono UTC). Un istante non parsabile
> resta invariato nella migrazione ed è **fuori contratto** (lo schema nasce con ISO 8601): non si
> garantisce che sia escluso dalle query né che sopravviva alla retention, perché `delete_before`
> confronta stringhe. Nessun nuovo `DELETE` viene aggiunto per gestirlo.

> **P-A-26** Rispetto ai documenti 07/08 (flussi a §7/§8, senza sezioni autonome per «Componenti e
> capacità non disponibili» e «Wiring»), il documento 09 aggiunge due sezioni autonome (3 e 4) e
> porta i flussi a §10: la numerazione 1…19 è dichiarata qui e non altera il contenuto richiesto.


## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | Migrazione e normalizzazione dati | D-02, D-03 | `005_executions_started_index.sql` usa `strftime('%Y-%m-%dT%H:%M:%S+00:00', …)` con guardia `datetime(…) IS NOT NULL` per colonna: ogni colonna valida viene normalizzata, ogni colonna non parsabile resta invariata (anche se l'altra è valida) e la migrazione non fallisce; crea `idx_executions_started`; `Database.migrate()` applica la 005 su DB nuovo e già migrato; `HistoryService.record`/`record_skipped`/`finish` normalizzano qualsiasi offset a UTC, conservano la nota del chiamante e calcolano i cutoff di retention/reset in UTC; test con offset `+02:00`, istante naive, riga non parsabile, ordinamento misto e cutoff |
| T2 | Parser del periodo | D-01 | insieme chiuso di D2 rispettato; `oggi`, `ieri`, settimana/mese corrente e precedente, `N giorni`/`Ng`, `GG/MM` (con regola anno), `GG/MM/AAAA`; default 24 h; punteggiatura e prefissi; ambiguità senza default; il parser propone la finestra grezza |
| T3 | Fallback LLM | D-01 | prompt JSON, validazione di P-A-03, `LLMError`/JSON invalido → `AmbiguousPeriod`; il modello non può cambiare compito; nessuna chiamata LLM sul comando |
| T4 | Query e visibilità | D-01 | `build_filter` applica il clamp alla retention e imposta `degenerate`; admin → tutte le esecuzioni; autorizzato → solo compiti iscritti; compito non visibile indistinguibile da inesistente; `UNKNOWN` → elenco vuoto; limite `max_rows + 1`; log `storico consultato` con ruolo, user, since, until, task, righe mostrate e `truncated` |
| T5 | Resa dell'elenco | D-01 | formato D1/P-A-06, riassunto troncato, `saltata` visibile, elenco vuoto, nota di troncamento, fuso `tz`, istante non parsabile reso `??/?? ??:??` |
| T6 | C-14 comando e NL | D-05 | `/history`, `/history ieri`, `/history 7g news`, `/history news`; uso errato → messaggio; `HELP_TEXT` aggiornato; richiesta NL di storico non passa alla chat; `Cosa hai fatto ieri?` è riconosciuto (case-insensitive); «mostra lo storico dei compiti» è storico e non elenco; creazione con «storico»/«esecuzioni» e «ogni giorno» resta una creazione (test con LLM che restituisce una bozza completa, atteso `Action("created")`); `storico news` risolve il compito senza LLM; solo i due parser puri in `asyncio.to_thread`; `build_filter` non produce mai «tutti i compiti» per un nome non risolto; `Action.kind` P-A-11/P-A-20 |
| T7 | Retention: log ed error handling | D-03, D-04 | `purge_expired` calcola il cutoff in UTC e logga i conteggi; le righe normalizzate sono confrontabili e cancellabili, quelle non parsabili restano fuori contratto (P-A-25); un `StorageError` di `purge_expired` in `_maintenance` è loggato (C-02 converte gli errori SQLite), `purge_idle` prosegue, il processo non si ferma e il job successivo (24 h) riprova; i due `DELETE` interni restano nella stessa chiamata ma non atomici (P-A-24); test dedicati |
| T8 | Wiring | D-06 | `AgentApp.build` accetta un `tz` opzionale (default `None` → `datetime.now().astimezone().tzinfo`), costruisce C-34 con C-11/C-15/C-05/`clock`/`tz`/retention e lo inietta in C-14; `AgentApp` espone `history_query`; `conftest` (`TaskHarness`) costruisce C-34, passa `clock` anche a `HistoryService`, `tz=ZoneInfo("Europe/Rome")` e inietta `history_query` in `CommandRouter`; nessun'altra dipendenza cambia |
| T9 | Test unit e di integrazione | D-07 | nuovi test C-34, C-11, migrazione 005; estensioni a `test_command_router.py`, `test_storage.py`, `test_bootstrap.py`, `conftest`; suite verde |
| T10 | AC-01…AC-03 end-to-end | D-07 | AC-01 admin scrive letteralmente «cosa hai fatto ieri?» → elenco con esito e riassunto; la riga «ieri» è inserita direttamente via C-11 con `record(started_at=…)` calcolato dal clock iniettato e `finish` che usa lo stesso clock (nessuna esecuzione reale, nessun orologio di sistema); AC-02 utente iscritto solo a news → solo news; AC-03: riga di 31 giorni fa + riga recente, `purge_expired()` esplicito, `/history 30g` → solo la recente (percorso di consultazione reale, non solo query diretta); `/history 365g` → clamp con nota (coperto anche dal test unitario) |
| T11 | Documento architettura 09 | D-08 | sezioni obbligatorie; 1 flowchart + 4 sequenze 10.1–10.4 (inclusa la scrittura e la normalizzazione); tabella periodo e formato elenco; checkpoint Phase 2 e Phase 4 **APPROVED**; vista deployment ed ER dichiarati assenti con motivo |
| T12 | Pubblicazione | D-09 | roadmap 09 `[x]`; spec 09 `Implemented (2026-11-01)` + note; delivery history con esito, gap e V-01…V-12; piano eseguito; note di continuità su spec 01/02 |

## Dipendenze

- Item 01: C-02 (`executions`, migrazioni), C-04 (ruoli), C-05 (`LLMClient.chat`), C-06 (job
  giornaliero), C-11 (`record`/`finish`/`query`/`purge_expired`), C-13 (log).
- Item 02: C-14 (comandi, NL, `HELP_TEXT`), C-15 (`find`, `list(role, user_id)`, `get`).
- Item 03/04: C-09/C-19/C-21 scrivono le esecuzioni; la normalizzazione avviene in C-11, i
  chiamanti restano invariati.
- Item 08: ordine di C-14 (callback → comandi → NL) e `HELP_TEXT` esteso.
- **Item 10/11 (non consegnati):** nessun avviso di sistema, nessuna gestione di riavvio qui.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Offset misti in `started_at` (C-09 UTC, C-19 locale) | normalizzazione a UTC in C-11 e nella migrazione 005; test con offset e ordinamento misto (V-10) |
| Riga non parsabile che fa fallire la migrazione | guardia `datetime(...) IS NOT NULL`; la riga resta intatta e la migrazione completa; test dedicato |
| Periodo NL interpretato male | parser deterministico sui casi comuni; LLM solo per il resto e ri-validato; ambiguità → domanda |
| LLM non disponibile o risposta invalida | `AmbiguousPeriod`, nessun default; il comando `/history` non usa il modello |
| Richiesta NL di storico assorbita dalla chat o dall'elenco compiti | pattern ancorati in apertura, veto sulle schedulazioni e ordine prima di `_NL_LIST` (P-A-13); test dedicati |
| LLM sincrono che blocca l'event loop | solo i due parser puri (`parse_filter`, `parse_window_with_llm`) in `asyncio.to_thread`; nessun accesso SQLite dal thread (P-A-14) |
| Elenco troppo lungo per Telegram | massimo 20 righe + nota; riassunto a 120 caratteri; `split_message` di C-03 resta la rete di sicurezza |
| Fuso orario sbagliato o dipendente dalla macchina | `tz` iniettabile, default `datetime.now().astimezone().tzinfo`; conversione esplicita in UTC per C-11; test con `ZoneInfo("Europe/Rome")` e confine DST |
| Visibilità leaks fra utenti | filtro `user_id` di C-11 e risoluzione del compito fra i soli visibili; test AC-02 |
| Retention non applicata | job esistente di C-06/C-11, log del conteggio ed error handling isolato (D-03/D-04); indice su `started_at` |
| Storico di compiti eliminati | cascade dichiarato (V-08); nessun orfano in tabella |
| Doppia retention (C-35) | nessun nuovo job; `purge_expired` è l'unico `DELETE` esplicito sulle esecuzioni (V-01); il cascade su `tasks` resta (V-08) |
| Regressione su item 02–08 | C-14 cambia per aggiunta di comando e ramo NL **e** per lo spostamento di `_NL_LIST` sotto il ramo storico (comportamento intenzionale, coperto da test); le asserzioni di migrazione passano a 005; gli altri test esistenti restano invariati |

## Criteri di validazione (done della voce)

1. `PYTHONPATH=src:.deps python3 -m pytest` verde (inclusi i test di item 01–08).
2. AC-01: admin chiede «cosa hai fatto ieri?» → elenco delle esecuzioni di ieri con esito e
   riassunto.
3. AC-02: utente iscritto solo a `news` scrive `/history` → solo esecuzioni di `news`.
4. AC-03: esecuzione di 31 giorni fa → assente dopo `purge_expired()`; con periodo richiesto più
   ampio, clamp e nota.
5. `/history` senza argomenti → ultime 24 ore; `/history <periodo> <compito>` filtra entrambi.
6. Periodo non interpretabile → richiesta di precisazione (NL) o messaggio d'uso (comando), nessun
   default silenzioso.
7. Riassunto troncato a 120 caratteri, massimo 20 righe, `saltata` visibile, nessun risultato →
   `Nessuna esecuzione nel periodo.`
8. Migrazione 005 applicata; indice `idx_executions_started` presente; `started_at`/`finished_at`
   normalizzati a UTC; nessuna tabella o colonna nuova; una riga non parsabile non blocca
   `migrate()`.
9. C-35 non creato; retention invariata (30 giorni, job giornaliero) con log del conteggio e
   gestione dell'errore isolata dal purge chat.
10. C-34 logga ogni consultazione con ruolo, utente, finestra, compito, righe mostrate e troncamento.
11. Documento D-08 conforme alla struttura dichiarata e approvato dal checkpoint Phase 4.
12. Catena di tracciabilità ricostruibile: voce roadmap 09 → spec 09 → binding → task → artefatti →
    validazione → pubblicazione.

## Tracciabilità attesa (compilata a Publish)

| Requisito / criterio | Test previsto |
|---|---|
| AC-01 admin «cosa hai fatto ieri?» | `tests/test_history_ac.py::test_ac01_admin_asks_about_yesterday` |
| AC-02 utente filtrato sui propri compiti | `tests/test_history_ac.py::test_ac02_authorized_user_sees_only_subscribed_tasks` |
| AC-03 retention 30 giorni | `tests/test_history_ac.py::test_ac03_expired_execution_is_not_listed` |
| Periodo deterministico | `tests/test_history_query.py::test_period_vocabulary`, `::test_default_period_is_last_24_hours`, `::test_explicit_day_and_week`, `::test_n_days`, `::test_day_without_year_in_the_future_uses_the_previous_year` |
| Punteggiatura e preposizioni | `tests/test_history_query.py::test_trailing_punctuation_is_ignored`, `::test_leading_preposition_is_ignored` |
| Fallback LLM e ambiguità | `tests/test_history_query.py::test_llm_fallback_is_validated`, `::test_invalid_llm_answer_asks_for_precision`, `::test_ambiguous_period_is_not_guessed` |
| Clamp alla retention (anche LLM) | `tests/test_history_query.py::test_period_is_clamped_to_retention`, `::test_llm_window_is_clamped_to_retention` |
| Visibilità per ruolo | `tests/test_history_query.py::test_admin_sees_every_execution`, `::test_authorized_user_sees_only_visible_tasks`, `::test_unknown_role_gets_no_rows`, `::test_build_filter_rejects_unresolved_name` |
| Parsing, clamp e filtro degenere | `tests/test_history_query.py::test_strip_uses_the_longest_prefix`, `::test_generic_names_are_removed`, `::test_window_before_retention_is_empty` |
| Formato elenco | `tests/test_history_query.py::test_render_format` (verifica l'intestazione con la label), `::test_render_truncates_summary_and_rows`, `::test_render_empty`, `::test_saltata_is_visible`, `::test_null_outcome_is_rendered_as_dash`, `::test_unknown_task_falls_back_to_id`, `::test_render_sanitizes_newlines`, `::test_render_tolerates_unparsable_started_at` |
| Log della consultazione | `tests/test_history_query.py::test_query_logs_the_result_count`, `::test_unknown_role_is_logged_without_query` |
| Normalizzazione UTC e ordinamento | `tests/test_history.py::test_record_normalizes_offsets`, `::test_record_skipped_is_normalized`, `::test_query_orders_across_offsets`, `::test_purge_uses_utc_cutoff`, `::test_reset_uses_utc_cutoff`, `::test_skipped_note_is_preserved` |
| Log e error handling della retention | `tests/test_history.py::test_purge_logs_the_deleted_counts`, `tests/test_bootstrap.py::test_maintenance_logs_purge_failure` |
| Migrazione 005 | `tests/test_storage.py::test_migration_005_normalizes_offsets_and_naive_timestamps`, `tests/test_storage.py::test_migration_005_tolerates_unparsable_timestamps` |
| Asserzioni di migrazione aggiornate | `tests/test_storage.py::test_migration_creates_spec_tables`, `::test_migrate_is_idempotent`, `::test_migration_003_preserves_existing_executions`, `::test_migration_004_preserves_ids_and_index`; `tests/test_bootstrap.py` (versione attesa `005_executions_started_index`) |
| Comando `/history` | `tests/test_command_router.py::test_history_command_default`, `::test_history_command_with_period_and_task`, `::test_history_usage_for_unknown_argument` |
| Richiesta NL di storico | `tests/test_command_router.py::test_natural_history_request_does_not_reach_chat`, `::test_history_request_is_case_insensitive`, `::test_history_request_wins_over_task_list`, `::test_history_ambiguous_nl_asks_period`, `::test_history_degenerate_nl`, `::test_history_degenerate_command`, `::test_schedule_request_with_history_word_is_still_a_creation` |
| `HELP_TEXT` aggiornato | `tests/test_command_router.py::test_help_lists_history` |
| Wiring | `tests/test_bootstrap.py::test_build_exposes_history_query`, `::test_build_accepts_tz`, `tests/conftest.py` espone `history_query` |
| Nessuna migrazione di modello dati | `005_executions_started_index.sql` contiene solo normalizzazione e `CREATE INDEX` |
| BR-7 retention 30 giorni | `tests/test_history.py::test_purge_removes_old_executions_and_messages`, `tests/test_history_ac.py::test_ac03_expired_execution_is_not_listed` |
| BR-12 visibilità per ruolo | `tests/test_history_query.py::test_admin_sees_every_execution`, `::test_authorized_user_sees_only_visible_tasks` |
| BR-15 esiti | `tests/test_history_query.py::test_render_format`, `::test_saltata_is_visible` |
| BR-14 fuso e italiano | `tests/test_history_query.py::test_period_vocabulary`, `::test_dst_boundary_uses_wall_clock`, `::test_render_format` |
| Confine DST | `tests/test_history_query.py::test_dst_boundary_uses_wall_clock` |
| C-35 non duplicato | nessun nuovo job in `scheduler.py`; `tests/test_scheduler.py` invariato |

## Ordine di consegna

Codice-first: T1 (migrazione e normalizzazione) → T2 → T3 → T4 → T5 → T6 → T7 → T8, poi test T9,
poi AC end-to-end T10, poi documentazione T11 (dipendente da codice stabile), infine pubblicazione
T12. Il documento descrive il comportamento validato.

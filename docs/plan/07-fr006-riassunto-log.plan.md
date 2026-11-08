# Piano 07 — FR-006 Lettura e riassunto dei log

- **Voce roadmap:** `07 — FR-006 Lettura e riassunto log` (non spuntata)
- **Spec:** [07-fr006-riassunto-log.spec.md](../specs/07-fr006-riassunto-log.spec.md), Stato `New`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack, `## Roadmap`
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`: C-02 con `tasks.log_allowlist`, C-05, C-07 `read_file` con allowlist, C-08 con `read_logs`, C-10 `alert_admin`, C-13 `agente.jsonl` in `paths.logs`, migrazione 001), item 02 (`02-fr001-gestione-compiti`: C-15 con `TaskDraft.log_allowlist`, C-14 che estrae i percorsi dalla richiesta NL, C-17), item 03 (`03-fr002-esecuzione-programmata`: C-09 con tool loop, BR-4, consegna con admin implicito), item 05 (`05-fr004-domande-libere`: C-23 con `ChatToolContext.log_allowlist` vuota e cattura di `AgenteError`), item 06 (`06-fr005-ricerca-web-conferma`: C-27 gate, `read_logs` read-only eseguito senza conferma)
- **Dipendenze non consegnate:** item 08 (utenti e privacy), item 09 (storico esecuzioni), item 10 (avvisi admin)
- **Data piano:** 2026-10-29
- **Stato piano:** approvato 2026-10-29; eseguito T1–T9 (delivery history: voce 07)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-30 Allowlist Validator: `is_allowed(path, task) -> bool` con normalizzazione (`expanduser` + `resolve`, quindi `..` e symlink), rifiuto di percorso vuoto, non assoluto o mancante (argomento assente) e di allowlist vuota; un percorso **inesistente** ma dentro l'allowlist è autorizzato e viene segnalato da C-29 (flusso 4); log delle validazioni | codice | `src/agente/log_allowlist.py` |
| D-02 | Estensione C-07: `inspect_path(path, allowlist) -> PathInfo` (esiste / è file / è cartella / dimensione / leggibile senza aprire il contenuto), `read_file_tail(path, allowlist, *, max_chars) -> FileTail` (legge fino a `4 × max_chars` byte dalla coda e restituisce gli ultimi `max_chars` **caratteri**), `list_files(directory, allowlist, *, limit) -> DirectoryListing` (solo file regolari, non ricorsivo, conta sottocartelle e symlink, segnala il troncamento). Tutti e tre riusano il controllo di allowlist dell'adapter | codice | `src/agente/device.py` |
| D-03 | C-29 Log Reader: `read(paths, allowlist) -> LogContent`; valida ogni percorso con C-30, classifica file/cartella/inesistente/vuoto/illeggibile, legge la coda, applica i limiti, produce `LogEntry` per file, `notes` per gli esiti di cartella e il testo `rendered` con intestazioni esplicite; log di letture e rifiuti | codice | `src/agente/log_reader.py` |
| D-04 | Errore `LogAccessError(AgenteError)` con l'elenco dei percorsi rifiutati e il contenuto parziale nel messaggio; il limite `MAX_TOTAL_CHARS - 200` è applicato dall'handler di C-08 (`MAX_ERROR_PAYLOAD_CHARS`), non dall'eccezione: serve a segnalare AC-02 senza perdere i file consentiti | codice | `src/agente/errors.py` |
| D-05 | Estensione C-08: `read_logs` usa C-29 (file **o** cartella), schema e descrizione aggiornati, `default_registry(device, *, search=None, log_reader=None)` costruisce C-29 se assente; un percorso rifiutato solleva `LogAccessError` con il contenuto parziale | codice | `src/agente/tools.py` |
| D-06 | Estensione C-09: `LogAccessError` è un esito di tool non fatale in **entrambi** i rami di `_invoke_tool` (con e senza gate): avviso immediato all'admin, testo restituito al modello, percorso rifiutato annotato e **nota deterministica anteposta al risultato consegnato** (AC-02) | codice | `src/agente/execution.py` |
| D-07 | Test della voce: unit C-30, C-29, C-07 (coda, multibyte, elenco, symlink, illeggibile), C-08 (`read_logs` file/cartella/rifiuto/schema), C-09 (avviso, nota e prosecuzione), AC-01…AC-03 end-to-end, chat che resta rifiutata, asserzione di confine sul filesystem | test | `tests/test_log_allowlist.py`, `tests/test_log_reader.py`, `tests/test_device_gate.py`, `tests/test_tools.py`, `tests/test_execution.py`, `tests/test_log_ac.py`, `tests/test_chat.py`, `tests/test_boundaries.py`, `tests/conftest.py` |
| D-08 | Documento architettura della feature con diagrammi Mermaid (1 flowchart componenti, 3 sequenze) e limiti di lettura | documentazione | `docs/architecture/07-fr006-riassunto-log.md` |
| D-09 | Pubblicazione: roadmap `[x]`, stato spec 07 `Implemented` + note, delivery history, piano allineato, note di continuità su spec 01 (C-07 esteso), spec 03 (esito non fatale), spec 05 e architettura 05 (chat rifiutata per progetto) | documentazione | `docs/specs/constitution.md`, `docs/specs/07-fr006-riassunto-log.spec.md`, `docs/specs/01-agent-runtime.spec.md`, `docs/specs/03-fr002-esecuzione-programmata.spec.md`, `docs/specs/05-fr004-domande-libere.spec.md`, `docs/architecture/05-fr004-domande-libere.md`, `docs/delivery-history.md`, questo piano |

Nessuna tabella nuova e nessuna migrazione: `tasks.log_allowlist` esiste dalla 001 ed è già
letta/scritta da C-02 e popolata da C-15/C-14. Nessuna nuova leva di configurazione: i limiti di
lettura sono costanti interne assunte (P-A-02), non valori dichiarati dalle spec.

### Fuori scope di questa voce (dichiarato)

- **Autorizzazione della chat (D6):** `read_logs` resta rifiutato in chat (`ChatToolContext.log_allowlist`
  vuota). La spec 07 descrive solo i compiti; nessuna allowlist implicita viene inventata.
- **Storico esecuzioni da SQLite (D4):** AC-03 si soddisfa leggendo il file C-13 (`agente.jsonl` e
  rotazioni) autorizzato nel compito; nessuno strumento `read_executions` viene aggiunto (item 09).
- **Parsing dei log (D3):** nessun riconoscimento di formato, nessuna estrazione regex di errori e
  nessuna normalizzazione JSONL; il testo è passato al modello così com'è.
- **Ricorsione e pattern (D2):** nessuna discesa nelle sottocartelle, nessun glob di inclusione o
  esclusione; le sottocartelle e i symlink sono contati e segnalati.
- **Modifica dell'allowlist durante l'esecuzione:** vale quella salvata sul compito al momento della
  lettura, scritta solo da C-15 con conferma C-17.
- **Installazione/pacchetti, upload dei log, invio dei file grezzi:** la spec non li dichiara.
- **Vista di deployment:** non dichiarata dalla spec 07 e non necessaria a descrivere il
  comportamento; **gap registrato** esplicitamente.

## Decisioni che sbloccano il piano

Chiuse dall'operatore il 2026-10-29. D1–D3 rispondono alle tre domande tecniche aperte di spec 07;
D4–D6 chiudono i comportamenti che la spec lascia impliciti.

| # | Domanda aperta / conflitto | Decisione | Impatto |
|---|----------------------------|-----------|---------|
| D1 | Limite di dimensione e strategia di lettura (domanda aperta di spec 07) | **Coda**: ultimi **8.000 caratteri per file**, **20.000 caratteri complessivi** per chiamata (lo stesso tetto dell'output dei tool in `gate.MAX_OUTPUT_CHARS`, così il gate non tronca a metà), nota con dimensione originale e flag `troncato`. La lettura fisica è limitata a `4 × 8.000 = 32.000` byte, sufficienti a 8.000 caratteri UTF-8 nel caso peggiore | D-02, D-03, P-A-02, V-03; test di troncamento e multibyte |
| D2 | Lettura ricorsiva delle directory (domanda aperta di spec 07) | **Non ricorsiva**: solo i file regolari direttamente nella cartella autorizzata, massimo **20 file**, ordine alfabetico; sottocartelle e symlink non aperti e **contati** in una nota | D-02, D-03, V-08; test di cartella con sottocartelle e symlink |
| D3 | Formato dei log attesi (domanda aperta di spec 07) | **Testo libero, nessun parsing**: nessuna interpretazione, nessuna regex, nessun formato preferito. Le righe JSONL di C-13 restano testo leggibile | D-03, P-A-08; test con testo libero e con JSONL |
| D4 | AC-03 «riassunto delle esecuzioni e dei loro errori» | **Solo file C-13 in allowlist**: il compito autorizza `paths.logs` e `read_logs` legge `agente.jsonl` e le rotazioni come file normali. Nessun componente o strumento nuovo | D-03, D-05, V-07, P-A-12 |
| D5 | AC-02 «l'amministratore ne viene informato» | **Avviso esplicito + nota deterministica nel risultato**: C-29 non legge il percorso e lo riporta nel contenuto; C-09 invia un avviso immediato all'admin e antepone al testo consegnato una nota con i percorsi rifiutati, quindi il compito prosegue | D-04, D-05, D-06, V-04, V-09, P-A-05/P-A-06/P-A-20 |
| D6 | Lettura log in chat (architettura 05 lasciava aperto a item 07) | **Resta rifiutata**: `ChatToolContext.log_allowlist` resta vuota e `read_logs` è rifiutato. Nessuna autorizzazione implicita per l'admin: BR-13 vale anche in chat | D-01, D-05, V-06, P-A-15; test in `tests/test_chat.py` |

## Riparto di responsabilità tra componenti (anti-duplicazione)

| Componente | Possiede | Delega a | Non duplica perché |
|---|---|---|---|
| C-30 Allowlist Validator | policy «questo compito può leggere questo percorso?», normalizzazione e contenimento | nessuno: riceve il compito già caricato dal chiamante | C-07 applica un controllo proprio come ultima barriera, ma non conosce compiti né allowlist per compito |
| C-29 Log Reader | classificazione degli esiti, limiti, note, rendering | C-07 per ogni accesso al filesystem, C-30 per l'autorizzazione | C-07 non conosce «log» né limiti per compito; C-08 registra lo strumento, non legge |
| C-07 Device Adapter | accesso fisico: metadati del percorso, coda di un file, elenco dei file di una cartella | sistema operativo | C-29 non apre file né enumera directory: passa sempre da qui (Tech Stack, confine filesystem) |
| C-08 Tool Registry | schema `read_logs`, metadati read-only, costruzione di C-29 | C-29 per la lettura | C-08 non applica policy di percorso né limiti |
| C-09 Execution Engine | esito del compito, avviso admin, nota deterministica nel risultato, prosecuzione del tool loop | C-10 per l'invio, C-27 per l'esecuzione | C-29 non invia nulla: non ha C-10 fra le dipendenze |
| C-27 Action Gate | classificazione read-only e troncamento dell'output riuscito a `MAX_OUTPUT_CHARS` | C-08 | il tetto per chiamata di C-29 è allineato a quello del gate con un test di uguaglianza fra costanti, non con un import |

**C-30 e C-07 restano separati.** C-30 risponde a «questo compito può leggere questo percorso?» e
lavora su `task.log_allowlist`; C-07 risponde a «l'adapter può consegnare questo file?» e difende
anche i chiamanti che non passano da C-30. Entrambe normalizzano prima di confrontare, così `..` e
symlink non aggirano il controllo.

**C-29 non duplica C-09.** C-29 produce contenuto e note; chi decide l'esito del compito, il testo
consegnato e l'avviso all'admin è C-09. Nessuna notifica parte da C-29, che non ha C-10 fra le
dipendenze.

**C-02 è la fonte, non un accesso diretto.** La spec elenca C-02 fra le dipendenze di C-29/C-30; qui
il compito arriva già caricato da C-09/C-08, quindi nessuno dei due apre SQL (V-10). Il dato resta
quello di `tasks.log_allowlist`.

## Contratti (forma dei tipi)

```python
# C-30
class _HasLogAllowlist(Protocol):
    log_allowlist: Sequence[str]

class AllowlistValidator:
    def is_allowed(self, path: str | Path, task: _HasLogAllowlist) -> bool: ...

# C-07 (estensione)
@dataclass(frozen=True)
class PathInfo:
    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size: int
    readable: bool

@dataclass(frozen=True)
class FileTail:
    text: str          # ultimi max_chars caratteri
    size: int          # dimensione reale del file
    truncated: bool    # True se il file supera i byte letti o i caratteri resi

@dataclass(frozen=True)
class DirectoryListing:
    files: tuple[str, ...]
    skipped_dirs: int
    skipped_links: int
    truncated: bool

class DeviceAdapter:
    def inspect_path(self, path, allowlist) -> PathInfo: ...
    def read_file_tail(self, path, allowlist, *, max_chars: int = MAX_LOG_SLICE_CHARS) -> FileTail: ...
    def list_files(self, directory, allowlist, *, limit: int = MAX_LOG_FILES) -> DirectoryListing: ...

# C-29
@dataclass(frozen=True)
class LogEntry:
    path: str
    text: str
    exists: bool
    size: int
    truncated: bool
    note: str = ""

@dataclass(frozen=True)
class LogContent:
    entries: tuple[LogEntry, ...]
    refused: tuple[str, ...]
    notes: tuple[str, ...]
    rendered: str

class LogReader:
    def read(self, paths: Sequence[str], allowlist: Sequence[str]) -> LogContent: ...
```

- `read` è sincrona e non tocca la rete; viene eseguita dall'handler dentro `asyncio.to_thread`
  del gate (C-27), quindi non blocca l'event loop.
- Un percorso rifiutato **non** interrompe gli altri e non produce un `LogEntry`: finisce in
  `refused` e nel testo reso. `notes` raccoglie gli esiti di cartella (sottocartelle/symlink
  ignorati, troncamento dell'elenco, cartella senza file) e il troncamento complessivo.
- Un file illeggibile produce un `LogEntry` con `exists=True`, `text=""` e `note="illeggibile"`.
  Precedenza: se `PathInfo.readable` è falso C-29 non tenta la lettura; altrimenti un `DeviceError`
  di `inspect_path`/`read_file_tail`/`list_files` viene catturato e trasformato in nota. Anche un
  `GateError` di C-07 (divergenza fra la policy di C-30 e la barriera dell'adapter) diventa una nota
  `rifiutato dall'adapter`, non un guasto del compito.
- `read([])` restituisce `LogContent(entries=(), refused=(), notes=("nessun percorso richiesto",),
  rendered="Nessun percorso richiesto.")` (P-A-19).
- L'handler di C-08 solleva `LogAccessError` solo se `refused` non è vuoto, con `rendered` nel
  messaggio, troncato a `MAX_TOTAL_CHARS - 200`: il testo che C-09 o C-23 restituiscono al modello,
  prefisso compreso, resta sotto il tetto di 20.000 caratteri (P-A-20).
- `read_logs` mantiene un solo parametro `path` (file o cartella) per chiamata: C-29 accetta una
  lista, lo schema del tool no (V-08).

## Deviazioni pre-dichiarate (numerazione stabile per il documento 07)

| # | Deviazione | Fonte modificata | Motivo |
|---|---|---|---|
| V-01 | C-07 espone `inspect_path`, `read_file_tail`, `list_files` e i tipi `PathInfo`, `FileTail`, `DirectoryListing` oltre a `read_file`/`write_file`/`delete_file`/`run_command` | spec 01 C-07 | metadati del percorso, coda limitata ed elenco di cartella sono necessari a C-29 e il filesystem resta accessibile solo da C-07 (Tech Stack); `read_file` resta invariata |
| V-02 | `LogContent`/`LogEntry` hanno campi espliciti e una lista `notes` | spec 07 C-29 | la spec dichiara il tipo di ritorno e «testo grezzo troncato + flag esiste», non la forma; i campi rendono verificabili AC-01/AC-02 e separano rifiuti, file e note di cartella |
| V-03 | I limiti di lettura (8.000 caratteri per file, 32.000 byte letti, 20.000 caratteri per chiamata, 20 file) sono costanti di modulo | spec 07 «domande tecniche aperte» | D1/D2: la spec lascia i valori aperti e non dichiara chiavi di configurazione; aggiungerle estenderebbe C-01 senza mandato |
| V-04 | In esecuzione `LogAccessError` è un esito di tool non fatale | spec 03 C-09 (gli altri errori di tool sono fatali; `SearchError` è già un esito dalla voce 06) | D5/AC-02: un percorso non autorizzato è un evento previsto, non un guasto del compito; il compito prosegue e riporta il rifiuto |
| V-05 | `read_logs` accetta file **o** cartella e il suo schema/descrizione cambiano | spec 01 C-08 («legge un file di log») | AC-01 richiede una cartella autorizzata; C-29 è il lettore dichiarato da spec 07 |
| V-06 | Nessuna autorizzazione per la chat: `read_logs` resta rifiutato con allowlist vuota | architettura 05 (attendeva una decisione di spec 07) e spec 07 silente | D6: BR-13 vale anche in chat; nessuna allowlist implicita viene inventata |
| V-07 | AC-03 si soddisfa con il file C-13 autorizzato, non con la tabella `executions` | spec 07 §Modello dati (cita file **e** SQLite) | D4: un solo meccanismo di lettura, nessun componente nuovo; lo storico strutturato resta item 09 |
| V-08 | C-29 accetta più percorsi ma il tool ne espone uno per chiamata | spec 07 C-29 (`read(paths, allowlist)`) | modifica minima dello schema di C-08; il modello può chiamare `read_logs` più volte nello stesso compito |
| V-09 | `LogAccessError` attraversa C-27 (che cattura solo `SearchError`) e viene intercettato da C-09 in entrambi i rami di `_invoke_tool`; in chat resta `AgenteError` e C-23 lo traduce in testo | spec 06 C-27 e spec 03 C-09 / spec 05 C-23 | D5: il rifiuto deve essere insieme un esito di tool e un avviso all'admin; C-27 resta invariato e continua a propagare gli errori che non conosce |
| V-10 | C-29/C-30 non aprono SQL: ricevono il compito già caricato dal chiamante | spec 07 (dipendenze C-02 di C-29 e C-30) | il dato è quello di `tasks.log_allowlist`, già letto da C-02 in C-09/C-08; un secondo accesso sarebbe una duplicazione di C-02 |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita leggendo il solo frontmatter
di `.opencode/agents/*.md`, `.opencode/commands/*.md`, `.opencode/skills/*/SKILL.md` e
`opencode.json`; discovery per ruolo, nessun asset legato per filename. Gli asset dichiarati dal
runtime ma non presenti in `.opencode/` non sono stati scansionati.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-07, D-09 (codice, test, aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione di codice Python, test o configurazione | Etichettati *"no specialized capability discovered"*; si procede su spec 07 + constitution + pattern esistenti in `src/agente/` |
| D-08 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** (Phase 2 struttura e Phase 4 validazione); il produttore resta il Conductor |
| D-08 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 07 e dai documenti 02–06; assunzione P-A-01 |

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

## Checkpoint di struttura (D-08) — Phase 2

Eseguito in modalità delegata su `sdd-governor` il 2026-10-29 sulla **prima** versione del piano:
esito **NOT APPROVED** (nessun critical; 7 MAJOR, 15 MINOR). Remediation recepita in questa versione:

- **Contratto C-07 (F1/F3):** aggiunti `inspect_path` con `PathInfo` (esiste / file / cartella /
  dimensione / leggibile) e `FileTail`/`DirectoryListing`; l'«illeggibile» è un `LogEntry` con nota,
  dopo la cattura di `DeviceError` in C-29 (P-A-08).
- **Unità della coda (F2):** contratto in **caratteri** (ultimi 8.000), lettura fisica limitata a
  `4 × 8.000` byte, decodifica `utf-8` con `errors="replace"`; test sul confine multibyte.
- **Symlink (F4):** `DirectoryListing.skipped_links` e nota corrispondente.
- **`LogAccessError` (F5/F11/F20):** nuova V-09 sul passaggio attraverso C-27 e sulla cattura in
  entrambi i rami di C-09; messaggio limitato a `MAX_TOTAL_CHARS`; «tutti gli altri errori di tool
  restano fatali», con `SearchError` e `LogAccessError` come esiti.
- **Nota AC-02 (F6):** C-09 tiene l'elenco dei percorsi rifiutati per esecuzione e antepone una nota
  deterministica al testo consegnato (P-A-20); non dipende dal modello.
- **Percorsi relativi (F7):** solo percorsi assoluti sono autorizzati; un percorso relativo è
  rifiutato (P-A-18). C-15 continua a salvare le stringhe indicate dall'admin.
- **Dipendenze C-02 (F8/F9):** V-10 e riparto corretti.
- **Costanti e nomi (F10/F16):** `MAX_TOTAL_CHARS` di C-29 allineato a `gate.MAX_OUTPUT_CHARS` con un
  test di uguaglianza (non un import); i default dei metodi C-07 riferiscono le costanti
  `MAX_LOG_SLICE_CHARS`/`MAX_LOG_FILES`; P-A-02 cita il nome reale.
- **Struttura (F12/F13):** vista deployment registrata in §Fuori scope; flusso 4 assorbito nella
  sequenza di lettura consentita; aggiunta la sezione «Concorrenza e ciclo di vita».
- **Tipi e semantica (F14/F15/F22):** `task: _HasLogAllowlist` (Protocol); `refused` separato dagli
  `entries`; `notes` per le cartelle; `read([])` definito.
- **Tracciabilità e confini (F18/F19):** righe per illeggibile, cartella vuota, multibyte, schema
  `read_logs`; asserzione AST in `test_boundaries.py` (nessun `open`/`scandir`/`os` né I/O `pathlib` —
  `read_text`/`open`/`iterdir`/`stat` — in `log_reader.py` e `log_allowlist.py`); item 05 fra le dipendenze.
- **Chat (F21):** dichiarato che C-23 cattura già `AgenteError`: nessuna modifica a C-23.

Struttura applicabile dopo remediation: **Metadata** (Spec · Voce roadmap · Piano · Constitution ·
Data · Struttura dichiarata + P-A-01) · Contesto e obiettivi · Componenti (C-29, C-30, estensioni
C-07/C-08/C-09, riusati, flowchart) · Riparto · Modello di dominio · Modello dati
(`tasks.log_allowlist`, nessuna tabella nuova, rimando all'ER di `02-fr001-gestione-compiti.md`) ·
Limiti e strategia di lettura · Flussi: 7.1 «lettura consentita» (AC-01), 7.2 «percorso rifiutato»
(AC-02), 7.3 «log dell'agente» (AC-03), tutte `sequenceDiagram` · Concorrenza e ciclo di vita
(`LogReader` senza stato; rifiuti accumulati per esecuzione e passati lungo `_work` → `_invoke_tool`,
non su un attributo del motore; handler in `asyncio.to_thread`; nessun lock aggiuntivo oltre a quello
per compito) ·
Integrazioni · Sicurezza · Requisiti non funzionali · Rischi e assunzioni · Domande aperte chiuse ·
Fuori scope · Deviazioni (V-01…V-10) · Tracciabilità (AC-01…AC-03, BR-13). Per ogni componente:
Responsabilità · Interfaccia · Input/Output · Dipendenze · Error handling · Osservabilità ·
Sicurezza. Nessuna vista deployment e nessun diagramma di stato: la spec 07 non li dichiara e non
introduce nuovi stati (gli stati di esecuzione restano quelli di spec 03). Nessun ER nuovo:
`log_allowlist` è già documentato nella 01/02.

- **Seconda passata:** **APPROVED** — nessun critical, nessun major; 11 minor residui recepiti in
  questa versione: semantica «assente» vs «inesistente» (D-01), precedenza `readable` e cattura di
  `DeviceError`/`GateError` in C-29 (P-A-08/P-A-21), tetto del messaggio `LogAccessError` riservando
  il prefisso dei chiamanti (P-A-20), attribuzione del clip a 500 caratteri a C-09, politica di
  budget esaurito (P-A-22), contenuto di «Concorrenza e ciclo di vita», nomi delle sequenze 7.1–7.3,
  ordine `expanduser`/assolutezza, modulo delle costanti, nessuna modifica ad `app.py`, asserzione
  AST estesa a `pathlib`, test dell'illeggibile con stub.
- **Phase 4 (2026-10-29):** **APPROVED** — nessun critical, nessun major; finding minor recepiti
  nell'artefatto (cartella `paths.logs`, osservabilità di C-30, symlink «risolti» invece di «mai
  seguiti», `GateError` da elenco e da ispezione per-file, «tre estensioni», soglia 500 e riserva
  300, troncamento del testo reso, margine di 200 caratteri con test, test reali in chat, due
  sottosezioni per wiring e riusati, righe di tracciabilità per C-30) e nel piano (riferimento al
  test di budget, attribuzione del clip a C-08, rischio del loop esaurito). La pubblicazione è
  avvenuta in Phase 5 (delivery history: voce 07).

## Assunzioni del piano (non dichiarate da spec 07)

> **P-A-01** Struttura del documento di architettura derivata da spec 07 e dai documenti 02–06, non
> da un template: in `docs/templates/` esistono solo `template.spec.md` e `template.constitution.md`.

> **P-A-02** Limiti (D1/D2): `device.MAX_LOG_SLICE_CHARS = 8_000` caratteri di coda per file
> (lettura fisica fino a `4 × 8.000 = 32.000` byte), `log_reader.MAX_TOTAL_CHARS = 20_000` caratteri
> per chiamata (intestazioni comprese), `device.MAX_LOG_FILES = 20` file per cartella. Il tetto di
> 20.000 coincide con `gate.MAX_OUTPUT_CHARS`; l'uguaglianza è verificata da un test, non da un import.

> **P-A-03** Formato del testo reso: per ogni file un'intestazione `== <percorso> (<dimensione> byte[,
> coda di 8000 caratteri][, troncato]) ==`, il testo, poi le note (`file inesistente`, `file vuoto`,
> `illeggibile`). Per un rifiuto: `== PERCORSO NON AUTORIZZATO: <percorso> ==`. Le note di cartella
> (`sottocartelle ignorate: N`, `symlink ignorati: N`, `elenco troncato`, `cartella senza file`) e il
> troncamento complessivo compaiono in coda al testo.

> **P-A-04** I file di una cartella sono letti in ordine alfabetico e, se superano 20, l'elenco è
> troncato con nota.

> **P-A-05** Il rifiuto è registrato in `LogContent.refused` e nel testo reso; non produce
> `LogEntry`. L'handler di C-08 solleva `LogAccessError` solo se `refused` non è vuoto, con
> `rendered` nel messaggio, così l'admin riceve l'avviso e il modello il contenuto parziale.

> **P-A-06** Testo dell'avviso admin: `Log non autorizzati per il compito <nome>: <percorsi>`,
> inviato con `NotificationService.alert_admin` (best effort, un invio fallito non cambia l'esito).

> **P-A-07** I symlink non sono mai seguiti: un symlink dentro la cartella è ignorato e contato; un
> percorso richiesto che si risolve fuori dall'allowlist è rifiutato da C-30.

> **P-A-08** Decodifica `utf-8` con `errors="replace"`; nessun rilevamento di file binari (D3).
> `PathInfo.readable` è il pre-check: se è falso C-29 non legge. `DeviceError` di
> `inspect_path`/`read_file_tail`/`list_files` e `GateError` di C-07 sono catturati per voce e
> riportati come nota (`illeggibile`, `rifiutato dall'adapter`), mai fatali (P-A-21).

> **P-A-09** Nessuna nuova chiave di configurazione e nessuna migrazione: i limiti sono costanti e
> `tasks.log_allowlist` esiste dalla 001. `AgentApp.build` e `app.py` non cambiano: C-29 è costruito
> dentro `default_registry`; il wiring resta quello della voce 06.

> **P-A-10** Lo schema di `read_logs` resta `{"path": string}`; la descrizione dice «file o cartella
> autorizzata». Nessun parametro `paths` (V-08).

> **P-A-11** C-07 mantiene il proprio controllo di allowlist: C-30 è la policy per compito, C-07 è
> l'ultima barriera dell'adapter, anche per i chiamanti che non passano da C-30.

> **P-A-12** Per AC-03 l'admin autorizza `paths.logs` alla creazione; il compito legge
> `agente.jsonl` e le rotazioni come file normali. Il JSONL non viene interpretato (D3) ma resta
> testo leggibile: le righe `esecuzione conclusa`/`esecuzione fallita` e i record `ERROR` sono nel
> contenuto.

> **P-A-13** Una cartella senza file regolari produce una nota `cartella senza file` e il conteggio
> delle sottocartelle e dei symlink ignorati; nessun `LogEntry` viene creato per la cartella.

> **P-A-14** L'ordine di `read` è quello dei percorsi richiesti; l'ordine dei file di una cartella è
> alfabetico. Il budget complessivo si consuma in questo ordine.
>
> **P-A-22** Budget esaurito: quando restano meno di 500 caratteri, C-29 smette di leggere e chiude
> il testo con una sola nota `limite complessivo raggiunto: N file non letti`. I file non letti non
> producono intestazioni. Con il tetto di 20.000 caratteri un compito che autorizza molti file deve
> restringere l'allowlist o chiedere un secondo `read_logs` (rischio dichiarato).

> **P-A-15** La chat resta invariata: `ChatToolContext.log_allowlist` è vuota, `read_logs` produce un
> rifiuto e C-23 lo traduce in testo perché cattura già `AgenteError`. Nessuna modifica a `chat.py`.

> **P-A-16** Il contratto degli handler di C-08 non cambia: `read_logs` restituisce una stringa
> (`LogContent.rendered`); `LogContent` resta interno a C-29/C-08.

> **P-A-17** `read_file` resta invariata e continua a servire i chiamanti esistenti e i test della
> fondazione; `read_file_tail` è aggiuntiva.

> **P-A-18** Sono autorizzati solo i percorsi **assoluti**: un percorso relativo è rifiutato da C-30
> e segnalato, perché la base di risoluzione sarebbe la directory di lavoro del processo e non una
> scelta dell'admin. C-15 continua a salvare le stringhe indicate.

> **P-A-19** `read([])` non è un errore: `LogContent` vuoto con nota `nessun percorso richiesto`.
>
> **P-A-21** Ordine di normalizzazione: prima `expanduser` (quindi `~/logs` è ammesso e diventa
> assoluto), poi il controllo di assolutezza. Un percorso relativo puro è rifiutato (P-A-18).

> **P-A-20** La nota AC-02 nel risultato è deterministica: C-09 accumula i percorsi rifiutati per
> esecuzione e antepone al testo consegnato `Log non autorizzati: <percorsi>`, anche se il modello
> non li cita. La nota entra anche nel `summary` registrato (troncato a 500 caratteri da
> `ExecutionEngine._clip` in C-09, non da C-11). Il messaggio di `LogAccessError` è limitato a
> `MAX_TOTAL_CHARS - 200`, così anche il ramo con gate di C-23, che aggiunge `errore dello
> strumento: `, resta sotto il tetto di 20.000 caratteri (N11).

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | C-30 Allowlist Validator | D-01 | `is_allowed` vero per il file autorizzato e per un file dentro la cartella autorizzata; falso per percorso fuori, `..` che esce, symlink che punta fuori, percorso vuoto, percorso relativo (P-A-18), allowlist vuota; log di validazione; nessun accesso al contenuto dei file |
| T2 | Estensioni C-07 | D-02 | `inspect_path` distingue file/cartella/inesistente e riporta dimensione e leggibilità; `read_file_tail` restituisce gli ultimi `max_chars` caratteri, `size` reale, `truncated`, gestisce UTF-8 multibyte, rispetta l'allowlist; `list_files` elenca solo file regolari, non ricorsivo, ignora e conta symlink, conta sottocartelle e troncamento, rispetta l'allowlist |
| T3 | C-29 Log Reader | D-03 | file letto con intestazione e nota; file inesistente/vuoto/illeggibile segnalato senza eccezione; cartella enumerata con note su sottocartelle, symlink e cartella vuota; rifiuto in `refused` e nel testo; budget 20.000 rispettato; `read([])` definito; log di letture e rifiuti |
| T4 | C-08 `read_logs` | D-04, D-05 | handler usa C-29; `default_registry(device)` e `default_registry(device, search=...)` continuano a funzionare; `log_reader` iniettabile; percorso rifiutato → `LogAccessError` con contenuto parziale; schema/descrizione aggiornati; metadati read-only invariati |
| T5 | C-09 avviso, nota e prosecuzione | D-06 | `LogAccessError` catturato in entrambi i rami di `_invoke_tool`: avviso admin con i percorsi, testo restituito al modello, nota anteposta al risultato consegnato, compito `ok`; **tutti** gli altri errori di tool restano fatali; senza gate il comportamento resta fail-safe |
| T6 | Test unit e di confine | D-07 | `test_log_allowlist.py`, `test_log_reader.py`, estensioni a `test_device_gate.py`, `test_tools.py`, `test_execution.py`, `test_chat.py`, `test_boundaries.py` (asserzione AST su `log_reader.py`); `pytest` verde |
| T7 | AC-01…AC-03 end-to-end | D-07 | AC-01 cartella con errori → risultato con riassunto ed elenco errori; AC-02 percorso fuori allowlist → non letto, avviso admin, nota nel risultato, compito prosegue; AC-03 log dell'agente da `paths.logs` → riassunto di esecuzioni ed errori |
| T8 | Documento architettura 07 | D-08 | sezioni obbligatorie presenti; Mermaid validi (1 flowchart, 3 sequenze 7.1–7.3); sezione «Concorrenza e ciclo di vita» non vuota; checkpoint Phase 2 e Phase 4 **APPROVED**; vista deployment e ER dichiarati assenti con motivo |
| T9 | Pubblicazione | D-09 | roadmap 07 `[x]`; spec 07 `Implemented (2026-10-29)` + note; note di continuità su spec 01/03/05 e architettura 05; delivery history con esito, gap e V-01…V-10; piano marcato eseguito |

## Dipendenze

- Item 01: C-02 (`tasks.log_allowlist`), C-07 (`read_file`, allowlist), C-08 (`read_logs`), C-10
  (`alert_admin`), C-13 (`agente.jsonl`, `paths.logs`), migrazione 001.
- Item 02: C-15 con `TaskDraft.log_allowlist`, C-14 che estrae i percorsi dalla richiesta NL, C-17.
- Item 03: C-09 con tool loop, BR-4, consegna; admin destinatario implicito.
- Item 05: C-23 con `ChatToolContext.log_allowlist` vuota e cattura di `AgenteError` (D6/P-A-15).
- Item 06: C-27 con classificazione read-only, nessuna conferma per `read_logs`, troncamento a
  `MAX_OUTPUT_CHARS`.
- **Item 08 (non consegnato):** utenti e privacy; qui conta solo il ruolo già risolto da C-04.
- **Item 09 (non consegnato):** storico esecuzioni strutturato; AC-03 resta sul file C-13 (D4).
- **Item 10 (non consegnato):** avvisi di sistema; qui solo l'avviso puntuale di percorso rifiutato.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Lettura fuori allowlist per path traversal o symlink | C-30 risolve `..` e symlink prima di confrontare (P-A-07); C-07 ripete il controllo; test con `../` e symlink che esce |
| Percorso relativo interpretato rispetto a una CWD imprevista | solo percorsi assoluti (P-A-18), rifiuto esplicito e test |
| Errore recente perso nel troncamento a coda | D1 legge la coda (dove stanno gli errori recenti), la nota dichiara il troncamento e il modello può chiedere un secondo `read_logs`; limite noto documentato |
| File enorme che satura memoria o event loop | `read_file_tail` legge solo gli ultimi 32.000 byte e gira dentro `asyncio.to_thread` del gate |
| Coda che taglia un code point UTF-8 | si leggono 4 byte per carattere e si decodifica con `errors="replace"`, poi si prendono gli ultimi `max_chars` caratteri; test dedicato |
| Cartella con migliaia di file | massimo 20 file, ordine alfabetico e nota di troncamento (P-A-04) |
| File illeggibile che uccide il compito | `DeviceError` catturato da C-29 e trasformato in nota (P-A-08) |
| Rifiuto non visto dall'admin | avviso esplicito da C-09 **e** nota deterministica anteposta al risultato (D5/P-A-20); test AC-02 |
| `LogAccessError` che cambia semantica al gate | V-09: C-27 invariato (cattura solo `SearchError`); cattura in C-09 su entrambi i rami; test con e senza gate |
| Rifiuto che uccide il compito | `LogAccessError` è un esito di tool: il compito prosegue e consegna il resto (V-04) |
| Doppia policy C-07/C-30 che diverge | stesso algoritmo di normalizzazione, test incrociati sullo stesso caso; C-30 è la policy, C-07 la barriera; un `GateError` dell'adapter diventa una nota, non un guasto (P-A-08/P-A-21) |
| Deriva fra il tetto di C-29 e quello del gate | test di uguaglianza fra `log_reader.MAX_TOTAL_CHARS` e `gate.MAX_OUTPUT_CHARS` (P-A-02) |
| Il modello chiede un file non citato dall'admin | rifiuto + avviso: l'allowlist è quella del compito, non quella del prompt |
| AC-03 confuso con lo storico SQLite | D4/V-07 dichiarati; il file C-13 contiene esiti ed errori; lo storico strutturato resta item 09 |
| Lettura in chat non autorizzata | allowlist vuota (D6), test dedicato; nessuna deroga per l'admin |
| Log con contenuti personali | l'allowlist è una scelta esplicita dell'admin; i dati restano sul telefono, il riassunto transita da DeepSeek come per ogni compito (privacy: spec 08) |
| Regressione su item 03/06 | `read_logs` resta read-only e senza conferma; `SearchError` invariato; tutti gli altri errori restano fatali; test esistenti mantenuti |
| Loop di tool esaurito dopo un rifiuto | l'avviso all'admin parte subito; l'esecuzione chiude `errore` senza consegnare la nota AC-02: limite dichiarato (MAX_TOOL_ROUNDS di C-09), non un percorso di autorizzazione |

## Criteri di validazione (done della voce)

1. `PYTHONPATH=src:.deps python3 -m pytest` verde (inclusi i test di item 01–06).
2. AC-01: cartella autorizzata con log contenenti errori → risultato con riassunto ed elenco degli
   errori.
3. AC-02: percorso non autorizzato → non letto, avviso immediato all'admin, **nota deterministica**
   nel risultato, compito `ok`.
4. AC-03: compito con `paths.logs` autorizzato → riassunto delle esecuzioni e dei loro errori.
5. File inesistente, vuoto e illeggibile segnalati nel risultato senza far fallire il compito.
6. Troncamento: file oltre 8.000 caratteri → coda + nota + dimensione; cap complessivo 20.000;
   nessun carattere rotto su UTF-8 multibyte.
7. Cartella: solo file regolari, non ricorsiva, symlink ignorati e contati, massimo 20 file, note
   esplicite; cartella senza file segnalata.
8. Chat: `read_logs` resta rifiutato; nessuna lettura fuori allowlist in nessun percorso.
9. Il filesystem dei log è toccato solo da C-07 (asserzione di confine); nessun import fuori dai
   confini; type hints sulle interfacce pubbliche; errori espliciti; italiano di default.
10. Documento D-08 conforme alla struttura dichiarata e approvato dal checkpoint Phase 4.
11. Catena di tracciabilità ricostruibile: voce roadmap 07 → spec 07 → binding → task → artefatti →
    validazione → pubblicazione.

## Tracciabilità attesa (compilata a Publish)

| Requisito / criterio | Test previsto |
|---|---|
| AC-01 riassunto + errori da cartella | `tests/test_log_ac.py::test_ac01_authorized_folder_is_summarized_with_errors` |
| AC-02 percorso non autorizzato | `tests/test_log_ac.py::test_ac02_unauthorized_path_is_refused_and_admin_is_alerted`, `tests/test_log_allowlist.py::test_path_outside_the_allowlist_is_refused` |
| AC-03 log dell'agente | `tests/test_log_ac.py::test_ac03_agent_logs_are_summarized` |
| BR-13 solo percorsi autorizzati | `tests/test_log_allowlist.py::test_file_inside_an_allowed_folder_is_allowed`, `::test_traversal_is_refused`, `::test_symlink_escape_is_refused`, `::test_relative_path_is_refused`, `tests/test_device_gate.py::test_read_file_tail_enforces_the_allowlist` |
| File inesistente/vuoto/illeggibile segnalato | `tests/test_log_reader.py::test_missing_file_is_reported`, `::test_empty_file_is_reported`, `::test_unreadable_file_is_reported` (stub di `DeviceAdapter` con `PathInfo.readable=False` e con `DeviceError`, non `chmod`), `::test_adapter_gate_error_is_a_note` |
| File grandi troncati con nota | `tests/test_log_reader.py::test_large_file_is_truncated_to_the_tail`, `::test_utf8_boundary_is_not_broken`, `::test_global_budget_is_respected` |
| Directory non ricorsiva | `tests/test_log_reader.py::test_directory_is_not_recursive_and_reports_subfolders`, `::test_symlinks_are_skipped_and_counted`, `::test_empty_directory_is_reported`, `::test_more_than_twenty_files_are_reported`, `::test_global_budget_is_respected` |
| Classificazione file/cartella/inesistente | `tests/test_device_gate.py::test_inspect_path_classifies_file_folder_and_missing` |
| Formato libero (JSONL leggibile) | `tests/test_log_reader.py::test_jsonl_agent_log_is_passed_as_text` |
| Nessun percorso richiesto | `tests/test_log_reader.py::test_empty_request_is_not_an_error` |
| Strumento read-only e senza conferma | `tests/test_device_gate.py::test_default_registry_marks_device_actions_as_gated`, `tests/test_gate.py::test_read_only_action_is_executed_without_approval` |
| Schema `read_logs` file/cartella | `tests/test_tools.py::test_read_logs_accepts_a_folder`, `::test_read_logs_schema_mentions_a_folder` |
| Rifiuto non fatale + avviso + nota | `tests/test_execution.py::test_log_access_error_alerts_admin_and_execution_continues`, `::test_log_access_error_note_is_delivered` |
| Chat senza autorizzazione | `tests/test_chat.py::test_log_reading_stays_refused_in_chat`, `::test_real_read_logs_is_refused_in_chat` |
| C-30: percorso vuoto, allowlist vuota, voci non valide, `~` | `tests/test_log_allowlist.py::test_empty_path_is_refused`, `::test_empty_allowlist_refuses_everything`, `::test_invalid_allowlist_entries_are_ignored`, `::test_home_prefix_is_expanded` |
| Margine del messaggio di errore | `tests/test_tools.py::test_refusal_payload_is_capped` |
| Tetto allineato al gate | `tests/test_log_reader.py::test_total_budget_matches_the_gate_limit` |
| Osservabilità C-29/C-30 | `tests/test_log_reader.py::test_reads_and_refusals_are_logged`, `tests/test_log_allowlist.py::test_validation_is_logged` |
| Confini: filesystem solo da C-07 | `tests/test_boundaries.py::test_log_modules_do_not_access_the_filesystem` (AST su `log_reader.py` e `log_allowlist.py`) |

## Ordine di consegna

Codice-first: T1 → T2 → T3 → T4 → T5, poi test T6, poi AC end-to-end T7, poi documentazione T8
(dipendente da codice stabile), infine pubblicazione T9. Il documento descrive il comportamento
validato.

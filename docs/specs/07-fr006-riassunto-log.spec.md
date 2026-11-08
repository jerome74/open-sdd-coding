# Specifica 07 — Lettura e riassunto dei log (FR-006)

- **ID:** `07-fr006-riassunto-log`
- **Stato:** Implemented (2026-10-29)
- **Requisiti collegati:** FR-006; BR-13
- **Dipendenze:** `01-agent-runtime`, `02-fr001-gestione-compiti`, `03-fr002-esecuzione-programmata`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

L'amministratore deve poter creare un compito (spec 02) che **legge i log** e ne produce un
**riassunto**, evidenziando eventuali **errori**. I log possono essere quelli dell'agente stesso o di
altri programmi/script eseguiti in Termux. L'agente legge **solo** da file o cartelle **autorizzati
dall'amministratore**; percorsi non autorizzati non vengono letti e la cosa viene segnalata (BR-13).

## Panoramica architetturale

Riutilizza: Task Manager (C-15), Execution Engine (C-09), LLM Client (C-05), Device Adapter (C-07),
Notification (C-10), Storage (C-02). La lettura avviene tramite lo strumento `read_logs` del Tool
Registry (C-08).

Componenti specifici:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-29 | Log Reader | Legge file/cartelle consentiti, produce il testo da riassumere |
| C-30 | Allowlist Validator | Verifica i percorsi contro l'allowlist del compito |

## Progettazione componenti

### C-29 — Log Reader
- **Responsabilità:** leggere i log dai percorsi del compito, normalizzarli e prepararli per il
  riassunto; rilevare file inesistenti/vuoti.
- **Interfaccia pubblica:** `read(paths, allowlist) -> LogContent`.
- **Dipendenze:** C-07 (accesso file), C-30, C-02.
- **Input:** percorsi + allowlist. **Output:** contenuto log (eventuale, troncato a un limite).
- **Error handling:** percorso non autorizzato → non letto, segnalato; file inesistente o vuoto →
  segnalato nel risultato; file troppo grandi → troncamento con nota.
- **Osservabilità:** log percorsi letti/rifiutati e dimensione.
- **Sicurezza:** nessuna lettura fuori dall'allowlist (BR-13).

### C-30 — Allowlist Validator
- **Responsabilità:** verificare che ogni percorso richiesto sia dentro l'allowlist definita
  **per il compito** alla creazione (decisione #10-spec, decisione utente).
- **Interfaccia pubblica:** `is_allowed(path, task) -> bool`.
- **Dipendenze:** C-02 (`tasks.log_allowlist`).
- **Input:** percorso + compito. **Output:** esito.
- **Error handling:** percorso vuoto/assente → non autorizzato.
- **Osservabilità:** log validazioni.
- **Sicurezza:** confronto normalizzato (risoluzione di `..`/symlink) per evitare escape.

## Modello di dominio

- **Compito log:** compito (spec 02) con `log_allowlist` valorizzata (uno o più percorsi file/
  cartella).
- **Percorso autorizzato:** file o directory indicata dall'admin alla creazione.
- **Contenuto log:** testo grezzo troncato + flag `esiste`.

## Modello dati

`tasks.log_allowlist` (JSON) in `01-agent-runtime`. Nessuna nuova tabella. I risultati dei compiti
log finiscono in `executions` come per gli altri compiti. I log dell'agente stesso sono in
`C-13` (file) e in SQLite.

## Flussi di dati

1. **Creazione compito log:** admin → spec 02 con percorso/cartella da leggere → `log_allowlist`
   salvata al compito.
2. **Esecuzione:** C-09 → C-29 legge i percorsi → C-30 valida ogni percorso → contenuto → C-05
   produce riassunto + elenco errori → C-20 invia ai destinatari → C-11 registra.
3. **Percorso non autorizzato:** C-30 nega → C-29 non legge → il risultato segnala il rifiuto e
   l'admin ne è informato.
4. **File inesistente/vuoto:** C-29 segnala nel risultato.

## Progettazione integrazioni

- **Filesystem (via C-07):** lettura file/cartelle.
- **Telegram:** invio risultato ai destinatari.
- **DeepSeek:** riassunto ed estrazione errori.

## Requisiti di sicurezza

- Lettura limitata all'allowlist del compito (BR-13); validazione difensiva contro path traversal.
- Nessuna azione modificante nella lettura log.
- I risultati vanno ai destinatari autorizzati (BR-12).

## Requisiti non funzionali

- Esecuzione entro il limite di 10 minuti (BR-4); file grandi troncati con nota.
- Lingua del riassunto: italiano (BR-14).

## Rischi e assunzioni

- **Rischio:** log molto grandi → troncamento può nascondere errori; mitigare con lettura delle code
  o campionamento (da definire).
- **Assunzione:** l'allowlist è definita a livello di compito (decisione utente).

## Domande tecniche aperte

- Limite di dimensione per file e strategia (testa/coda/finestra temporale).
- Lettura ricorsiva delle directory (sì/no, profondità, pattern inclusione/esclusione).
- Formato dei log attesi (testo libero vs strutturato).

## Criteri di accettazione

- **AC-01** Data una cartella autorizzata contenente log con errori, quando il compito viene
  eseguito, allora il risultato contiene un riassunto e l'elenco degli errori trovati.
- **AC-02** Dato un percorso non autorizzato, quando il compito tenta di leggerlo, allora la lettura
  non avviene e l'amministratore ne viene informato.
- **AC-03** Dato l'amministratore chiede un riassunto dei log dell'agente stesso, quando il compito
  viene eseguito, allora riceve il riassunto delle esecuzioni e dei loro errori.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-006, BR-13, §8 (journey 2), §10, §12.

## Assunzioni

- **A-01** Allowlist di percorsi definita per-compito alla creazione (decisione utente).

## Domande in sospeso

- Limiti dimensione, ricorsione directory, formato log atteso (vedi sopra).

**Risposte (operatore, 2026-10-29 — decisioni D1/D2/D3 del piano 07):** coda di **8.000 caratteri
per file** e **20.000 caratteri per chiamata** (lettura fisica fino a 32.000 byte, UTF-8),
**directory non ricorsiva** con massimo 20 file e sottocartelle/symlink contati, **testo libero senza
parsing**. Le decisioni D4–D6 chiudono i comportamenti impliciti: AC-03 si soddisfa con il file C-13
autorizzato, AC-02 con avviso esplicito all'admin più nota deterministica nel risultato, e la chat
resta senza autorizzazione alla lettura dei log.

## Valutazione di confidenza

**Alta** — FR-006 documentato con criteri di accettazione; le domande su dimensioni, ricorsione e
formato sono state chiuse il 2026-10-29 (D1–D3).

## Note di implementazione (2026-10-29)

- **Componenti:** C-29 `src/agente/log_reader.py` (`read(paths, allowlist) -> LogContent` con
  `LogEntry`/`notes`/`refused`/`rendered`), C-30 `src/agente/log_allowlist.py`
  (`is_allowed(path, task)`, normalizzazione `expanduser` + `resolve`, solo percorsi assoluti).
  Estensioni: C-07 (`inspect_path`, `read_file_tail`, `list_files` con tipi `PathInfo`/`FileTail`/
  `DirectoryListing`), C-08 (`read_logs` accetta file o cartella, `log_reader` iniettabile), C-09
  (`LogAccessError` come esito di tool, avviso admin, nota anteposta al risultato). `errors.py`:
  `LogAccessError`. `app.py` invariato.
- **Decisioni:** D1 coda 8.000 caratteri/file e 20.000 per chiamata; D2 directory non ricorsiva,
  max 20 file; D3 testo libero; D4 AC-03 dal file C-13; D5 avviso esplicito + nota deterministica;
  D6 chat senza autorizzazione.
- **Deviazioni:** V-01…V-10 nel documento
  [07-fr006-riassunto-log.md](../architecture/07-fr006-riassunto-log.md). V-01 estende C-07, V-04/V-09
  rendono il rifiuto un esito non fatale, V-06 chiude la nota lasciata aperta dall'architettura 05.
- **Modello dati:** nessuna tabella e nessuna migrazione; `tasks.log_allowlist` resta l'unica fonte
  dell'autorizzazione.
- **Sicurezza:** lettura solo entro l'allowlist del compito, `..` e symlink risolti prima del
  confronto, nessuna azione modificante, nessuna lettura in chat, avviso all'admin per ogni rifiuto.
- **Test:** 386 raccolti, tutti verdi (`PYTHONPATH=src:.deps python3 -m pytest`), inclusi AC-01…AC-03
  in `tests/test_log_ac.py` e i test di confine sul filesystem.
- **Gap:** lo storico strutturato delle esecuzioni resta item 09 (AC-03 legge il file C-13); la
  lettura in chat resta non disponibile (D6); la latenza reale e i permessi del filesystem su
  dispositivo non sono verificabili in questo ambiente; se il loop di tool esaurisce i cicli dopo un
  rifiuto il compito chiude `errore` senza consegnare la nota AC-02 (l'avviso è già partito).
- **Documento:** [07-fr006-riassunto-log.md](../architecture/07-fr006-riassunto-log.md), checkpoint di
  struttura `sdd-governor` Phase 4 **APPROVED** (2026-10-29).

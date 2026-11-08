# Specifica 06 — Ricerca web e strumenti con conferma (FR-005)

- **ID:** `06-fr005-ricerca-web-conferma`
- **Stato:** Implemented (2026-10-25)
- **Requisiti collegati:** FR-005; BR-2, BR-3
- **Dipendenze:** `01-agent-runtime`, `03-fr002-esecuzione-programmata`, `05-fr004-domande-libere`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

Durante un compito o una chat l'agente decide quali strumenti usare. Le **azioni di sola lettura** e
la **ricerca web** vengono eseguite senza conferma. Per qualsiasi **azione che modifica il
telefono** (eseguire comandi, scrivere/cancellare file, installare — definizione A4), l'agente si
ferma e invia all'amministratore una richiesta con cosa vuole fare e perché, e i pulsanti
**Approva / Rifiuta**. Solo dopo "Approva" l'azione viene eseguita. Una richiesta senza risposta
entro **15 minuti** è considerata rifiutata (BR-3). La conferma va **sempre all'amministratore**,
anche quando la richiesta nasce da un utente autorizzato (A5).

## Panoramica architetturale

Riutilizza: Tool Registry (C-08), Device Adapter (C-07), Notification (C-10), Role Guard (C-04),
Storage (C-02).

Componenti specifici:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-26 | Web Search Adapter | Ricerca web read-only con provider pluggable |
| C-27 | Action Gate | Classifica le azioni e impone la conferma per quelle modificanti |
| C-28 | Approval Manager | Crea/gestisce le richieste di conferma con timeout |

## Progettazione componenti

### C-26 — Web Search Adapter
- **Responsabilità:** eseguire ricerche web tramite un provider configurabile; normalizzare i
  risultati per il LLM.
- **Interfaccia pubblica:** `search(query, k) -> list[Result]`.
- **Dipendenze:** C-01 (`search.provider`, `search.api_key`), HTTP.
- **Input:** query. **Output:** risultati (titolo, URL, estratto).
- **Error handling:** provider non raggiungibile → retry BR-8; provider non configurato → strumento
  non disponibile, errore esplicito.
- **Osservabilità:** log query/latenza/esito.
- **Sicurezza:** read-only, **nessuna conferma** (BR-2); chiave provider `600`.

### C-27 — Action Gate
- **Responsabilità:** classificare ogni azione richiesta come `read_only` o `modifying`; per le
  modificanti, bloccare l'esecuzione finché non c'è approvazione.
- **Interfaccia pubblica:** `classify(action) -> Gate`, `execute_if_allowed(action, approval)`.
- **Dipendenze:** C-08, C-28, C-07.
- **Input:** azione proposta. **Output:** esecuzione o attesa/rifiuto.
- **Error handling:** azione modificante senza approvazione → non eseguita; approvazione scaduta →
  rifiuto.
- **Osservabilità:** log classificazione e decisione.
- **Sicurezza:** **nessuna** azione modificante senza approvazione admin (BR-2); la conferma va solo
  all'admin (A5).

### C-28 — Approval Manager
- **Responsabilità:** creare la richiesta di conferma (azione + motivo + pulsanti), inviarla
  all'admin, raccogliere la risposta, applicare il timeout di 15 minuti.
- **Interfaccia pubblica:** `request(action, reason, requester) -> Approval`,
  `resolve(id, decision)`.
- **Dipendenze:** C-02, C-10, C-04.
- **Input:** azione + motivo + richiedente. **Output:** esito `approved`/`rejected`.
- **Error handling:** nessuna risposta entro 15 min → `rejected` e azione non eseguita (BR-3).
- **Osservabilità:** log richieste e tempi di risoluzione.
- **Sicurezza:** il destinatario della richiesta è **sempre** l'admin (A5); l'utente autorizzato
  richiedente non riceve mai i pulsanti di approvazione.

## Modello di dominio

- **Azione:** operazione richiesta dall'agente, con classificazione `read_only`/`modifying`.
- **RichiestaConferma:** `id`, `azione`, `motivo`, `richiedente`, `stato`, `scadenza`.

Stati richiesta (BR-15 esteso dal §10): `pending` → `approved` | `rejected` (per timeout).

## Modello dati

Tabella `approvals` (spec 01): `id`, `action`, `reason`, `requested_by`, `status`, `created_at`,
`expires_at` (created_at + 15 min), `resolved_at`.

## Flussi di dati

1. **Azione read-only / ricerca web:** C-27 classifica `read_only` → C-08/C-26 esegue direttamente →
   nessuna conferma.
2. **Azione modificante:** C-27 classifica `modifying` → C-28 crea richiesta → C-10 invia all'admin
   con Approva/Rifiuta → esito:
   - **Approva** entro 15 min → C-27 esegue via C-07 → l'agente prosegue;
   - **Rifiuta** o timeout → azione non eseguita; l'agente prosegue senza o comunica l'impossibilità.
3. **Richiesta da utente autorizzato:** identica, ma i pulsanti vanno all'admin (A5).

## Progettazione integrazioni

- **Telegram:** inline keyboard `Approva`/`Rifiuta`; callback di risposta.
- **Web search provider:** adapter pluggable (decisione #6): Brave/Tavily/Google CSE/SerpAPI.
- **Device Adapter (C-07):** esecuzione effettiva dell'azione approvata.

## Requisiti di sicurezza

- Nessuna azione modificante senza approvazione admin (BR-2) — controllo centrale, non aggirabile
  dagli altri componenti.
- Approvazione sempre e solo all'admin (A5).
- Timeout 15 min = rifiuto (BR-3).
- Ricerca web read-only, nessuna conferma (BR-2).

## Requisiti non funzionali

- Timeout approvazione: 15 minuti (BR-3).
- Retry provider/LLM: 3×1 min (BR-8).

## Rischi e assunzioni

- **Rischio:** classificazione errata di un'azione modificante come read-only → mitigato da policy
  whitelist per tool (`requires_approval`) e gate fail-safe (in dubbio → richiedere conferma).
- **Rischio:** admin offline → azioni modificanti bloccate; accettato (A5, BR-3).

## Domande tecniche aperte

- Elenco/criterio esatto di classificazione delle azioni modificanti (whitelist vs rilevazione).
- Comportamento di default se la classificazione è incerta (raccomandato: richiedere conferma).
- Provider di ricerca di default in config.

## Criteri di accettazione

- **AC-01** Dato l'agente deve cancellare un file, quando prepara l'azione, allora l'amministratore
  riceve la richiesta con Approva/Rifiuta e il file non viene toccato prima dell'approvazione.
- **AC-02** Data una richiesta di conferma senza risposta, quando passano 15 minuti, allora l'azione
  è rifiutata e non viene eseguita.
- **AC-03** Dato l'agente deve fare una ricerca web, quando la esegue, allora non chiede alcuna
  conferma.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-005, BR-2/3, §6 (A4, A5), §8 (journey 4), §9, §10, §11.

## Assunzioni

- **A-01** Provider di ricerca pluggable via config (decisione #6).
- **A-02** Gate centralizzato con default fail-safe (in dubbio → conferma).

## Domande in sospeso

- Criterio di classificazione azioni; provider di default (vedi sopra).

**Risposte (operatore, 2026-10-25 — decisioni D1/D2 del piano 06):** la classificazione usa i
metadati di C-08 (`read_only`/`requires_approval`) con fail-safe; uno strumento sconosciuto non viene
eseguito e i metadati contraddittori sono rifiutati alla registrazione. Il provider di default è
**Tavily** (`search.provider = "tavily"`), con adapter pluggable; gli altri candidati restano
estensioni future.

## Valutazione di confidenza

**Alta** — FR-005 documentato con criteri di accettazione e regole esplicite; le due domande aperte
sono state chiuse il 2026-10-25 (D1/D2).

## Note di implementazione (2026-10-25)

- **Decisioni che chiudono le domande aperte:** D1 classificazione con whitelist dei metadati di C-08
  e fail-safe (strumento sconosciuto rifiutato, metadati contraddittori rifiutati alla registrazione);
  D2 provider di ricerca default **Tavily**, adapter pluggable. Altre decisioni del piano: D3 dentro
  un'esecuzione vince BR-4 (10 min) sull'attesa di approvazione; D4 le richieste `pending` sono
  scartate al riavvio; D5 `web_search` resta esposto con errore esplicito se il provider manca;
  D6 approvazioni solo con bottoni e solo dall'admin.
- **Deliverable:** C-26 `src/agente/web_search.py`, C-27 `src/agente/gate.py`, C-28
  `src/agente/approvals.py`; estensioni C-08 (`approved`, regola di registrazione, `web_search`),
  C-09/C-23 (tool modificanti via gate, rifiuto come esito), C-14 (callback `approval:`), C-10
  (`send_approval`), C-02 (`reject_pending`), C-01 (`provider` default `tavily`); wiring in `app.py`.
  Nessuna migrazione: `approvals` esiste dalla 001.
- **Deviazioni:** V-01…V-16 nel documento [06-fr005-ricerca-web-conferma.md](../architecture/06-fr005-ricerca-web-conferma.md).
  V-04/V-07/V-10/V-12 modificano comportamenti dichiarati in spec 01/03/05: note di continuità nelle
  rispettive sedi.
- **Sicurezza:** solo l'admin approva (doppia verifica C-14/C-28); timeout 15 min = rifiuto; ricerca
  read-only senza conferma; chiave del provider mai nei log; nessuna richiesta sopravvive al riavvio.
- **Test:** 334 raccolti, tutti verdi (`PYTHONPATH=src:.deps python3 -m pytest`), inclusi AC-01…AC-03
  in `tests/test_approval_ac.py` e la chiusura di AC-06 di spec 05.
- **Gap:** nessuno strumento `install` è dichiarato da C-08 (A4 lo nomina); la latenza reale di BR-17
  resta da misurare sul dispositivo; BR-4 interrompe l'attesa, non un handler già avviato in thread
  (P-A-19); i provider Brave/Google CSE/SerpAPI non sono implementati.
- **Documento:** [06-fr005-ricerca-web-conferma.md](../architecture/06-fr005-ricerca-web-conferma.md),
  checkpoint di struttura `sdd-governor` Phase 4 **APPROVED** (2026-10-25).

## Nota di continuità (2026-11-01, voce 08)

Il callback `approval:` di C-28 resta invariato. La voce 08 ha spostato l'instradamento dei callback
prima del rifiuto agli utenti `UNKNOWN` e ha aggiunto i prefissi `authorize:` (C-33) e `consent:`
(C-32); il registro è esaustivo e un prefisso sconosciuto resta `ignored`.

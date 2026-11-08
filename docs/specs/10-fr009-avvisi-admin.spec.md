# Specifica 10 — Avvisi all'amministratore (FR-009)

- **ID:** `10-fr009-avvisi-admin`
- **Stato:** Implemented (2026-11-03)
- **Requisiti collegati:** FR-009; BR-4, BR-8, BR-9, BR-10
- **Dipendenze:** `01-agent-runtime`, `03-fr002-esecuzione-programmata`, `11-fr010-riavvio-liveness`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

L'amministratore deve ricevere un **avviso Telegram** tempestivo quando:
1. un compito **fallisce** (dopo i tentativi di BR-8) o **supera i 10 minuti**, con nome del compito
   e motivo;
2. la **batteria** dell'S24 scende sotto il **15%** (BR-9);
3. il telefono è rimasto **offline per più di un'ora** (avviso inviato al rientro online, BR-10);
4. la **chiave DeepSeek** risulta scaduta, non valida o senza credito.

Se l'agente è completamente fuori uso non può avvisare: il **segnale di vita** quotidiano (spec 11)
serve a rilevare questa situazione **per assenza**.

## Panoramica architetturale

Riutilizza: Notification Service (C-10), Device Adapter (C-07), LLM Client (C-05), Execution Engine
(C-09), Storage (C-02), Scheduler (C-06).

Componenti specifici:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-36 | Alert Service | Compone e invia gli avvisi all'admin |
| C-37 | Device Monitor | Sorveglia batteria e connettività, rileva il rientro online |
| C-38 | Credential Monitor | Rileva problemi della chiave DeepSeek |

## Progettazione componenti

### C-36 — Alert Service
- **Responsabilità:** raccogliere gli eventi di anomalia e inviare un avviso all'admin, con
  deduplicazione per non ripetere lo stesso avviso.
- **Interfaccia pubblica:** `alert(kind, detail)`.
- **Dipendenze:** C-10, C-04, C-02.
- **Input:** evento (fallimento compito, timeout, batteria, offline, chiave). **Output:** messaggio
  all'admin.
- **Error handling:** invio fallito → retry BR-8; se Telegram è irraggiungibile l'avviso non può
  partire (coperto dalla logica liveness).
- **Osservabilità:** log avvisi inviati/deduplicati.

### C-37 — Device Monitor
- **Responsabilità:** leggere periodicamente batteria e stato di connessione; rilevare il
  superamento delle soglie e il periodo offline.
- **Interfaccia pubblica:** `check_battery()`, `check_online()`, `offline_since() -> ts`.
- **Dipendenze:** C-07 (`battery_level`, `is_online`), C-06.
- **Input:** stato device. **Output:** eventi verso C-36.
- **Error handling:** lettura batteria non disponibile → log, nessun avviso spurio.
- **Osservabilità:** log valori e soglie.
- **Sicurezza:** sola lettura.

### C-38 — Credential Monitor
- **Responsabilità:** rilevare risposte DeepSeek di autenticazione/credito insufficiente e generare
  un avviso specifico.
- **Interfaccia pubblica:** `on_llm_error(http_status, body)`.
- **Dipendenze:** C-05, C-36.
- **Input:** errore LLM. **Output:** evento verso C-36.
- **Error handling:** distinzione tra errore di credenziale e errore transitorio (retry BR-8).
- **Osservabilità:** log tipo di errore.

## Modello di dominio

- **Avviso:** `kind` (`task_failed` | `task_timeout` | `battery_low` | `offline_resumed` |
  `credential`), `detail`, `sent_at`.
- **Soglie:** batteria < 15% (BR-9); offline > 1 h (BR-10); timeout 10 min (BR-4); fallimento dopo
  3 retry (BR-8).

## Modello dati

`settings` conserva i marcatori: `last_online_at`, `offline_since`, `battery_last_alert`,
`liveness_last_sent`. Nessuna nuova tabella obbligatoria; eventualmente una tabella `alerts` per la
deduplicazione.

## Flussi di dati

1. **Fallimento/timeout compito:** C-09 conclude con `errore`/`interrotto` → C-36 → C-10 → admin.
2. **Batteria:** C-37 rileva < 15% → C-36 → admin.
3. **Offline prolungato:** C-37 registra `offline_since`; al rientro, se offline > 1 h → C-36 avvisa
   con il periodo di assenza.
4. **Chiave DeepSeek:** C-05 riceve errore di credenziale → C-38 → C-36 → admin.

## Progettazione integrazioni

- **Telegram:** invio avvisi all'admin.
- **Termux:API:** batteria, connettività.
- **DeepSeek API:** segnalazione errori di credenziale.

## Requisiti di sicurezza

- Gli avvisi vanno **solo** all'admin.
- Nessun contenuto sensibile nei messaggi di avviso oltre a nome compito/motivo.

## Requisiti non funzionali

- Tempestività: avviso al rientro per l'offline > 1 h; immediato per fallimento/timeout/batteria/
  chiave.
- Deduplicazione per evitare raffiche.

## Rischi e assunzioni

- **Rischio:** batteria non leggibile (Termux:API assente) → nessun avviso batteria; segnalato a
  livello di runtime.
- **Rischio:** Telegram irraggiungibile → l'avviso non parte; coperto da liveness (spec 11).

## Domande tecniche aperte

- Frequenza di campionamento batteria/connettività.
- Soglia di deduplicazione (né ripetere ogni check né perdere escalation).
- Rilevamento offline: assenza di rete vs processo non attivo (condiviso con spec 11).

## Criteri di accettazione

- **AC-01** Dato un compito che fallisce dopo 3 tentativi, quando viene dichiarato fallito, allora
  l'amministratore riceve un avviso con nome e motivo.
- **AC-02** Data la batteria al 14%, quando l'agente lo rileva, allora l'amministratore riceve un
  avviso.
- **AC-03** Dato il telefono offline 2 ore, quando torna online, allora l'amministratore riceve un
  avviso con il periodo di assenza.
- **AC-04** Data la chiave DeepSeek senza credito, quando l'agente prova a usarla, allora
  l'amministratore riceve un avviso specifico.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-009, BR-4/8/9/10, §10, §12.

## Assunzioni

- **A-01** Batteria e connettività lette via Termux:API (decisione #5).
- **A-02** Lo stato offline è dedotto da C-37; definizione condivisa con spec 11.

## Domande in sospeso

- Frequenza campionamento, deduplicazione, definizione di offline (vedi sopra).

## Valutazione di confidenza

**Alta** — FR-009 documentato con soglie esplicite; i dettagli di campionamento e deduplicazione sono
stati chiusi il 2026-11-03 (D2–D4).

## Note di implementazione (2026-11-03)

- **Componenti:** C-36 `src/agente/alerts.py` (`alert`, `alert_threadsafe`, `bind_loop`, `close`);
  C-37 `src/agente/device_monitor.py` (`check_battery`, `check_online`, `is_online`, `offline_since`);
  C-38 `src/agente/credential_monitor.py` (`on_llm_error`).
- **Estensioni:** C-05 callback `on_credentials_error` e `LLMCredentialsError.status`; C-09 avvisi
  `task_timeout`/`task_failed`; C-19 `monitor` al posto di `device` e nessun `settings`; C-06
  `schedule_battery`; C-01 `limits.battery_check_s = 300`; `AgentApp` con `alerts`,
  `device_monitor`, `credentials`, bind del loop e `close()` in `stop`.
- **Decisioni:** D1 confini con spec 11; D2 batteria ogni 5 min; D3 scaglioni di 5 punti; D4
  credenziali una volta all'ora; D5 offline = rete assente; D6 un avviso per esecuzione, credenziali
  solo da C-38.
- **Deviazioni:** V-01…V-17 nel documento
  [10-fr009-avvisi-admin.md](../architecture/10-fr009-avvisi-admin.md).
- **Test:** 596 raccolti, tutti verdi (`PYTHONPATH=src:.deps python3 -m pytest`), inclusi
  AC-01…AC-04 in `tests/test_alerts_ac.py`.
- **Gap:** un invio offline fallito non viene ritentato oltre BR-8 (coperto dalla liveness di spec
  11); un'oscillazione 14→15→14 al valore di soglia produce un nuovo avviso a ogni campionamento;
  `AgentApp.build` con `LLMClient` iniettato non riceve il callback di C-38; BR-16 non misurato con
  test di carico; riavvio e segnale di vita restano a spec 11.
- **Documento:** [10-fr009-avvisi-admin.md](../architecture/10-fr009-avvisi-admin.md), checkpoint di
  struttura `sdd-governor` Phase 4 **APPROVED** (2026-11-03).

## Nota di continuità (2026-11-04, voce 11)

`liveness_last_sent` è ora scritto da C-40 solo dopo un segnale di vita inviato con successo; C-39
lo legge per riportare il segnale mancato nel messaggio di ripartenza. `human_duration` di C-36 è
pubblica e riusata da C-41. L'invio di un avviso offline fallito resta coperto dalla liveness solo
per assenza: un segnale mancato con processo vivo e rete assente è riportato al prossimo avvio, non
al rientro di rete.

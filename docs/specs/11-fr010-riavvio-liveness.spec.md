# Specifica 11 — Riavvio automatico e segnale di vita (FR-010)

- **ID:** `11-fr010-riavvio-liveness`
- **Stato:** Implemented (2026-11-04)
- **Requisiti collegati:** FR-010; BR-5, BR-8, BR-11
- **Dipendenze:** `01-agent-runtime`, `03-fr002-esecuzione-programmata`
- **Priorità:** Must
- **Data:** 2026-10-07

## Contesto funzionale

L'agente deve mantenersi attivo nel tempo **senza interventi manuali**. Dopo un crash dell'agente o
un riavvio del telefono, riparte da solo, **recupera i compiti saltati** (come in FR-002/BR-5) e
invia all'amministratore un **messaggio di ripartenza** (es. *"Sono di nuovo attivo — offline dalle X
alle Y, recuperati N compiti"*). Ogni giorno alle **8:00** invia all'admin un **segnale di vita**
("tutto ok", BR-11).

Se l'agente era offline alle 8:00, al rientro segnala il segnale mancato insieme al messaggio di
ripartenza. Se DeepSeek o Telegram non rispondono, valgono i 3 tentativi a 1 minuto (BR-8).

## Panoramica architetturale

Riutilizza: Supervisor (C-12), Scheduler (C-06), Recovery Handler (C-19), Notification (C-10),
Storage (C-02), Device Adapter (C-07), History (C-11).

Componenti specifici:

| ID | Componente | Ruolo |
|----|-----------|-------|
| C-39 | Boot Recovery | Al riavvio, ripristina stato, registra i job e recupera i compiti |
| C-40 | Liveness Scheduler | Invia il segnale di vita quotidiano alle 8:00 |
| C-41 | Restart Notifier | Compone e invia il messaggio di ripartenza con periodo di assenza |

## Progettazione componenti

### C-39 — Boot Recovery
- **Responsabilità:** all'avvio/riavvio, acquisire il wake-lock, caricare i job attivi, riprendere
  lo stato persistito e attivare il recupero dei compiti saltati.
- **Interfaccia pubblica:** `on_start() -> RecoverySummary`.
- **Dipendenze:** C-12, C-06, C-19, C-18, C-02.
- **Input:** stato persistito (`next_run`, `offline_since`, `last_online_at`). **Output:** job
  ripristinati + esecuzioni di recupero.
- **Error handling:** avvio parziale → log e retry; DeepSeek/Telegram non raggiungibili → BR-8.
- **Osservabilità:** log avvio con periodo di assenza e compiti recuperati.
- **Sicurezza:** nessuna azione privilegiata; ripristino fedele dello stato.

### C-40 — Liveness Scheduler
- **Responsabilità:** inviare ogni giorno alle 8:00 (timezone telefono) il segnale di vita
  all'admin; segnare l'esito in `settings`.
- **Interfaccia pubblica:** `send_liveness()`.
- **Dipendenze:** C-06, C-10, C-02.
- **Input/Output:** messaggio all'admin; `liveness_last_sent` aggiornato.
- **Error handling:** invio fallito → retry BR-8; se fallisce del tutto, resta traccia per il
  rilevamento per assenza.
- **Osservabilità:** log invio/segnale mancato.

### C-41 — Restart Notifier
- **Responsabilità:** comporre il messaggio di ripartenza con periodo di assenza e numero di compiti
  recuperati; segnalare l'eventuale segnale delle 8:00 non inviato.
- **Interfaccia pubblica:** `notify_restart(recovery_summary, offline_period, liveness_missed)`.
- **Dipendenze:** C-10, C-39, C-40, C-02.
- **Error handling:** invio fallito → retry BR-8.
- **Osservabilità:** log invio ripartenza.

## Modello di dominio

- **Sessione agente:** periodo di attività con inizio/fine; `offline_since`, `last_online_at`.
- **RecoverySummary:** `missed_count`, `recovered`, `offline_period`, `liveness_missed`.
- **Segnale di vita:** evento quotidiano alle 8:00.

## Modello dati

`settings`: `offline_since`, `last_online_at`, `liveness_last_sent`, `last_start_at`. Gli job
ripristinati stanno in `apscheduler_jobs`; le esecuzioni di recupero in `executions` (trigger
`recovery`).

## Flussi di dati

1. **Riavvio:** processo parte (C-12, autostart boot) → C-39 acquisisce wake-lock, ripristina i job →
   C-19 recupera **una volta** i compiti saltati (BR-5) → C-41 invia il messaggio di ripartenza con
   periodo di assenza e N recuperati.
2. **Segnale di vita:** C-06 scatta alle 8:00 → C-40 invia "tutto ok" → aggiorna `liveness_last_sent`.
3. **Segnale mancato:** se alle 8:00 l'agente era offline, al rientro C-41 include "segnale delle
   8:00 non inviato — offline dalle X alle Y".
4. **Retry:** errori DeepSeek/Telegram → 3 tentativi a 1 min (BR-8).

## Progettazione integrazioni

- **Termux / Android:** autostart via `~/.termux/boot/`, `termux-wake-lock` per la continuità.
- **APScheduler:** job liveness e recupero.
- **Telegram:** messaggi di ripartenza e segnale di vita.

## Requisiti di sicurezza

- I messaggi di sistema vanno solo all'admin.
- Ripristino fedele dello stato; nessuna azione privilegiata implicita.

## Requisiti non funzionali

- Attivo per settimane senza riavvii manuali (FR §12).
- Segnale di vita ogni giorno alle 8:00 (BR-11).
- Recupero: una sola occorrenza (BR-5).
- Retry: 3×1 min (BR-8).

## Rischi e assunzioni

- **Rischio:** Android termina il processo nonostante wake-lock → mitigato da autostart boot +
  Supervisor; validare sul dispositivo.
- **Rischio:** distinzione tra "crash" e "riavvio telefono" → il recupero è identico; il messaggio
  può differire.
- **Assunzione A1:** S24 sempre acceso e connesso; in caso contrario l'agente non lavora.

## Domande tecniche aperte

- Rilevamento affidabile del riavvio dispositivo vs crash processo e del periodo di assenza.
- Meccanismo di autostart su Android recente (limitazioni batteria/OEM).
- Definizione condivisa di "offline" (con spec 10).

## Criteri di accettazione

- **AC-01** Dato il telefono viene riavviato, quando torna acceso, allora l'agente riparte senza
  intervento e l'amministratore riceve il messaggio di ripartenza.
- **AC-02** Dato l'agente attivo, quando sono le 8:00, allora l'amministratore riceve il segnale di
  vita.
- **AC-03** Dato l'agente offline alle 8:00, quando torna attivo, allora il messaggio di ripartenza
  indica che il segnale delle 8:00 non è stato inviato e il periodo di assenza.
- **AC-04** Dato l'agente rimasto attivo per settimane, quando si controlla lo storico, allora non
  risultano riavvii manuali necessari.

## Fonti documentali

- `docs/input/functional-requirements.md` FR-010, BR-5/8/11, §6 (A1), §8 (journey 5), §12, §13.

## Assunzioni

- **A-01** Autostart via `~/.termux/boot/` + wake-lock (decisione #4).
- **A-02** Recupero una sola occorrenza al rientro (decisione #8).

## Domande in sospeso

- Rilevamento riavvio/periodo di assenza e limitazioni OEM (vedi sopra).

## Valutazione di confidenza

**Alta** — FR-010 documentato con criteri di accettazione; residui su meccanismi Android da validare
sul dispositivo.

## Note di implementazione (2026-11-04)

- **Componenti:** C-39 `src/agente/boot.py` (`on_start`, `RecoverySummary`, `OfflinePeriod`);
  C-40 `src/agente/liveness.py` (`send_liveness`, `liveness_last_sent`); C-41
  `src/agente/restart.py` (`notify_restart`).
- **Estensioni:** C-19 `last_summary`/`RecoveryStats`; C-06 `schedule_liveness` (`liveness:send`,
  `CronTrigger` con timezone dello scheduler); C-01 validazione stretta di `limits.liveness_at`;
  C-36 `human_duration` pubblica; `AgentApp` con `boot`, `liveness`, `restart_notifier`, log del
  fallimento gateway e `notify_restart` dopo `on_start`.
- **Decisioni:** D1 wake-lock/autostart restano negli script; D2 messaggio a ogni avvio con
  `last_start_at` precedente; D3 segnale mancato solo al riavvio; D4 periodo da `last_online_at` con
  fallback; D5 `last_summary` additivo; D6 nessuna distinzione crash/riavvio.
- **Deviazioni:** V-01…V-13 nel documento
  [11-fr010-riavvio-liveness.md](../architecture/11-fr010-riavvio-liveness.md).
- **Test:** 646 raccolti, tutti verdi (`PYTHONPATH=src:.deps python3 -m pytest`), inclusi
  AC-01…AC-04 in `tests/test_restart_ac.py`.
- **Gap:** riavvio reale, autostart e limitazioni OEM da validare sul dispositivo (AC-01/AC-04);
  un invio di ripartenza fallito non viene ritentato oltre BR-8; un segnale mancato con processo
  vivo e rete assente è riportato solo al prossimo avvio; un'occorrenza può andare persa se
  `next_run` avanza prima di un rientro `resumed`; crash-loop produce messaggi ravvicinati.
- **Documento:** [11-fr010-riavvio-liveness.md](../architecture/11-fr010-riavvio-liveness.md),
  checkpoint di struttura `sdd-governor` Phase 4 **APPROVED** (2026-11-04).

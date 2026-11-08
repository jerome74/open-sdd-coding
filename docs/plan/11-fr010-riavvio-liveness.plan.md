# Piano 11 — FR-010 Riavvio automatico e segnale di vita

- **Voce roadmap:** `11 — FR-010 Riavvio e liveness` (non spuntata)
- **Spec:** [11-fr010-riavvio-liveness.spec.md](../specs/11-fr010-riavvio-liveness.spec.md), Stato `New`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack,
  §Pattern e vincoli architetturali, `## Roadmap`
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`: C-01 con `limits.liveness_at`, C-02
  `settings`, C-03 gateway con retry BR-8, C-06 scheduler con job store persistente, C-07 device,
  C-10 `alert_admin`, C-11 history, C-12 supervisor), item 03
  (`03-fr002-esecuzione-programmata`: C-18 registrar, C-19 `recover_missed`/`check_connectivity`,
  BR-5 una sola occorrenza), item 10 (`10-fr009-avvisi-admin`: C-36/C-37/C-38, `last_online_at`,
  `offline_since`, `limits.liveness_at` già presente nella forma, `AlertService` con dedup,
  `close()`)
- **Dipendenze non consegnate:** nessuna: è l'ultima voce della roadmap
- **Data piano:** 2026-11-04
- **Stato piano:** approvato 2026-11-04; eseguito T1–T12 (delivery history: voce 11)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-39 Boot Recovery: `on_start() -> RecoverySummary`; all'ingresso calcola periodo di assenza e segnale mancato, poi scheduler in pausa, sync marcatori, recupero via C-19, resume, scrittura `last_start_at`; log di avvio | codice | `src/agente/boot.py` |
| D-02 | C-40 Liveness Scheduler: `send_liveness() -> bool`; testo «tutto ok», invio via C-10, `liveness_last_sent` scritto solo dopo invio riuscito, log invio/fallimento | codice | `src/agente/liveness.py` |
| D-03 | C-41 Restart Notifier: `notify_restart(recovery_summary, offline_period, liveness_missed) -> bool`; testo di ripartenza con periodo e compiti recuperati, riga sul segnale mancato, invio solo all'admin | codice | `src/agente/restart.py` |
| D-04 | C-19: `last_summary` additivo (`RecoveryStats`: mancate, recuperate, fallite, saltate, rinviate) senza cambiare il ritorno `list[ExecutionResult]`; azzeramento all'ingresso di `recover_missed`/`check_connectivity` | codice | `src/agente/recovery.py` |
| D-05 | C-06: job cron liveness `schedule_liveness(callback, *, at="08:00")`, `LIVENESS_JOB_ID = "liveness:send"`, entry point module-level con errori isolati; registrato a ogni avvio con `replace_existing=True` e trigger ricalcolato da now | codice | `src/agente/scheduler.py` |
| D-06 | C-01: validazione **stretta** di `limits.liveness_at` come `HH:MM` a due cifre con ora 0–23 e minuti 0–59; nessuna chiave nuova | configurazione | `src/agente/config.py`, `config/config.example.toml` (solo commento se serve) |
| D-07 | C-36: espone `human_duration` (rinomina dell'helper privato, aggiunto a `__all__`) per il riuso da C-41; comportamento invariato | codice | `src/agente/alerts.py` |
| D-08 | Wiring `AgentApp`: costruzione di C-39/C-40/C-41, campi `boot`/`liveness`/`restart_notifier`, registrazione di `schedule_liveness` prima di `boot.on_start()`, `start` che delega a `on_start` e poi chiama `notify_restart` dopo `gateway.start`; `try/except Exception` attorno a `gateway.start()` con `logger.error("avvio gateway fallito", exc_info=True)` e `raise` (il gateway non solleva `AgenteError`) | codice | `src/agente/app.py` |
| D-09 | Test unit: C-39/C-40/C-41, `last_summary` di C-19, job liveness di C-06, validazione `liveness_at`, `human_duration`, fake scheduler e harness | test | `tests/test_boot.py`, `tests/test_liveness.py`, `tests/test_restart.py`, `tests/test_recovery.py`, `tests/test_scheduler.py`, `tests/test_config.py`, `tests/test_bootstrap.py`, `tests/test_scheduled_ac.py`, `tests/test_alerts.py` |
| D-10 | AC-01…AC-04 end-to-end con dipendenze finte; AC-04 usa uno scheduler finto che persiste `next_run` in `settings` (o il registrar reale) per rendere discriminante l'idempotenza | test | `tests/test_restart_ac.py` |
| D-11 | Documento di architettura con Mermaid (1 flowchart componenti, 4 sequenze: riavvio, liveness, segnale mancato, retry) e tabelle di marcatori/testi/regole | documentazione | `docs/architecture/11-fr010-riavvio-liveness.md` |
| D-12 | Pubblicazione: roadmap `[x]`, stato spec 11 `Implemented` + note, delivery history, piano allineato, note di continuità su spec 01 (C-06/C-12, `liveness_at`), spec 03 (C-18/C-19 e `last_summary`), spec 10 (`liveness_last_sent` ora scritto; `human_duration` esposto da C-36; ripartenza e limite dell'invio offline fallito) e architetture 01/03/10 (arch 10: `human_duration` pubblico e `liveness_last_sent` scritto da C-40) | documentazione | `docs/specs/constitution.md`, `docs/specs/11-fr010-riavvio-liveness.spec.md`, `docs/specs/01-agent-runtime.spec.md`, `docs/specs/03-fr002-esecuzione-programmata.spec.md`, `docs/specs/10-fr009-avvisi-admin.spec.md`, `docs/architecture/01-agent-runtime.md`, `docs/architecture/03-fr002-esecuzione-programmata.md`, `docs/architecture/10-fr009-avvisi-admin.md`, `docs/delivery-history.md`, questo piano |

Nessuna tabella nuova e nessuna migrazione: `settings` (chiave/valore) è già nel modello dati di
spec 01 e conserva `offline_since`, `last_online_at`, `liveness_last_sent`, `last_start_at`. I job
ripristinati restano in `apscheduler_jobs`; le esecuzioni di recupero in `executions` con trigger
`recovery`. Nessuna nuova dipendenza esterna: lo scheduler è C-06, l'invio C-10/C-03, lo stato
C-02, il recupero C-19.

### Fuori scope di questa voce (dichiarato)

- **Wake-lock e autostart:** restano nello script `scripts/boot/start-agent.sh` (già presente:
  `termux-wake-lock`, trap di unlock, loop di riavvio con backoff) e in `scripts/boot/90-agent.sh`
  per `~/.termux/boot/` (D1/V-01). C-39 non chiama C-07: le sue dipendenze dichiarate non lo
  includono e un'azione di sistema al boot non passa dal gate C-27.
- **Distinzione riavvio telefono vs crash processo:** non rilevabile in modo affidabile da Termux;
  un solo testo di ripartenza (D6/V-06), come la spec stessa ammette nei rischi.
- **Segnale mancato al rientro di rete senza riavvio:** resta al messaggio di ripartenza (D3/V-09);
  l'avviso `offline_resumed` di item 10 copre il rientro di rete.
- **Notifiche di ripartenza multiple per crash-loop:** nessuna soglia inventata (D2); rischio
  dichiarato in §Rischi.
- **Retry della ripartenza oltre BR-8:** il gateway C-03 fa 3 tentativi a 1 minuto; un fallimento
  persistente è loggato e **non** viene ritentato al giro successivo (gap dichiarato).
- **Installazione automatica di Termux:Boot:** lo script esiste; l'installazione sul dispositivo
  resta operativa e non è un deliverable di codice.
- **Vista di deployment ed ER nuovo:** non dichiarati da spec 11 e non necessari; assenti con
  motivo in §3 del documento di architettura e richiamati in §17.

## Decisioni che sbloccano il piano

Chiuse dall'operatore il 2026-11-04.

| # | Domanda aperta / conflitto | Decisione | Impatto |
|---|---|---|---|
| D1 | C-39 deve «acquisire il wake-lock», ma le dipendenze dichiarate non includono C-07 e lo script di boot lo fa già | **Resta nello script di boot**: C-39 non chiama C-07 né avvia C-12, registra il prerequisito e lascia l'acquisizione a `start-agent.sh`/`AgentApp.run` | D-01, D-11, V-01; nessun metodo nuovo in C-07 |
| D2 | Quando parte il messaggio di ripartenza | **Sempre con un `last_start_at` precedente**; il primo avvio assoluto non invia nulla. Nessuna soglia inventata | D-01/D-03, P-A-03/P-A-19, V-12 |
| D3 | Segnale delle 8:00 mancato con processo vivo | **Solo nel messaggio di ripartenza**: se la rete manca alle 8:00 e il processo resta vivo, l'avviso `offline_resumed` di item 10 copre il rientro e il segnale mancato sarà riportato al prossimo avvio | D-01/D-03, V-09; gap dichiarato |
| D4 | Sorgente del periodo di assenza | **`last_online_at`** (scritto da C-37 ogni 60 s quando online); se `last_online_at` è assente o invalido, fallback a `last_start_at` valido | D-01, P-A-02, V-02 |
| D5 | Sorgente di `missed_count`/`recovered` | **C-19 espone `last_summary`** additivo (`RecoveryStats`); il ritorno `list[ExecutionResult]` resta invariato | D-04, V-03; test di recovery estesi |
| D6 | Riavvio dispositivo vs crash processo | **Nessuna distinzione**: un solo testo «Sono di nuovo attivo» con periodo e recuperati | D-03, V-06 |

## Riparto di responsabilità tra componenti (anti-duplicazione)

| Componente | Possiede | Delega a | Non duplica perché |
|---|---|---|---|
| C-39 Boot Recovery | sequenza di avvio: calcolo periodo e **se** il segnale è mancato (`bool`), scheduler in pausa, sync marcatori, recupero, resume, `last_start_at`, `RecoverySummary` | C-06 (start/resume), C-18 (sync), C-19 (recupero), C-02 (marcatori) | C-19 resta l'unico che recupera; C-39 orchestra e misura |
| C-40 Liveness Scheduler | testo e invio del segnale quotidiano, `liveness_last_sent` | C-10 (invio), C-03 (retry BR-8), C-02 (marcatore), C-06 (quando) | C-06 decide *quando*, C-40 *cosa* e *se segnare* |
| C-41 Restart Notifier | testo di ripartenza e riga del segnale mancato, inclusa la **finestra** quando l'occorrenza cade nel periodo (ricalcolata da `at` + `offline_period.until`) | C-10 (invio), C-03 (retry BR-8) | C-39 decide *se* il segnale è mancato; C-41 decide *come* scriverlo |
| C-19 Recovery Handler | recupero occorrenze e conteggi (`RecoveryStats`) | C-06, C-09, C-18 | C-39 non ricalcola le occorrenze |
| C-06 Scheduler | job liveness, job compiti, manutenzione, connettività, batteria | C-40, C-19, C-37 | nessun orologio duplicato |
| C-01 Config Loader | `limits.liveness_at` tipizzato e validato (unico validatore all'avvio) | — | `schedule_liveness` rifiuta solo input malformato come guardia dell'API |
| C-10 Notification Service | invio, split, tastiera | C-03 (retry) | C-40/C-41 non parlano con Telegram |
| C-12 Supervisor | watchdog e loop di riavvio esterno | script di boot | C-39 non duplica il watchdog |

**Un solo scrittore di `liveness_last_sent`.** C-40 lo scrive solo dopo un invio riuscito; C-39 lo
legge per il segnale mancato; C-41 non lo tocca. **Un solo scrittore di `last_start_at`.** C-39.
**Un solo recupero.** C-19, invocato una volta da C-39 all'avvio. **Un solo invio.** Tutti i
messaggi passano da `NotificationService.alert_admin`.

## Contratti (forma dei tipi)

```python
# boot.py — C-39
LAST_START_AT = "last_start_at"

@dataclass(frozen=True)
class OfflinePeriod:
    since: datetime          # ultimo contatto (last_online_at, fallback last_start_at valido)
    until: datetime          # istante di ingresso in on_start
    seconds: int             # max(0, until - since)

@dataclass(frozen=True)
class RecoverySummary:
    missed_count: int
    recovered: int
    offline_period: OfflinePeriod | None
    liveness_missed: bool

class BootRecovery:
    def __init__(
        self,
        *,
        scheduler: TaskScheduler,
        registrar: ScheduleRegistrar,
        tasks: TaskRepository,
        recovery: RecoveryHandler,
        settings: SettingsRepository,
        liveness_at: str = "08:00",
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    async def on_start(self) -> RecoverySummary: ...
```

```python
# liveness.py — C-40
LIVENESS_MARKER = "liveness_last_sent"

class LivenessScheduler:
    def __init__(
        self,
        notifications: NotificationService,
        settings: SettingsRepository,
        *,
        at: str = "08:00",
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    async def send_liveness(self) -> bool: ...
```

```python
# restart.py — C-41
class RestartNotifier:
    def __init__(
        self,
        notifications: NotificationService,
        *,
        at: str = "08:00",
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    async def notify_restart(
        self,
        recovery_summary: RecoverySummary,
        offline_period: OfflinePeriod | None,
        liveness_missed: bool,
    ) -> bool: ...
```

```python
# recovery.py — C-19 (estensione additiva)
@dataclass(frozen=True)
class RecoveryStats:
    missed: int = 0
    recovered: int = 0     # esiti "ok"
    failed: int = 0        # esiti "errore"/"interrotto"
    skipped: int = 0       # occorrenze registrate "saltata"
    deferred: int = 0      # occorrenze coperte da LockHeldError

class RecoveryHandler:
    ...
    @property
    def last_summary(self) -> RecoveryStats: ...
```

```python
# scheduler.py — C-06 (estensione)
LIVENESS_JOB_ID = "liveness:send"

class TaskScheduler:
    def schedule_liveness(
        self, callback: Callable[[], Any], *, at: str = "08:00"
    ) -> str: ...
```

**Ordine fissato di `on_start`** (nessuna variazione ammessa):

1. `now = clock()`; `previous_start = parse(last_start_at)`.
2. `offline_period` e `liveness_missed` calcolati **all'ingresso**, con `until = now`, prima di
   qualsiasi effetto sullo scheduler. Il segnale mancato è valutato prima di `resume()` per non
   correre con il job delle 8:00.
3. `scheduler.start(paused=True)` → `registrar.sync(tasks.list("active"))` →
   `await recovery.recover_missed()` → `stats = recovery.last_summary` → `scheduler.resume()`.
4. `settings.set(last_start_at, now.isoformat(timespec="seconds"))` e ritorno di `RecoverySummary`.

**Ordine fissato di `AgentApp.start`** (invariato salvo tre modifiche all'ordine —
`schedule_liveness`, la delega a `boot.on_start()` al posto di quattro istruzioni, `notify_restart`
— più il `try/except` di log attorno a `gateway.start()`):

1. `db.migrate()`, `alerts.bind_loop`, `approvals.recover_pending`, handler, inbound, dispatcher.
2. Callback dei job: `schedule_maintenance`, `schedule_connectivity`, `schedule_battery`,
   **`schedule_liveness(at=limits.liveness_at)`**. Sono registrazioni su scheduler non ancora
   avviato: nessun job parte qui.
3. `gateway.start()`.
4. `summary = await boot.on_start()` (start in pausa → sync → recupero → resume → `last_start_at`).
5. `await restart_notifier.notify_restart(summary, summary.offline_period, summary.liveness_missed)`.
6. `supervisor.heartbeat()`, `_started = True`.

- **`on_start`** è asincrona. Se `recover_missed` solleva `AgenteError`, logga `avvio parziale` e
  **rilancia**: il loop esterno di `start-agent.sh` riavvia il processo (V-13). `last_start_at` non
  viene scritto, quindi il tentativo successivo riporta l'assenza completa.
- **Ciclo di vita.** `AgentApp.start` protegge il doppio avvio con `_started`. Dopo `stop()` il
  database è chiuso e l'istanza non è riutilizzabile: un nuovo avvio è un **nuovo processo/istanza**
  (il loop di `start-agent.sh`), che riapre risorse e produce un nuovo messaggio di ripartenza.
- **`send_liveness`** compone `✅ Segnale di vita: tutto ok ({at}).`, chiama
  `notifications.alert_admin`, scrive `liveness_last_sent` con l'orario corrente **solo** dopo
  successo; su `AgenteError` logga `segnale di vita non inviato` e restituisce `False`.
- **`notify_restart`** restituisce `False` senza inviare se `offline_period is None` (primo avvio
  assoluto). Su `AgenteError` logga `ripartenza non inviata` e restituisce `False`; non solleva.
  Usa i parametri espliciti (`offline_period`, `liveness_missed`); `recovery_summary` fornisce solo
  i conteggi. Se i parametri contraddicono il riepilogo, prevalgono i parametri (sono la firma
  dichiarata da spec 11).
- **`last_summary`** è azzerato all'ingresso di `recover_missed` e di `check_connectivity`, prima di
  qualsiasi ramo. In `_recover`: `recovered` = risultati con esito `ok`, `failed` = risultati con
  esito `errore`/`interrotto`, `skipped` = occorrenze `saltata`, `deferred` = `LockHeldError`;
  `missed = recovered + failed + skipped + deferred`.
- **`schedule_liveness`** rifiuta `at` malformato con `SchedulerError` (guardia dell'API; la
  validazione di merito è C-01) e registra `CronTrigger(hour=hour, minute=minute,
  timezone=self._scheduler.timezone)` con l'id `liveness:send`, `replace_existing=True`,
  `misfire_grace_time=None`. La timezone è quella dello scheduler (telefono, BR-14). Il trigger è
  ricalcolato a ogni avvio: un job arretrato di un processo precedente non parte al boot.

## Regole di comportamento e testi

| Evento | Regola | Marcatore | Note |
|---|---|---|---|
| Avvio con `last_start_at` precedente | messaggio di ripartenza sempre | `last_start_at` = istante d'ingresso, scritto a fine `on_start` | primo avvio assoluto: nessun messaggio (D2); ogni avvio successivo ha il suo messaggio |
| Periodo di assenza | richiede un `last_start_at` **valido** (esiste un avvio precedente). `since = last_online_at` se valido, altrimenti `last_start_at`; `until` = ingresso in `on_start`, secondi = `max(0, until-since)` | — | `last_start_at` invalido → nessun periodo, nessun messaggio, `liveness_missed=False`; log per il marcatore scartato; C-39 **non** legge `offline_since` |
| Segnale mancato | `liveness_last_sent` assente o precedente all'ultima occorrenza di `liveness_at` ≤ now, purché quell'occorrenza sia ≥ `last_start_at` | — | solo con `last_start_at` precedente (D3); un'occorrenza anteriore al precedente avvio non conta |
| Liveness quotidiana | job cron alle `liveness_at`; invio riuscito → marcatore; fallito → nessun marcatore | `liveness_last_sent` | dentro il processo un job in ritardo viene eseguito (`misfire_grace_time=None`); fra processi il trigger è ricalcolato |
| Avvio senza Telegram raggiungibile | `gateway.start()` fallisce e `on_start` non viene eseguito: log, il loop esterno riavvia. Nessun messaggio di ripartenza finché un avvio non riesce; al riavvio riuscito il periodo include l'assenza | — | V-13; nessun invio «0 recuperati» in questo caso |
| Avvio con C-07 offline ma gateway avviato | `recover_missed` rinvia (`missed_count = 0`); C-41 invia il messaggio con «recuperati 0 compiti». Il recupero avviene al rientro via `check_connectivity`, **senza** un secondo messaggio | — | caso raro (rete C-07 assente ma Telegram raggiungibile); conteggio del momento dell'avvio |
| Ripartenza inviata | log `ripartenza inviata` con periodo e conteggi | — | osservabilità di C-41 |
| Ripartenza non inviata | log `ripartenza non inviata`; nessuna marcatura aggiuntiva; l'assenza **non** viene ritentata al giro successivo | — | BR-8 già nel gateway C-03; gap dichiarato |
| Recupero al rientro dopo avvio offline | `check_connectivity` recupera solo se `resumed` (C-37 ha registrato `offline_since` al primo campionamento offline). Se la rete torna prima di quel campionamento il rientro non è `resumed`; l'occorrenza resta recuperabile a un rientro successivo o al prossimo avvio, **a meno che** `next_run` sia stato nel frattempo avanzato da un'esecuzione regolare o da un `LockHeldError` del job (`finally: registrar.refresh`): in quel caso è persa (perdita dichiarata) | — | comportamento di C-19/C-37 invariato; finestra ≤ `connectivity_check_s`; gap dichiarato |

**Semantica di «offline» nei testi.** Nel messaggio di ripartenza «offline dalle X alle Y» indica
il **periodo senza contatto dell'agente** (processo fermo e/o rete assente): la sorgente
`last_online_at` è aggiornata solo quando la rete è disponibile, quindi un'assenza di rete mentre
il processo è vivo allunga il periodo. È un significato diverso da `offline_since` di item 10
(rete assente, avviso `offline_resumed`). Il documento di architettura lo dichiara in §9 e §16.

**Testi** (italiano, solo dati non sensibili; `at` = `limits.liveness_at`):

| Evento | Testo |
|---|---|
| Liveness | `✅ Segnale di vita: tutto ok ({at}).` |
| Ripartenza | `🔄 Sono di nuovo attivo — offline dalle {since:%d/%m %H:%M} alle {until:%d/%m %H:%M} ({durata}), recuperati {n} compiti.` |
| Ripartenza, singolare | `… recuperato 1 compito.` |
| Segnale mancato | `⏰ Segnale delle {at} non inviato.` — se l'ultima occorrenza delle `{at}` cade nel periodo: `⏰ Segnale delle {at} non inviato — offline dalle {since:%d/%m %H:%M} alle {until:%d/%m %H:%M}.` |

- La durata usa lo stesso formato degli avvisi (`X h Y min`, `X h`, `Y min`, `0 min`), esposto da
  C-36 come funzione pura e riusato da C-41 (V-10): nessuna seconda implementazione.
- `n` è il numero di **recuperi riusciti** (`RecoverySummary.recovered`, esito `ok`); `missed_count`
  (riusciti + falliti + saltati + rinviati) resta nel riepilogo e nel log. Gli esiti puntuali stanno
  nello storico (spec 09).
- Inizio/fine sono formattati nel fuso del telefono (`astimezone()`, BR-14).

## Marcatori in `settings` (nessuna migrazione)

| Chiave | Scritta da | Letta da | Formato | Note |
|---|---|---|---|---|
| `last_start_at` | C-39 | C-39 | ISO 8601 con offset | valore = istante d'ingresso, scritto al termine di `on_start` anche se la ripartenza non è stata inviata; non scritto se `on_start` fallisce |
| `liveness_last_sent` | C-40 | C-39 (segnale mancato) | ISO 8601 con offset | solo dopo invio riuscito |
| `last_online_at` | C-37 (voce 10) | C-39 | ISO 8601 con offset (UTC) | sorgente del periodo di assenza (D4) |
| `offline_since` | C-37 | C-37; C-19 via `OnlineStatus` | ISO 8601 con offset | invariata: periodo di rete assente; **non letta da C-39** |
| `last_contact_at` | C-07 `record_last_contact` | nessuno in `src/` (solo test) | ISO 8601 con offset | invariata |
| `battery_last_alert`, `credential_last_alert` | C-36 | C-36 | — | invariate (voce 10) |

Un marcatore non parsabile o nel futuro è trattato come assente e loggato; non produce un periodo
inventato. Per `liveness_last_sent` «assente o invalido» equivale a segnale mai inviato. Il confronto
avviene sempre su datetime aware e ogni valore conserva il proprio offset: C-37 scrive UTC, C-39/C-40 scrivono con l'offset del clock. I job ripristinati
stanno in `apscheduler_jobs`; le esecuzioni di recupero in `executions` (trigger `recovery`).

## Concorrenza e ciclo di vita

- **Un solo avvio per ciclo di vita.** `AgentApp.start` è protetto da `_started`; dopo `stop()`
  l'istanza non è riutilizzabile (`db` chiuso) e un nuovo avvio è un nuovo processo/istanza.
  `BootRecovery` non è thread-safe
  per scelta: è chiamato sul thread dell'event loop.
- **Recupero una volta.** C-19 conserva il marcatore `next_run:<task_id>` e lo avanza dopo
  l'esecuzione, oppure subito su `LockHeldError` (occorrenza `deferred`); un nuovo avvio non
  recupera due volte la stessa occorrenza.
- **Job persistiti.** `schedule_liveness` è registrato prima di `scheduler.start(paused=True)`; i
  job persistiti si caricano in pausa, il recupero avviene, poi `resume()`. Il job liveness è
  ri-registrato a ogni avvio con `replace_existing=True`: il trigger è ricalcolato da now, quindi un
  job arretrato di un processo precedente non parte al boot.
- **Chiusura.** `AgentApp.stop` resta invariato (`scheduler.shutdown` → `alerts.close()` →
  `gateway.stop()` → `db.close()`). C-39/C-40/C-41 non tengono risorse proprie.
- **Riavvio.** I marcatori sono persistenti: dopo un crash il periodo di assenza è ricostruibile e
  il recupero è idempotente.

## Deviazioni pre-dichiarate (numerazione stabile per il documento 11)

| # | Deviazione | Fonte modificata | Motivo |
|---|---|---|---|
| V-01 | Wake-lock, autostart e supervisor restano in `scripts/boot/` e in `AgentApp.run`; C-39 non chiama C-07 né C-12 | spec 11 C-39 | D1: le dipendenze dichiarate non includono C-07 e un'azione di sistema al boot non passa dal gate; C-12 è già avviato da `run()` |
| V-02 | Periodo di assenza da `last_online_at`; se questo è assente o invalido, fallback a `last_start_at` valido; `offline_since` non è letto da C-39 | spec 11 §Modello dati | D4: `last_start_at` da solo misura da quanto l'agente girava, non da quando si è fermato; `offline_since` descrive la rete assente ed è di C-37 |
| V-03 | C-19 espone `last_summary` (`RecoveryStats`) senza cambiare il ritorno | spec 03 C-19 | D5: C-39 ha bisogno di conteggi esatti senza interrogare lo storico |
| V-04 | `schedule_liveness(callback, *, at)` con `CronTrigger`, ri-registrato a ogni avvio | spec 11 C-40/C-06 | l'orario è `limits.liveness_at`, già dichiarato; il trigger ricalcolato evita job arretrati |
| V-05 | `misfire_grace_time=None` sul job liveness | spec 11 flusso 2 | dentro il processo un job in ritardo non deve perdere il segnale del giorno; fra processi il trigger è ricalcolato |
| V-06 | Un solo testo di ripartenza, nessuna distinzione crash/riavvio | spec 11 rischi | D6: nessun segnale affidabile disponibile |
| V-07 | C-41 riceve i dati già calcolati; non chiama C-39/C-40/C-02 | spec 11 C-41 | la firma dichiarata passa `recovery_summary`, `offline_period`, `liveness_missed`; le dipendenze sono soddisfatte dai parametri |
| V-08 | `limits.liveness_at` validato come `HH:MM` stretto con intervalli | spec 01 C-01 | l'orario guida un job cron; la forma era già controllata, non i valori |
| V-09 | Segnale mancato solo al riavvio, non al rientro di rete | spec 11 BR-11 | D3: il testo della spec lo lega al messaggio di ripartenza; l'avviso di item 10 copre il rientro |
| V-10 | `human_duration` esposto da C-36 e riusato da C-41 | spec 10 C-36 | un solo formato di durata; nessuna dipendenza di runtime nuova (funzione pura) |
| V-11 | `send_liveness() -> bool` | spec 11 C-40 | C-40 deve loggare l'esito e non marcare un invio fallito |
| V-12 | Primo avvio assoluto senza messaggio di ripartenza | spec 11 AC-01 | D2: senza `last_start_at` non esiste un'assenza da riportare |
| V-13 | Fallimento all'avvio: `gateway.start()` (eccezione del gateway, non `AgenteError`) è loggato da `AgentApp` e rilanciato; `AgenteError` dal recupero è loggato da C-39 e rilanciato. Il retry è il riavvio esterno | spec 11 C-39 error handling | la spec chiede «log e retry»: il retry è il loop di `start-agent.sh`; con Telegram irraggiungibile nessun messaggio «0 recuperati» viene tentato |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita in questa invocazione
leggendo il solo frontmatter di `.opencode/agents/*.md`, `.opencode/commands/*.md`,
`.opencode/skills/*/SKILL.md` e `opencode.json`; discovery per ruolo, nessun asset legato per
filename.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-10, D-12 (codice, configurazione, test, aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione di codice Python, test o configurazione | Etichettati *"no specialized capability discovered"*; si procede su spec 11 + constitution + pattern esistenti in `src/agente/` |
| D-11 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** (Phase 2 struttura e Phase 4 validazione); il produttore resta il Conductor |
| D-11 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 11 e dai documenti 10/09/03; assunzione P-A-01 |

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

## Checkpoint di struttura (D-11) — Phase 2

**Struttura applicabile:** Metadata (Spec · Voce roadmap · Piano · Constitution · Data · Struttura
dichiarata + P-A-01 + Governance) · **1** Contesto e obiettivi · **2** Componenti (C-39, C-40,
C-41; estensioni C-19/C-06/C-01/C-36; C-02/C-03/C-07/C-09/C-10/C-11/C-12/C-18/C-37 invariati in tabella;
flowchart) · **3**
Componenti e capacità non disponibili (wake-lock nello script, distinzione crash/riavvio, segnale
mancato al rientro di rete, vista deployment, ER; §17 vi rimanda) · **4** Wiring di `AgentApp` ·
**5** Riparto di responsabilità · **6** Modello di dominio (`RecoverySummary`, `OfflinePeriod`,
`RecoveryStats`, segnale di vita, sessione) · **7** Modello dati (`settings`, marcatori,
`apscheduler_jobs`, `executions` con trigger `recovery`, nessuna migrazione) · **8** Regole di
liveness e testi · **9** Rilevamento dell'assenza e del riavvio (significati di «offline») ·
**10 Flussi di dati**: 10.1 riavvio (AC-01), 10.2 liveness (AC-02), 10.3 segnale mancato (AC-03),
10.4 retry (BR-8), tutte `sequenceDiagram` · **11** Concorrenza e ciclo di vita · **12**
Integrazioni (Termux boot/wake-lock, APScheduler, Telegram, SQLite) · **13** Sicurezza (solo admin, nessun segreto; ripristino fedele dello stato; nessuna azione
privilegiata implicita) · **14** Requisiti non funzionali (settimane di attività, BR-5/8/11) ·
**15** Rischi e assunzioni (Android che termina il processo nonostante wake-lock; A1 S24 sempre
acceso/connesso; crash vs riavvio; invio fallito) · **16** Domande aperte chiuse (rilevamento
riavvio, autostart Android con validazione OEM sul dispositivo, definizione condivisa di offline) · **17** Fuori scope · **18** Deviazioni (V-01…V-13) ·
**19** Tracciabilità (AC-01…AC-04, BR-5/8/11). Per ogni componente: Responsabilità · Interfaccia ·
Input/Output · Dipendenze · Error handling · Osservabilità · Sicurezza.

**Idoneità:** la struttura è adatta perché spec 11 dichiara componenti, flussi, modello di dominio e
dati, integrazioni, sicurezza e criteri; i documenti 10/09/03 ne confermano lo stile.

**Deliverable richiesti dal documento:** D-11 con sezioni 1…19, 1 flowchart, 4 sequenze, tabelle
marcatori/testi/regole, assenza motivata di deployment ed ER.

**Dipendenze del documento:** codice D-01…D-08 stabile e test D-09/D-10 verdi; esito del checkpoint
Phase 2.

**Perché niente deployment né ER:** la spec 11 non li dichiara; `settings` e le tabelle esistenti
sono già nel modello dati di spec 01 e non cambiano.

**Passate del 2026-11-04:**

1. **NOT APPROVED** — claim falso su `_started`/secondo `on_start`; registro della remediation
   assente; `schedule_liveness` fuori dall'ordine fissato; «recuperati» contava anche esiti falliti;
   BR-16 estraneo ai NFR; `human_duration` senza deliverable; AC-04 indefinibile («nessun doppio
   messaggio» contro D2); C-18/C-19 attribuiti a item 01; retry C-39 non dichiarato; `settings.set`
   con datetime; orario ancora hard-coded nei testi; precedenza di `notify_restart` non definita;
   ordine di `AgentApp.start` incompleto; test V-04/V-05 mancanti; `offline_since` non dichiarato;
   reset di `last_summary` ambiguo; ordine dei task; rischio oltre mezzanotte.
2. **NOT APPROVED** — claim falso su `_started`/secondo `on_start`; punto della remediation
   assente; `schedule_liveness` fuori dall'ordine fissato; «recuperati» contava anche esiti falliti;
   BR-16 estraneo ai NFR; `human_duration` senza deliverable; AC-04 indefinibile; C-18/C-19
   attribuiti a item 01; retry C-39 non dichiarato; `settings.set` con datetime; orario hard-coded
   nei testi; precedenza di `notify_restart` non definita; ordine di `AgentApp.start` incompleto;
   test V-04/V-05 mancanti; `offline_since` non dichiarato; reset di `last_summary` ambiguo; ordine
   dei task; rischio oltre mezzanotte.
3. **NOT APPROVED** — claim su `stop()`/`start()` sullo stesso oggetto, fake scheduler senza
   `schedule_liveness` nella tracciabilità, ordine dei task contraddittorio, registro governance
   incompleto, note C-18/C-19 attribuite a spec 01, P-A-21 troppo assoluto, timestamp di
   `last_start_at` ambiguo, test di precedenza di `notify_restart` mancante.
4. **NOT APPROVED** — AC-04 non seminava `last_start_at`; segnale mancato senza limite inferiore;
   fallback ambiguo su `last_online_at` invalido; test dell'invio fallito etichettato come AC-04;
   note spec 10/arch 10 senza `human_duration`; fake scheduler anche in T2; C-18/C-02 fuori da
   §2 del documento; BR-11 senza riga di tracciabilità; rischi Android/A1 non riportati.
5. **NOT APPROVED** — D4 non allineato al fallback su marcatore invalido; nota arch 10 senza
   `human_duration`; avvio con rete assente non dichiarato; proprietario della finestra del segnale
   mancato ambiguo; P-A-21 senza C-39; C-03/C-09 fuori da §2; AC-04 senza strategia di scheduler;
   test di idempotenza e «C-40 solo admin» non tracciati; asserzione del test di invio fallito
   ambigua.
6. **NOT APPROVED** — regola per `last_start_at` invalido ambigua; ramo «rete assente» non
   eseguibile come scritto; recupero al rientro non garantito in una finestra stretta; test di
   idempotenza non ancora esteso; fallback non allineato in tre punti; C-37 assente da §2; conteggio
   messaggi vs chiamate; qualificazione P-A-04; normalizzazione marker naive.
7. **NOT APPROVED** — avvio senza Telegram: `gateway.start()` fallisce prima di `on_start`, il ramo
   «0 recuperati» non è raggiungibile in produzione; perdita dell'occorrenza nella finestra senza
   `resumed` non dichiarata; D4/V-02 ambigui sul marcatore; test mancanti per naive/UTC, finestra
   inclusiva e log; P-A-20 impreciso; conteggio delle modifiche a `start`.
8. **NOT APPROVED** — V-13 attribuiva al gateway un `AgenteError` che non solleva; mancava il log
   del fallimento gateway; rami d'avvio senza test; perdita d'occorrenza troppo larga; P-A-20
   meccanicamente impreciso; mancava il rischio di perdita; `next_run` avanzato anche su
   `LockHeldError`; semantica del marcatore liveness invalido ambigua; test timezone non tracciato.
9. **NOT APPROVED** — conteggio delle modifiche a `start` non aggiornato; eccezione catturata e
   assert del test gateway imprecisi; perdita d'occorrenza non include il job regolare con
   `LockHeldError`; §13 senza ripristino fedele/azioni privilegiate; test `deferred` non nominato;
   P-A-20 non distingue scheduler predefinito e iniettato.
10. **NOT APPROVED** — `CronTrigger` con argomenti posizionali (firma APScheduler 3.11); log di
    invio ripartenza riuscito senza test; V-02 senza test; `Alerts` invece di `AlertService`; gap
    dispositivo di AC-01 non dichiarato nei criteri.
11. **APPROVED** con due note non bloccanti recepite: il test del log di successo deve verificare
    anche periodo e conteggi; §16/§Criteri qualificano l'autostart Android come «deciso, da validare
    sul dispositivo» (criterio 6).

**Phase 4 (2026-11-04):** **APPROVED** alla prima passata con minor recepiti nel documento 11:
riga del segnale mancato al testo esatto del codice; `(V-07)` corretto in V-11; C-39 «legge i
marcatori e scrive solo `last_start_at`»; motivazione BR-16 corretta; job store attribuito ad
APScheduler; aggiunte le righe di tracciabilità di `test_failed_restart_is_not_retried` e del fake
scheduler di `test_bootstrap.py`.

## Assunzioni del piano (non dichiarate da spec 11)

> **P-A-01** Struttura del documento di architettura derivata da spec 11 e dai documenti 10/09/03,
> non da un template: in `docs/templates/` esistono solo `template.spec.md` e
> `template.constitution.md`.

> **P-A-02** Periodo di assenza: richiede un `last_start_at` valido (avvio precedente). `since =
> last_online_at` se presente e valido, altrimenti `last_start_at`; `until` = istante di ingresso in
> `on_start`; `seconds = max(0, until-since)`. `last_start_at` invalido → nessun periodo e nessun
> messaggio (P-A-03).
> Il periodo misura l'assenza di contatto dell'agente, non solo il processo fermo: include
> l'eventuale rete assente mentre il processo era vivo. `offline_since` non è usato.

> **P-A-03** «Avvio precedente» = `last_start_at` presente e parsabile. Primo avvio assoluto →
> `offline_period=None`, nessun messaggio.

> **P-A-04** Segnale mancato: C-39 calcola l'ultima occorrenza di `liveness_at` ≤ now nel fuso del
> telefono. È mancato solo se quell'occorrenza è **≥ `last_start_at`** (l'agente era già in un ciclo
> di vita) e `liveness_last_sent` è assente o precedente. Un'occorrenza anteriore al precedente
> avvio non è imputabile a questa assenza. C-41 ricalcola la stessa occorrenza da `at` e
> `offline_period.until` per decidere la **finestra**: «offline dalle X alle Y» compare solo se
> l'occorrenza cade nel periodo; altrimenti resta la sola frase «Segnale delle {at} non inviato».
> La finestra è inclusiva: `since <= occorrenza <= until`.
> C-39 e C-41 usano lo stesso istante (`until`) quando i parametri coincidono con il riepilogo;
> se `AgentApp` passasse parametri diversi, la finestra seguirebbe i parametri (V-07).

> **P-A-05** Testo liveness: `✅ Segnale di vita: tutto ok ({at}).` con l'orario di
> `limits.liveness_at`.

> **P-A-06** Testo ripartenza: `🔄 Sono di nuovo attivo — offline dalle … alle … (durata),
> recuperati N compiti.`; con `N=1`, «recuperato 1 compito». La riga del segnale mancato è separata
> e qualificata secondo P-A-04.

> **P-A-07** La durata è formattata da `human_duration` di C-36 (`X h Y min`, `X h`, `Y min`,
> `0 min`); C-41 non reimplementa il formato.

> **P-A-08** C-39 non acquisisce il wake-lock: lo fa `scripts/boot/start-agent.sh`, che resta
> invariato. C-39 registra nel log l'avvio e il periodo; nessuna azione di sistema.

> **P-A-09** `last_start_at` è scritto **al termine** di `on_start`, dopo scheduler/sync/recupero,
> anche se il messaggio di ripartenza poi fallisce. Un invio di ripartenza fallito non viene
> ritentato al giro successivo: il periodo è ormai trascorso e `last_online_at` è stato aggiornato
> mentre l'agente era online. Gap dichiarato.

> **P-A-10** `last_online_at`/`last_start_at`/`liveness_last_sent` non parsabili o nel futuro:
> trattati come assenti e loggati `marcatore … non valido`. `last_start_at` invalido annulla periodo
> e messaggio (P-A-03); `last_online_at` invalido usa il fallback `last_start_at`;
> `liveness_last_sent` invalido equivale a «mai inviato» e **può** produrre la riga «segnale non
> inviato». I marcatori senza offset sono interpretati in UTC, come fa C-37.

> **P-A-11** Il messaggio di ripartenza è inviato anche se il periodo è brevissimo (crash-loop):
> nessuna soglia non dichiarata. Rischio registrato.

> **P-A-12** Ogni marcatore conserva il proprio offset: `last_online_at` è UTC, i nuovi marcatori
> usano il clock iniettato (tipicamente offset locale). Ogni confronto avviene su datetime aware;
> la formattazione per l'utente usa `astimezone()`.

> **P-A-13** `LIVENESS_JOB_ID = "liveness:send"`, registrato con `replace_existing=True` a ogni
> avvio; un errore del callback è loggato da C-06 e non ferma gli altri job.

> **P-A-14** `misfire_grace_time=None`: dentro un processo attivo un job liveness in ritardo viene
> eseguito (meglio un segnale in ritardo che un giorno senza segnale). Fra processi il trigger è
> ricalcolato all'avvio, quindi un job arretrato non parte al boot e il segnale mancato è riportato
> dalla ripartenza. Un'esecuzione che scavalca la mezzanotte scrive comunque il marcatore con
> l'orario effettivo: il giorno successivo il job regolare resta l'unico invio previsto.

> **P-A-15** `AgenteError` da `recover_missed`: log `avvio parziale` e rilancio (V-13); il loop
> esterno riavvia il processo e `last_start_at` non viene scritto. Le eccezioni impreviste seguono
> lo stesso percorso.

> **P-A-16** `RecoveryStats` è azzerato all'ingresso di `recover_missed` e `check_connectivity` e
> calcolato in `_recover`: `recovered` = esiti `ok`, `failed` = esiti `errore`/`interrotto`,
> `skipped` = occorrenze `saltata`, `deferred` = `LockHeldError`;
> `missed = recovered + failed + skipped + deferred`.

> **P-A-17** `RecoverySummary` e `OfflinePeriod` sono modelli in memoria di C-39; nessuna
> persistenza.

> **P-A-18** `notify_restart` è best-effort: un invio fallito è loggato e non solleva; BR-8 resta
> nel gateway C-03. Nessun secondo retry applicativo.

> **P-A-19** Il primo avvio assoluto scrive `last_start_at` ma non invia nulla; il secondo avvio
> produce il primo messaggio.

> **P-A-20** Il job liveness passa esplicitamente `timezone=self._scheduler.timezone` a
> `CronTrigger`. Con lo scheduler predefinito (`timezone=None`) è il fuso locale del sistema
> (telefono, BR-14); con uno scheduler iniettato è il suo fuso, che i test fissano. Nessuna timezone
> diversa viene forzata.

> **P-A-21** `limits.liveness_at` è l'unica sorgente dell'orario applicativo; C-39 (segnale
> mancato), C-40 (testo e cron) e C-41 (finestra e testo) ricevono lo stesso valore da `AgentApp`. I
> default `at="08:00"` nelle firme e in `LimitsConfig` sono fallback dell'API, non un secondo orario
> di produzione; nessun testo contiene un orario letterale.

> **P-A-22** `AgentApp` espone `boot`, `liveness`, `restart_notifier`; `start` segue l'ordine
> fissato in §Contratti.

> **P-A-23** I test usano clock, scheduler, gateway, device e LLM finti; nessun test dipende da ora,
> rete, Termux:API, Telegram o DeepSeek reali.

> **P-A-24** AC-04 («settimane senza riavvii manuali») non è misurabile in suite: si verifica che,
> con `last_start_at` già presente, due cicli di avvio producano un messaggio ciascuno, non
> duplichino il recupero della stessa occorrenza e non richiedano intervento manuale. Soak test sul
> dispositivo: **gap dichiarato**.

> **P-A-25** Nessuna migrazione e nessuna tabella nuova; `settings` è l'unico storage dei marcatori.

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | C-19 `last_summary` | D-04 | conteggi corretti (ok/fallite/saltate/rinviate/mancate); azzeramento all'ingresso; ritorno e idempotenza invariati |
| T2 | Job liveness in C-06 | D-05 | `schedule_liveness` registra `liveness:send` con ora/minuto; `at` malformato → `SchedulerError`; `misfire_grace_time=None`; `replace_existing` verificabile; errori isolati |
| T3 | C-39 Boot Recovery | D-01 | `on_start` calcola periodo e segnale mancato all'ingresso, poi scheduler in pausa → sync → recupero → resume → `last_start_at`; periodo da `last_online_at` con fallback; `liveness_missed` corretto prima/dopo le 8:00; `AgenteError` → log e rilancio; log di avvio |
| T4 | C-40 Liveness Scheduler | D-02 | testo con `{at}`; marcatore scritto solo su successo; invio fallito → `False`, log, marcatore intatto |
| T5 | C-41 Restart Notifier | D-03 | testo con periodo/durata/recuperati riusciti; singolare; riga segnale mancato con finestra solo se pertinente; nessun invio con periodo assente; invio fallito → `False`; solo admin |
| T6 | Validazione `liveness_at` | D-06 | `08:00` valido; `24:00`, `8:5`, `08:60`, forma errata → `ConfigError` con messaggio che nomina `liveness_at` |
| T7 | C-36 `human_duration` | D-07 | funzione pubblica in `__all__`, comportamento identico, test esistenti invariati |
| T8 | Wiring `AgentApp` | D-08 | build di C-39/C-40/C-41; `schedule_liveness` prima di `on_start`; `start` segue l'ordine fissato e notifica dopo `gateway.start`; campi esposti; `start` idempotente; nessun'altra dipendenza cambia |
| T9 | Test unit | D-09 | nuovi test C-39/C-40/C-41; estensioni recovery/scheduler/config/bootstrap/scheduled_ac/alerts; suite verde |
| T10 | AC-01…AC-04 end-to-end | D-10 | AC-01 avvio con marcatore → messaggio con periodo; AC-02 8:00 → liveness e marcatore; AC-03 offline alle 8 → messaggio con segnale mancato; AC-04 con `last_start_at` già presente e scheduler che persiste `next_run`, due avvii → un messaggio per avvio, nessun recupero duplicato, nessun passo manuale |
| T11 | Documento architettura 11 | D-11 | sezioni 1…19; 1 flowchart + 4 sequenze 10.1–10.4; tabelle marcatori/testi/regole; checkpoint Phase 2 e Phase 4 **APPROVED**; deployment ed ER dichiarati assenti con motivo |
| T12 | Pubblicazione | D-12 | roadmap 11 `[x]`; spec 11 `Implemented (2026-11-04)` + note; delivery history con esito, gap e V-01…V-13; piano eseguito; note di continuità su spec 01/03/10 e arch 01/03/10 (C-18/C-19 in spec 03) |

## Dipendenze

- Item 01: C-01 (`liveness_at`), C-02 (`settings`), C-03 (retry BR-8), C-06 (job store persistente,
  cron), C-10 (`alert_admin`), C-11, C-12 (supervisor e script di boot).
- Item 03: C-18 (sync dei marcatori), C-19 (`recover_missed`, `check_connectivity`, marcatore
  `next_run`, idempotenza BR-5).
- Item 10: C-36 (`human_duration`, `alerts.close()`), C-37 (`last_online_at`, `offline_since`),
  decisione D5 di item 10 (offline = rete assente).
- **Nessuna dipendenza non consegnata:** è l'ultima voce della roadmap.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Crash-loop con molti messaggi di ripartenza | D2: nessuna soglia inventata; rischio dichiarato e loggato; operatore può fermare il processo |
| `last_online_at` mancante o invalido | fallback a `last_start_at` valido; `last_start_at` assente/invalido → nessun periodo e nessun messaggio (P-A-03) |
| Periodo che include un'assenza di rete mentre il processo era vivo | dichiarato in §8 e §9: «offline» nella ripartenza = assenza di contatto; item 10 avvisa separatamente il rientro di rete |
| Invio di ripartenza fallito dopo BR-8 | gap dichiarato: log, nessun retry al giro successivo; l'assenza non viene ripetuta |
| Job liveness in ritardo dentro il processo | `misfire_grace_time=None`: il segnale parte in ritardo invece di perdersi; log di invio con orario effettivo |
| Job liveness arretrato fra processi | trigger ricalcolato a ogni avvio; nessun «tutto ok» stantio al boot |
| Job che scavalca la mezzanotte | il marcatore registra l'orario effettivo; il job regolare del giorno dopo resta l'unico previsto (P-A-14) |
| Segnale mancato con processo vivo e rete assente | gap dichiarato (D3/V-09); l'avviso `offline_resumed` di item 10 informa del rientro |
| Avvio senza Telegram raggiungibile | `gateway.start()` fallisce prima di `on_start`: log e riavvio esterno, nessun messaggio. Al primo avvio riuscito il periodo include l'assenza. Comportamento dichiarato in §Regole (V-13). |
| Perdita di un'occorrenza dopo avvio offline | se il rientro non è `resumed` e `next_run` viene avanzato da un'esecuzione regolare o da un `LockHeldError` del job, l'occorrenza persa non è più recuperabile. Gap dichiarato, comportamento invariato di C-19/C-37. |
| Doppio invio liveness nello stesso giorno | una sola occorrenza cron al giorno; `replace_existing=True`; marcatore aggiornato solo su successo |
| Recupero duplicato tra `on_start` e job di connettività | C-19 idempotente sul marcatore `next_run`; test dedicato |
| `last_start_at` scritto prima del recupero | ordine fissato: scrittura dopo resume; un crash a metà lascia il marcatore vecchio |
| Timezone errata nel calcolo delle 8:00 | datetime aware nel fuso del telefono; confronto su aware; test con fuso fisso |
| Dati sensibili nei testi | solo orari, durata e conteggi; nessun contenuto dei compiti |
| Regressione su item 01/03/10 | C-19 mantiene ritorno e idempotenza; C-37/C-36 invariati; test esistenti aggiornati solo per i fake scheduler, `human_duration` e `last_summary` |

## Criteri di validazione (done della voce)

1. `PYTHONPATH=src:.deps python3 -m pytest` verde (inclusi i test di item 01–10).
2. AC-01: avvio con `last_start_at` precedente → messaggio di ripartenza con periodo e recuperati.
3. AC-02: alle `liveness_at` → segnale di vita all'admin e `liveness_last_sent` aggiornato.
4. AC-03: `liveness_last_sent` precedente alle 8:00 → messaggio con «segnale non inviato» e periodo
   quando l'occorrenza cade nell'assenza.
5. AC-04: con `last_start_at` già presente (seed dichiarato nel test), due avvii su due
   istanze/processi distinti → un messaggio per avvio, un solo recupero per occorrenza, nessun passo
   manuale (soak test sul dispositivo: gap).
6. AC-01 lato dispositivo (riavvio reale, autostart e limitazioni OEM): coperto dagli script di boot
   e dalla documentazione, non misurabile in suite; validazione sul dispositivo: **gap
   dichiarato**.
7. Primo avvio assoluto: nessun messaggio, `last_start_at` scritto.
8. Liveness fallita: marcatore intatto, log, nessuna eccezione.
9. Marcatori: `last_start_at`, `liveness_last_sent`, `last_online_at`, `offline_since` con i formati
   della tabella; nessuna migrazione; `settings` invariato nello schema.
10. C-19: `last_summary` corretto; ritorno `list[ExecutionResult]` e idempotenza invariati.
11. C-06: job `liveness:send` con ora/minuto da `liveness_at`; errori isolati.
12. Documento D-11 conforme alla struttura dichiarata e approvato al checkpoint Phase 4.
13. Catena di tracciabilità ricostruibile: voce roadmap 11 → spec 11 → binding → task → artefatti →
    validazione → pubblicazione.

## Tracciabilità attesa (compilata a Publish)

| Requisito / criterio | Test previsto |
|---|---|
| AC-01 ripartenza dopo riavvio | `tests/test_restart_ac.py::test_ac01_restart_sends_message` |
| AC-02 segnale di vita alle 8:00 | `tests/test_restart_ac.py::test_ac02_liveness_at_eight` |
| AC-03 segnale mancato | `tests/test_restart_ac.py::test_ac03_missed_liveness_is_reported` |
| AC-04 nessun riavvio manuale | `tests/test_restart_ac.py::test_ac04_repeated_boots_are_idempotent` (due istanze sullo stesso DB, `last_start_at` iniziale seminato) |
| P-A-09 ripartenza fallita non ritentata | `tests/test_restart_ac.py::test_failed_restart_is_not_retried`: una sola chiamata a `alert_admin` per avvio e nessun secondo tentativo nello stesso avvio; il numero di chiamate è pari al numero di avvii (gap dichiarato, non AC-04) |
| C-39 primo avvio | `tests/test_boot.py::test_first_start_has_no_period_and_no_message` |
| C-39 periodo | `tests/test_boot.py::test_absence_period_uses_last_online_at`, `::test_absence_period_falls_back_to_last_start` |
| C-39 segnale mancato | `tests/test_boot.py::test_liveness_missed_before_and_after_eight`, `::test_liveness_not_missed_when_already_sent`, `::test_liveness_before_previous_start_is_not_missed` |
| C-39 ordine | `tests/test_boot.py::test_period_is_captured_before_recovery`, `::test_last_start_is_written_after_recovery` |
| C-39 avvio parziale | `tests/test_boot.py::test_recovery_error_fails_start` |
| C-39 marcatori invalidi | `tests/test_boot.py::test_invalid_last_online_falls_back_to_start`, `::test_invalid_markers_are_ignored`, `::test_naive_marker_is_read_as_utc` |
| C-41 finestra inclusiva | `tests/test_restart.py::test_missed_window_is_inclusive` |
| Log di avvio | `tests/test_boot.py::test_start_logs_period_and_recovery` |
| Log liveness | `tests/test_liveness.py::test_liveness_logs_send_and_failure` |
| C-40 invio | `tests/test_liveness.py::test_liveness_sends_and_marks`, `::test_liveness_failure_keeps_marker` |
| C-40 testo | `tests/test_liveness.py::test_liveness_text` |
| C-41 testo | `tests/test_restart.py::test_restart_text_with_period_and_count`, `::test_restart_singular_task` |
| C-41 segnale mancato | `tests/test_restart.py::test_restart_text_includes_missed_liveness`, `::test_missed_line_omits_window_when_not_in_period` |
| C-41 primo avvio | `tests/test_restart.py::test_no_message_without_period` |
| C-41 errore invio | `tests/test_restart.py::test_failed_send_is_logged` |
| C-41 log invio riuscito | `tests/test_restart.py::test_restart_logs_successful_send` |
| C-39 non legge `offline_since` | `tests/test_boot.py::test_boot_ignores_offline_since` |
| C-41 solo admin | `tests/test_restart.py::test_restart_goes_only_to_admin` |
| C-41 precedenza parametri | `tests/test_restart.py::test_explicit_parameters_win_over_summary` |
| C-19 `last_summary` | `tests/test_recovery.py::test_last_summary_counts_outcomes`, `::test_last_summary_counts_deferred`, `::test_last_summary_resets_on_postponed_recovery` |
| BR-5 una occorrenza | `tests/test_recovery.py::test_only_last_occurrence_is_recovered` (invariato) |
| BR-8 retry | `tests/test_llm.py::test_transient_error_is_retried_three_times`; `tests/test_telegram_gateway.py::test_retry_three_times_on_transient_error` |
| BR-11 segnale quotidiano | `tests/test_restart_ac.py::test_ac02_liveness_at_eight`, `tests/test_liveness.py::test_liveness_sends_and_marks` |
| Job liveness | `tests/test_scheduler.py::test_liveness_job_is_registered`, `::test_liveness_job_is_replaced_with_a_fresh_trigger`, `::test_liveness_job_has_no_misfire_grace`, `::test_liveness_job_uses_the_scheduler_timezone`, `::test_liveness_job_error_is_isolated`, `::test_liveness_time_must_be_valid` |
| Configurazione | `tests/test_config.py::test_loads_valid_config`, `::test_invalid_liveness_time_is_rejected` |
| `human_duration` | `tests/test_alerts.py::test_human_duration_is_public` |
| Wiring | `tests/test_bootstrap.py::test_build_exposes_boot_components`, `::test_start_schedules_liveness_and_notifies_restart` |
| Ordine di avvio | `tests/test_bootstrap.py::test_start_uses_boot_recovery` |
| Gateway non avviabile | `tests/test_bootstrap.py::test_start_stops_when_gateway_fails`: fake che solleva un'eccezione non-`AgenteError`, `pytest.raises` sul rilancio, log presente, `on_start`/`notify_restart` non chiamati |
| C-07 offline con gateway su | `tests/test_bootstrap.py::test_c07_offline_with_gateway_up_reports_zero` |
| Un solo `on_start` per ciclo | `tests/test_bootstrap.py::test_start_is_idempotent` (esteso: `boot.on_start` chiamato una volta e `notify_restart` una volta) |
| C-40 solo admin | `tests/test_liveness.py::test_liveness_goes_only_to_admin` |
| Fake scheduler aggiornato | `tests/test_bootstrap.py::test_start_migrates_starts_polling_and_scheduler` (con `schedule_liveness`), `tests/test_scheduled_ac.py::test_ac02_start_recovers_before_resuming_jobs` (con `schedule_liveness`) |
| Nessuna migrazione | `tests/test_storage.py::test_migration_creates_spec_tables` (schema 005 invariato) |
| Confini | `tests/test_boundaries.py` invariato |

## Ordine di consegna

Codice-first, rispettando le dipendenze dei test: T1 (C-19) → T2 (C-06) → T3 (C-39) → T4 (C-40) →
T5 (C-41) → T6 (C-01) → T7 (`human_duration`) → T8 (wiring) → T9 (test unit) → T10 (AC end-to-end) →
T11 (documentazione, dipendente da codice stabile) → T12 (pubblicazione).

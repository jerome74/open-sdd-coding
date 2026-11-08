# Piano 10 — FR-009 Avvisi all'amministratore

- **Voce roadmap:** `10 — FR-009 Avvisi all'amministratore` (non spuntata)
- **Spec:** [10-fr009-avvisi-admin.spec.md](../specs/10-fr009-avvisi-admin.spec.md), Stato `New`
- **Constitution:** [constitution.md](../specs/constitution.md), principi 1–9, Tech Stack,
  §Pattern e vincoli architetturali, `## Roadmap`
- **Dipendenze consegnate:** item 01 (`01-agent-runtime`: C-01 con `limits.battery_threshold_pct`,
  `offline_threshold_s`; C-02 `settings`; C-03; C-04; C-05 `LLMClient` con
  `LLMCredentialsError`; C-06 con job di connettività; C-07 `battery_level`/`is_online`/
  `record_last_contact`; C-10 `alert_admin`; il retry BR-8 è nel gateway C-03; C-13), item 03 (C-09 con avvisi diretti
  su timeout/errore; C-19 con `offline_since` e `last_contact_at`), item 06 (gate e avvisi del gate),
  item 07 (avviso allowlist), item 08 (C-33 avvisi sconosciuti, sistema di notifica già esteso)
- **Dipendenze non consegnate:** item 11 (riavvio, liveness, messaggio di ripartenza) — confine
  dichiarato in D1/V-10, nessun blocco
- **Data piano:** 2026-11-03
- **Stato piano:** approvato 2026-11-03; eseguito T1–T13 (delivery history: voce 10)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | C-36 Alert Service: `alert(kind, detail) -> bool`, composizione dei cinque tipi di avviso, deduplicazione batteria/credenziali (decisione sotto lock, invio fuori lock), invio solo all'admin tramite C-10, log inviati/deduplicati/non inviati; `alert_threadsafe` e `bind_loop` per il chiamante sincrono di C-38 | codice | `src/agente/alerts.py` |
| D-02 | C-37 Device Monitor: `check_battery()`, `check_online() -> OnlineStatus`, `offline_since()`, `is_online()`; marcatori `offline_since`, `last_online_at`, `last_contact_at`; avvisi batteria e offline al rientro; log di livello, soglia, stato rete e durata | codice | `src/agente/device_monitor.py` |
| D-03 | C-38 Credential Monitor: `on_llm_error(http_status, body="") -> bool`, classificazione 401/402/403 e inoltro a C-36; log del solo status e del tipo di problema, mai del corpo | codice | `src/agente/credential_monitor.py` |
| D-04 | C-05: callback opzionale `on_credentials_error(status, body)` invocato su 401/402/403 prima di `LLMCredentialsError`; `LLMCredentialsError.status`; corpo dell'errore troncato e mai loggato | codice | `src/agente/llm.py`, `src/agente/errors.py` |
| D-05 | C-09: timeout e fallimento instradati a C-36 (`task_timeout`/`task_failed`); un errore di credenziale **non** produce `task_failed` e non invia `credential` (unico produttore: C-38); avviso allowlist di spec 07 invariato; dipendenza `alerts` opzionale con fallback per i test | codice | `src/agente/execution.py` |
| D-06 | C-19: delega a C-37 il tracciamento di `offline_since`/`last_online_at` e l'avviso di rientro; `recover_missed` usa `await is_online()` (lettura asincrona, senza marcatori), senza duplicare l'avviso al boot; il costruttore perde `settings` | codice | `src/agente/recovery.py` |
| D-07 | C-06: job periodico batteria `schedule_battery(callback, *, interval_s=300)`, validazione `interval_s > 0`, `BATTERY_JOB_ID`, entry point module-level | codice | `src/agente/scheduler.py` |
| D-08 | C-01: `limits.battery_check_s = 300` (tipizzato e validato) e aggiornamento della configurazione di esempio | configurazione | `src/agente/config.py`, `config/config.example.toml` |
| D-09 | Wiring `AgentApp`: costruzione di C-36/C-37/C-38, callback di credenziale in C-05, campi `alerts`/`device_monitor`/`credentials`, `bind_loop` in `start`, `await alerts.close()` in `stop` dopo `scheduler.shutdown(wait=False)` e **prima** di `gateway.stop()` e `db.close()`, schedulazione del job batteria | codice | `src/agente/app.py` |
| D-10 | Test della voce: unit C-36/C-37/C-38/C-05/C-09/C-19/C-06, AC-01…AC-04 end-to-end, aggiornamento di configurazione e scheduler | test | `tests/test_alerts.py`, `tests/test_device_monitor.py`, `tests/test_credentials.py`, `tests/test_alerts_ac.py`, `tests/test_execution.py`, `tests/test_llm.py`, `tests/test_recovery.py`, `tests/test_scheduler.py`, `tests/test_storage.py`, `tests/test_config.py`, `tests/test_bootstrap.py`, `tests/test_scheduled_ac.py` |
| D-11 | Documento architettura con Mermaid (1 flowchart componenti, 4 sequenze nella sezione 10: fallimento compito, batteria, offline, credenziali) e tabelle di deduplicazione/testi/marcatori | documentazione | `docs/architecture/10-fr009-avvisi-admin.md` |
| D-12 | Pubblicazione: roadmap `[x]`, stato spec 10 `Implemented` + note, delivery history, piano allineato, note di continuità su spec 01 (C-05/C-07/C-10), spec 03 (C-19 delega a C-37), aggiornamento esplicito di architettura 01 (§2 C-05 callback e `.status`, C-07 `record_last_contact`; `last_online_at` da C-37; C-10 invariato; §8 con le righe di spec 10 AC-01…AC-04 e BR-4/8/9/10), architettura 03 (§2 C-19, §5 tabella marcatori, §6.2 sequenza di recupero, §14 tracciabilità) e spec 09 (avvisi di sistema restano a voce 10) | documentazione | `docs/specs/constitution.md`, `docs/specs/10-fr009-avvisi-admin.spec.md`, `docs/specs/01-agent-runtime.spec.md`, `docs/specs/03-fr002-esecuzione-programmata.spec.md`, `docs/specs/09-fr008-storico-esecuzioni.spec.md`, `docs/architecture/01-agent-runtime.md`, `docs/architecture/03-fr002-esecuzione-programmata.md`, `docs/delivery-history.md`, questo piano |

Nessuna tabella nuova e nessuna migrazione: la deduplicazione usa `settings` (chiave/valore), come
dichiarato da spec 10 §Modello dati. Nessuna nuova dipendenza esterna: batteria e rete passano da
C-07 (Termux:API), l'invio da C-10, il modello da C-05. **C-36/C-37/C-38 non duplicano** ciò che
esiste: C-09 già compone il motivo del fallimento, C-19 già rileva il rientro online, il gateway
C-03 (invocato da C-10) già ritenta gli invii. Gli avvisi esistenti di spec 07/08 (allowlist, sconosciuti) restano dove sono:
non sono `kind` di spec 10 e non vengono rifatti.

### Fuori scope di questa voce (dichiarato)

- **Segnale di vita, messaggio di ripartenza, `liveness_last_sent`, boot recovery:** spec 11
  (D1/V-10). C-37 scrive `last_online_at` e `offline_since`, che spec 11 userà; nessun invio di
  ripartenza qui.
- **Rilevamento del processo fermo:** C-37 osserva solo la rete; l'agente spento è rilevato per
  assenza dal segnale di vita di spec 11 (D5).
- **Tabella `alerts`:** la spec la dichiara «eventualmente»; si usano i marcatori in `settings`,
  nessuna migrazione (V-04).
- **Avvisi di allowlist log (spec 07), gate (spec 06), sconosciuti (spec 08):** restano nei
  rispettivi componenti; C-36 non li assorbe.
- **Retry BR-8:** già in C-05 (LLM) e nel gateway C-03 per Telegram; qui nessun nuovo retry.
- **Vista di deployment ed ER nuovo:** non dichiarati dalla spec 10 e non necessari; **gap
  registrato**. `settings` è già nel modello dati di spec 01.

## Decisioni che sbloccano il piano

Chiuse dall'operatore il 2026-11-03.

| # | Domanda aperta / conflitto | Decisione | Impatto |
|---|---|---|---|
| D1 | Dipendenza da spec 11 non consegnata | **Si procede**: item 10 possiede batteria, offline prolungato e credenziali; riusa `offline_since`/`last_online_at`; ripartenza, liveness e boot recovery restano a 11 | D-02, D-06, V-10; test di recovery senza messaggio di ripartenza |
| D2 | Frequenza di campionamento batteria | **Ogni 5 minuti** (`limits.battery_check_s = 300`); la connettività resta sul job esistente da 60 s (`connectivity_check_s`) | D-07/D-08, P-A-03 |
| D3 | Deduplicazione batteria | **Scaglioni da 5 punti**: primo valore sotto 15%, poi solo se scende di almeno 5 punti (14→9→4); `battery_last_alert` conserva istante e livello; si azzera sopra soglia | D-01, P-A-04/P-A-14 |
| D4 | Deduplicazione credenziali | **Una volta all'ora** (`credential_last_alert`, finestra 3600 s); errori successivi soppressi e loggati; il marcatore si scrive solo dopo un invio riuscito | D-01/D-03, P-A-05/P-A-16 |
| D5 | Definizione di «offline» (BR-10) | **Solo rete assente da C-07**: `is_online()` falso. Il processo spento è coperto dal segnale di vita assente di spec 11 | D-02/D-06, V-10 |
| D6 | Deduplicazione fallimenti/timeout | **Un avviso per esecuzione**; se la causa è `LLMCredentialsError` parte **solo** l'avviso `credential` (senza nome compito: C-38 non lo conosce, il nome resta nello storico e nel messaggio di esito), non anche `task_failed` | D-05, V-08 |

## Riparto di responsabilità tra componenti (anti-duplicazione)

| Componente | Possiede | Delega a | Non duplica perché |
|---|---|---|---|
| C-36 Alert Service | composizione del testo, deduplicazione batteria/credenziali, invio all'admin, log; nessuna interrogazione di C-04 (V-09) | C-10 (invio), C-02 (`settings`) | C-09/C-37/C-38 decidono *quando*; C-36 decide *se* e *come* |
| C-37 Device Monitor | lettura batteria/rete, marcatori `offline_since`/`last_online_at`, avviso batteria e rientro offline | C-07 (letture), C-36 (avvisi), C-02 (marcatori) | C-19 non scrive più i marcatori; un solo scrittore |
| C-38 Credential Monitor | classificazione 401/402/403 e inoltro | C-36 | C-05 rileva l'HTTP; C-38 traduce in avviso |
| C-05 LLM Client | chiamata DeepSeek, retry BR-8, `LLMCredentialsError.status`, callback di credenziale | C-38 (callback) | nessuna decisione di avviso dentro C-05 |
| C-09 Execution Engine | esito dell'esecuzione e motivo; inoltro degli avvisi di compito | C-36 (task), C-10 (allowlist invariata), C-11 (storico) | non compone più i testi degli avvisi di sistema |
| C-19 Recovery Handler | recupero occorrenze | C-37 (stato rete e offline) | non scrive marcatori né invia avvisi |
| C-06 Scheduler | esecuzione periodica batteria e connettività | C-37/C-19 | nessun orologio o soglia duplicata |
| C-10 Notification Service | invio, split; il retry BR-8 è nel gateway C-03 | C-03 | C-36 non parla direttamente con Telegram |

**Un solo scrittore di `offline_since`.** C-37 è l'unico punto che imposta e cancella il marcatore;
C-19 non lo legge direttamente: riceve solo `OnlineStatus`. **Un solo punto di deduplicazione.** C-36 possiede i
marcatori `battery_last_alert` e `credential_last_alert`; C-37 e C-38 non li toccano. **Un solo
punto di invio.** Tutti gli avvisi passano da `NotificationService.alert_admin`.

## Contratti (forma dei tipi)

```python
# alerts.py — C-36
BATTERY_MARKER = "battery_last_alert"
CREDENTIAL_MARKER = "credential_last_alert"
BATTERY_ESCALATION_STEP = 5
CREDENTIAL_ALERT_WINDOW_S = 3600
CLOSE_TIMEOUT_S = 5
ALERT_KINDS = frozenset(
    {"task_failed", "task_timeout", "battery_low", "offline_resumed", "credential"}
)

@dataclass(frozen=True)
class Alert:
    kind: str
    detail: Mapping[str, Any]
    sent_at: datetime | None = None   # valorizzato solo dopo un invio riuscito

class AlertService:
    def __init__(
        self,
        notifications: NotificationService,
        settings: SettingsRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        battery_escalation_step: int = BATTERY_ESCALATION_STEP,
        credential_window_s: int = CREDENTIAL_ALERT_WINDOW_S,
    ) -> None: ...
    async def alert(self, kind: str, detail: Mapping[str, Any]) -> bool: ...
    def alert_threadsafe(
        self, kind: str, detail: Mapping[str, Any]
    ) -> concurrent.futures.Future[bool] | None: ...
    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None: ...
    def unbind_loop(self) -> None: ...
    async def close(self) -> None: ...   # chiude, dissocia e attende gli alert in volo
```

```python
# device_monitor.py — C-37
OFFLINE_SINCE = "offline_since"
LAST_ONLINE_AT = "last_online_at"

@dataclass(frozen=True)
class OnlineStatus:
    online: bool | None          # None = stato non leggibile (DeviceError)
    resumed: bool = False        # True se esisteva offline_since e la rete è tornata
    offline_s: int | None = None # durata, solo con marcatore valido; None se assente/invalido

class DeviceMonitor:
    def __init__(
        self,
        device: DeviceAdapter,
        settings: SettingsRepository,
        alerts: AlertService,
        *,
        battery_threshold_pct: int,
        offline_threshold_s: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    async def check_battery(self) -> int | None: ...
    async def check_online(self) -> OnlineStatus: ...
    async def is_online(self) -> bool | None: ...
    def offline_since(self) -> datetime | None: ...
```

```python
# credential_monitor.py — C-38
class CredentialMonitor:
    def __init__(self, alerts: AlertService) -> None: ...
    def on_llm_error(self, http_status: int, body: str = "") -> bool: ...
```

```python
# llm.py — C-05 (estensione)
LLMClient(
    config,
    ...,
    on_credentials_error: Callable[[int, str], bool] | None = None,  # valore ignorato da C-05
)
# errors.py
class LLMCredentialsError(LLMError):
    def __init__(self, message: str, *, status: int | None = None) -> None: ...
```

```python
# execution.py — C-09 (estensione)
ExecutionEngine(
    llm, history, notifications,
    ...,
    alerts: AlertService | None = None,
)
# task_timeout: alerts.alert("task_timeout", {"task": ..., "timeout_s": ...})
# task_failed:  alerts.alert("task_failed",  {"task": ..., "reason": ...})
# credential:   nessun avviso da C-09; C-38 è l'unico produttore
```

```python
# recovery.py — C-19 (estensione)
RecoveryHandler(
    ...,                      # tasks, registrar, engine, history; `settings` rimosso
    monitor: DeviceMonitor,   # sostituisce `device`
)
# check_connectivity: status = await monitor.check_online()
#   online is not True -> []
#   resumed -> _recover(now)
# recover_missed: await monitor.is_online() is True, altrimenti rinvio
```

- **`alert`** è asincrona e idempotente rispetto alla deduplicazione: restituisce `True` se il
  messaggio è stato inviato, `False` se soppresso, non riconosciuto o non inviato. Non solleva
  eccezioni di invio: un Telegram irraggiungibile è loggato (la liveness di spec 11 copre
  l'assenza). La decisione di deduplicazione e la **prenotazione** del marcatore avvengono sotto
  `asyncio.Lock`; l'invio (con i retry BR-8 del gateway C-03, invocato da C-10) avviene **fuori** dal lock. Un secondo avviso
  dello stesso tipo durante l'invio trova la prenotazione e viene soppresso; a invio riuscito il
  marcatore definitivo è scritto, a invio fallito la prenotazione è rilasciata e il successivo
  tentativo può riprovare.
- **`alert_threadsafe`** esiste per C-05/C-38, che girano in `asyncio.to_thread`: se il loop è
  associato e il servizio non è chiuso, pianifica `alert` con `run_coroutine_threadsafe`; altrimenti
  logga e restituisce `None`. Il chiamante non attende.
- **`check_battery`** legge C-07 in `asyncio.to_thread`, poi chiama **sempre** C-36 con
  `{"level": livello, "threshold": soglia}`: C-36 usa la soglia ricevuta (nessuna seconda copia in
  C-36), invia o azzera il marcatore. Un `DeviceError` produce `None`, log e nessun avviso.
- **`check_online`** legge C-07 in `asyncio.to_thread`. Online: aggiorna `last_online_at` e
  `last_contact_at`; se `offline_since` esiste, calcola la durata, **cancella sempre**
  `offline_since` (il periodo è concluso) e poi tenta l'avviso `offline_resumed` quando
  `durata > offline_threshold_s`. Un invio fallito non deve produrre un nuovo avviso a ogni
  campionamento. Offline:
  imposta `offline_since` se assente. `DeviceError`: `OnlineStatus(online=None)`, nessuna modifica
  ai marcatori. L'invio fallito è loggato e coperto dalla liveness di spec 11 (rischio dichiarato
  da spec 10).
- **`is_online`** è la lettura pura per C-19 (`recover_missed`): non scrive marcatori e non invia
  avvisi. È **asincrona** e offloada C-07 in `asyncio.to_thread`, come faceva C-19. `offline_since`
  è sincrona ma legge solo `SettingsRepository` e va chiamata sul thread dell'event loop; nessun
  metodo di C-37 tocca il database da un worker (la connessione ha `check_same_thread=True`).
- **`on_llm_error`** è sincrona (C-05 è sincrona): classifica `401`/`402`/`403` e chiama
  `alerts.alert_threadsafe("credential", {"status": status})`. Restituisce `True` se lo status è
  stato riconosciuto e inoltrato (anche se la deduplicazione o il loop assente lo sopprimono),
  `False` per gli altri status. Il valore non è l'esito dell'invio e C-05 lo ignora.

## Regole di deduplicazione e testi

| `kind` | Quando | Deduplicazione | Marcatore | Reset |
|---|---|---|---|---|
| `task_failed` | C-09 conclude `errore` (eccetto credenziali) | nessuna: un avviso per esecuzione | — | — |
| `task_timeout` | C-09 conclude `interrotto` per BR-4 | nessuna: un avviso per esecuzione | — | — |
| `battery_low` | C-37 legge la batteria e passa `level` + `threshold` | scaglioni da 5 punti sotto soglia; `level < threshold` | `battery_last_alert` = `{"at": ISO, "level": N}` | `level >= threshold` cancella il marcatore |
| `offline_resumed` | C-37 rileva il rientro dopo un periodo | un avviso per periodo | nessuno di C-36; `offline_since` è di C-37 e viene cancellato | nuovo periodo = nuovo avviso |
| `credential` | C-38 riceve 401/402/403 | una volta ogni 3600 s | `credential_last_alert` = ISO dell'invio riuscito | finestra scaduta |

**Campi di `detail`** (obbligatori salvo dove indicato):

| `kind` | Campi |
|---|---|
| `task_failed` | `task` (nome), `reason` (tipo dell'eccezione) |
| `task_timeout` | `task` (nome), `timeout_s` (secondi) |
| `battery_low` | `level` (intero), `threshold` (intero) |
| `offline_resumed` | `since` (ISO), `until` (ISO), `offline_s` (interi) |
| `credential` | `status` (intero) |

**Testi** (italiano, solo dati non sensibili):

| `kind` | Testo |
|---|---|
| `task_failed` | `⚠️ Compito «{task}» fallito: {reason}` |
| `task_timeout` | `⏱️ Compito «{task}» interrotto: timeout dopo {minuti} minuti` |
| `battery_low` | `🔋 Batteria al {level}% (soglia {threshold}%)` |
| `offline_resumed` | `📡 Telefono di nuovo online dopo {durata}: offline dalle {inizio} alle {fine}.` |
| `credential` | `🔑 DeepSeek: {motivo} (HTTP {status}). Controlla la chiave o il credito.` |

- `reason` per `task_failed` è il **tipo** dell'eccezione (es. `TimeoutError`), non il messaggio:
  evita di esporre percorsi o contenuti.
- `credential` mappa `401 → chiave non valida`, `402 → credito esaurito`, `403 → accesso negato`.
- `offline_resumed` formatta inizio/fine nel fuso del telefono (`astimezone()`) e la durata in
  `X h Y min`, `X h` (ore esatte; secondi troncati) o `Y min`; sotto il minuto è `0 min`.
- `task_timeout` usa `minuti = max(1, round(timeout_s / 60))`, quindi 600 s → `10 minuti`; il
  valore è sempre un intero e non contiene decimali.
- Un `kind` sconosciuto o un `detail` privo dei campi obbligatori produce log `avviso scartato` e
  `False`, mai un messaggio inventato.

## Marcatori in `settings` (nessuna migrazione)

| Chiave | Scritta da | Letta da | Formato | Note |
|---|---|---|---|---|
| `offline_since` | C-37 | C-37 (`_read_offline_since`); **C-19 no** (riceve `OnlineStatus`) | ISO 8601 con offset | già usata da spec 03; un solo scrittore e un solo validatore |
| `last_online_at` | C-37 | spec 11 | ISO 8601 con offset | C-37 scrive e non rilegge; nome dichiarato da spec 10 |
| `last_contact_at` | C-07 `record_last_contact` (invocato da C-37) | nessuno in `src/` (solo test) | ISO 8601 con offset | mantenuta per compatibilità; arch 03 la aggiorna in T13 (V-02) |
| `battery_last_alert` | C-36 | C-36 | JSON `{"at": ISO, "level": int}` | valore corrotto = nessun marcatore |
| `credential_last_alert` | C-36 | C-36 | ISO 8601 con offset | scritto solo dopo invio riuscito |
| `liveness_last_sent` | spec 11 | spec 11 | — | **non toccata** in questa voce |

La durata offline si calcola da `offline_since` all'istante del rientro. **Un solo punto** legge e
valida il marcatore: `DeviceMonitor._read_offline_since() -> tuple[bool, datetime | None]`, usato
sia da `offline_since()` sia da `check_online()`. Restituisce `(esisteva, istante)`: `False` se il
marcatore è assente; `True` con l'istante se è valido; `True` con `None` se è invalido o nel futuro,
dopo averlo **cancellato** e loggato `marcatore offline non valido`. `check_online` usa `esisteva`
per `resumed` e valorizza `offline_s` solo con un istante valido: un marcatore invalido produce
`resumed=True`, `offline_s=None`, nessun avviso, e C-19 recupera comunque le occorrenze mancate.
`offline_since()` pubblico restituisce solo l'istante o `None`.

## Modello di dominio

- **Avviso:** `Alert(kind, detail, sent_at)`; è un evento in memoria, non una riga persistita.
  `sent_at` è valorizzato solo dopo un invio riuscito; il testo composto resta interno a C-36.
- **Tipi:** `task_failed`, `task_timeout`, `battery_low`, `offline_resumed`, `credential`
  (spec 10 §Modello di dominio).
- **Soglie:** batteria < 15% (BR-9); offline > 1 h (BR-10); timeout 10 min (BR-4); fallimento
  dopo i retry BR-8 di C-05.
- **Stato rete:** `OnlineStatus.online` è `True`, `False` o `None` (non leggibile); `resumed` e
  `offline_s` descrivono l'eventuale periodo appena concluso.

## Concorrenza e ciclo di vita

- **Loop e thread.** C-36 `alert` gira sull'event loop; `alert_threadsafe` è l'ingresso dai
  chiamanti sincroni di C-05, che possono stare sul loop o su un worker. Un `asyncio.Lock`
  serializza **solo** decisione e prenotazione della deduplicazione; l'invio resta fuori dal lock,
  così i retry BR-8 non bloccano gli altri avvisi.
- **Chiusura.** `AgentApp.stop` segue quest'ordine: `scheduler.shutdown(wait=False)` (nessun nuovo
  job batteria), `await alerts.close()` (marca il servizio chiuso, dissocia il loop e attende gli
  `alert` già pianificati per al massimo `CLOSE_TIMEOUT_S = 5` secondi), `gateway.stop()`,
  `db.close()`. Allo scadere `close()` logga `avvisi in volo non attesi` e prosegue. Chiudere dopo
  il gateway renderebbe inutile l'attesa (gli invii fallirebbero); chiudere dopo il database
  rischierebbe scritture su una connessione chiusa.
- **Riavvio.** I marcatori sono in `settings`: dopo un riavvio la deduplicazione batteria e
  credenziali resta valida. `offline_since` sopravvive e il primo `check_online` al rientro produce
  l'avviso, se la durata supera la soglia.
- **Nessuna cache di ruolo.** Gli avvisi vanno all'id admin di configurazione tramite C-10; C-04 non
  viene interrogato (V-09).

## Deviazioni pre-dichiarate (numerazione stabile per il documento 10)

| # | Deviazione | Fonte modificata | Motivo |
|---|---|---|---|
| V-01 | C-37 è l'unico scrittore di `offline_since`; C-19 delega e non scrive più marcatori | spec 03 C-19 / spec 10 C-37 | evitare due scrittori e due avvisi sullo stesso rientro; C-19 conserva il recupero |
| V-02 | `last_online_at` (spec 10) è **autoritativo** ed è scritto accanto a `last_contact_at` (spec 01/03), mantenuto per compatibilità | spec 01 C-07, architettura 03 | la divergenza di naming era già dichiarata dall'architettura 03; un solo significato, due chiavi, nessun lettore in `src/` che decida su `last_contact_at` |
| V-03 | `alert(kind, detail)` accetta un mapping strutturato e restituisce `bool` | spec 10 C-36 | C-36 deve comporre il testo e deduplicare; il tipo di `detail` non è dichiarato |
| V-04 | Nessuna tabella `alerts`: deduplicazione in `settings` | spec 10 §Modello dati («eventualmente») | evita una migrazione e un secondo modello dati; i marcatori sono già il meccanismo dichiarato |
| V-05 | C-05 invoca C-38 tramite callback opzionale; C-36 espone un ponte thread-safe | spec 10 flusso 4 (C-05 → C-38 → C-36) | C-05 è sincrona e può essere chiamata sia dal loop sia da `asyncio.to_thread`; `run_coroutine_threadsafe` è sicuro da entrambi, quindi il ponte preserva la catena senza bloccare l'event loop |
| V-06 | Job batteria ogni 300 s con `limits.battery_check_s` | spec 10 domanda aperta 1 | D2; la connettività resta a 60 s |
| V-07 | `task_failed`/`task_timeout` passano da C-36; l'avviso allowlist di spec 07 resta diretto | spec 10 C-36 / spec 07 | l'allowlist non è un `kind` di spec 10 e ha già un testo e un test propri |
| V-08 | Un errore di credenziale non produce anche `task_failed` | spec 10 AC-01/AC-04 | D6: un solo avviso specifico evita raffiche quando la chiave è rotta |
| V-09 | C-04 non è interrogato da C-36 | spec 10 C-36 (dipendenze) | l'admin è l'id di configurazione e C-10 invia solo a quello; nessuna decisione di ruolo da duplicare |
| V-10 | Ripartenza, liveness, `liveness_last_sent`, boot recovery restano a spec 11 | spec 10 dipendenza 11 | D1: la voce 10 non invia messaggi di ripartenza né segnali di vita |
| V-11 | Batteria non leggibile o rete non leggibile → nessun avviso spurio; stato rete `None` | spec 10 C-37 error handling; spec 03 fail-safe | un guasto di Termux:API non deve simulare un periodo offline o una batteria scarica |
| V-12 | Deduplicazione batteria a scaglioni e credenziali a 1 h come costanti di modulo | spec 10 domanda aperta 2 | D3/D4; nessuna chiave di configurazione inventata oltre al campionamento |
| V-13 | Nessuna vista di deployment e nessun ER nuovo | spec 10 | non dichiarati; `settings` è già nel modello dati di spec 01 |
| V-14 | C-37 espone anche `is_online()` (lettura pura) oltre a `check_online()` | spec 10 C-37 | C-19 ha bisogno di una lettura senza marcatori/avvisi per `recover_missed`; evita un secondo scrittore |
| V-15 | Nuovo marcatore `credential_last_alert` in `settings` | spec 10 §Modello dati (elenca solo `battery_last_alert`) | D4 richiede dedup persistente delle credenziali; la tabella `alerts` era «eventuale» e non viene creata |
| V-16 | `RecoveryHandler` riceve `monitor` al posto di `device`, perde `settings`; `OFFLINE_SINCE` è definito in `device_monitor.py` e **riesportato** da `recovery.py` | spec 03 C-19 | `device_monitor.py` è il modulo canonico; il re-export mantiene l'import dei test e dei chiamanti esistenti |
| V-17 | C-06 invoca C-37 (job batteria) e C-19 (connettività); C-37 non chiama C-06 | spec 10 C-37 (dipendenze C-07, C-06) | la dipendenza dichiarata è soddisfatta dal job che invoca il monitor; il monitor non pianifica sé stesso |

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita in questa invocazione
leggendo il solo frontmatter di `.opencode/agents/*.md`, `.opencode/commands/*.md`,
`.opencode/skills/*/SKILL.md` e `opencode.json`; discovery per ruolo, nessun asset legato per
filename.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01…D-10, D-12 (codice, configurazione, test, aggiornamenti di stato) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di produzione di codice Python, test o configurazione | Etichettati *"no specialized capability discovered"*; si procede su spec 10 + constitution + pattern esistenti in `src/agente/` |
| D-11 (documento architettura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata sugli artefatti prodotti e di non generare contenuto | Vincolato **solo come validatore** (Phase 2 struttura e Phase 4 validazione); il produttore resta il Conductor |
| D-11 (struttura del documento) | *nessuno* | — | Nessuna skill dichiara un template per documenti di architettura | Struttura derivata dalle sezioni di spec 10 e dai documenti 09/03; assunzione P-A-01 |

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

Struttura applicabile proposta: **Metadata** (Spec · Voce roadmap · Piano · Constitution · Data ·
Struttura dichiarata + P-A-01 + Governance) · **1** Contesto e obiettivi · **2** Componenti (C-36,
C-37, C-38, estensioni C-05/C-09/C-19/C-06/C-01, C-04/C-10/C-07 invariati in tabella, flowchart) ·
**3** Componenti e capacità non disponibili (liveness/ripartenza, tabella `alerts`, vista
deployment, ER) · **4** Wiring di `AgentApp` · **5** Riparto di responsabilità · **6** Modello di
dominio (`Alert`, `OnlineStatus`, esiti, soglie) · **7** Modello dati (`settings`, marcatori,
nessuna migrazione) · **8** Regole di deduplicazione e testi · **9** Rilevamento offline e
credenziali (regole, non diagramma) · **10 Flussi di dati**: 10.1 fallimento/timeout compito
(AC-01), 10.2 batteria (AC-02), 10.3 offline prolungato (AC-03), 10.4 credenziali (AC-04), tutte
`sequenceDiagram` · **11** Concorrenza e ciclo di vita (ponte thread, lock, riavvio) · **12**
Integrazioni · **13** Sicurezza (solo admin, nessun segreto) · **14** Requisiti non funzionali
(tempestività, deduplicazione; BR-16 non pertinente: avvisi occasionali, nessun volume) · **15** Rischi e assunzioni · **16** Domande aperte chiuse ·
**17** Fuori scope · **18** Deviazioni (V-01…V-17) · **19** Tracciabilità (AC-01…AC-04,
BR-4/8/9/10). Per ogni componente: Responsabilità · Interfaccia · Input/Output · Dipendenze ·
Error handling · Osservabilità · Sicurezza. Nessuna vista deployment e nessun ER: la spec 10 non li
dichiara e `settings` è già nella fondazione.

**Passate del 2026-11-03:**

1. **NOT APPROVED** — soglia batteria non iniettabile in C-36; `offline_since` cancellato prima di
   sapere l'esito; lock tenuto durante i retry BR-8; architettura 03 non aggiornata;
   `last_online_at`/`last_contact_at` senza autorità; AC-01 vs D-06; ordine `bind_loop`;
   `battery_check_s` non passato; DB/thread; log mancanti; `Alert` senza modello; test mancanti.
2. **NOT APPROVED** — `is_online` sincrona sul loop; nome compito nel testo `credential`
   irraggiungibile; arch 03 citata solo come «nota»; `tests/test_llm.py` fuori da D-10; tabella
   marcatori con C-19 lettore; `settings` inutilizzato in C-19; lock/prenotazione generici;
   `Alert.text` non nel modello; `is_online` attribuita all'instradamento job; firma
   `schedule_battery` non keyword-only; soglia al valore esatto; `offline_since` invalido senza
   stato finale; dipendenza C-06 non dichiarata; retry attribuito a C-10; test di log/threshold/
   getter mancanti; checkpoint non registrato.
3. **NOT APPROVED** — retry ancora a C-10; validatore `offline_since` non assegnato; V-17 fuori dal
   §18; test di log non nominati; callback `-> bool` vs `None`; doppio produttore `credential`;
   cella marcatore C-19; ritardo recupero non rischiato; proprietario `OFFLINE_SINCE`.
4. **NOT APPROVED** — retry residuo a C-10; rischio di C-09 produttore; recupero con marcatore
   invalido non dichiarato; ordine build C-10; C-04 nel riparto; test gateway/`is_online` mancanti;
   `on_llm_error` bool; lifecycle avvisi in volo; fake scheduler non nominati.
5. **NOT APPROVED** — semantica `resumed` con marcatore invalido, helper senza forma, nomi test
   offline, `conftest` citato a torto, `test_llm.py invariato` falso, tetto di `close()` non
   dichiarato, doppio `unbind_loop`/`close`, ownership `offline_since`, nota C-04 nel riparto, test
   recovery da migrare, righe di tracciabilità senza id.
6. **NOT APPROVED** — id offline duplicato, test storage inesistente e file fuori da D-10,
   «harness» ancora in T10, path `delivery_history`, spec 09/arch 01 non elencate, ordine
   `close()` rispetto a `gateway.stop()`, «log allowlist», id mancanti per timeout `close()` e
   intervallo batteria.
7. **NOT APPROVED** — contenuto di arch 01 non specificato, BR-8 senza id, `test_storage.py` solo
   in D-10, nome `test_stop_unbinds_alert_loop`, `test_one_alert_per_offline_period` fuori dalla
   tracciabilità BR-10, ordine `scheduler.shutdown`/`alerts.close()` non dichiarato.
8. **APPROVED** con due precisazioni recepite: `last_online_at` attribuito a C-37 (non a C-07) in
   D-12/T13 e righe di spec 10 esplicitate in arch 01 §8 (AC-01…AC-04, BR-4/8/9/10).

**Phase 4 (2026-11-03):** prima **NOT APPROVED** (Governance anticipata, `Alert` mai istanziato,
ordine `offline_since`, C-10 assente in tre sequenze, flowchart C-06→C-37, qualificazione
marcatore, lettori `last_contact_at`, log mancanti, tabella invariati, test lock non discriminante,
formato durata, rischio oscillazione, nomi test nel piano); seconda **NOT APPROVED** (piano non
allineato su ordine offline/lettori/formato, §7 senza ramo offline, `X h` non dichiarato, log
`batteria non leggibile`, stato piano, tracciabilità); terza **NOT APPROVED** (`last_online_at`
letto da C-37, `last_contact_at` con lettore inesistente, V-02 su spec 03, tabella §2 attaccata,
log test mancanti); quarta **APPROVED** con minor recepiti (chiarezza §7, secondi troncati, caso
`0 min`, ordine `start`, test di log aggiunti).

## Assunzioni del piano (non dichiarate da spec 10)

> **P-A-01** Struttura del documento di architettura derivata da spec 10 e dai documenti 09/03, non
> da un template: in `docs/templates/` esistono solo `template.spec.md` e `template.constitution.md`.

> **P-A-02** Soglie: batteria `limits.battery_threshold_pct` (15), offline
> `limits.offline_threshold_s` (3600), timeout `limits.execution_timeout_s` (600). Nessun valore
> duplicato nei componenti.

> **P-A-03** `limits.battery_check_s = 300` è l'unica chiave nuova; la connettività usa
> `limits.connectivity_check_s` (60) già esistente.

> **P-A-04** `battery_last_alert` contiene JSON `{"at": ISO, "level": int}`. Valore corrotto o
> chiave assente = nessun avviso precedente. Con `level < threshold` si invia al primo valore o a
> un'escursione di almeno 5 punti; con `level >= threshold` il marcatore è cancellato e non si
> invia nulla (il valore esatto di soglia non è un avviso).

> **P-A-05** `credential_last_alert` è ISO 8601 e si scrive **dopo** un invio riuscito; una finestra
> di 3600 s sopprime gli errori successivi.

> **P-A-06** Offline: `durata = now - offline_since`; l'avviso scatta solo con
> `durata > offline_threshold_s` (strettamente maggiore). `offline_since` è impostato al primo
> campionamento offline e cancellato al rientro.

> **P-A-07** `last_online_at` è scritto a ogni campionamento online; `last_contact_at` continua a
> essere scritto da `DeviceAdapter.record_last_contact` per i test e per la compatibilità con
> l'architettura 03; nessun lettore in `src/`; spec 11 usa `last_online_at`.

> **P-A-08** `alert` non solleva errori di invio: un `TelegramError`/`AgenteError` è loggato e
> restituisce `False`. La prenotazione di deduplicazione viene rilasciata, così il tentativo
> successivo può riprovare. Eccezione dichiarata: `offline_since` è cancellato **prima** del tentativo
> anche se l'invio fallisce, perché il periodo offline è concluso e un retry a ogni campionamento
> sarebbe una raffica; l'assenza è coperta da spec 11.

> **P-A-09** `alert_threadsafe` richiede `bind_loop`, eseguito in `AgentApp.start`. Senza loop
> associato l'avviso è loggato e scartato; nessuna attesa bloccante.

> **P-A-10** `task_failed`/`task_timeout` non hanno deduplicazione: ogni esecuzione è un evento
> distinto. Un errore di credenziale è l'eccezione (V-08).

> **P-A-11** Mappatura credenziali: `401` chiave non valida, `402` credito esaurito, `403` accesso
> negato. Altri status non producono `credential` (restano errori transitori o generici di C-05).

> **P-A-12** `DeviceError` su batteria → `None` e log; su rete → `OnlineStatus(online=None)`, nessun
> marcatore toccato. C-19 tratta `None` come non-online e rinvia il recupero, senza avvisi.

> **P-A-13** I test usano clock, device, notifiche e LLM finti; nessun test dipende da ora, rete,
> Termux:API o DeepSeek reali.

> **P-A-14** `check_battery` chiama C-36 a ogni campionamento; C-36 invia solo al primo valore sotto
> soglia o a un'escursione di almeno 5 punti, e azzera il marcatore sopra soglia.

> **P-A-15** C-19 `check_connectivity` usa `check_online` (marcatori + avviso); `recover_missed` usa
> `await is_online()` (sola lettura, C-07 offloadato in `to_thread`), così un riavvio non duplica
> l'avviso di rientro e non blocca l'event loop.

> **P-A-16** La deduplicazione credenziali è persistente al riavvio; il marcatore non viene toccato
> da un invio fallito.

> **P-A-17** Un `offline_since` non parsabile o nel futuro è **cancellato** e loggato `marcatore
> offline non valido` dall'unico helper `_read_offline_since() -> tuple[bool, datetime | None]`.
> `check_online` restituisce `resumed=True` con `offline_s=None` (nessun avviso, durata non
> inventata), così C-19 recupera le occorrenze mancate; `offline_since()` restituisce `None`. Il
> valore non resta leggibile a spec 11.

> **P-A-18** Nessuna migrazione e nessuna tabella `alerts`; `settings` è l'unico storage dei
> marcatori.

> **P-A-19** L'avviso allowlist di spec 07 resta diretto su C-10 con il testo esistente; non passa
> da C-36 e non è deduplicato.

> **P-A-20** C-38 non logga il corpo della risposta DeepSeek: solo status e tipo. C-05 tronca il
> corpo a 500 caratteri prima del callback e non lo include nell'eccezione.

> **P-A-21** `AlertService` usa un `asyncio.Lock` per serializzare **solo** la decisione di
> deduplicazione e la prenotazione del marcatore; l'invio con i retry BR-8 resta fuori dal lock. Il
> lock è creato pigramente nel loop di `alert`, non nel costruttore. `task_failed` e `task_timeout`
> non hanno marcatore né prenotazione: non entrano nel lock e non vengono deduplicati.

> **P-A-22** `AgentApp` espone `alerts`, `device_monitor`, `credentials`; `start` associa il loop
> **prima** di `recover_missed` e schedula il job batteria; `stop` esegue `scheduler.shutdown(wait=
> False)`, poi `await alerts.close()` (dissocia e attende gli avvisi in volo), poi `gateway.stop()` e
> `db.close()`.

> **P-A-23** Un `LLMClient` iniettato nei test non riceve automaticamente il callback di C-38: i
> test di credenziale usano un `LLMClient` reale con `httpx.MockTransport` o chiamano C-38
> direttamente.

> **P-A-24** Il job batteria è registrato con `replace_existing=True` e id `battery:check`; un
> errore del callback è loggato da C-06 senza fermare gli altri job.

> **P-A-25** `OnlineStatus.resumed` è `True` se `offline_since` esisteva (valido o invalido) e la
> rete è tornata online; un primo avvio online senza marcatore non produce `offline_resumed`.
> `offline_s` è valorizzato solo con marcatore valido e durata calcolata.

> **P-A-26** `last_online_at` è il nome **autoritativo** per spec 10/11; `last_contact_at` resta
> scritto da `DeviceAdapter.record_last_contact` per compatibilità con spec 01/03 e non ha lettori
> in `src/` oltre ai test. I due valori sono scritti nello stesso istante; nessun codice decide in
> base a `last_contact_at`.

> **P-A-27** `Alert` è un modello **in memoria** (`kind`, `detail`, `sent_at`), non persistito e senza
> tabella; `sent_at` è valorizzato solo dopo un invio riuscito. Il testo composto è interno a
> `_compose` e non fa parte del modello.

> **P-A-28** `CredentialMonitor.on_llm_error` accetta `body` per rispettare il contratto di spec 10,
> ma non lo usa e non lo logga; C-05 lo tronca comunque a 500 caratteri. La classificazione dipende
> solo dallo status HTTP.

> **P-A-29** C-37 è chiamato solo dal thread dell'event loop per la parte `settings`; le letture
> C-07 sono in `asyncio.to_thread` (`check_*` e `is_online`). `offline_since()` è sincrona, legge
> solo `settings` e non va invocata da worker.

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | C-36 Alert Service | D-01 | cinque `kind` con testi della tabella; `alert` restituisce `True/False`; `battery_low` usa `level` e `threshold` del `detail`; dedup batteria a scaglioni e reset; dedup credenziali a 3600 s; `kind` sconosciuto/detail incompleto scartato; invio solo all'admin; log inviato/deduplicato/scartato/non inviato; decisione sotto lock, invio fuori lock |
| T2 | Ponte thread-safe | D-01 | `bind_loop`/`unbind_loop`/`alert_threadsafe`; chiamata da worker senza bloccare; senza loop log e `None`; dopo `unbind` nessun invio; `close()` attende gli in-flight e allo scadere di `CLOSE_TIMEOUT_S` logga senza bloccare |
| T3 | C-37 Device Monitor | D-02 | batteria 14 → avviso, 15 → nessuno, `DeviceError` → `None`; offline imposta `offline_since`; rientro <1 h nessun avviso, >1 h avviso con durata; `offline_since` cancellato **prima** del tentativo; `last_online_at` e `last_contact_at`; stato non leggibile non tocca i marcatori; `offline_since` invalido/futuro cancellato con `resumed=True` e `offline_s=None`; log di livello, soglia, stato e durata |
| T4 | C-38 Credential Monitor | D-03 | 401/402/403 → `credential` con motivo; 400/429/500 → nessun avviso; callback chiamato una volta; nessun corpo nei log (test dedicato); log del solo status |
| T5 | C-05 callback e errore tipizzato | D-04 | `LLMCredentialsError.status`; callback su 401/402/403 prima dell'eccezione; corpo troncato; callback assente = comportamento invariato; nessun segreto in messaggio o log |
| T6 | C-09 avvisi di compito | D-05 | timeout → `task_timeout`; errore → `task_failed` con tipo; credenziale → nessun `task_failed` e nessun `credential` da C-09 (solo C-38); avviso allowlist invariato; `alerts=None` fallback ai testi esistenti |
| T7 | C-19 delega a C-37 | D-06 | `check_connectivity` usa `check_online`; `recover_missed` usa `await is_online()`; `resumed=True` (anche con `offline_s=None`) esegue il recupero; nessun secondo scrittore di `offline_since`; `OFFLINE_SINCE` riesportato; costruttore senza `settings`, con `monitor=`; `test_offline_marker_is_written_and_cleared_on_return` rimosso da `tests/test_recovery.py` e sostituito da `tests/test_device_monitor.py::test_offline_marker_is_written_and_cleared` + `tests/test_recovery.py::test_connectivity_uses_the_monitor` |
| T8 | Job batteria | D-07, D-08 | `schedule_battery(callback, *, interval_s)` registra `battery:check`, rifiuta `interval_s <= 0`; `_run_battery_job` attende il callback e isola gli errori; `battery_check_s` tipizzato, validato (positivo) e documentato; `FakeScheduler` in `tests/test_bootstrap.py` e `AppScheduler` in `tests/test_scheduled_ac.py` aggiornati (`tests/conftest.py` non contiene scheduler finti) |
| T9 | Wiring `AgentApp` | D-09 | build di C-10, poi C-36/C-37/C-38, poi C-05 con callback; `stop` esegue `scheduler.shutdown(wait=False)`, `await alerts.close()`, poi `gateway.stop()` e `db.close()`; campi esposti; `start` associa il loop **prima** di `recover_missed` e schedula `battery_check_s` (non il default); `_dispatch_task` continua a usare C-07 direttamente |
| T10 | Test unit e di integrazione | D-10 | nuovi test C-36/C-37/C-38/C-05/C-09/C-19/C-06; casi per marcatore batteria corrotto, persistenza credenziali al riavvio, `offline_since` invalido/futuro, `battery_check_s` non valido, isolamento errori job, corpo C-38 non loggato, soglia batteria dal `detail`, getter `offline_since`, minuti timeout interi; estensioni a `test_llm.py`, configurazione, scheduler, bootstrap, `test_storage.py`; suite verde |
| T11 | AC-01…AC-04 end-to-end | D-10 | AC-01 compito fallito → avviso con nome e motivo; AC-02 batteria 14% → avviso; AC-03 offline 2 h → avviso con periodo al rientro; AC-04 DeepSeek 402 → avviso credenziale specifico; nessun doppione |
| T12 | Documento architettura 10 | D-11 | sezioni 1…19; 1 flowchart + 4 sequenze 10.1–10.4; tabelle dedup/testi/marcatori; `Alert` in memoria e assenza di tabella; checkpoint Phase 2 e Phase 4 **APPROVED**; deployment ed ER dichiarati assenti con motivo |
| T13 | Pubblicazione | D-12 | roadmap 10 `[x]`; spec 10 `Implemented (2026-11-03)` + note; delivery history con esito, gap e V-01…V-17; piano eseguito; note di continuità su spec 01/03/09, aggiornamento esplicito di architettura 01 (§2 con `last_online_at` attribuito a C-37; §8 con AC-01…AC-04 e BR-4/8/9/10 di spec 10) e architettura 03 (§2, §5, §6.2, §14) |

## Dipendenze

- Item 01: C-01 (`limits`), C-02 (`settings`), C-05 (`LLMClient`, `LLMCredentialsError`), C-06
  (scheduler), C-07 (`battery_level`, `is_online`, `record_last_contact`), C-10 (`alert_admin`),
  C-13.
- Item 03: C-09 (timeout/errore e avvisi), C-19 (`check_connectivity`, `recover_missed`,
  `offline_since`).
- Item 07/08: avvisi allowlist e sconosciuti restano invariati; nessuna interazione.
- **Item 11 (non consegnata):** confini condivisi in D1/V-10; nessun blocco. `last_online_at` e
  `offline_since` sono i marcatori che 11 userà.

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Doppio avviso di credenziale (C-38 ripetuto) | stesso `kind` e stessa finestra di deduplicazione in C-36; C-09 non produce `credential`; test dedicato |
| Due scrittori di `offline_since` | C-37 unico scrittore; C-19 delega (V-01); test che verifica un solo avviso per rientro |
| Avviso offline spurio per Termux:API assente | `DeviceError` → stato `None`, marcatori intatti (V-11) |
| Raffica di avvisi batteria | scaglioni da 5 punti e reset sopra soglia (D3) |
| Raffica con chiave rotta | una volta all'ora e un solo produttore `credential` (C-38); `task_failed` soppresso (D4/D6) |
| Ponte thread che perde l'avviso | `bind_loop` in `start` **prima** di `recover_missed`; log `avviso non pianificato`; test con `LLMClient` reale e loop associato |
| Lock C-36 tenuto durante i retry BR-8 | decisione/prenotazione sotto lock, invio fuori; test `test_send_happens_outside_the_lock` |
| Avviso offline perso se Telegram è irraggiungibile | `offline_since` cancellato **prima** del tentativo; log e liveness di spec 11 (P-A-08/V-10) |
| Recupero C-19 ritardato dai retry dell'avviso offline | l'avviso è awaited con i retry del gateway; il recupero resta idempotente e avviene al termine; ritardo dichiarato |
| Invio Telegram irraggiungibile | il gateway C-03 ritenta BR-8; C-36 logga e non marca la dedup; liveness di spec 11 copre l'assenza |
| Dati sensibili nei testi | solo nome compito, tipo errore, livello batteria, orari, status HTTP (P-A-20) |
| Riavvio che duplica l'avviso di rientro | `recover_missed` in sola lettura (P-A-15); `offline_since` cancellato al primo rientro; test `tests/test_device_monitor.py::test_one_alert_per_offline_period` |
| Regressione su item 01/03 | C-09/C-19 mantengono esiti e recupero; test esistenti aggiornati solo per la dipendenza `monitor`/`alerts` |
| Job batteria che blocca l'event loop | lettura in `asyncio.to_thread`; invio asincrono |

## Criteri di validazione (done della voce)

1. `PYTHONPATH=src:.deps python3 -m pytest` verde (inclusi i test di item 01–09).
2. AC-01: compito fallito dopo i tentativi (cause diverse dalle credenziali) → avviso admin con nome e motivo; un errore di credenziale segue AC-04 e produce solo `credential`.
3. AC-02: batteria al 14% → avviso; al 15% nessun avviso.
4. AC-03: offline 2 h → al rientro avviso con il periodo; offline 30 min → nessun avviso.
5. AC-04: DeepSeek 402 → avviso credenziale specifico, una volta per finestra.
6. Dedup: batteria a scaglioni (14→9→4) e reset sopra soglia; credenziali a 1 h; fallimenti per
   esecuzione.
7. Marcatori: `offline_since`/`last_online_at`/`last_contact_at`/`battery_last_alert`/
   `credential_last_alert` con i formati della tabella; `liveness_last_sent` non toccata.
8. C-19: un solo scrittore di `offline_since`; recupero invariato; nessun avviso duplicato al boot.
9. C-05: `LLMCredentialsError.status`; callback su 401/402/403; nessun segreto nei log.
10. Wiring: `AgentApp` espone i tre componenti, associa il loop, schedula `battery:check`, dissocia
    in `stop`.
11. Documento D-11 conforme alla struttura dichiarata e approvato al checkpoint Phase 4.
12. Catena di tracciabilità ricostruibile: voce roadmap 10 → spec 10 → binding → task → artefatti →
    validazione → pubblicazione.

## Tracciabilità attesa (compilata a Publish)

| Requisito / criterio | Test previsto |
|---|---|
| AC-01 compito fallito (cause non-credenziali) | `tests/test_alerts_ac.py::test_ac01_failed_task_alerts_admin` |
| AC-02 batteria 14% | `tests/test_alerts_ac.py::test_ac02_low_battery_alerts_admin` |
| AC-03 offline 2 h | `tests/test_alerts_ac.py::test_ac03_offline_period_alerts_on_return` |
| AC-04 credenziale | `tests/test_alerts_ac.py::test_ac04_credential_error_alerts_admin` |
| BR-4 timeout | `tests/test_execution.py::test_timeout_uses_alert_service`, `tests/test_alerts.py::test_task_timeout_text` |
| BR-8 retry | `tests/test_llm.py::test_transient_error_is_retried_three_times`, `::test_failure_after_three_attempts`; `tests/test_telegram_gateway.py::test_retry_three_times_on_transient_error` (gateway C-03) |
| BR-9 soglia batteria | `tests/test_device_monitor.py::test_battery_below_threshold_alerts`, `::test_battery_at_threshold_does_not_alert` |
| BR-10 offline | `tests/test_device_monitor.py::test_long_offline_alerts_on_return`, `::test_short_offline_does_not_alert`, `::test_one_alert_per_offline_period` |
| Dedup batteria | `tests/test_alerts.py::test_battery_escalates_every_five_points`, `::test_battery_marker_resets_above_threshold` |
| Dedup credenziali | `tests/test_alerts.py::test_credential_is_deduplicated_within_one_hour`, `::test_credential_dedup_survives_a_new_service` |
| Fallimenti per esecuzione | `tests/test_alerts.py::test_task_failure_is_not_deduplicated` |
| Testi e admin-only | `tests/test_alerts.py::test_alert_texts`, `::test_alerts_go_only_to_admin`, `::test_timeout_minutes_are_integers` |
| Errori di invio | `tests/test_alerts.py::test_failed_send_does_not_mark_dedup`, `::test_send_happens_outside_the_lock` |
| `kind` sconosciuto / detail incompleto | `tests/test_alerts.py::test_unknown_kind_is_discarded`, `::test_missing_detail_is_discarded` |
| Marcatore batteria corrotto | `tests/test_alerts.py::test_corrupted_battery_marker_is_ignored` |
| Persistenza credenziali al riavvio | `tests/test_alerts.py::test_credential_dedup_survives_a_new_service` |
| Log C-36/C-37/C-38 | `tests/test_alerts.py::test_logs_sent_and_deduplicated`, `::test_logs_marker_reset_and_unplanned`, `::test_logs_discarded_alerts`, `tests/test_device_monitor.py::test_logs_level_and_threshold`, `::test_logs_network_state`, `::test_logs_unreadable_and_invalid_marker`, `tests/test_credentials.py::test_logs_status_only`, `::test_logs_invalid_status` |
| Ponte thread | `tests/test_alerts.py::test_alert_threadsafe_requires_a_bound_loop`, `::test_alert_threadsafe_schedules_on_loop`, `::test_unbind_stops_scheduling`, `::test_close_waits_for_inflight_alerts`, `::test_close_times_out_pending_alerts` |
| C-37 batteria | `tests/test_device_monitor.py::test_battery_unreadable_is_silent`, `::test_battery_reading_is_returned`, `::test_battery_at_threshold_resets_marker` |
| Soglia dal `detail` | `tests/test_alerts.py::test_battery_uses_the_threshold_from_detail` |
| C-37 offline | `tests/test_device_monitor.py::test_offline_marker_is_written_and_cleared`, `::test_unknown_state_does_not_touch_markers`, `::test_invalid_marker_is_cleared_and_recovers`, `::test_future_marker_is_cleared_and_recovers`, `::test_offline_marker_is_cleared_after_a_failed_alert` |
| Recupero con marcatore invalido | `tests/test_recovery.py::test_invalid_marker_still_recovers` |
| C-37 marcatori | `tests/test_device_monitor.py::test_last_online_and_last_contact_are_written`, `::test_offline_since_getter` |
| C-37 `is_online` pura | `tests/test_device_monitor.py::test_is_online_does_not_write_markers`, `::test_is_online_unreadable_returns_none` |
| C-38 classificazione | `tests/test_credentials.py::test_credential_statuses_are_classified`, `::test_transient_status_is_ignored`, `::test_body_is_not_logged` |
| Marcatore credenziale corrotto | `tests/test_alerts.py::test_corrupted_credential_marker_is_ignored` |
| C-05 callback | `tests/test_llm.py::test_credentials_error_calls_the_monitor`, `::test_credentials_error_exposes_status` |
| C-09 credenziale | `tests/test_execution.py::test_credential_error_does_not_alert_task_failed`, `::test_generic_failure_uses_alert_service` |
| C-38 unico produttore `credential` | `tests/test_credentials.py::test_credential_is_produced_once` |
| C-19 delega | `tests/test_recovery.py::test_connectivity_uses_the_monitor`, `::test_boot_does_not_alert` |
| Job batteria | `tests/test_scheduler.py::test_battery_job_is_registered`, `::test_battery_job_error_is_isolated`, `::test_battery_interval_must_be_positive` |
| Configurazione | `tests/test_config.py::test_loads_valid_config` (battery_check_s), `::test_invalid_battery_check_is_rejected` |
| Wiring | `tests/test_bootstrap.py::test_build_exposes_alert_components`, `::test_start_binds_alert_loop_and_schedules_battery`, `::test_stop_closes_alert_service` |
| Nessuna migrazione | `tests/test_storage.py::test_migration_creates_spec_tables` (versione 005 invariata) |
| Spec 11 non invasa | `tests/test_alerts_ac.py::test_no_restart_or_liveness_message` |

## Ordine di consegna

Codice-first: T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9, poi test T10, poi AC end-to-end T11,
poi documentazione T12 (dipendente da codice stabile), infine pubblicazione T13. Il documento
descrive il comportamento validato.

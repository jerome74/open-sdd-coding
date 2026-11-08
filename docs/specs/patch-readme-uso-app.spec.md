# Micro-Spec: README come guida operativa dell'app Telegram

> Patch scoped — non sostituisce una spec completa. Generata da `/micro-spec` il 2026-11-07.
> Per il Conductor: **Scope limitato** è l'inventario dei deliverable di questa voce.
> Nessun file fuori da quell'elenco può essere modificato.

## Comportamento attuale

`README.md` (199 righe, radice) descrive il framework SDD OpenCode/DeepSeek: pipeline a 5 comandi,
modelli, knowledge pipeline, checklist di verifica. L'app Python è citata solo di passaggio
(`src/agente/`, `tests/`, `requirements.txt`). Non esistono istruzioni su installazione,
configurazione, avvio, comandi Telegram né accesso al bot da un altro telefono.

## Comportamento atteso

`README.md` diventa la guida operativa dell'app Agente Personale Telegram, in italiano, dettagliata
ma semplice e tecnica:

- **Prerequisiti** — Termux/S24, Python 3, dipendenze (`requirements.txt`).
- **Configurazione** — `~/.config/agente/config.toml` (`admin_telegram_id`, `secrets_file`) e
  `secrets.env` nella stessa directory con permessi `600`; chiave API DeepSeek e token BotFather
  solo nei segreti, mai nel repo. I template restano `config/config.example.toml` e
  `config/secrets.example.env`.
- **Avvio** — manuale (`python -m agente`, entrypoint `src/agente/__main__.py`) e automatico tramite
  `scripts/boot/start-agent.sh` / `scripts/boot/90-agent.sh`, wake-lock e posizione dei log.
- **Uso da Telegram** — comandi e flussi principali: gestione compiti (`/tasks`, `/pause`, `/resume`,
  `/delete`, `/rename` + linguaggio naturale), esecuzione immediata (`/run`), chat (`/chat`,
  `/reset`), storico (`/history`), utenti (`/adduser`, `/removeuser`, `/users`, `/subscribe`,
  `/unsubscribe`), log (lettura e riassunto).
- **Accesso da un altro telefono** — stesso account Telegram dell'admin → stesso `telegram_id`,
  quindi stessi permessi; account diverso → deve essere autorizzato dall'admin (`/adduser`); nessun
  secondo bot o server da configurare.
- **Sicurezza** — token mai condiviso, segreti fuori dal repo, permessi `600` sui file sensibili.
- **Troubleshooting essenziale** — avvio fallito, config/segreti mancanti o con permessi errati,
  utente non autorizzato.

## Scope limitato

- `README.md` (radice) — riscrittura completa.

## Fuori scope

Qualsiasi file non elencato sopra, incluso il codice in `src/` e i documenti in `docs/`. Se la
correzione ne richiede uno, fermarsi e riportare — non allargare lo scope.

## Test di validazione

Controllo manuale: il README contiene le sezioni Setup, Configurazione, Avvio, Comandi, Accesso da
un altro telefono, Sicurezza; ogni comando citato esiste in `src/agente/command_router.py`;
`grep -R "sk-" README.md` → 0 occorrenze.

## Acceptance criteria

### AC-01

Dato il `README.md` riscritto, quando si leggono le sezioni Setup, Configurazione, Avvio, Comandi,
Accesso da un altro telefono e Sicurezza e si confrontano i comandi citati con
`src/agente/command_router.py`, allora ogni comando citato esiste nel router e
`grep -R "sk-" README.md` restituisce 0 occorrenze.

## Origine

Spec/voce correlata: nessuna (documentazione post-roadmap, roadmap 11/11 `- [x]`) · Input: richiesta
di modifica dell'operatore · Data: 2026-11-07

## Nota di implementazione (2026-11-07)

- `README.md` riscritto come guida operativa dell'app: Prerequisiti, Setup, Configurazione, Avvio,
  Comandi (uso da Telegram), Accesso da un altro telefono, Sicurezza, Troubleshooting essenziale.
- **Interpretazione di AC-01 (P-A-12 del piano):** «ogni comando citato esiste in
  `command_router.py`» vale per i comandi **Telegram slash**; i comandi shell (`pip`, `chmod`,
  `python3`, `termux-wake-lock`) e i percorsi (`/sdcard`, `/dev/null`) non sono verificati contro il
  router.
- **Verifica:** 16 comandi Telegram documentati (`HELP_TEXT` + `/help` + `/start`), ruoli coerenti
  con router/dispatcher/manager/query/chat; `grep -R "sk-" README.md` → 0; nessun comando `/log`;
  sezioni presenti; `README.md` tracciato e modificato.
- **Scope rispettato:** solo `README.md` come deliverable di prodotto; gli aggiornamenti di
  pubblicazione sono i metadata autorizzati (roadmap, questa nota, delivery history, piano).
- **Follow-up:** `scripts/boot/90-agent.sh` nel repo invoca `start-agent.sh` direttamente; il README
  istruisce la modifica del file copiato in `~/.termux/boot/` (invocazione con `bash`). Modifica
  degli script fuori scope, registrata in delivery history.

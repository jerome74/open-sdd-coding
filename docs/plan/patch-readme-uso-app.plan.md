# Piano — Micro-Spec `patch-readme-uso-app`

- **Voce roadmap:** `patch-readme-uso-app` (non spuntata, ultima)
- **Spec:** [patch-readme-uso-app.spec.md](../specs/patch-readme-uso-app.spec.md), nessuno stato dichiarato
- **Constitution:** [constitution.md](../specs/constitution.md), principi, Tech Stack, `## Roadmap`
- **Tipo di lavoro:** documentazione post-roadmap; nessun codice, nessuna migrazione
- **Data piano:** 2026-11-07
- **Stato piano:** approvato 2026-11-07; eseguito T1–T3 (delivery history: patch-readme-uso-app)

## Inventario deliverable

| # | Deliverable | Tipo | Destinazione |
|---|-------------|------|--------------|
| D-01 | Guida operativa dell'app Agente Personale Telegram: prerequisiti, setup Termux, configurazione e segreti, avvio manuale/automatico, comandi Telegram, accesso da un altro telefono, sicurezza, troubleshooting essenziale | documentazione | `README.md` (radice, riscrittura completa) |

**Unico file di prodotto:** `README.md`. Nessun file in `src/`, `docs/`, `config/` o `scripts/`
viene modificato come deliverable. Gli aggiornamenti di pubblicazione richiesti dal Conductor
(roadmap, nota di stato sulla patch spec, delivery history, piano) sono **metadata di processo** e sono
autorizzati dall'operatore con l'approvazione di questo piano (DEC-01): non allargano lo scope di
prodotto.

## Capability Bindings

Registry `docs/sdd/capability-registry.md`: **assente**. Phase 0 eseguita leggendo il solo
frontmatter di `.opencode/agents/*.md`, `.opencode/commands/*.md`, `.opencode/skills/*/SKILL.md` e
`opencode.json`.

| Deliverable | Bound asset | Kind | Why bound | Notes |
|---|---|---|---|---|
| D-01 (`README.md`) | *nessuno* | — | Fallback ladder passo 2: nessuna skill dichiara capacità di redazione di un README di repository (la skill `docs` copre documenti condivisi, non README di repo) | Etichettato *"no specialized capability discovered"*; si procede su spec + constitution + contenuto reale del repo |
| D-01 (struttura) | `.opencode/agents/sdd-governor.md` | agent (governance) | Dichiara di governare la fedeltà alla struttura dichiarata e di non generare contenuto | Solo validatore ai checkpoint Phase 2 e Phase 4 |
| D-01 (struttura) | `.opencode/skills/sdd-guardrail` | skill (vincolo) | La spec è una Micro-Spec: template e Append-Only sono della skill | Già caricata da `/micro-spec`; vincola la forma della patch spec, non il README |

**Registry assente:** `AGENTS.md` §0 lo cita come fonte, ma `docs/sdd/` non esiste. Fallback ladder
passo 1/2 applicato: si procede su spec + constitution, capacità ridotta dichiarata. Remediation
(creare `docs/sdd/capability-registry.md` o allineare `AGENTS.md` §0): **fuori scope**, gap
registrato.

**Scartati:** `skills/drawio` (nessun diagramma richiesto), `skills/document-to-markdown` (nessun
documento binario), `skills/okf-*`/`wiki-*` (nessun bundle), `skills/prompt-engineering` (nessun
template di prompt), `agents/planner`/`specification`/`prd` (producono piani/spec, non README),
`commands/*` (mai invocati).

## Checkpoint di struttura (D-01) — Phase 2

**Struttura applicabile:** sezioni dichiarate dal `## Comportamento atteso` e dal
`## Test di validazione` della patch spec, in italiano e nell'ordine:

1. Titolo e descrizione breve dell'app (elemento editoriale minimo, non una sezione richiesta dalla
   patch spec).
2. **Prerequisiti** — S24/Termux, **Termux:API** e pacchetto `termux-api` (batteria e rete),
   Termux:Boot, Python 3, dipendenze.
3. **Setup** — progetto in `~/agente-personale` (default di `APP_DIR`); se è altrove, modificare
   `APP_DIR=` nello `start-agent.sh` copiato, perché Termux:Boot non eredita l'ambiente della shell;
   `pip install --target .deps -r requirements.txt`; struttura minima; nessun venv (Tech Stack).
   `APP_DIR` è una variabile dei soli script di boot: `python -m agente` non la usa; un
   `start-agent.sh` lanciato a mano la accetta dall'ambiente.
4. **Configurazione** — `~/.config/agente/config.toml` e `secrets.env` con `chmod 600` **su
   entrambi**; `admin_telegram_id`, `secrets_file` (opzionale: senza, i segreti arrivano
   dall'ambiente), `[deepseek]` (`model` opzionale, default `deepseek-flash`; `api_base`,
   `max_context_tokens`), `[paths]` (`db`, `logs`), `[search].provider` opzionale (default
   `tavily`), token BotFather, chiave DeepSeek, chiave ricerca opzionale;
   rimando a `config/config.example.toml` e `config/secrets.example.env`.
5. **Avvio** — manuale dalla **radice del progetto**:
   `PYTHONPATH=src:.deps python3 -m agente --config ~/.config/agente/config.toml` (entrypoint
   `src/agente/__main__.py`); automatico:
   copiare **entrambi** `scripts/boot/start-agent.sh` e `scripts/boot/90-agent.sh` in
   `~/.termux/boot/` (stessa directory); `chmod 700 ~/.termux/boot/90-agent.sh` e
   `chmod 600 ~/.termux/boot/start-agent.sh` (Termux:Boot esegue ogni file eseguibile: due script
   eseguibili avvierebbero due supervisori); **modificare nel `90-agent.sh` copiato** la riga di
   invocazione in `bash "$SCRIPT_DIR/start-agent.sh"` mantenendo `>/dev/null 2>&1 &` e `disown`
   (il file nel repo usa l'invocazione diretta: gap noto, fuori scope, follow-up registrato). Termux:Boot installato, `APP_DIR` default `$HOME/agente-personale` (la
   catena non esporta variabili di override: in Termux:Boot si modifica `APP_DIR=` nello script
   copiato o si esporta in `90-agent.sh`; lanciando `start-agent.sh` da una shell, l'ambiente
   esportato viene ereditato),
   `termux-wake-lock`; `supervisor.log` in `$LOG_DIR` (`start-agent.sh`, default
   `~/.local/share/agente/logs`, in append senza rotazione), distinto da `agente.jsonl` in
   `[paths].logs` (2 000 000 byte per file + 5 backup, ≈ 12 MB).
   I default coincidono; se si cambia `[paths].logs`, impostare `LOG_DIR` nello stesso modo
   (`start-agent.sh` o `export` in `90-agent.sh`).
6. **Comandi (uso da Telegram)** — tabella di **tutti** i comandi di `HELP_TEXT` più `/help` e
   `/start`, con ruolo e descrizione; i ruoli si derivano da `command_router.py`,
   `run_dispatcher.py`, `task_manager.py`, `history_query.py`, `chat.py` e `role_guard.py`, non dalle
   annotazioni parziali di `HELP_TEXT`: `/pause`, `/resume`, `/delete`, `/rename` e la creazione di
   compiti sono solo admin; `/chat`, `/adduser`, `/removeuser`, `/users`, `/subscribe`,
   `/unsubscribe` sono solo admin; `/help` e `/start` sono per ogni ruolo riconosciuto (gli sconosciuti
   sono rifiutati prima del dispatch); `/tasks` e `/history` sono per admin e autorizzati ma mostrano
   solo i compiti/lo storico visibili al ruolo; `/run` è admin su qualsiasi compito, autorizzato
   solo se iscritto e attivo; `/reset` azzera la propria conversazione (admin e autorizzati); creazione in linguaggio
   naturale; **lettura e riassunto log**
   come capacità di un compito con percorso in allowlist (`read_logs`), non come comando slash.
   «Comandi» è l'alias della sezione «Uso da Telegram» del Comportamento atteso.
7. **Accesso da un altro telefono** — stesso account Telegram → stesso `telegram_id`; account
   diverso → `/adduser` + consenso privacy; nessun secondo bot/server.
8. **Sicurezza** — token mai condiviso, segreti fuori dal repo, permessi `600`, admin solo da config.
9. **Troubleshooting essenziale** — config/segreti mancanti o con permessi errati (`600` su
   entrambi), avvio fallito, `PYTHONPATH`/`.deps` errati o cwd non radice, utente non autorizzato,
   bot che non risponde, Termux:Boot non installato, `APP_DIR` errato. Boot: `90-agent.sh` non
   eseguibile; `90-agent.sh` **e** `start-agent.sh` entrambi eseguibili → doppio supervisore;
   `90-agent.sh` copiato non modificato → invocazione diretta di un file `600`, avvio muto con
   output in `/dev/null`; avvio manuale della copia con `bash start-agent.sh`.

**Idoneità:** la struttura copre tutti i punti richiesti dalla patch spec; il README attuale viene
sostituito, quindi non c'è una struttura preesistente da preservare.

**Deliverable richiesti:** un solo `README.md` con il titolo editoriale e le 8 sezioni
Prerequisiti, Setup, Configurazione, Avvio, Comandi, Accesso da un altro telefono, Sicurezza,
Troubleshooting essenziale.

**Dipendenze:** nessuna; il contenuto deriva da `src/agente/command_router.py`, `src/agente/app.py`,
`src/agente/config.py`, `src/agente/__main__.py`, `src/agente/logging_setup.py`,
`src/agente/tools.py`, `src/agente/chat.py`, `src/agente/run_dispatcher.py`,
`src/agente/task_manager.py`, `src/agente/history_query.py`, `src/agente/role_guard.py`,
`src/agente/user_manager.py`, `src/agente/consent.py`, `src/agente/user_state.py`,
`config/config.example.toml`, `config/secrets.example.env`, `scripts/boot/*`, `requirements.txt`.

**Esito checkpoint:** Phase 2 **NOT APPROVED** alla prima passata (setup non eseguibile senza
`.deps`/`PYTHONPATH`; `chmod 600` solo sui segreti; avvio automatico senza `~/.termux/boot/`;
lettura log non mappata; `/help`/`/start` esclusi; scope vs metadata di pubblicazione non
riconciliato). **NOT APPROVED** alla seconda (boot con un solo script; campi config obbligatori
assenti; `APP_DIR`/cwd non dichiarati; `D-01` duplicato; T2 incompleto; P-A-06/P-A-11 duplicati).
Terza passata **NOT APPROVED** (cwd/`APP_DIR` confusi, destinazione setup assente, T2 ambiguo su
`/log` e incompleto sui campi, P-A fuori ordine, `agente.jsonl` vs `supervisor.log`, git non
verificato). Quarta passata **NOT APPROVED** (`APP_DIR` attribuito anche all'avvio manuale;
conteggio sezioni; path `supervisor.log`; T2 senza `admin_telegram_id`/`[deepseek]`/copertura
comandi; regex `/log` ancorata; Termux:API assente; alias «Comandi»/«Uso da Telegram»). Quinta passata **NOT APPROVED** (`APP_DIR` ancora «override via ambiente»; `LOG_DIR` vs
`[paths].logs`; T2 senza Termux:API/`termux-api`/`read_logs`/alias/entrypoint; criterio git
transitorio; `model`/`provider` opzionali assenti). Sesta passata **NOT APPROVED** (minor:
`termux-api` fuori da §2; P-A-11 ambiguo su export nel boot; nome «Troubleshooting»;
`[paths].db`/`logs` non asseriti; comando git impreciso; `LOG_DIR` senza punto di modifica;
`model` non marcato opzionale). Settima passata **NOT APPROVED** (contraddizione residua su override ambiente; nome
«Troubleshooting» non uniforme; `secrets_file` senza fallback ambiente; default `[search].provider`
non citato). Ottava passata **NOT APPROVED** (avvio automatico con entrambi gli script eseguibili → doppio
supervisore; «non esporta variabili» troppo assoluto; T2 confonde comandi Telegram e shell; check
git transitorio). Nona passata **NOT APPROVED** (`90-agent.sh` nel repo invoca `start-agent.sh` direttamente: serve
la modifica esplicita del file copiato + `chmod`; P-A-02 e criterio 2 non qualificati; AC-01 non
referenziato; MB decimale). Decima passata **NOT APPROVED** (T2 senza check dei permessi/invocazione boot; §9 contraddittorio
sugli script eseguibili; ruoli comandi non derivati dal router; rotazione log ambigua; perdita di
redirezione/`disown`; scope git non verificato; AC-01 etichettato ma più ampio). Undicesima passata **NOT APPROVED** (ruoli anche fuori dal router: `/run`, `/tasks`, `/history`,
`/chat`; §9 «start-agent.sh eseguibile» senza la congiunzione; set git non enumerato e piano fuori
da DEC-01; interpretazione AC-01 senza ID). Dodicesima passata **NOT APPROVED** (ruoli di `/tasks`, `/run`, `/reset`, `/history` non dichiarati
e fonte §6 limitata al router; piano fuori da DEC-01; fonti utenti/consenso assenti; destinazione
follow-up e `PYTHON_BIN`; P-A-02/P-A-12 ridondanti). Tredicesima passata **APPROVED** con note editoriali recepite: refuso «lo storico», ruoli di
`/help`/`/start`/`/reset`, follow-up «da registrare in T3», piano nei metadata, T2 qualificato,
P-A-12 citato in T3.

**Phase 4 (2026-11-07):** **APPROVED** alla quarta passata. Prima: `LOG_DIR`/`[paths].logs`,
troubleshooting boot, `read_logs`, prerequisiti, `SEARCH_API_KEY`; seconda: creazione solo admin,
ricerca web senza conferma, path `cp`, avviso 24 h, wake-lock, URL repo; terza: `termux-tools`,
finestra anti-spam per processo, avvio preventivo del bot. Quarta: solo note opzionali
(percorso assoluto, transito DeepSeek/Telegram, tabella `/adduser`/`/subscribe`), recepite.

## Assunzioni del piano

> **P-A-01** Il README è in italiano, come il resto della documentazione di progetto.

> **P-A-02** I comandi **Telegram slash** citati sono quelli di `HELP_TEXT` in
> `src/agente/command_router.py` più `/help` e `/start`, gestiti dal router ma assenti da
> `HELP_TEXT`; nessun comando Telegram inventato. Per l'esenzione dei comandi shell vale P-A-12.

> **P-A-03** I percorsi citati sono quelli reali del repo: `~/.config/agente/config.toml`,
> `secrets.env` accanto al config, DB e log da `config/config.example.toml`.

> **P-A-04** Nessun segreto o token reale compare nel README; solo nomi di variabili e istruzioni.

> **P-A-05** «Accesso da un altro telefono» è spiegato come accesso allo **stesso bot** con lo
> stesso account Telegram (stesso `telegram_id`) oppure con un account autorizzato dall'admin; il
> bot non viene reinstallato e non serve un secondo server.

> **P-A-06** La lettura dei log è descritta come capacità dell'agente (compito con percorso in
> allowlist), non come comando slash: `/log` non esiste.

> **P-A-07** La sostituzione del README del framework SDD è voluta dall'operatore (gate `/micro-spec`
> del 2026-11-07): il vecchio contenuto non viene preservato.

> **P-A-08** Nessun diagramma: la patch spec non lo richiede e il README resta una guida lineare.

> **P-A-09** Il setup usa `.deps` e `PYTHONPATH=src:.deps`, come `scripts/boot/start-agent.sh` e la
> constitution; nessun venv.

> **P-A-10** Sia `config.toml` sia `secrets.env` richiedono permessi `600`; il README lo dice in
> Configurazione e in Troubleshooting essenziale.

> **P-A-11** L'avvio **manuale** (`python -m agente`) richiede cwd = radice del progetto e
> `PYTHONPATH=src:.deps`. L'avvio **automatico** non dipende dal cwd: `start-agent.sh` usa percorsi
> assoluti `$APP_DIR/src:$APP_DIR/.deps` e `APP_DIR` (default `$HOME/agente-personale`). La catena
> non esporta variabili di override (`APP_DIR`/`CONFIG`/`LOG_DIR`/`PYTHON_BIN`): in Termux:Boot si modificano
> nello script copiato o si esportano in `90-agent.sh`; un `start-agent.sh` lanciato da shell eredita
> l'ambiente esportato. In `~/.termux/boot/` solo `90-agent.sh` è eseguibile (`chmod 700`),
> `start-agent.sh` è `chmod 600` e il `90-agent.sh` copiato lo invoca con `bash` (modifica
> esplicita; il repo usa l'invocazione diretta — gap noto, fuori scope, follow-up da registrare in
> T3).

> **P-A-12** L'AC-01 della patch spec («ogni comando citato esiste in `command_router.py`») è
> interpretata come riferita ai soli comandi **Telegram slash**; i comandi shell (`pip`, `chmod`,
> `python3`, `termux-wake-lock`) non sono verificati contro il router.

## Task

| # | Task | Deliverable | Criterio di done |
|---|------|-------------|------------------|
| T1 | Riscrittura del README | D-01 | titolo + 8 sezioni presenti; contenuto coerente con codice e config reali; nessun comando o path inventato; italiano semplice e tecnico |
| T2 | Validazione documentale (AC-01 + controlli README, P-A-12) | D-01 | la colonna ruolo della tabella è coerente con `command_router.py`, `run_dispatcher.py`, `task_manager.py`, `history_query.py`, `chat.py`, `role_guard.py`; tutti i comandi di `HELP_TEXT` più `/help` e `/start` sono documentati e nessun comando **Telegram slash** citato è inventato (i comandi shell come `pip`, `chmod`, `git` sono fuori da questo controllo); nessun comando `/log` (check `(^|[^[:alnum:]_])/log([^[:alnum:]_]|$)`, non il path `logs`); `grep -R "sk-" README.md` → 0; nessun token o segreto; `chmod 600` citato per entrambi i file; campi config `admin_telegram_id`, `secrets_file` (opzionale, fallback ambiente), `[deepseek]` (`model` con default, `api_base`, `max_context_tokens`), `[paths].db` e `[paths].logs`, `[search].provider` (default `tavily`) presenti; `APP_DIR` default, copia di **entrambi** gli script di boot, `chmod 700` su `90-agent.sh`, `chmod 600` su `start-agent.sh`, riga `bash "$SCRIPT_DIR/start-agent.sh"` e nota del gap repo; `PYTHONPATH`/cwd per l'avvio manuale e entrypoint `src/agente/__main__.py`; `$LOG_DIR/supervisor.log` e `agente.jsonl` distinti con nota di allineamento; prerequisiti Termux:API + pacchetto `termux-api` + Termux:Boot; lettura log come `read_logs` con allowlist; alias «Comandi (uso da Telegram)»; `git ls-files --error-unmatch README.md` e `git diff --stat HEAD -- README.md` non vuoto (check eseguito in T2, prima di T3); `git status --porcelain` limitato ai path ammessi (`README.md`, `docs/specs/constitution.md`, `docs/specs/patch-readme-uso-app.spec.md`, `docs/delivery-history.md`, `docs/plan/patch-readme-uso-app.plan.md`); nessun commit tra T1 e T2; sezioni richieste presenti; **Troubleshooting essenziale** copre i casi dichiarati; link interni validi |
| T3 | Pubblicazione | D-01 + metadata | roadmap `[x]`; nota append-only nella patch spec con l'interpretazione di AC-01 (P-A-12: solo comandi Telegram slash verificati contro il router; shell fuori); voce in `docs/delivery-history.md`; piano allineato; checkpoint Phase 4 registrato; DEC-01 richiamata; follow-up sul gap `90-agent.sh` registrato in `docs/delivery-history.md` |

## Rischi e mitigazione

| Rischio | Mitigazione |
|---|---|
| Comandi o path inesistenti | verifica contro `HELP_TEXT`, `config.example.toml`, `scripts/boot/*` |
| Istruzioni Android/Termux non valide | si citano solo gli script e i percorsi già presenti nel repo; il resto resta generico |
| Confusione «altro telefono» = nuovo bot | sezione dedicata: stesso bot, stesso account o account autorizzato |
| Segreto reale nel README | solo nomi di variabili; grep di controllo |
| `90-agent.sh` nel repo invoca `start-agent.sh` direttamente | il README istruisce la modifica del file copiato; gap del repo da registrare come follow-up in delivery history (T3), fuori scope |
| Perdita del README del framework | scelta esplicita dell'operatore (P-A-07). `AGENTS.md` documenta processo e pipeline, non la matrice modelli/checklist: la perdita è accettata e dichiarata. Il contenuto precedente è recuperabile da git (`git show HEAD:README.md`) |

## Criteri di validazione (done della voce)

1. `README.md` contiene Prerequisiti, Setup, Configurazione, Avvio, Comandi, Accesso da un altro
   telefono, Sicurezza, Troubleshooting essenziale.
2. Ogni comando **Telegram slash** citato esiste in `src/agente/command_router.py`; i comandi
   shell sono fuori da questo controllo (come in T2).
3. `grep -R "sk-" README.md` → 0 occorrenze; nessun token o chiave.
4. I percorsi di config, segreti, DB e log corrispondono a `config/config.example.toml` e
   `scripts/boot/start-agent.sh`.
5. Nessun file fuori da `README.md` modificato come deliverable di prodotto; `git status
   --porcelain` mostra solo `README.md` più i path ammessi da DEC-01 (`constitution.md`, patch spec,
   delivery history, piano).
6. Documento conforme alla struttura dichiarata e approvato al checkpoint Phase 4.
7. Catena di tracciabilità: roadmap → patch spec → binding → task → README → validazione →
   pubblicazione.

## Ordine di consegna

Docs-first: T1 → T2 → checkpoint Phase 4 → T3.

## Decisioni che sbloccano il piano

| # | Domanda / conflitto | Decisione | Impatto |
|---|---|---|---|
| DEC-01 | Lo Scope limitato della patch spec dice «nessun file fuori da README.md», ma la Phase 5 del Conductor richiede roadmap, nota sulla spec, delivery history e piano | **Metadata di processo autorizzati dall'operatore con l'approvazione del piano**: `constitution.md` (roadmap), `patch-readme-uso-app.spec.md` (nota append-only), `delivery-history.md`, `patch-readme-uso-app.plan.md`; nessun altro file di prodotto | T3; nessun allargamento del deliverable |

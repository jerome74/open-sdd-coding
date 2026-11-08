# Agente Personale Telegram

Agente personale che gira su un telefono Android (S24) sotto Termux e si comanda da Telegram:
crea ed esegue compiti ricorrenti, risponde a domande libere, cerca sul web, legge e riassume log,
gestisce utenti e storico. La conferma dell'amministratore serve per le azioni che modificano il
telefono, non per la ricerca web. È un processo Python unico con database SQLite locale; non
serve un server esterno.

Questa guida spiega installazione, configurazione, avvio e uso quotidiano, incluso l'accesso al bot
da un altro telefono.

## 1. Prerequisiti

- **Telefono S24** acceso e connesso a Internet (Wi-Fi o dati). Se il telefono è spento o offline,
  l'agente non risponde.
- **Termux** installato da F-Droid.
- **Termux:API** (app) e il pacchetto CLI `termux-api`: servono per batteria e rete.
- Il comando **`termux-wake-lock`** (fornito da Termux, pacchetto `termux-tools`): mantiene attivo
  il processo.
- **Termux:Boot** (app): serve per l'avvio automatico dopo un riavvio del telefono.
- **Python 3** in Termux (`pkg install python`).
- Le **dipendenze Python** elencate in `requirements.txt` (installate nel Setup).
- Un **bot Telegram** e il suo token (creato con **@BotFather**).
- Una **chiave API DeepSeek**.
- Facoltativo: una chiave **Tavily** per la ricerca web.

## 2. Setup

Mettere il progetto in `~/agente-personale` (è il percorso predefinito di `APP_DIR`):

```bash
cd ~
git clone https://github.com/jerome74/open-sdd-coding.git agente-personale
cd agente-personale
```

Installare le dipendenze dentro `.deps`, senza venv (vincolo del progetto):

```bash
pip install --target .deps -r requirements.txt
```

Se `pip` non è disponibile: `pkg install python` e riprovare.

Struttura minima:

```text
agente-personale/
  src/agente/          codice dell'agente
  config/              template di configurazione e segreti
  scripts/boot/        avvio automatico e wake-lock
  requirements.txt
  .deps/               dipendenze installate (creata dal comando sopra)
```

## 3. Configurazione

Creare la directory di configurazione e copiare i template:

```bash
mkdir -p ~/.config/agente
cp config/config.example.toml ~/.config/agente/config.toml
cp config/secrets.example.env ~/.config/agente/secrets.env
chmod 600 ~/.config/agente/config.toml ~/.config/agente/secrets.env
```

I permessi `600` sono obbligatori: l'agente rifiuta file leggibili da altri.

### 3.1 `config.toml`

Campi principali:

```toml
admin_telegram_id = 123456789   # ID Telegram numerico dell'amministratore
secrets_file = "secrets.env"    # relativo alla directory del config

[deepseek]
model = "deepseek-flash"        # opzionale, default deepseek-flash
api_base = "https://api.deepseek.com/v1"
max_context_tokens = 8000

[search]
provider = "tavily"             # opzionale, default tavily; vuoto = ricerca non configurata

[paths]
db = "~/.local/share/agente/agente.db"
logs = "~/.local/share/agente/logs"
```

`admin_telegram_id` è l'unico amministratore: non si cambia da chat, solo modificando questo file e
riavviando l'agente. Per conoscere il proprio ID numerico si può usare un bot Telegram che lo mostra
(ad esempio `@userinfobot`).

`secrets_file` è opzionale: se lo si omette, i segreti vengono letti dalle variabili d'ambiente
`TELEGRAM_TOKEN`, `DEEPSEEK_API_KEY`, `SEARCH_API_KEY`.

### 3.2 `secrets.env`

```dotenv
TELEGRAM_TOKEN=123456:token-del-bot
DEEPSEEK_API_KEY=chiave-deepseek
SEARCH_API_KEY=chiave-tavily
```

- `TELEGRAM_TOKEN`: token rilasciato da **@BotFather** creando un nuovo bot.
- `DEEPSEEK_API_KEY`: chiave dell'account DeepSeek.
- `SEARCH_API_KEY`: facoltativa; serve alla ricerca web. Se manca, la ricerca risponde con un
  errore esplicito. `search.provider` è `tavily` per default.

Il token del bot è una password: non va condiviso, non va messo nel repository e non va inviato in
chat. Se viene esposto, revocarlo da BotFather e generarne uno nuovo.

## 4. Avvio

### 4.1 Avvio manuale

Dalla **radice del progetto** (la directory che contiene `src/` e `.deps/`):

```bash
cd ~/agente-personale
PYTHONPATH=src:.deps python3 -m agente --config ~/.config/agente/config.toml
```

L'entrypoint è `src/agente/__main__.py`. Il processo resta in primo piano; `Ctrl+C` lo ferma.
All'avvio l'agente migra il database, carica i job e recupera i compiti saltati; se esiste un avvio
precedente, invia all'amministratore il messaggio di ripartenza con il periodo di assenza. Ogni
giorno all'orario `liveness_at` (default `08:00`) invia un segnale di vita; se il telefono era
offline, il segnale mancato è riportato alla ripartenza successiva.

### 4.2 Avvio automatico (Termux:Boot)

1. Installare **Termux:Boot** e aprirlo una volta.
2. Copiare **entrambi** gli script nella directory di boot:

```bash
mkdir -p ~/.termux/boot
cp ~/agente-personale/scripts/boot/90-agent.sh ~/.termux/boot/
cp ~/agente-personale/scripts/boot/start-agent.sh ~/.termux/boot/
chmod 700 ~/.termux/boot/90-agent.sh
chmod 600 ~/.termux/boot/start-agent.sh
```

Se il progetto non è in `~/agente-personale`, sostituire il percorso nei due `cp` con quello reale
e impostare `APP_DIR` come allo step 4.

Termux:Boot esegue **ogni** file eseguibile della directory: solo `90-agent.sh` deve avere il bit
eseguibile, altrimenti partirebbero due supervisori e due processi in polling sullo stesso bot.

3. Modificare il `90-agent.sh` **copiato** in `~/.termux/boot/`: la riga di invocazione deve usare
   `bash`, perché `start-agent.sh` non è eseguibile:

```bash
# dentro ~/.termux/boot/90-agent.sh
bash "$SCRIPT_DIR/start-agent.sh" >/dev/null 2>&1 &
disown
```

4. Se il progetto non è in `~/agente-personale`, impostare `APP_DIR` nel `start-agent.sh` copiato:

```bash
APP_DIR="$HOME/percorso/reale"
```

In Termux:Boot non arriva l'ambiente della shell: la modifica va fatta nello script copiato (o con
un `export` dentro `90-agent.sh`). `start-agent.sh` acquisisce il wake-lock e rilancia l'agente se
termina.

### 4.3 Log

- **Applicativo:** `agente.jsonl` nella directory `[paths].logs` (default
  `~/.local/share/agente/logs`). Una riga JSON per evento, rotazione a 2 000 000 byte per file con 5
  backup (circa 12 MB).
- **Supervisore:** `$LOG_DIR/supervisor.log` (default `~/.local/share/agente/logs`), in append senza
  rotazione: contiene i riavvii e il codice di uscita del processo.

`LOG_DIR` e `[paths].logs` sono indipendenti: se si cambia `[paths].logs`, impostare `LOG_DIR` nello
stesso modo (`APP_DIR`/`LOG_DIR` nello `start-agent.sh` copiato o `export` in `90-agent.sh`),
altrimenti i due log finiscono in directory diverse.

```bash
tail -f ~/.local/share/agente/logs/agente.jsonl
tail -f ~/.local/share/agente/logs/supervisor.log
```

## 5. Comandi (uso da Telegram)

I comandi si inviano al bot come normali messaggi. `@NomeBot` dopo il comando è accettato.

| Comando | Ruolo | Cosa fa |
|---|---|---|
| `/help`, `/start` | ogni ruolo riconosciuto | mostra l'elenco dei comandi |
| `/tasks` | admin e autorizzati | elenca i compiti visibili al ruolo |
| `/run <nome>` | admin su qualsiasi compito; autorizzato solo se iscritto e attivo | esegue subito un compito |
| `/reset` | admin e autorizzati | azzera la propria conversazione |
| `/pause <nome>` | solo admin | sospende un compito |
| `/resume <nome>` | solo admin | riattiva un compito |
| `/delete <nome>` | solo admin | elimina un compito |
| `/rename <nome> <nuovo nome>` | solo admin | rinomina un compito |
| `/history [periodo] [compito]` | admin e autorizzati | storico delle esecuzioni visibili al ruolo |
| `/chat <telegram_id>` | solo admin | rilegge la chat di un utente |
| `/adduser <telegram_id> [username]` | solo admin | avvia l'autorizzazione e invia l'informativa privacy |
| `/removeuser <telegram_id>` | solo admin | revoca un utente |
| `/users` | solo admin | elenca utenti e compiti |
| `/subscribe <compito> <telegram_id>` | solo admin | iscrive un utente che ha accettato l'informativa |
| `/unsubscribe <compito> <telegram_id>` | solo admin | disiscrive un utente |

### 5.1 Creare un compito in linguaggio naturale

Non serve un comando: si scrive cosa deve fare e quando. Esempi:

- «Ogni giorno alle 8 riassumi le notizie sull'IA e mandamele.»
- «Ogni lunedì alle 9 leggimi `/sdcard/logs/app.log` e segnalami gli errori.»
- «Ogni 30 minuti controlla il sito e avvisami se cambia.»

Solo l'amministratore può creare compiti: un utente autorizzato che ci prova riceve un rifiuto.
L'agente mostra un riepilogo e chiede conferma; il compito viene salvato solo dopo la conferma.
Per eseguirlo subito: «lancia <nome>» oppure `/run <nome>`.

### 5.2 Leggere e riassumere i log

La lettura dei log non è un comando dedicato: è una capacità di un **compito**. Nel testo si
indica il percorso **assoluto** del file (o della cartella) e l'agente lo usa come allowlist di
lettura; i percorsi relativi vengono scartati. Esempio:

> «Ogni giorno alle 7 leggi `/sdcard/logs/app.log` e riassumi gli errori delle ultime 24 ore.»

La lettura è limitata ai percorsi indicati nel compito: lo strumento `read_logs` applica
l'allowlist del compito. Le azioni modificanti sul telefono passano invece dal gate di conferma
dell'amministratore.

## 6. Accesso da un altro telefono

Il bot non è un'app da installare: è un **bot Telegram**. Si usa da qualsiasi telefono o computer su
cui sia installato Telegram.

### Stesso account (stessi permessi)

Se sul secondo telefono si accede a Telegram con lo **stesso account** dell'amministratore, il
`telegram_id` è lo stesso: il bot riconosce l'amministratore e tutti i comandi funzionano come sul
telefono principale. Non serve configurare nulla, non serve un secondo bot e non serve un secondo
server. Le chat sono sincronizzate da Telegram.

### Account diverso (utente autorizzato)

Un'altra persona, con un altro account, deve essere autorizzata dall'amministratore:

1. L'utente deve aver **avviato il bot almeno una volta**: Telegram non permette al bot di
   scrivere per primo.
2. L'amministratore invia `/adduser <telegram_id> [username]`.
3. L'utente riceve l'informativa privacy con i pulsanti **Accetto** / **Rifiuto**.
4. Dopo **Accetto** può usare il bot: chat, `/tasks`, `/history`, `/run` sui compiti a cui è
   iscritto e i risultati dei compiti sottoscritti.
5. `/removeuser <telegram_id>` revoca l'accesso.

Un utente non autorizzato riceve il rifiuto «Non sei autorizzato a usare questo agente» e nessun
comando viene eseguito; l'amministratore riceve un avviso, al massimo uno ogni 24 ore per lo stesso
utente all'interno dello stesso processo (un riavvio può produrne uno in più). L'autorizzazione e la
revoca sono riservate all'amministratore.

### Cosa ricordare

- L'agente gira **solo sull'S24**: l'altro telefono è un client. Se l'S24 è spento o offline, il bot
  non risponde.
- Non serve esporre porte, installare un server o creare un secondo bot.
- Non condividere il token: chi lo possiede può controllare il bot.
- L'amministratore è solo quello indicato in `admin_telegram_id`; per cambiarlo si modifica il file
  di configurazione e si riavvia l'agente.

## 7. Sicurezza

- Token del bot e chiavi API vivono solo in `secrets.env` (permessi `600`) o nell'ambiente. Mai nel
  repository, mai in chat.
- Anche `config.toml` deve avere permessi `600`.
- L'amministratore è definito solo dalla configurazione, non da un comando Telegram.
- I log applicativi non contengono segreti: i campi sensibili sono oscurati.
- Database e log restano sul telefono. I messaggi transitano dai server di DeepSeek (per generare
  le risposte) e di Telegram (per il trasporto), come indicato nell'informativa privacy.
- Il bot legge solo i percorsi indicati nei compiti (allowlist); non esegue azioni modificanti senza
  la conferma dell'amministratore.

## 8. Troubleshooting essenziale

| Sintomo | Causa probabile | Rimedio |
|---|---|---|
| `ConfigError: limite non valido` o file mancante | `config.toml` assente o incompleto | copiare il template e compilare i campi obbligatori |
| `ConfigError` sui permessi | `config.toml` o `secrets.env` leggibili da altri | `chmod 600` su entrambi |
| `ConfigError` sui segreti | token o chiave assenti | compilare `secrets.env` o esportare le variabili |
| `ModuleNotFoundError` | dipendenze non installate o `PYTHONPATH` errato | `pip install --target .deps -r requirements.txt`, avviare dalla radice con `PYTHONPATH=src:.deps` |
| Il bot non risponde | processo fermo, token errato o telefono offline | controllare `agente.jsonl` e `supervisor.log`, verificare rete e token |
| `Non sei autorizzato a usare questo agente` | utente non autorizzato o revocato | `/adduser` dall'amministratore e consenso privacy |
| Avvio automatico muto | `90-agent.sh` copiato non modificato: invoca direttamente un file `600` e l'output va in `/dev/null` | applicare la modifica con `bash "$SCRIPT_DIR/start-agent.sh"` |
| Due processi / conflitto polling | `start-agent.sh` eseguibile in `~/.termux/boot/` | `chmod 600 ~/.termux/boot/start-agent.sh`, lasciare eseguibile solo `90-agent.sh` |
| Boot non trova il progetto | `APP_DIR` errato | correggere `APP_DIR=` nello `start-agent.sh` copiato |
| Avvio manuale fallito | non si è nella radice del progetto | `cd ~/agente-personale` e riprovare |
| Ricerca web non disponibile | `search.provider` vuoto o chiave assente | impostare `provider` e `SEARCH_API_KEY` |
| L'avvio automatico non parte | Termux:Boot non installato o non aperto | installare Termux:Boot e aprirlo una volta |
| Il boot non esegue lo script | `90-agent.sh` senza bit eseguibile | `chmod 700 ~/.termux/boot/90-agent.sh` |
| Serve vedere l'errore del boot | l'output è rediretto in `/dev/null` | provare a mano `bash ~/.termux/boot/start-agent.sh` |

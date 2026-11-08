# Functional Requirements Document — Agente Personale Telegram

## 1. Document Control

| Field | Value |
|-------|-------|
| Version | 0.2 (draft) |
| Date | 2026-09-24 |
| Author | TBD |
| Status | Draft — pending review |
| Source | Interview via /gather-requirements (0.2: chiusura domande aperte Q1–Q4) |

## 2. Executive Summary

L'Agente Personale Telegram è un assistente sempre attivo che vive sullo smartphone Samsung S24 del proprietario e svolge in autonomia compiti ricorrenti definiti dall'utente, come una rassegna quotidiana di notizie o il riassunto dei log. Si comanda interamente via Telegram, anche da un altro dispositivo (es. un Samsung S5 Ultra), in linguaggio naturale o con comandi rapidi. Ragiona tramite il modello linguistico DeepSeek e sceglie da solo gli strumenti da usare, come la ricerca web. Non esegue mai azioni che modificano il telefono senza l'approvazione esplicita dell'amministratore. Il valore è eliminare il lavoro manuale quotidiano e ricevere i risultati puntualmente, ovunque ci si trovi.

## 3. Business Context & Problem Statement

- **Problem today:** tutte le attività ricorrenti (consultare le notizie, controllare i log dei programmi in Termux, ecc.) vengono svolte a mano.
- **Current workaround / cost of inaction:** occorre ricordarsi di farle e avere in mano lo smartphone S24; senza un agente il lavoro resta manuale e dipende dalla memoria e dalla disponibilità del proprietario.
- **Desired outcome:** definire i compiti direttamente da Telegram e lasciarli eseguire all'agente in modo continuativo e automatico, ricevendo i risultati senza toccare l'S24.

## 4. Goals & Success Metrics

| # | Goal | How success is measured |
|---|------|-------------------------|
| G1 | Risultati puntuali senza intervento | I risultati dei compiti programmati arrivano su Telegram all'orario previsto senza toccare l'S24. |
| G2 | Gestione completa da Telegram | Creare, modificare, sospendere ed eliminare un compito è possibile solo scrivendo su Telegram, senza aprire Termux. |
| G3 | Funzionamento continuativo | L'agente resta attivo per giorni o settimane senza riavvii manuali. |
| G4 | Domande al volo | È possibile fare domande libere all'agente, non solo gestire compiti programmati. |

## 5. Stakeholders & Personas

| Actor | Type (user / stakeholder / external system) | Goal / role |
|-------|----------------------------------------------|-------------|
| Amministratore (proprietario dell'S24) | User | Crea, modifica, sospende ed elimina i compiti; autorizza, revoca e iscrive gli utenti; approva le azioni che modificano il telefono; può rileggere le chat degli utenti autorizzati. |
| Utente autorizzato | User | Riceve i risultati dei compiti a cui è iscritto, fa domande libere, lancia manualmente i compiti a cui è iscritto e ne consulta lo storico. Non può creare né modificare compiti. |
| Utente non autorizzato (sconosciuto) | User (esterno) | Viene ignorato; il suo primo contatto genera un avviso all'amministratore. |
| Telegram | External system | Canale di comunicazione tra utenti e agente. |
| DeepSeek | External system | Modello linguistico che fa ragionare l'agente, usato tramite la chiave API del proprietario. |
| Web / strumenti dell'agente | External system | Fonti e azioni usate dall'agente (es. ricerca web); le fonti non sono fisse, le sceglie l'agente. |

## 6. Scope

- **In scope (this version):** tutte le capacità FR-001 … FR-010: gestione dei compiti via Telegram, esecuzione programmata e manuale, domande libere, ricerca web e strumenti con conferma, lettura e riassunto dei log, gestione utenti, storico esecuzioni, avvisi all'amministratore, riavvio automatico con segnale di vita.
- **Out of scope (deferred):** esecuzione di qualsiasi comando o azione che modifica il telefono senza conferma dell'amministratore (escluso in modo permanente, non solo rinviato).
- **Assumptions:**
  - A1 — L'S24 resta sempre acceso e connesso a internet (Wi-Fi o dati); se è spento o offline l'agente non lavora.
  - A2 — Il costo delle chiamate a DeepSeek è a carico del proprietario; non è previsto alcun limite di spesa.
  - A3 — L'agente risponde in italiano, salvo che l'utente scriva in un'altra lingua.
  - A4 — "Azione che richiede conferma" = qualsiasi azione che modifica qualcosa sul telefono (eseguire comandi, scrivere o cancellare file, installare). Leggere e cercare sul web non richiede conferma.
  - A5 — La conferma può darla solo l'amministratore, anche quando la richiesta nasce dall'interazione con un utente autorizzato.

## 7. Functional Requirements

### FR-001 — Gestione dei compiti via Telegram

- **Priority:** Must
- **Goal:** permettere all'amministratore di creare e gestire i compiti ricorrenti solo scrivendo su Telegram.
- **Main flow:**
  1. L'amministratore descrive un compito in linguaggio naturale (es. *"Ogni giorno alle 8 mandami le 5 notizie più importanti sull'IA, anche a Marco"*) oppure usa un comando rapido.
  2. L'agente ricava dal messaggio: nome, istruzioni, quando eseguirlo (orario o intervallo), destinatari.
  3. L'agente mostra un riepilogo e chiede conferma.
  4. Solo dopo la conferma il compito viene salvato come attivo.
  5. Con messaggi in linguaggio naturale o comandi rapidi (es. `/tasks`, `/pause news`) l'amministratore può elencare i compiti, modificarli, sospenderli, riattivarli o eliminarli; modifica ed eliminazione richiedono conferma.
- **Alternate / error handling:**
  - Orario ambiguo (es. *"la mattina"*): l'agente chiede di precisare prima di proporre il riepilogo.
  - Un utente autorizzato tenta di creare o modificare un compito: riceve un rifiuto cortese.
  - L'amministratore non conferma: il compito non viene salvato.
- **Business rules referenced:** BR-1, BR-12, BR-14, BR-15
- **Acceptance criteria:**
  - Given l'amministratore scrive un compito in linguaggio naturale, when l'agente lo interpreta, then mostra un riepilogo (nome, istruzioni, orario, destinatari) e lo salva solo dopo la conferma.
  - Given un orario ambiguo, when l'agente riceve la richiesta, then chiede di precisarlo invece di assumerlo.
  - Given un utente autorizzato, when prova a creare un compito, then riceve un rifiuto e nessun compito viene creato.
  - Given un compito attivo, when l'amministratore invia `/pause <nome>`, then il compito passa a sospeso e non viene più eseguito finché non viene riattivato.

### FR-002 — Esecuzione programmata dei compiti

- **Priority:** Must
- **Goal:** eseguire automaticamente ogni compito attivo all'orario o intervallo previsto.
- **Main flow:**
  1. All'orario previsto (fuso orario del telefono) l'agente avvia il compito.
  2. Ragiona tramite DeepSeek e usa gli strumenti necessari (es. ricerca web).
  3. Invia il risultato su Telegram a tutti i destinatari del compito.
  4. Registra l'esecuzione nello storico (FR-008).
- **Alternate / error handling:**
  - Telefono spento o offline all'orario previsto: al ritorno online il compito saltato viene recuperato una sola volta.
  - Esecuzione oltre 10 minuti: il compito viene interrotto e l'amministratore riceve un avviso (FR-009).
  - DeepSeek o Telegram non rispondono: si applicano i tentativi di BR-8 prima di dichiarare il compito fallito.
- **Business rules referenced:** BR-4, BR-5, BR-8, BR-14
- **Acceptance criteria:**
  - Given un compito attivo programmato alle 8:00, when arrivano le 8:00, then i destinatari ricevono il risultato su Telegram senza alcun intervento.
  - Given il telefono era offline alle 8:00 e torna online alle 9:30, when l'agente riparte, then esegue il compito saltato una sola volta.
  - Given un compito che supera 10 minuti, when scade il limite, then viene interrotto, registrato come "interrotto" e l'amministratore viene avvisato.

### FR-003 — Lancio manuale di un compito

- **Priority:** Must
- **Goal:** eseguire subito un compito esistente su richiesta.
- **Main flow:**
  1. L'amministratore o un utente autorizzato scrive *"lancia news"* o `/run news`.
  2. L'agente esegue subito il compito.
  3. Il risultato viene inviato solo a chi ha fatto la richiesta.
  4. L'esecuzione viene registrata nello storico.
- **Alternate / error handling:**
  - Un utente autorizzato chiede di lanciare un compito a cui non è iscritto: riceve un rifiuto.
  - Compito inesistente: l'agente lo segnala e può elencare i compiti disponibili per quell'utente.
  - Stesso limite di 10 minuti e stessi tentativi di FR-002.
- **Business rules referenced:** BR-4, BR-8, BR-12
- **Acceptance criteria:**
  - Given un utente iscritto al compito "news", when scrive `/run news`, then riceve il risultato solo lui.
  - Given un utente non iscritto al compito "log", when scrive `/run log`, then riceve un rifiuto e il compito non viene eseguito.

### FR-004 — Domande libere (chat)

- **Priority:** Must
- **Goal:** consentire di fare domande qualsiasi all'agente, al volo.
- **Main flow:**
  1. L'amministratore o un utente autorizzato scrive una domanda.
  2. L'agente risponde, usando la ricerca web se serve (FR-005); se deve cercare sul web, nel frattempo mostra "sto cercando…".
  3. L'agente ricorda la conversazione in corso con quell'utente.
- **Alternate / error handling:**
  - Dopo 24 ore di silenzio, o con il comando `/reset`, la memoria della conversazione si azzera.
  - Se per rispondere serve un'azione che modifica il telefono, si applica FR-005.
- **Business rules referenced:** BR-2, BR-6, BR-12, BR-17
- **Acceptance criteria:**
  - Given un utente autorizzato, when fa una domanda e poi una domanda di seguito che vi fa riferimento, then l'agente risponde tenendo conto della conversazione precedente.
  - Given sono passate 24 ore dall'ultimo messaggio, when l'utente scrive, then l'agente non ricorda la conversazione precedente.
  - Given un utente scrive `/reset`, when invia un nuovo messaggio, then la conversazione riparte da zero.
  - Given l'amministratore, when chiede di rileggere la chat di un utente autorizzato, then può consultarla.
  - Given una domanda semplice, when l'utente la invia, then riceve la risposta entro 30 secondi.
  - Given una domanda che richiede ricerca web, when l'utente la invia, then vede "sto cercando…" e riceve la risposta entro 2 minuti.

### FR-005 — Ricerca web e strumenti con conferma

- **Priority:** Must
- **Goal:** far usare all'agente gli strumenti necessari (es. ricerca web) garantendo che nessuna azione che modifica il telefono avvenga senza approvazione.
- **Main flow:**
  1. Durante un compito o una chat l'agente decide quali strumenti usare.
  2. Le azioni di sola lettura e la ricerca web vengono eseguite senza conferma.
  3. Per un'azione che modifica il telefono (A4), l'agente si ferma e invia all'amministratore una richiesta con cosa vuole fare e perché, e i pulsanti **Approva / Rifiuta**.
  4. Solo dopo "Approva" l'agente esegue l'azione e prosegue.
- **Alternate / error handling:**
  - L'amministratore rifiuta: l'azione non viene eseguita e l'agente prosegue senza, o comunica di non poter completare la richiesta.
  - Nessuna risposta entro 15 minuti: l'azione è considerata rifiutata.
  - Richiesta nata da un utente autorizzato: la conferma va comunque all'amministratore, mai all'utente.
- **Business rules referenced:** BR-2, BR-3
- **Acceptance criteria:**
  - Given l'agente deve cancellare un file, when prepara l'azione, then l'amministratore riceve la richiesta con Approva/Rifiuta e il file non viene toccato prima dell'approvazione.
  - Given una richiesta di conferma senza risposta, when passano 15 minuti, then l'azione è rifiutata e non viene eseguita.
  - Given l'agente deve fare una ricerca web, when la esegue, then non chiede alcuna conferma.

### FR-006 — Lettura e riassunto dei log

- **Priority:** Must
- **Goal:** riassumere i log e segnalare errori, sia delle esecuzioni dell'agente sia di altri programmi o script eseguiti in Termux.
- **Main flow:**
  1. L'amministratore crea un compito sui log (FR-001), indicando il file o la cartella da leggere.
  2. All'esecuzione l'agente legge i log, ne produce un riassunto ed evidenzia eventuali errori.
  3. Il risultato viene inviato ai destinatari del compito.
- **Alternate / error handling:**
  - File o cartella non autorizzati: l'agente non li legge e lo segnala.
  - File inesistente o vuoto: l'agente lo segnala nel risultato.
- **Business rules referenced:** BR-13
- **Acceptance criteria:**
  - Given una cartella autorizzata contenente log con errori, when il compito viene eseguito, then il risultato contiene un riassunto e l'elenco degli errori trovati.
  - Given un percorso non autorizzato, when il compito tenta di leggerlo, then la lettura non avviene e l'amministratore ne viene informato.
  - Given l'amministratore chiede un riassunto dei log dell'agente stesso, when il compito viene eseguito, then riceve il riassunto delle esecuzioni e dei loro errori.

### FR-007 — Gestione degli utenti

- **Priority:** Must
- **Goal:** controllare chi può interagire con l'agente e a quali compiti è iscritto.
- **Main flow:**
  1. Uno sconosciuto scrive al bot: riceve un rifiuto e l'amministratore riceve un avviso con il suo nome Telegram e il pulsante **Autorizza**.
  2. In alternativa l'amministratore autorizza un utente con `/adduser`.
  3. Dopo l'autorizzazione l'agente invia al nuovo utente un messaggio informativo sulla privacy: i suoi messaggi transitano da DeepSeek e Telegram, sono conservati sull'S24 e l'amministratore può rileggerli. L'utente deve accettarlo esplicitamente; solo dopo l'accettazione può usare l'agente.
  4. L'amministratore può revocare un utente (`/removeuser`), iscriverlo o disiscriverlo da un compito, ed elencare gli utenti.
- **Alternate / error handling:**
  - Un utente revocato scrive al bot: viene trattato come sconosciuto.
  - Un utente autorizzato tenta un comando di gestione utenti: riceve un rifiuto.
  - L'utente rifiuta o non accetta il messaggio informativo: resta non autorizzato e l'amministratore riceve un avviso.
- **Business rules referenced:** BR-12, BR-18
- **Acceptance criteria:**
  - Given uno sconosciuto scrive al bot, when il messaggio arriva, then lo sconosciuto non riceve risposte utili e l'amministratore riceve l'avviso con Autorizza.
  - Given l'amministratore preme Autorizza, when l'utente accetta il messaggio informativo sulla privacy, then l'agente gli risponde come utente autorizzato.
  - Given l'amministratore preme Autorizza, when l'utente rifiuta il messaggio informativo, then resta non autorizzato e l'amministratore riceve un avviso.
  - Given l'amministratore revoca un utente, when quell'utente scrive, then viene ignorato.
  - Given un utente autorizzato, when invia `/adduser`, then il comando viene rifiutato (solo l'amministratore autorizza).

### FR-008 — Storico delle esecuzioni

- **Priority:** Must
- **Goal:** tenere traccia di ogni esecuzione e renderla consultabile da Telegram.
- **Main flow:**
  1. Ogni esecuzione (programmata o manuale) registra: compito, data e ora, esito (ok / errore / interrotto), breve riassunto.
  2. L'utente consulta lo storico chiedendo (es. *"cosa hai fatto ieri?"*) o con `/history`.
- **Alternate / error handling:**
  - Le voci più vecchie di 30 giorni vengono eliminate.
  - Un utente autorizzato vede solo lo storico dei compiti a cui è iscritto; l'amministratore vede tutto.
- **Business rules referenced:** BR-7, BR-12, BR-15
- **Acceptance criteria:**
  - Given un compito eseguito ieri, when l'amministratore chiede *"cosa hai fatto ieri?"*, then riceve l'elenco delle esecuzioni con esito e riassunto.
  - Given un utente iscritto solo a "news", when scrive `/history`, then vede solo le esecuzioni di "news".
  - Given un'esecuzione di 31 giorni fa, when si consulta lo storico, then non compare più.

### FR-009 — Avvisi all'amministratore

- **Priority:** Must
- **Goal:** informare tempestivamente l'amministratore di problemi e anomalie.
- **Main flow:** l'amministratore riceve un avviso Telegram quando:
  1. un compito fallisce (dopo i tentativi di BR-8) o supera i 10 minuti, con nome del compito e motivo;
  2. la batteria dell'S24 scende sotto il 15%;
  3. il telefono è rimasto offline per più di un'ora (avviso inviato al rientro online);
  4. la chiave DeepSeek risulta scaduta, non valida o senza credito.
- **Alternate / error handling:** se l'agente è completamente fuori uso non può avvisare; il segnale di vita quotidiano (FR-010) serve a rilevare questa situazione per assenza.
- **Business rules referenced:** BR-4, BR-8, BR-9, BR-10
- **Acceptance criteria:**
  - Given un compito che fallisce dopo 3 tentativi, when viene dichiarato fallito, then l'amministratore riceve un avviso con nome e motivo.
  - Given la batteria scende al 14%, when l'agente lo rileva, then l'amministratore riceve un avviso.
  - Given il telefono è stato offline 2 ore, when torna online, then l'amministratore riceve un avviso con il periodo di assenza.
  - Given la chiave DeepSeek è senza credito, when l'agente prova a usarla, then l'amministratore riceve un avviso specifico.

### FR-010 — Riavvio automatico e segnale di vita

- **Priority:** Must
- **Goal:** mantenere l'agente attivo nel tempo senza interventi manuali.
- **Main flow:**
  1. Dopo un crash dell'agente o un riavvio del telefono, l'agente riparte da solo.
  2. Recupera i compiti saltati (come in FR-002).
  3. Invia all'amministratore un messaggio di ripartenza, es. *"Sono di nuovo attivo — offline dalle X alle Y, recuperati N compiti"*.
  4. Ogni giorno alle 8:00 invia all'amministratore un segnale di vita ("tutto ok").
- **Alternate / error handling:**
  - DeepSeek o Telegram non raggiungibili: 3 tentativi a 1 minuto di distanza (BR-8).
  - Se il segnale di vita delle 8:00 non arriva, l'amministratore sa che l'agente potrebbe essere fuori uso.
  - Se alle 8:00 l'agente era offline, al rientro segnala il segnale mancato insieme al messaggio di ripartenza (es. *"segnale delle 8:00 non inviato — offline dalle X alle Y"*).
- **Business rules referenced:** BR-5, BR-8, BR-11
- **Acceptance criteria:**
  - Given il telefono viene riavviato, when torna acceso, then l'agente riparte senza intervento e l'amministratore riceve il messaggio di ripartenza.
  - Given l'agente è attivo, when sono le 8:00, then l'amministratore riceve il segnale di vita.
  - Given l'agente era offline alle 8:00, when torna attivo, then il messaggio di ripartenza indica che il segnale delle 8:00 non è stato inviato e il periodo di assenza.
  - Given l'agente è rimasto attivo per settimane, when si controlla lo storico, then non risultano riavvii manuali necessari.

## 8. User Journeys / Workflows

1. **Rassegna stampa quotidiana (amministratore).** L'amministratore scrive su Telegram dall'S5 Ultra *"ogni giorno alle 8 mandami le notizie sull'IA, anche a Marco"* (FR-001) → conferma il riepilogo → ogni mattina alle 8 l'agente cerca sul web e invia la rassegna a entrambi (FR-002, FR-005) → l'esecuzione finisce nello storico (FR-008).
2. **Controllo dei log.** L'amministratore crea un compito sui log di uno script Termux indicando la cartella autorizzata (FR-001, FR-006) → a ogni esecuzione riceve riassunto ed errori → se il compito fallisce riceve un avviso (FR-009).
3. **Nuovo utente.** Un collega scrive al bot → l'amministratore riceve l'avviso con Autorizza (FR-007) → lo autorizza → il collega accetta il messaggio informativo sulla privacy (FR-007) → l'amministratore lo iscrive al compito "news" → il collega riceve la rassegna, può lanciarla con `/run news` (FR-003), fare domande libere (FR-004) e consultarne lo storico (FR-008).
4. **Azione che modifica il telefono.** Durante una chat l'agente deve scrivere un file → l'amministratore riceve Approva/Rifiuta (FR-005) → approva entro 15 minuti e l'agente prosegue, oppure l'azione viene rifiutata.
5. **Ripartenza.** Il telefono si riavvia di notte → l'agente riparte da solo, recupera i compiti saltati, invia il messaggio di ripartenza e alle 8:00 il segnale di vita (FR-010, FR-002).

## 9. Business Rules

| ID | Rule | Exact values / states | Applies to |
|----|------|-----------------------|------------|
| BR-1 | Creazione, modifica ed eliminazione di un compito richiedono conferma dell'amministratore prima di avere effetto. | Riepilogo + conferma esplicita | FR-001 |
| BR-2 | Nessuna azione che modifica il telefono è eseguita senza approvazione dell'amministratore; lettura e ricerca web non la richiedono. | Modifica = eseguire comandi, scrivere/cancellare file, installare | FR-004, FR-005 |
| BR-3 | Una richiesta di conferma senza risposta è considerata rifiutata. | 15 minuti | FR-005 |
| BR-4 | Un'esecuzione che supera la durata massima viene interrotta e segnalata. | 10 minuti | FR-002, FR-003, FR-009 |
| BR-5 | Un compito saltato perché il telefono era spento o offline viene recuperato una sola volta al rientro. | 1 recupero | FR-002, FR-010 |
| BR-6 | La memoria della conversazione si azzera dopo un periodo di silenzio o su richiesta. | 24 ore di silenzio, oppure `/reset` | FR-004 |
| BR-7 | Lo storico delle esecuzioni è conservato per un periodo limitato. | 30 giorni | FR-008 |
| BR-8 | Se DeepSeek o Telegram non rispondono, l'agente ritenta prima di dichiarare il fallimento. | 3 tentativi, a 1 minuto di distanza | FR-002, FR-003, FR-009, FR-010 |
| BR-9 | Avviso di batteria scarica. | Sotto il 15% | FR-009 |
| BR-10 | Avviso di assenza di connessione, inviato al rientro online. | Offline oltre 1 ora | FR-009 |
| BR-11 | Segnale di vita quotidiano all'amministratore; se l'agente era offline, il segnale mancato è segnalato al rientro nel messaggio di ripartenza. | Ogni giorno alle 8:00 | FR-010 |
| BR-12 | Permessi per ruolo. | Amministratore: tutto. Utente autorizzato: ricevere risultati dei compiti a cui è iscritto, chat, lancio manuale e storico dei soli compiti a cui è iscritto. Sconosciuto/revocato: ignorato. Solo l'amministratore autorizza utenti (via Telegram) e dà conferme. L'amministratore può rileggere le chat degli utenti. | FR-001, FR-003, FR-004, FR-007, FR-008 |
| BR-13 | L'agente legge log solo da file o cartelle autorizzati dall'amministratore. | Percorso indicato alla creazione del compito | FR-006 |
| BR-14 | Orari e lingua. | Fuso orario del telefono; risposte in italiano salvo lingua diversa dell'utente | FR-001, FR-002 |
| BR-15 | Stati di compiti ed esecuzioni. | Compito: attivo / sospeso (eliminabile). Esecuzione: ok / errore / interrotto | FR-001, FR-008 |
| BR-16 | Dimensionamento previsto (uso personale/familiare). | Fino a 5 utenti autorizzati e 10 compiti attivi | NFR (volumi) |
| BR-17 | Tempi di risposta alle domande libere. | Entro 30 secondi; fino a 2 minuti con ricerca web, mostrando "sto cercando…" | FR-004 |
| BR-18 | Un nuovo utente può usare l'agente solo dopo aver accettato il messaggio informativo sulla privacy; in caso di rifiuto resta non autorizzato e l'amministratore viene avvisato. | Utente: in attesa di accettazione / autorizzato / revocato | FR-007 |

## 10. Information / Data Requirements

| Thing (entity) | Key information it holds | Notes / lifecycle |
|----------------|--------------------------|-------------------|
| Compito | Nome, istruzioni, quando (orario o intervallo), destinatari, stato, eventuale percorso log autorizzato | Creato, modificato, sospeso/riattivato, eliminato solo dall'amministratore con conferma |
| Utente | Nome Telegram, ruolo (amministratore / autorizzato), compiti a cui è iscritto, accettazione dell'informativa privacy | Autorizzato dall'amministratore → in attesa di accettazione → autorizzato; revocabile dall'amministratore |
| Esecuzione (storico) | Compito, data e ora, esito (ok / errore / interrotto), breve riassunto | Conservata 30 giorni |
| Conversazione | Messaggi scambiati tra un utente e l'agente | Memoria azzerata dopo 24 ore di silenzio o con `/reset`; rileggibile dall'amministratore |
| Richiesta di conferma | Azione proposta, motivo, esito (approvata / rifiutata) | Rifiutata automaticamente dopo 15 minuti |
| Chiave DeepSeek | Chiave API del proprietario | Conservata solo sull'S24 |

Tutti i dati sono conservati **solo sull'S24**, senza copie altrove. Il contenuto di messaggi, compiti e ricerche transita comunque, per natura del servizio, da DeepSeek (per il ragionamento) e da Telegram (per la comunicazione).

## 11. External Systems & Integrations

| System / partner | Purpose of the exchange | Direction (send / receive / both) |
|------------------|-------------------------|-----------------------------------|
| Telegram | Ricevere messaggi e comandi dagli utenti; inviare risultati, avvisi, richieste di conferma | Both |
| DeepSeek (via chiave API) | Ragionamento dell'agente: interpretare richieste, produrre risposte e riassunti | Both |
| Web (ricerca) | Reperire informazioni, es. notizie | Receive |
| S24 / Termux | Lettura log autorizzati, stato batteria e connessione; azioni che modificano il telefono solo con approvazione | Both |

## 12. Non-Functional Requirements

| Category | Requirement (business terms) |
|----------|------------------------------|
| Volume & scale | Fino a 5 utenti autorizzati e 10 compiti attivi (uso personale/familiare). |
| Performance / speed | Durata massima di un'esecuzione: 10 minuti. Domande libere: risposta entro 30 secondi; fino a 2 minuti se serve la ricerca web, mostrando "sto cercando…". |
| Availability | Sempre attivo (24/7) finché l'S24 è acceso e connesso; ripartenza automatica dopo crash o riavvio; segnale di vita alle 8:00; attivo per settimane senza intervento manuale. |
| Security & privacy | Solo utenti autorizzati dall'amministratore possono interagire; gli sconosciuti sono ignorati. Nessuna azione che modifica il telefono senza approvazione dell'amministratore. Lettura log limitata ai percorsi autorizzati. Dati e chiave DeepSeek conservati solo sull'S24. L'amministratore può rileggere le chat degli utenti autorizzati. |
| Compliance | Ogni nuovo utente riceve un messaggio informativo sulla privacy (transito dei messaggi da DeepSeek e Telegram, conservazione sull'S24, possibilità di rilettura da parte dell'amministratore) e deve accettarlo prima di usare l'agente. Eventuali obblighi normativi specifici non sono stati valutati in questa sede. |
| Localization / accessibility | Italiano come lingua predefinita; risposta nella lingua dell'utente se diversa. Fuso orario del telefono. |

## 13. Constraints & Dependencies

- **Constraints:**
  - L'agente gira sullo smartphone Samsung S24 in Termux, **senza permessi di root**.
  - Il modello linguistico è **DeepSeek**, tramite la chiave API del proprietario; nessun limite di spesa.
  - Il canale di comunicazione è **Telegram**, utilizzabile anche da un altro dispositivo (es. Samsung S5 Ultra).
  - Il prodotto viene costruito con **Claude Code**.
  - Nessuna scadenza e nessun budget di sviluppo definiti.
- **Dependencies:**
  - Disponibilità dei servizi DeepSeek e Telegram.
  - S24 acceso e connesso a internet (A1).
  - Chiave DeepSeek valida e con credito.

## 14. Open Questions & Assumptions to Validate

| # | Question / assumption | Owner | Blocking? |
|---|-----------------------|-------|-----------|
| A1–A5 | Ipotesi della sezione 6 (telefono sempre acceso e connesso, nessun limite di spesa, italiano predefinito, definizione di "azione che modifica", conferma solo dall'amministratore) — confermate in intervista, da rivalidare in revisione. | Amministratore | no |

## 15. Glossary

| Term | Meaning |
|------|---------|
| Agente | Il programma sempre attivo sull'S24 che esegue compiti e risponde su Telegram. |
| Compito | Un'attività ricorrente o su richiesta definita dall'amministratore (es. rassegna notizie, riassunto log). |
| Amministratore | Il proprietario dell'S24, unico a poter creare compiti, gestire utenti e approvare azioni. |
| Utente autorizzato | Una persona abilitata dall'amministratore con permessi limitati. |
| DeepSeek | Il modello linguistico (LLM) che fa "ragionare" l'agente. |
| LLM | Large Language Model: un modello di intelligenza artificiale che comprende e produce testo. |
| Termux | L'applicazione Android che fornisce un ambiente a riga di comando sull'S24. |
| Comando rapido | Un comando Telegram che inizia con `/` (es. `/tasks`, `/run`, `/history`). |
| Segnale di vita | Messaggio quotidiano "tutto ok" che conferma che l'agente è attivo. |
| Azione che modifica | Qualsiasi azione che cambia qualcosa sul telefono: eseguire comandi, scrivere o cancellare file, installare. |
| Root | Permessi di amministratore di sistema Android; non richiesti né usati. |

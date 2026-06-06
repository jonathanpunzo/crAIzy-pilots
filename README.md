# crAIzy pilots - TORCS Plug and Play

Progetto Python per TORCS / IBM AI Racing League sul circuito Corkscrew.

La cartella contiene due modalita di guida:

- `craizy_manual.py`: guida con DualShock 4 e raccolta del dataset;
- `craizy_auto_v3.py`: guida automatica principale basata sul profilo umano;
- `craizy_auto_v2.py`: guida autonoma stabile con controllo anti-oscillazione;
- `craizy_auto.py`: prima versione del pilota automatico, conservata invariata.

I file originali usati come base restano nella radice e non vengono modificati:

- `controller_ps4_torcs_dataset_auto_stop_v2 (1).py`;
- `torcs_jm_par_modulare.py`.

## Requisiti

- Python 3;
- `pygame`;
- TORCS gia installato e configurato;
- `scr_server 1` in ascolto sulla porta `3001`.

Installazione:

```powershell
py -m pip install -r requirements.txt
```

## Preparazione TORCS

1. Apri TORCS.
2. Seleziona il circuito Corkscrew.
3. Seleziona `scr_server 1` come pilota.
4. Avvia la gara e lascia TORCS in attesa del client Python.

La cartella del gioco TORCS non fa parte di questo repository.

## Guida manuale e dataset

Collega il DualShock 4 tramite USB o Bluetooth, poi esegui:

```powershell
py craizy_manual.py
```

Comandi predefiniti:

- stick sinistro: sterzo;
- `R2`: acceleratore;
- `L2`: freno;
- `SHARE`: scarta il tentativo e riavvia pista e registrazione;
- `OPTIONS`: salva il tentativo valido e riavvia pista e registrazione;
- `Ctrl+C`: scarta ed esce.

Il dataset viene scritto in:

```text
torcs_ps4_dataset.csv
```

Un giro completo viene salvato automaticamente. `OPTIONS` permette anche di
salvare manualmente il buffer valido corrente prima di ripartire. Un fuori
pista, `SHARE`, una disconnessione o un'interruzione eliminano invece le righe
temporanee del tentativo.

Dopo il traguardo non premere pulsanti: il controller salva e chiude
automaticamente, anche quando il server TORCS termina subito la gara.
`Ctrl+C` serve sempre a scartare il tentativo corrente.

Il CSV salva sensori TORCS e intenzioni del pilota prima degli aiuti elettronici.
ABS, controllo trazione, smoothing e limite sterzo non contaminano quindi i
target che verranno usati dal pilota automatico.

Il mapping predefinito pygame e:

```text
asse 0 = stick sinistro X
asse 4 = L2
asse 5 = R2
pulsante 4 = SHARE
pulsante 6 = OPTIONS
```

Se il sistema assegna numeri diversi al controller, modifica le costanti
raccolte all'inizio di `craizy_manual.py`.

## Guida automatica

Avvia TORCS nello stesso modo, poi:

```powershell
py craizy_auto_v3.py
```

La V3:

1. legge `torcs_ps4_dataset.csv` dalla stessa cartella dello script;
2. considera soltanto i giri completi;
3. costruisce velocita e traiettoria umane per settori di 5 metri;
4. combina piu giri dando a ciascuno lo stesso peso;
5. ignora automaticamente partenze e tentativi parziali;
6. usa il profilo umano come guida principale per tutto il giro;
7. anticipa le frenate osservando i settori successivi;
8. usa il pilota base soltanto per partenza e assenza del dataset.

Il riepilogo di ogni prova viene aggiunto a:

```text
auto_v3_runs.csv
```

La telemetria dettagliata dell'ultima prova viene scritta in:

```text
auto_v3_trace.csv
```

## Struttura

```text
craizy_auto.py
craizy_auto_v2.py
craizy_auto_v3.py
craizy_manual.py
torcs_ps4_dataset.csv
torcs_jm_par_modulare.py
controller_ps4_torcs_dataset_auto_stop_v2 (1).py
snakeoil3_jm2.py
```

Le costanti principali sono raccolte all'inizio di `craizy_auto_v3.py` e
`craizy_manual.py`. Non sono necessari file di configurazione o argomenti CLI.

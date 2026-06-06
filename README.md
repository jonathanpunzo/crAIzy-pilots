# crAIzy pilots - TORCS Plug and Play

Progetto Python per TORCS / IBM AI Racing League sul circuito Corkscrew.

La cartella contiene due soli programmi da avviare:

- `craizy_manual.py`: guida con DualShock 4 e raccolta del dataset;
- `craizy_auto.py`: guida autonoma stabile con supporto diretto al dataset umano.

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
- `SHARE`: scarta il tentativo e riavvia la gara;
- `OPTIONS` due volte entro 2,5 secondi: scarta ed esce;
- `Ctrl+C`: scarta ed esce.

Il dataset viene scritto in:

```text
data/torcs_ps4_dataset.csv
```

Un tentativo viene salvato soltanto dopo un giro completo. Un'uscita di pista,
un restart, una disconnessione o un'interruzione eliminano tutte le righe
temporanee del tentativo.

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
py craizy_auto.py
```

Il pilota:

1. usa la logica stabile di `torcs_jm_par_modulare.py`;
2. cerca automaticamente `data/torcs_ps4_dataset.csv`;
3. costruisce un profilo umano per settori di 5 metri;
4. usa il profilo al 35% solo quando velocita, angolo e posizione sono compatibili;
5. torna automaticamente alla guida stabile quando il dataset manca o non e
   affidabile per la situazione corrente;
6. applica gli stessi ADAS usati dal controller manuale.

Il riepilogo di ogni prova viene aggiunto a:

```text
results/auto_runs.csv
```

## Struttura

```text
craizy_auto.py
craizy_manual.py
torcs_jm_par_modulare.py
controller_ps4_torcs_dataset_auto_stop_v2 (1).py
snakeoil3_jm2.py
data/
results/
archive/
```

Le costanti principali sono raccolte all'inizio di `craizy_auto.py` e
`craizy_manual.py`. Non sono necessari file di configurazione o argomenti CLI.

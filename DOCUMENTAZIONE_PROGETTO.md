# crAIzy Auto: relazione tecnica

## 1. Obiettivo

Il progetto realizza un agente autonomo per TORCS capace di completare il
circuito Corkscrew in modo ripetibile, usando la telemetria del server di
gara e dimostrazioni raccolte con un controller umano.

La soluzione non e' un replay temporale o spaziale. La guida ordinaria nasce
dalla geometria percepita, dallo stato dinamico della vettura e da esempi
sensorialmente simili presenti nel dataset.

## 2. Metodo di lavoro

Il lavoro e' stato organizzato come ciclo sperimentale:

1. registrazione di giri umani completi con gli stessi ADAS del pilota
   autonomo;
2. controllo automatico di schema, distanza, danni e uscite;
3. costruzione di una base deterministica guidabile senza machine learning;
4. addestramento e valutazione leave-one-lap-out dell'advisor KNN;
5. integrazione con autorita' limitata, logging e Safety Governor;
6. analisi delle telemetrie nei punti critici;
7. correzioni locali introdotte solo quando supportate dalle prove;
8. validazione con giri completi, tempi, stabilita' e recovery.

Questa impostazione mantiene sempre disponibile una baseline comprensibile e
separa il contributo appreso dalle regole necessarie a proteggere il veicolo.

## 3. Architettura

```text
Sensori TORCS
     |
     +--> BaseSensorPolicy --------> sterzo e velocita' obiettivo
     |
     +--> feature normalizzate ---> KNN residuale
                                      |
                                      +--> delta sterzo e delta velocita'
                                                   |
Base + residuo --> Safety Governor --> ADAS --> comandi TORCS
```

### Base sensoriale

`BaseSensorPolicy` interpreta:

- 19 sensori di distanza dal bordo;
- `trackPos` e angolo rispetto all'asse pista;
- velocita' longitudinale e laterale;
- regime motore e velocita' delle ruote.

Dalla geometria stima direzione, apertura della strada, urgenza della curva e
velocita' sicura. Produce uno sterzo deterministico e un pedale firmato:
positivo per accelerare, negativo per frenare.

La base e' indipendente dal dataset. Questo garantisce un fallback, permette
i test `--base-only` e impedisce al modello di essere l'unico responsabile
della stabilita'.

### Advisor KNN residuale

Il modello usa `KNeighborsRegressor` con:

```text
k = 7
weights = distance
metric = euclidean
```

Le feature comprendono 19 distanze pista normalizzate, `trackPos`, angolo,
`speedX`, `speedY`, RPM, slip delle ruote e l'azione proposta dalla base.

Il KNN non predice direttamente i comandi finali. Impara due residui:

```text
delta_steer = steer_expert - steer_base
delta_speed = funzione(pedale_expert - pedale_base)
```

L'autorita' e' limitata a `+/-0,12` sullo sterzo e `+/-25 km/h` sulla
velocita' obiettivo. La correzione viene moltiplicata per una confidenza
ricavata dalla distanza media dei sette vicini. Quando lo stato e' lontano
dalle dimostrazioni, il contributo appreso decade verso zero.

Questo spiega perche' l'auto usa il KNN ma non segue alla lettera i giri
umani: il modello suggerisce correzioni locali, non riproduce una traiettoria
memorizzata.

### Profilo esperto

Dai dieci giri viene ricavata la velocita' mediana ogni 5 metri. Nei settori
ordinari questo profilo impedisce alla base di diventare ingiustificatamente
lenta. Prima curva, Corkscrew e ultima curva restano protetti e non ricevono
il bonus prestazionale ordinario.

### Safety Governor

Il Safety Governor applica i vincoli finali:

- priorita' alla frenata richiesta dalla base;
- riduzione del gas vicino al bordo;
- frenata per sovravelocita';
- controsterzo limitato in presenza di deriva laterale;
- proiezione di `trackPos` per anticipare un'uscita;
- limiti locali nelle curve protette;
- recovery a stati per stabilizzazione, retromarcia e rientro.

Il circuito e' descritto da dieci blocchi contigui:

| Blocco | Intervallo | Ruolo |
|---|---:|---|
| S01 | 0-330 m | rettilineo iniziale |
| S02_FIRST_CORNER | 330-550 m | prima curva protetta |
| S03 | 550-1000 m | settore tecnico |
| S04 | 1000-1500 m | settore veloce |
| S05 | 1500-2000 m | settore tecnico |
| S06 | 2000-2330 m | ingresso Corkscrew |
| S07_CORKSCREW | 2330-2530 m | Corkscrew protetto |
| S08 | 2530-3080 m | settore tecnico |
| S09_LAST_CORNER | 3080-3310 m | ultima curva protetta |
| S10 | 3310-3610 m | rettilineo finale |

Le correzioni locali su S03, S05, Corkscrew e ultima curva sono limitate a
finestre e condizioni dinamiche precise. In S05 una frenata preventiva si
attiva soltanto quando la posizione proiettata converge oltre il bordo
interno. Queste protezioni non sostituiscono la policy normale quando
traiettoria e velocita' sono gia' corrette.

### ADAS e cambio

L'ultimo livello trasforma l'intenzione in comandi fisicamente coerenti:

- smoothing e rate limit dello sterzo;
- ABS basato sulla differenza tra velocita' veicolo e ruote;
- TCS basato sullo slittamento delle ruote posteriori;
- esclusione reciproca di gas e freno;
- cambio automatico con isteresi, cooldown e protezione dalle scalate durante
  accelerazione forte.

Il cambio del controller manuale e quello autonomo usano la stessa logica e
sono confrontati automaticamente dai test.

## 4. Dataset

`craizy_manual.py` registra per ogni tick:

- identificativo del giro, step e tempo;
- intenzioni del pilota;
- azioni post-ADAS realmente inviate a TORCS;
- velocita', RPM, ruote, posizione e angolo;
- 19 sensori pista, danno e distanza percorsa.

Sono salvati solo giri completi. Un tentativo e' invalidato dopo tre tick
consecutivi fuori pista o al primo aumento del danno. Il commit controlla che
l'intestazione del CSV coincida esattamente con lo schema previsto e usa una
sostituzione atomica.

Il dataset consegnato contiene 10 giri e 37.726 righe. Tutti superano:

- almeno 800 campioni;
- almeno 3.500 metri;
- danno massimo zero;
- nessuna uscita persistente;
- vettori ruote e pista della dimensione attesa.

## 5. Validazione e telemetria

Ogni tentativo autonomo produce:

- trace dettagliato dell'ultimo giro;
- archivio timestampato del trace;
- riepilogo con distanza, velocita', uscite, recovery e latenza KNN;
- statistiche di tempo, velocita' e massimo `trackPos` per settore.

I test automatici verificano geometria dei blocchi, segni delle correzioni,
limiti del KNN, priorita' delle frenate, protezione dei bordi, recovery,
protezioni locali, cambio automatico e compatibilita' del dataset.

## 6. Risultati

### Dimostrazioni

| Misura | Risultato |
|---|---:|
| Giri puliti | 10 |
| Campioni totali | 37.726 |
| Campioni per giro | 3.691-3.907 |
| Tempo registrato | 75,932-80,684 s |
| Velocita' massima | 265,731-273,462 km/h |

### Guida autonoma

Sulle dieci prove registrate dal sistema di validazione:

| Misura | Risultato |
|---|---:|
| Tentativi | 10 |
| Giri completati | 8 |
| Giri puliti senza recovery | 7 |
| Affidabilita' complessiva | 70% |
| Best lap | 88,406 s |
| Tempo mediano pulito | 90,202 s |
| Tempo medio pulito | 90,029 s |
| Deviazione standard | 1,021 s |

Il risultato principale e' un comportamento stabile e ripetibile, con
traiettoria non identica alle dimostrazioni ma influenzata dal KNN entro
limiti espliciti. Le differenze rispetto al pilota umano derivano dalla base
sensoriale, dai vincoli di sicurezza e dalla natura residuale del modello.

## 7. Ambiente e riproduzione

Il progetto viene eseguito nell'ambiente Anaconda predisposto dai docenti,
che include Python, NumPy, scikit-learn e pygame. NumPy gestisce i vettori
numerici, scikit-learn fornisce `KNeighborsRegressor` e pygame acquisisce gli
input del DualShock 4 durante la raccolta manuale.

Non e' prevista un'installazione locale delle dipendenze. Con l'ambiente del
corso attivo:

```powershell
python -m unittest test_craizy_auto.py
python craizy_auto.py --analyze-only
python craizy_auto.py
python craizy_auto.py --base-only
python craizy_auto.py --validation-report --validation-runs 10
```

I risultati dipendono dalla configurazione di TORCS, dalla pista Corkscrew,
dalla monoposto e dal setup fisico usati durante la raccolta.

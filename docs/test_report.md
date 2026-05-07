# Test report

Compilare una riga per ogni sessione.

| Data | Config | Track | Driver | Giri completati | Best lap | Media lap | Damage max | Offtrack | Note |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-05-07 | best_lap | Corkscrew | scr_server 1 | TBD | TBD | TBD | TBD | TBD | Unico preset automatico da gara |
| 2026-05-07 | manual_control | Corkscrew | scr_server 1 | TBD | TBD | TBD | TBD | TBD | Guida manuale per debug e dataset |
| 2026-05-07 | best_lap | Corkscrew | scr_server 1 | No | N/A | N/A | 0 | 0 | Log `20260507_092734_best_lap.csv`: blocco a ~56 km/h, accel medio 0.87, RPM medi ~7879, picchi 17800, cambio oscillante 1/2. Fix: isteresi cambio, launch control, traction cut piu' forte, log comandi con prefisso `cmd_`. |
| 2026-05-07 | best_lap | Corkscrew | scr_server 1 | No | N/A | N/A | 0 | Si | Log `20260507_093300_best_lap.csv`: oscillazione su rettilineo a ~155 km/h, `cmd_steer` fino a +0.46/-0.61, `speedY` oltre 13 km/h e recovery penalizzato dalla sesta a bassa velocita'. Fix: gain sterzo ridotto, damping su `speedY`, limite sterzo ad alta velocita', rate limit sterzo, scalata forzata in recovery. |

## Criteri minimi

- 5 giri consecutivi: baseline accettabile.
- 10 giri consecutivi: stabilita' accettabile.
- Test con altri driver: must-have.
- Miglior giro registrato da partenza ferma: materiale video ufficiale.

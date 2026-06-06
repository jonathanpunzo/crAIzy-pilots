import csv
import json
import os
import sys
import time
import math

import pygame
import snakeoil3_jm2 as snakeoil3


# ============================================================
# TORCS - PS4 CONTROLLER DRIVER + DATASET RECORDER
# ============================================================
# Comandi consigliati DualShock 4 / controller PS4:
# - Stick sinistro       = sterzo
# - R2                   = accelera
# - L2                   = frena
# - OPTIONS              = salva ed esce
# - SHARE                = restart TORCS/race
# - CTRL+C               = salva ed esce
#
# Dataset salvato nel formato:
# steer,accel,brake,gear,speedX,speedY,speedZ,wheelSpinVel,z,track,trackPos,angle,rpm,damage,distFromStart
# ============================================================


PORT = 3001

# Nome fisso: ogni run aggiunge righe in append.
DATASET_FILENAME = "torcs_ps4_dataset_mattia15.csv"

DATASET_COLUMNS = [
    "steer", "accel", "brake", "gear",
    "speedX", "speedY", "speedZ",
    "wheelSpinVel", "z", "track", "trackPos", "angle",
    "rpm", "damage", "distFromStart",
]

# ----------------- Mapping PS4 -----------------
# Mapping più comune con pygame/SDL:
# axis 0 = left stick X
# axis 4 = L2
# axis 5 = R2
#
# Su alcuni PC/driver può cambiare. Se i trigger non vanno, prova:
# L2_AXIS = 3
# R2_AXIS = 4
STEER_AXIS = 0
L2_AXIS = 4
R2_AXIS = 5

# Pulsanti PS4 più comuni:
# 0 = X/Croce, 1 = Cerchio, 2 = Quadrato, 3 = Triangolo
# 4 = Share, 6 = Options in molti mapping pygame
SHARE_BUTTON = 4
OPTIONS_BUTTON = 6

# Se il tuo mapping ha Options/Share diversi, metti True per stampare gli eventi.
PRINT_BUTTON_EVENTS = False

# ----------------- Guida stabile -----------------
INVERT_STEERING = True

STEER_DEADZONE = 0.08
TRIGGER_DEADZONE = 0.08

# Curva dello sterzo: più alto = meno sensibile vicino al centro.
STEER_PROGRESSION = 2.20

# Curva trigger: più alto = gas/freno più progressivi.
TRIGGER_PROGRESSION = 1.70

# Smoothing: più basso = più morbido/lento, più alto = più reattivo.
STEER_SMOOTHING = 0.16
PEDAL_SMOOTHING = 0.20

# Limite sterzo in base alla velocità.
# A velocità alta riduce lo sterzo massimo per evitare testacoda.
USE_SPEED_SENSITIVE_STEERING = True
MAX_STEER_LOW_SPEED = 0.92
MAX_STEER_HIGH_SPEED = 0.24
SPEED_FOR_MIN_STEER = 175.0

# Riduzione gas quando stai sterzando molto.
THROTTLE_LIMIT_WHILE_STEERING = True
THROTTLE_STEER_START = 0.35
THROTTLE_STEER_FULL = 0.70
THROTTLE_STEER_MIN_ACCEL = 0.45

# Limitatore morbido velocità per raccogliere dati puliti.
SPEED_CAP_ENABLED = True
SPEED_CAP_KMH = 160.0
SPEED_CAP_SOFT_ZONE = 22.0
SPEED_CAP_MIN_ACCEL = 0.18

# Cambio automatico.
MIN_FORWARD_GEAR = 1
MAX_FORWARD_GEAR = 6
SHIFT_COOLDOWN = 0.35

UPSHIFT_RPM = 7600
DOWNSHIFT_RPM = 3300
PANIC_DOWNSHIFT_RPM = 2300

UPSHIFT_SPEED = {
    1: 45.0,
    2: 78.0,
    3: 112.0,
    4: 148.0,
    5: 184.0,
}

DOWNSHIFT_SPEED = {
    2: 30.0,
    3: 58.0,
    4: 90.0,
    5: 122.0,
    6: 155.0,
}

MIN_SPEED_FOR_UPSHIFT = {
    1: 22.0,
    2: 48.0,
    3: 78.0,
    4: 110.0,
    5: 145.0,
}

PRINT_EVERY = 50
FLUSH_EVERY = 250

# Stop automatico dopo un giro completato.
# Serve a evitare righe "a vuoto" dopo il traguardo / fine gara.
AUTO_STOP_AFTER_LAP = True
LAPS_TO_RECORD = 1

# Protezioni anti-falso positivo nei primi secondi.
MIN_SECONDS_BEFORE_LAP_DETECTION = 8.0
MIN_DIST_RACED_BEFORE_LAP_DETECTION = 80.0

# Rilevamento passaggio traguardo:
# - curLapTime si resetta
# - distFromStart torna vicino a 0
# - lastLapTime cambia/diventa positivo
CUR_LAP_RESET_DROP_SECONDS = 3.0
DIST_FROM_START_RESET_DROP_METERS = 120.0
LAP_DETECTION_COOLDOWN_SECONDS = 3.0


# ============================================================
# UTILITY
# ============================================================

def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except Exception:
        return default


def safe_list(value, length, default_value):
    if isinstance(value, str):
        cleaned = value.replace("[", " ").replace("]", " ").replace(",", " ").strip()
        value = [safe_float(x, default_value) for x in cleaned.split()] if cleaned else []

    if not isinstance(value, (list, tuple)):
        value = [default_value] * length

    value = [safe_float(x, default_value) for x in value]

    if len(value) < length:
        value = value + [default_value] * (length - len(value))

    if len(value) > length:
        value = value[:length]

    return value


def axis_value(joystick, axis_index, default=0.0):
    try:
        if axis_index is None:
            return default
        if axis_index < 0 or axis_index >= joystick.get_numaxes():
            return default
        return safe_float(joystick.get_axis(axis_index), default)
    except Exception:
        return default


def normalize_trigger(raw):
    """
    Con molti controller i trigger vanno da -1 a +1:
    -1 = non premuto, +1 = premuto.
    Alcuni driver invece danno già 0..1.
    Questa funzione gestisce entrambi i casi.
    """
    raw = safe_float(raw, 0.0)

    if raw < -0.05:
        value = (raw + 1.0) / 2.0
    else:
        value = raw

    return clamp(value, 0.0, 1.0)


def apply_deadzone_and_curve(value, deadzone, progression):
    value = safe_float(value, 0.0)

    if abs(value) <= deadzone:
        return 0.0

    sign = 1.0 if value > 0 else -1.0
    normalized = (abs(value) - deadzone) / max(0.0001, 1.0 - deadzone)
    normalized = clamp(normalized, 0.0, 1.0)

    return sign * (normalized ** progression)


def apply_trigger_curve(value):
    value = clamp(value, 0.0, 1.0)

    if value <= TRIGGER_DEADZONE:
        return 0.0

    normalized = (value - TRIGGER_DEADZONE) / max(0.0001, 1.0 - TRIGGER_DEADZONE)
    normalized = clamp(normalized, 0.0, 1.0)

    return normalized ** TRIGGER_PROGRESSION


def linear_limit(abs_value, start, full, min_value):
    abs_value = abs(abs_value)

    if abs_value <= start:
        return 1.0

    if abs_value >= full:
        return min_value

    ratio = (abs_value - start) / max(0.0001, full - start)
    return 1.0 + (min_value - 1.0) * ratio


def max_steer_for_speed(speed):
    if not USE_SPEED_SENSITIVE_STEERING:
        return MAX_STEER_LOW_SPEED

    ratio = clamp(abs(speed) / SPEED_FOR_MIN_STEER, 0.0, 1.0)
    value = MAX_STEER_LOW_SPEED + (MAX_STEER_HIGH_SPEED - MAX_STEER_LOW_SPEED) * ratio
    return clamp(value, MAX_STEER_HIGH_SPEED, MAX_STEER_LOW_SPEED)


def ensure_dataset_exists():
    file_exists = os.path.exists(DATASET_FILENAME)

    if not file_exists or os.path.getsize(DATASET_FILENAME) == 0:
        with open(DATASET_FILENAME, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=DATASET_COLUMNS)
            writer.writeheader()
        print(f"[DATASET] Creato nuovo file: {DATASET_FILENAME}")
    else:
        print(f"[DATASET] File esistente trovato: {DATASET_FILENAME}. Append attivo.")


def append_dataset_row(row):
    with open(DATASET_FILENAME, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DATASET_COLUMNS)
        writer.writerow(row)


def server_is_closed(client):
    """
    Ritorna True quando TORCS/SCR ha chiuso la gara.

    Questo è il punto chiave: se client.so diventa None, NON dobbiamo più
    scrivere righe nel dataset, perché i sensori rimasti in client.S.d sono
    solo l'ultimo pacchetto ricevuto e genererebbero migliaia di righe spazzatura.
    """
    return client is None or getattr(client, "so", None) is None


def build_dataset_row(sensors, action):
    return {
        "steer": action.get("steer", 0.0),
        "accel": action.get("accel", 0.0),
        "brake": action.get("brake", 0.0),
        "gear": int(action.get("gear", 1)),

        "speedX": sensors.get("speedX", 0.0),
        "speedY": sensors.get("speedY", 0.0),
        "speedZ": sensors.get("speedZ", 0.0),
        "wheelSpinVel": json.dumps(
            safe_list(
                sensors.get("wheelSpinVel", sensors.get("wheelSpedVel", [0.0] * 4)),
                4,
                0.0,
            )
        ),
        "z": sensors.get("z", 0.0),
        "track": json.dumps(safe_list(sensors.get("track", [200.0] * 19), 19, 200.0)),
        "trackPos": sensors.get("trackPos", 0.0),
        "angle": sensors.get("angle", 0.0),
        "rpm": sensors.get("rpm", 0.0),
        "damage": sensors.get("damage", 0.0),
        "distFromStart": sensors.get("distFromStart", 0.0),
    }



# ============================================================
# RILEVAMENTO FINE GIRO
# ============================================================

class RaceFinishDetector:
    """
    Rileva il completamento del giro usando più sensori TORCS.

    Non tutti i setup SCR mandano un evento esplicito di fine gara.
    Per questo controlliamo:
    - lastLapTime che diventa positivo/cambia;
    - curLapTime che si resetta;
    - distFromStart che torna verso lo start.
    """

    def __init__(self):
        self.completed_laps = 0
        self.prev_cur_lap_time = None
        self.prev_dist_from_start = None
        self.prev_last_lap_time = 0.0
        self.last_detection_elapsed = -999.0

    def update(self, sensors, elapsed):
        if not AUTO_STOP_AFTER_LAP:
            return False, ""

        cur_lap_time = safe_float(sensors.get("curLapTime", 0.0))
        last_lap_time = safe_float(sensors.get("lastLapTime", 0.0))
        dist_from_start = safe_float(sensors.get("distFromStart", 0.0))
        dist_raced = safe_float(sensors.get("distRaced", 0.0))

        lap_completed = False
        reasons = []

        enough_race_done = (
            elapsed >= MIN_SECONDS_BEFORE_LAP_DETECTION
            and dist_raced >= MIN_DIST_RACED_BEFORE_LAP_DETECTION
        )

        if enough_race_done:
            if last_lap_time > 0.0 and abs(last_lap_time - self.prev_last_lap_time) > 0.05:
                lap_completed = True
                reasons.append(f"lastLapTime={last_lap_time:.2f}")

            if self.prev_cur_lap_time is not None:
                if self.prev_cur_lap_time - cur_lap_time >= CUR_LAP_RESET_DROP_SECONDS:
                    lap_completed = True
                    reasons.append(
                        f"curLapTime reset {self.prev_cur_lap_time:.2f}->{cur_lap_time:.2f}"
                    )

            if self.prev_dist_from_start is not None:
                if self.prev_dist_from_start - dist_from_start >= DIST_FROM_START_RESET_DROP_METERS:
                    lap_completed = True
                    reasons.append(
                        f"distFromStart reset {self.prev_dist_from_start:.1f}->{dist_from_start:.1f}"
                    )

        self.prev_cur_lap_time = cur_lap_time
        self.prev_dist_from_start = dist_from_start
        if last_lap_time > 0.0:
            self.prev_last_lap_time = last_lap_time

        if lap_completed and (elapsed - self.last_detection_elapsed) > LAP_DETECTION_COOLDOWN_SECONDS:
            self.completed_laps += 1
            self.last_detection_elapsed = elapsed
            reason = "; ".join(reasons) if reasons else "giro completato"
            print(f"\n[LAP COMPLETATO] giro={self.completed_laps} - {reason}")

        if self.completed_laps >= LAPS_TO_RECORD:
            return True, f"raggiunti {self.completed_laps} giro/i registrati"

        return False, ""

# ============================================================
# PS4 CONTROLLER
# ============================================================

class PS4Controller:
    def __init__(self):
        self.running = True
        self.restart_requested = False
        self.last_shift_time = 0.0

        self.state = {
            "steer": 0.0,
            "accel": 0.0,
            "brake": 0.0,
            "gear": 1,
            "clutch": 0.0,
            "meta": 0,
        }

        pygame.init()
        pygame.joystick.init()

        count = pygame.joystick.get_count()
        if count <= 0:
            print("ERRORE: nessun controller rilevato.")
            print("Collega il controller PS4 via USB/Bluetooth e riavvia lo script.")
            sys.exit(1)

        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()

        print(f"[CONTROLLER] Rilevato: {self.joystick.get_name()}")
        print(f"[CONTROLLER] Assi: {self.joystick.get_numaxes()} | Pulsanti: {self.joystick.get_numbuttons()}")
        print("[CONTROLLER] Stick sinistro = sterzo | R2 = gas | L2 = freno | OPTIONS = salva/esci")

    def automatic_gear(self, sensors):
        now = time.time()
        speed = abs(safe_float(sensors.get("speedX", 0.0)))
        rpm = safe_float(sensors.get("rpm", 0.0))
        current = int(self.state.get("gear", 1))

        if current < MIN_FORWARD_GEAR:
            current = MIN_FORWARD_GEAR

        if now - self.last_shift_time < SHIFT_COOLDOWN:
            return int(clamp(current, MIN_FORWARD_GEAR, MAX_FORWARD_GEAR))

        new_gear = current

        if current > MIN_FORWARD_GEAR:
            too_slow_for_gear = speed < DOWNSHIFT_SPEED.get(current, 0.0)
            rpm_too_low = rpm > 0 and rpm < PANIC_DOWNSHIFT_RPM
            rpm_low_and_slow = (
                rpm > 0
                and rpm < DOWNSHIFT_RPM
                and speed < DOWNSHIFT_SPEED.get(current, 0.0) + 12.0
            )

            if too_slow_for_gear or rpm_too_low or rpm_low_and_slow:
                new_gear = current - 1

        if new_gear == current and current < MAX_FORWARD_GEAR:
            enough_speed = speed >= MIN_SPEED_FOR_UPSHIFT.get(current, 999.0)
            by_rpm = rpm >= UPSHIFT_RPM and enough_speed
            by_speed = speed >= UPSHIFT_SPEED.get(current, 999.0)

            if by_rpm or by_speed:
                new_gear = current + 1

        new_gear = int(clamp(new_gear, MIN_FORWARD_GEAR, MAX_FORWARD_GEAR))

        if new_gear != current:
            self.last_shift_time = now

        return new_gear

    def process_events(self):
        self.restart_requested = False
        self.state["meta"] = 0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.JOYBUTTONDOWN:
                if PRINT_BUTTON_EVENTS:
                    print(f"[BUTTON DOWN] {event.button}")

                if event.button == OPTIONS_BUTTON:
                    print("\n[STOP] Premuto OPTIONS. Salvo ed esco.")
                    self.running = False

                elif event.button == SHARE_BUTTON:
                    print("\n[RESTART] Premuto SHARE. Richiedo restart race.")
                    self.restart_requested = True
                    self.state["meta"] = 1

            elif event.type == pygame.JOYAXISMOTION:
                # Utile solo se abiliti PRINT_BUTTON_EVENTS.
                pass

    def update(self, sensors):
        self.process_events()

        speed = safe_float(sensors.get("speedX", 0.0))

        raw_steer = axis_value(self.joystick, STEER_AXIS, 0.0)
        if INVERT_STEERING:
            raw_steer *= -1.0

        target_steer = apply_deadzone_and_curve(
            raw_steer,
            STEER_DEADZONE,
            STEER_PROGRESSION,
        )

        steer_limit = max_steer_for_speed(speed)
        target_steer = clamp(target_steer, -steer_limit, steer_limit)

        raw_l2 = normalize_trigger(axis_value(self.joystick, L2_AXIS, 0.0))
        raw_r2 = normalize_trigger(axis_value(self.joystick, R2_AXIS, 0.0))

        target_brake = apply_trigger_curve(raw_l2)
        target_accel = apply_trigger_curve(raw_r2)

        if SPEED_CAP_ENABLED and speed > SPEED_CAP_KMH:
            over = min(speed - SPEED_CAP_KMH, SPEED_CAP_SOFT_ZONE)
            ratio = over / max(0.001, SPEED_CAP_SOFT_ZONE)
            cap = 1.0 + (SPEED_CAP_MIN_ACCEL - 1.0) * ratio
            target_accel *= cap

        if THROTTLE_LIMIT_WHILE_STEERING:
            throttle_limit = linear_limit(
                target_steer,
                THROTTLE_STEER_START,
                THROTTLE_STEER_FULL,
                THROTTLE_STEER_MIN_ACCEL,
            )
            target_accel *= throttle_limit

        # Se freni, taglia il gas. Evita gas+freno insieme nel dataset.
        if target_brake > 0.05:
            target_accel = 0.0

        self.state["steer"] += STEER_SMOOTHING * (target_steer - self.state["steer"])
        self.state["accel"] += PEDAL_SMOOTHING * (target_accel - self.state["accel"])
        self.state["brake"] += PEDAL_SMOOTHING * (target_brake - self.state["brake"])

        self.state["steer"] = clamp(self.state["steer"], -1.0, 1.0)
        self.state["accel"] = clamp(self.state["accel"], 0.0, 1.0)
        self.state["brake"] = clamp(self.state["brake"], 0.0, 1.0)
        self.state["gear"] = self.automatic_gear(sensors)
        self.state["clutch"] = 0.0

        return {
            "raw_steer": raw_steer,
            "raw_l2": raw_l2,
            "raw_r2": raw_r2,
            "target_steer": target_steer,
            "steer_limit": steer_limit,
        }

    def stop(self):
        try:
            pygame.joystick.quit()
            pygame.quit()
        except Exception:
            pass


def send_safe_stop_command(client):
    try:
        if server_is_closed(client):
            return
        client.R.d["steer"] = 0.0
        client.R.d["accel"] = 0.0
        client.R.d["brake"] = 1.0
        client.R.d["gear"] = 1
        client.R.d["clutch"] = 0.0
        client.R.d["meta"] = 0
        client.respond_to_server()
    except Exception:
        pass


# ============================================================
# MAIN
# ============================================================

def main():
    ensure_dataset_exists()

    print("Avvio client TORCS...")
    client = snakeoil3.Client(p=PORT, vision=False)
    controller = PS4Controller()

    client.get_servers_input()

    print("=" * 70)
    print(" TORCS PS4 CONTROLLER DRIVER")
    print("=" * 70)
    print(" Stick sinistro = sterzo")
    print(" R2             = accelera")
    print(" L2             = frena")
    print(" SHARE          = restart race")
    print(" OPTIONS        = salva ed esce")
    print(" CTRL+C         = salva ed esce")
    print(f" AUTO-STOP      = {'ON' if AUTO_STOP_AFTER_LAP else 'OFF'} dopo {LAPS_TO_RECORD} giro/i")
    print("-" * 70)
    print(f"Dataset CSV    = {DATASET_FILENAME}")
    print("Formato        = steer,accel,brake,gear,speedX,speedY,speedZ,wheelSpinVel,z,track,trackPos,angle,rpm,damage,distFromStart")
    print("=" * 70)

    step = 0
    start_time = time.time()
    finish_detector = RaceFinishDetector()

    recording_enabled = True
    stop_reason = ""

    try:
        while controller.running and recording_enabled:
            # Failsafe assoluto: se TORCS ha chiuso il socket, NON usare più client.S.d.
            if server_is_closed(client):
                stop_reason = "socket TORCS/SCR chiuso prima del tick"
                print(f"\n[STOP DATASET] {stop_reason}.")
                recording_enabled = False
                break

            sensors = client.S.d
            elapsed = time.time() - start_time

            # 1) Prima controlliamo se il giro è finito.
            # Se è finito, NON costruiamo row e NON scriviamo sul CSV.
            race_finished, finish_reason = finish_detector.update(sensors, elapsed)
            if race_finished:
                stop_reason = f"fine giro rilevata: {finish_reason}"
                print(f"\n[STOP AUTOMATICO] {stop_reason}.")
                print("[STOP AUTOMATICO] Chiudo immediatamente la scrittura del dataset.")
                recording_enabled = False
                controller.running = False
                break

            # 2) Aggiorniamo il controller solo se stiamo ancora registrando.
            debug = controller.update(sensors)
            action = controller.state.copy()

            client.R.d["steer"] = action["steer"]
            client.R.d["accel"] = action["accel"]
            client.R.d["brake"] = action["brake"]
            client.R.d["gear"] = action["gear"]
            client.R.d["clutch"] = action["clutch"]
            client.R.d["meta"] = action["meta"]

            if controller.restart_requested:
                client.respond_to_server()
                print("\n[RESTART] Comando inviato. Resetto stato e continuo.")
                controller.state["gear"] = 1
                controller.state["steer"] = 0.0
                controller.state["accel"] = 0.0
                controller.state["brake"] = 0.0

                client.get_servers_input()
                if server_is_closed(client):
                    stop_reason = "socket TORCS/SCR chiuso durante il restart"
                    print(f"\n[STOP DATASET] {stop_reason}.")
                    recording_enabled = False
                    break
                continue

            # 3) Scriviamo UNA riga solo se il socket è ancora vivo.
            # Se la gara è finita, client.get_servers_input() al tick precedente
            # avrebbe già messo client.so = None e qui non si arriverebbe.
            if not recording_enabled or server_is_closed(client):
                stop_reason = "registrazione disattivata prima della scrittura"
                print(f"\n[STOP DATASET] {stop_reason}.")
                break

            row = build_dataset_row(sensors, action)
            append_dataset_row(row)
            step += 1

            if step % PRINT_EVERY == 0:
                speed = safe_float(sensors.get("speedX", 0.0))
                dist = safe_float(sensors.get("distFromStart", 0.0))
                rpm = safe_float(sensors.get("rpm", 0.0))
                track_pos = safe_float(sensors.get("trackPos", 0.0))

                sys.stdout.write(
                    f"\rstep={step:6d} "
                    f"dist={dist:7.1f}m "
                    f"speed={speed:6.1f} "
                    f"rpm={rpm:7.0f} "
                    f"gear={action['gear']:2d} "
                    f"steer={action['steer']:6.3f} "
                    f"accel={action['accel']:5.2f} "
                    f"brake={action['brake']:5.2f} "
                    f"trackPos={track_pos:6.2f} "
                    f"R2={debug['raw_r2']:.2f} "
                    f"L2={debug['raw_l2']:.2f}   "
                )
                sys.stdout.flush()

            # 4) Invia comando e aspetta il prossimo pacchetto.
            # Subito dopo get_servers_input controlliamo il socket.
            # Questo è il fix principale contro le 15.000 righe spazzatura.
            client.respond_to_server()
            client.get_servers_input()

            if server_is_closed(client):
                stop_reason = "gara terminata: socket TORCS/SCR chiuso dopo get_servers_input"
                print(f"\n[STOP DATASET] {stop_reason}.")
                print("[STOP DATASET] Da questo momento non scrivo più nessuna riga.")
                recording_enabled = False
                break

    except KeyboardInterrupt:
        print("\n[CTRL+C] Interruzione manuale. Salvo ed esco.")

    finally:
        send_safe_stop_command(client)
        controller.stop()
        print()
        print("Dataset salvato correttamente.")
        print(f"CSV: {DATASET_FILENAME}")
        print(f"Righe aggiunte in questa sessione: {step}")
        try:
            print(f"Giri rilevati: {finish_detector.completed_laps}")
        except Exception:
            pass
        try:
            if stop_reason:
                print(f"Motivo stop: {stop_reason}")
        except Exception:
            pass
        print("Fine.")


if __name__ == "__main__":
    main()

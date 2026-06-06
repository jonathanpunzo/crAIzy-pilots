import csv
import importlib.util
import os
import sys
import time
from pathlib import Path

from craizy_auto import DATASET_COLUMNS, DATASET_PATH, PORT, SharedADAS


# ============================================================
# crAIzy pilots - DualShock 4 controller and dataset recorder
# ============================================================

LEGACY_CONTROLLER_PATH = Path(__file__).with_name(
    "controller_ps4_torcs_dataset_auto_stop_v2 (1).py"
)

OPTIONS_CONFIRM_SECONDS = 2.5
OFFTRACK_CONFIRM_TICKS = 10
OFFTRACK_TRACK_POS = 1.05
PRINT_EVERY = 50


def load_legacy_controller():
    spec = importlib.util.spec_from_file_location(
        "craizy_legacy_ps4_controller",
        LEGACY_CONTROLLER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Impossibile caricare il controller PS4 originale.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load_legacy_controller()
pygame = legacy.pygame
snakeoil3 = legacy.snakeoil3

# DualShock 4 mapping and input calibration.
STEER_AXIS = 0
L2_AXIS = 4
R2_AXIS = 5
SHARE_BUTTON = 4
OPTIONS_BUTTON = 6

INVERT_STEERING = True
STEER_DEADZONE = 0.08
TRIGGER_DEADZONE = 0.08
STEER_PROGRESSION = 2.20
TRIGGER_PROGRESSION = 1.70


def apply_trigger_curve(value):
    value = max(0.0, min(1.0, legacy.safe_float(value)))
    if value <= TRIGGER_DEADZONE:
        return 0.0

    normalized = (value - TRIGGER_DEADZONE) / max(1.0 - TRIGGER_DEADZONE, 0.0001)
    return max(0.0, min(1.0, normalized)) ** TRIGGER_PROGRESSION


class SupremePS4Controller:
    def __init__(self):
        self.running = True
        self.restart_requested = False
        self.exit_requested = False
        self.stop_reason = ""
        self.options_armed_at = None

        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() <= 0:
            raise RuntimeError("Nessun controller rilevato.")

        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        print("[CONTROLLER] %s" % self.joystick.get_name())
        print(
            "[CONTROLLER] Assi: %d | Pulsanti: %d"
            % (self.joystick.get_numaxes(), self.joystick.get_numbuttons())
        )

    def reset_requests(self):
        self.restart_requested = False
        self.exit_requested = False
        self.options_armed_at = None

    def process_events(self):
        self.restart_requested = False
        now = time.monotonic()

        if (
            self.options_armed_at is not None
            and now - self.options_armed_at > OPTIONS_CONFIRM_SECONDS
        ):
            self.options_armed_at = None
            print("\n[OPTIONS] Conferma scaduta.")

        removed_event = getattr(pygame, "JOYDEVICEREMOVED", None)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                self.exit_requested = True
                self.stop_reason = "window_closed"
                continue

            if removed_event is not None and event.type == removed_event:
                self.running = False
                self.exit_requested = True
                self.stop_reason = "controller_disconnected"
                print("\n[STOP] Controller scollegato.")
                continue

            if event.type != pygame.JOYBUTTONDOWN:
                continue

            if event.button == SHARE_BUTTON:
                self.restart_requested = True
                self.options_armed_at = None
                print("\n[SHARE] Tentativo scartato. Riavvio gara.")
                continue

            if event.button == OPTIONS_BUTTON:
                if (
                    self.options_armed_at is not None
                    and now - self.options_armed_at <= OPTIONS_CONFIRM_SECONDS
                ):
                    self.running = False
                    self.exit_requested = True
                    self.stop_reason = "options_confirmed"
                    print("\n[OPTIONS] Uscita confermata. Tentativo scartato.")
                else:
                    self.options_armed_at = now
                    print(
                        "\n[OPTIONS] Premi di nuovo entro %.1f secondi per uscire."
                        % OPTIONS_CONFIRM_SECONDS
                    )

    def intention(self):
        self.process_events()
        if not self.running:
            return {"steer": 0.0, "accel": 0.0, "brake": 0.0}

        raw_steer = legacy.axis_value(self.joystick, STEER_AXIS, 0.0)
        if INVERT_STEERING:
            raw_steer *= -1.0

        steer = legacy.apply_deadzone_and_curve(
            raw_steer,
            STEER_DEADZONE,
            STEER_PROGRESSION,
        )
        raw_l2 = legacy.normalize_trigger(
            legacy.axis_value(self.joystick, L2_AXIS, 0.0)
        )
        raw_r2 = legacy.normalize_trigger(
            legacy.axis_value(self.joystick, R2_AXIS, 0.0)
        )

        return {
            "steer": steer,
            "accel": apply_trigger_curve(raw_r2),
            "brake": apply_trigger_curve(raw_l2),
        }

    def stop(self):
        try:
            pygame.joystick.quit()
            pygame.quit()
        except Exception:
            pass


class TransactionalDataset:
    def __init__(self, path=DATASET_PATH):
        self.path = path
        self.rows = []
        self.valid = True
        self.invalid_reason = ""
        self.offtrack_ticks = 0

    def reset(self):
        self.rows = []
        self.valid = True
        self.invalid_reason = ""
        self.offtrack_ticks = 0

    def discard(self, reason):
        discarded = len(self.rows)
        self.rows = []
        self.valid = False
        self.invalid_reason = reason
        return discarded

    def observe_track(self, sensors):
        track = legacy.safe_list(sensors.get("track", [200.0] * 19), 19, 200.0)
        track_pos = abs(legacy.safe_float(sensors.get("trackPos", 0.0)))
        offtrack = track_pos > OFFTRACK_TRACK_POS or min(track) < 0.0

        if offtrack:
            self.offtrack_ticks += 1
        else:
            self.offtrack_ticks = 0

        if self.valid and self.offtrack_ticks >= OFFTRACK_CONFIRM_TICKS:
            discarded = self.discard("offtrack")
            print(
                "\n[DATASET] Tentativo invalidato: fuori pista. "
                "%d righe eliminate. Premi SHARE per ripartire." % discarded
            )

    def append(self, sensors, intention, gear):
        if not self.valid:
            return
        dataset_action = {
            "steer": intention["steer"],
            "accel": intention["accel"],
            "brake": intention["brake"],
            "gear": gear,
        }
        self.rows.append(legacy.build_dataset_row(sensors, dataset_action))

    def commit(self):
        if not self.valid or not self.rows:
            return 0

        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        temporary_path = self.path + ".tmp"
        existing = os.path.exists(self.path) and os.path.getsize(self.path) > 0

        with open(temporary_path, "w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=DATASET_COLUMNS)
            writer.writeheader()

            if existing:
                with open(self.path, newline="", encoding="utf-8") as input_file:
                    reader = csv.DictReader(input_file)
                    if reader.fieldnames != DATASET_COLUMNS:
                        raise ValueError(
                            "Il dataset esistente ha colonne incompatibili."
                        )
                    writer.writerows(reader)

            writer.writerows(self.rows)

        committed = len(self.rows)
        os.replace(temporary_path, self.path)
        self.rows = []
        return committed


def create_client():
    client = snakeoil3.Client(p=PORT, vision=False)
    client.get_servers_input()
    return client


def restart_client(client):
    try:
        if client is not None and getattr(client, "so", None) is not None:
            client.R.d["steer"] = 0.0
            client.R.d["accel"] = 0.0
            client.R.d["brake"] = 0.0
            client.R.d["gear"] = 1
            client.R.d["clutch"] = 0.0
            client.R.d["meta"] = 1
            client.respond_to_server()
            client.get_servers_input()
    finally:
        if client is not None:
            client.shutdown()

    return create_client()


def send_safe_stop(client):
    try:
        if client is None or getattr(client, "so", None) is None:
            return
        client.R.d.update(
            {
                "steer": 0.0,
                "accel": 0.0,
                "brake": 1.0,
                "gear": 1,
                "clutch": 0.0,
                "meta": 0,
            }
        )
        client.respond_to_server()
    except Exception:
        pass


def main():
    controller = None
    client = None
    dataset = TransactionalDataset()
    adas = SharedADAS()
    finish_detector = legacy.RaceFinishDetector()
    attempt_started_at = time.time()
    step = 0
    stop_reason = "unknown"

    try:
        controller = SupremePS4Controller()
        client = create_client()

        print("=" * 72)
        print(" crAIzy pilots - DUALSHOCK 4 DATASET CONTROLLER")
        print("=" * 72)
        print(" Stick sinistro = sterzo | R2 = gas | L2 = freno")
        print(" SHARE = scarta e riparti | OPTIONS x2 = scarta ed esci")
        print(" Dataset valido solo dopo un giro completo: %s" % DATASET_PATH)
        print("=" * 72)

        while controller.running:
            if client is None or getattr(client, "so", None) is None:
                stop_reason = "server_closed"
                break

            sensors = client.S.d
            elapsed = time.time() - attempt_started_at
            finished, finish_reason = finish_detector.update(sensors, elapsed)

            if finished:
                if dataset.valid:
                    committed = dataset.commit()
                    print(
                        "\n[GIRO COMPLETO] %d righe aggiunte a %s."
                        % (committed, DATASET_PATH)
                    )
                    stop_reason = "lap_complete"
                else:
                    print(
                        "\n[GIRO NON SALVATO] Tentativo invalido: %s."
                        % dataset.invalid_reason
                    )
                    stop_reason = "invalid_lap_complete"
                break

            intention = controller.intention()
            if controller.exit_requested or not controller.running:
                stop_reason = controller.stop_reason or "controller_exit"
                break

            if controller.restart_requested:
                dataset.discard("restart")
                adas.reset()
                finish_detector = legacy.RaceFinishDetector()
                attempt_started_at = time.time()
                step = 0
                client = restart_client(client)
                dataset.reset()
                controller.reset_requests()
                print("[RESTART] Nuovo tentativo pronto.")
                continue

            dataset.observe_track(sensors)
            action, diagnostics = adas.apply(sensors, intention)
            dataset.append(sensors, intention, action["gear"])
            client.R.d.update(action)
            client.respond_to_server()
            client.get_servers_input()
            step += 1

            if step % PRINT_EVERY == 0:
                sys.stdout.write(
                    "\rstep=%6d speed=%6.1f gear=%d steer=%6.3f "
                    "accel=%5.2f brake=%5.2f ABS=%4.2f TCS=%4.2f rows=%6d   "
                    % (
                        step,
                        legacy.safe_float(sensors.get("speedX")),
                        action["gear"],
                        action["steer"],
                        action["accel"],
                        action["brake"],
                        diagnostics["abs_release"],
                        diagnostics["traction_cut"],
                        len(dataset.rows),
                    )
                )
                sys.stdout.flush()

    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
        print("\n[CTRL+C] Tentativo scartato.")
    except RuntimeError as error:
        stop_reason = "controller_error"
        print("\n[ERRORE] %s" % error)
    finally:
        discarded = len(dataset.rows)
        dataset.rows = []
        send_safe_stop(client)
        if client is not None:
            client.shutdown()
        if controller is not None:
            controller.stop()
        print()
        print("Sessione terminata: %s" % stop_reason)
        if stop_reason != "lap_complete":
            print("Righe temporanee scartate: %d" % discarded)


if __name__ == "__main__":
    main()

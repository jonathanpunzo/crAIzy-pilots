import csv
import importlib.util
import os
import socket
import sys
import time
from pathlib import Path

from craizy_auto import DATASET_COLUMNS, PORT, SharedADAS


# ============================================================
# crAIzy pilots - DualShock 4 controller and dataset recorder
# ============================================================

LEGACY_CONTROLLER_PATH = Path(__file__).with_name(
    "controller_ps4_torcs_dataset_auto_stop_v2 (1).py"
)
DATASET_PATH = str(Path(__file__).with_name("torcs_ps4_dataset.csv"))

OFFTRACK_CONFIRM_TICKS = 10
OFFTRACK_TRACK_POS = 1.05
PRINT_EVERY = 50
SERVER_SILENCE_TIMEOUTS = 3
SERVER_FINISH_MIN_SECONDS = 45.0
SERVER_FINISH_MIN_DISTANCE = 3500.0
SERVER_FINISH_MIN_ROWS = 1000


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
        self.save_restart_requested = False
        self.exit_requested = False
        self.stop_reason = ""

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
        self.save_restart_requested = False
        self.exit_requested = False

    def process_events(self):
        self.restart_requested = False
        self.save_restart_requested = False

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
                self.save_restart_requested = False
                print("\n[SHARE] Tentativo scartato. Riavvio gara.")
                continue

            if event.button == OPTIONS_BUTTON:
                self.restart_requested = False
                self.save_restart_requested = True
                print("\n[OPTIONS] Salvo il tentativo e riavvio la gara.")

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


class RaceProgress:
    def __init__(self):
        self.max_dist_raced = 0.0
        self.max_dist_from_start = 0.0

    def observe(self, sensors):
        self.max_dist_raced = max(
            self.max_dist_raced,
            legacy.safe_float(sensors.get("distRaced", 0.0)),
        )
        self.max_dist_from_start = max(
            self.max_dist_from_start,
            legacy.safe_float(sensors.get("distFromStart", 0.0)),
        )

    def confirms_corkscrew_finish(self, elapsed, dataset):
        distance = max(self.max_dist_raced, self.max_dist_from_start)
        return (
            dataset.valid
            and len(dataset.rows) >= SERVER_FINISH_MIN_ROWS
            and elapsed >= SERVER_FINISH_MIN_SECONDS
            and distance >= SERVER_FINISH_MIN_DISTANCE
        )


def create_client():
    client = snakeoil3.Client(p=PORT, vision=False)
    client.get_servers_input()
    return client


def receive_server_input(client):
    """Receive one telemetry packet without waiting forever after the race."""
    if client is None or getattr(client, "so", None) is None:
        return "closed"

    timeouts = 0
    while timeouts < SERVER_SILENCE_TIMEOUTS:
        try:
            sockdata, _ = client.so.recvfrom(snakeoil3.data_size)
            sockdata = sockdata.decode("utf-8")
        except socket.timeout:
            timeouts += 1
            print(".", end=" ", flush=True)
            continue
        except OSError:
            client.shutdown()
            return "socket_error"

        if "***identified***" in sockdata:
            continue
        if "***shutdown***" in sockdata:
            print(
                "\nServer TORCS ha terminato la gara sulla porta %d."
                % client.port
            )
            client.shutdown()
            return "shutdown"
        if "***restart***" in sockdata:
            print("\nServer TORCS ha riavviato la gara sulla porta %d." % client.port)
            client.shutdown()
            return "restart"
        if not sockdata:
            continue

        client.S.parse_server_str(sockdata)
        return "data"

    return "timeout"


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
    race_progress = RaceProgress()
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
        print(" SHARE = scarta e riparti | OPTIONS = salva e riparti")
        print(" Ctrl+C = scarta il tentativo ed esce")
        print(" Dataset: %s" % DATASET_PATH)
        print("=" * 72)

        while controller.running:
            if client is None or getattr(client, "so", None) is None:
                stop_reason = "server_closed"
                break

            sensors = client.S.d
            elapsed = time.time() - attempt_started_at
            race_progress.observe(sensors)
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

            if (
                controller.restart_requested
                or controller.save_restart_requested
            ):
                if controller.save_restart_requested:
                    if dataset.valid and dataset.rows:
                        committed = dataset.commit()
                        print(
                            "[OPTIONS] %d righe aggiunte a %s."
                            % (committed, DATASET_PATH)
                        )
                    else:
                        print(
                            "[OPTIONS] Nessun dato salvato: tentativo %s."
                            % (
                                dataset.invalid_reason
                                if not dataset.valid
                                else "vuoto"
                            )
                        )
                else:
                    discarded = dataset.discard("share_restart")
                    print("[SHARE] %d righe temporanee eliminate." % discarded)

                adas.reset()
                finish_detector = legacy.RaceFinishDetector()
                race_progress = RaceProgress()
                attempt_started_at = time.time()
                step = 0
                client = restart_client(client)
                dataset.reset()
                controller.reset_requests()
                print("[RESTART] Pista e registrazione riavviate.")
                continue

            dataset.observe_track(sensors)
            action, diagnostics = adas.apply(sensors, intention)
            dataset.append(sensors, intention, action["gear"])
            client.R.d.update(action)
            client.respond_to_server()
            receive_status = receive_server_input(client)
            step += 1

            if receive_status != "data":
                elapsed = time.time() - attempt_started_at
                if race_progress.confirms_corkscrew_finish(elapsed, dataset):
                    committed = dataset.commit()
                    print(
                        "\n[GIRO COMPLETO] %d righe aggiunte a %s."
                        % (committed, DATASET_PATH)
                    )
                    print(
                        "[GIRO COMPLETO] Confermato dalla fine del server "
                        "dopo %.0f m." % max(
                            race_progress.max_dist_raced,
                            race_progress.max_dist_from_start,
                        )
                    )
                    stop_reason = "lap_complete_server_" + receive_status
                else:
                    stop_reason = "server_" + receive_status
                break

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
        if not stop_reason.startswith("lap_complete"):
            print("Righe temporanee scartate: %d" % discarded)


if __name__ == "__main__":
    main()

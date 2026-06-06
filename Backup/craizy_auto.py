import csv
import json
import math
import os
import time

import torcs_jm_par_modulare as legacy_auto


# ============================================================
# crAIzy pilots - automatic driver and shared driving assists
# ============================================================

PORT = 3001
MAX_STEPS = 100000

DATASET_PATH = os.path.join("data", "torcs_ps4_dataset.csv")
AUTO_RESULTS_PATH = os.path.join("results", "auto_runs.csv")

PROFILE_BIN_METERS = 5.0
PROFILE_BLEND = 0.35
PROFILE_ANGLE_TOLERANCE = 0.18
PROFILE_TRACK_POS_TOLERANCE = 0.35
PROFILE_SPEED_TOLERANCE = 55.0

WHEEL_RADII = (0.3306, 0.3306, 0.3276, 0.3276)

STEER_SMOOTHING = 0.16
PEDAL_SMOOTHING = 0.20
MAX_STEER_LOW_SPEED = 0.92
MAX_STEER_HIGH_SPEED = 0.24
SPEED_FOR_MIN_STEER = 175.0

THROTTLE_STEER_START = 0.35
THROTTLE_STEER_FULL = 0.70
THROTTLE_STEER_MIN_ACCEL = 0.45

ABS_MIN_SPEED_KMH = 10.0
ABS_SLIP_START_MPS = 2.0
ABS_SLIP_FULL_MPS = 6.0
ABS_MAX_RELEASE = 0.75

TCS_SLIP_START_MPS = 2.0
TCS_SLIP_FULL_MPS = 8.0
TCS_MAX_CUT = 0.65

SHIFT_COOLDOWN = 0.35
UPSHIFT_RPM = 7600.0
DOWNSHIFT_RPM = 3300.0
PANIC_DOWNSHIFT_RPM = 2300.0
UPSHIFT_SPEED = {1: 45.0, 2: 78.0, 3: 112.0, 4: 148.0, 5: 184.0}
DOWNSHIFT_SPEED = {2: 30.0, 3: 58.0, 4: 90.0, 5: 122.0, 6: 155.0}
MIN_SPEED_FOR_UPSHIFT = {1: 22.0, 2: 48.0, 3: 78.0, 4: 110.0, 5: 145.0}

DATASET_COLUMNS = [
    "steer", "accel", "brake", "gear",
    "speedX", "speedY", "speedZ",
    "wheelSpinVel", "z", "track", "trackPos", "angle",
    "rpm", "damage", "distFromStart",
]


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def safe_float(value, default=0.0):
    try:
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except Exception:
        return default


def safe_list(value, length, default_value=0.0):
    if not isinstance(value, (list, tuple)):
        return [default_value] * length

    values = [safe_float(item, default_value) for item in value[:length]]
    if len(values) < length:
        values += [default_value] * (length - len(values))
    return values


def linear_limit(value, start, full, minimum):
    value = abs(value)
    if value <= start:
        return 1.0
    if value >= full:
        return minimum
    ratio = (value - start) / max(full - start, 0.0001)
    return 1.0 + (minimum - 1.0) * ratio


class AutomaticGearbox:
    def __init__(self):
        self.gear = 1
        self.last_shift_time = 0.0

    def reset(self):
        self.gear = 1
        self.last_shift_time = 0.0

    def update(self, sensors):
        now = time.monotonic()
        speed = abs(safe_float(sensors.get("speedX")))
        rpm = safe_float(sensors.get("rpm"))
        current = int(clamp(self.gear, 1, 6))

        if now - self.last_shift_time < SHIFT_COOLDOWN:
            return current

        new_gear = current
        if current > 1:
            too_slow = speed < DOWNSHIFT_SPEED.get(current, 0.0)
            rpm_too_low = 0.0 < rpm < PANIC_DOWNSHIFT_RPM
            rpm_low_and_slow = (
                0.0 < rpm < DOWNSHIFT_RPM
                and speed < DOWNSHIFT_SPEED.get(current, 0.0) + 12.0
            )
            if too_slow or rpm_too_low or rpm_low_and_slow:
                new_gear = current - 1

        if new_gear == current and current < 6:
            enough_speed = speed >= MIN_SPEED_FOR_UPSHIFT.get(current, 999.0)
            if (rpm >= UPSHIFT_RPM and enough_speed) or speed >= UPSHIFT_SPEED.get(current, 999.0):
                new_gear = current + 1

        new_gear = int(clamp(new_gear, 1, 6))
        if new_gear != current:
            self.last_shift_time = now
        self.gear = new_gear
        return new_gear


class SharedADAS:
    """Applies the same physical assists to human and automatic intentions."""

    def __init__(self):
        self.gearbox = AutomaticGearbox()
        self.reset()

    def reset(self):
        self.steer = 0.0
        self.accel = 0.0
        self.brake = 0.0
        self.gearbox.reset()

    def apply(self, sensors, intent):
        speed = abs(safe_float(sensors.get("speedX")))
        target_steer = clamp(safe_float(intent.get("steer")), -1.0, 1.0)
        target_accel = clamp(safe_float(intent.get("accel")), 0.0, 1.0)
        target_brake = clamp(safe_float(intent.get("brake")), 0.0, 1.0)

        speed_ratio = clamp(speed / SPEED_FOR_MIN_STEER, 0.0, 1.0)
        steer_limit = (
            MAX_STEER_LOW_SPEED
            + (MAX_STEER_HIGH_SPEED - MAX_STEER_LOW_SPEED) * speed_ratio
        )
        target_steer = clamp(target_steer, -steer_limit, steer_limit)

        throttle_limit = linear_limit(
            target_steer,
            THROTTLE_STEER_START,
            THROTTLE_STEER_FULL,
            THROTTLE_STEER_MIN_ACCEL,
        )
        target_accel *= throttle_limit

        self.steer += STEER_SMOOTHING * (target_steer - self.steer)
        self.accel += PEDAL_SMOOTHING * (target_accel - self.accel)
        self.brake += PEDAL_SMOOTHING * (target_brake - self.brake)
        output_accel = self.accel
        output_brake = self.brake

        wheel_spin = safe_list(sensors.get("wheelSpinVel"), 4)
        wheel_speed = [
            abs(wheel_spin[index]) * WHEEL_RADII[index]
            for index in range(4)
        ]
        vehicle_speed = speed / 3.6
        mean_wheel_speed = sum(wheel_speed) / len(wheel_speed)
        driven_wheel_speed = (wheel_speed[2] + wheel_speed[3]) / 2.0

        abs_slip = max(0.0, vehicle_speed - mean_wheel_speed)
        abs_release = 0.0
        if speed >= ABS_MIN_SPEED_KMH and abs_slip > ABS_SLIP_START_MPS:
            abs_release = clamp(
                (abs_slip - ABS_SLIP_START_MPS)
                / max(ABS_SLIP_FULL_MPS - ABS_SLIP_START_MPS, 0.001),
                0.0,
                1.0,
            ) * ABS_MAX_RELEASE
            output_brake *= 1.0 - abs_release

        traction_slip = max(0.0, driven_wheel_speed - vehicle_speed)
        traction_cut = 0.0
        if traction_slip > TCS_SLIP_START_MPS:
            traction_cut = clamp(
                (traction_slip - TCS_SLIP_START_MPS)
                / max(TCS_SLIP_FULL_MPS - TCS_SLIP_START_MPS, 0.001),
                0.0,
                1.0,
            ) * TCS_MAX_CUT
            output_accel *= 1.0 - traction_cut

        if target_brake > 0.05 or output_brake > 0.05:
            output_accel = 0.0

        action = {
            "steer": clamp(self.steer, -1.0, 1.0),
            "accel": clamp(output_accel, 0.0, 1.0),
            "brake": clamp(output_brake, 0.0, 1.0),
            "gear": self.gearbox.update(sensors),
            "clutch": 0.0,
            "meta": 0,
        }
        diagnostics = {
            "steer_limit": steer_limit,
            "abs_slip": abs_slip,
            "abs_release": abs_release,
            "traction_slip": traction_slip,
            "traction_cut": traction_cut,
        }
        return action, diagnostics


class ExpertProfile:
    def __init__(self, path=DATASET_PATH):
        self.path = path
        self.bins = {}
        self.rows = 0
        self.load()

    @property
    def available(self):
        return bool(self.bins)

    def load(self):
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            return

        totals = {}
        try:
            with open(self.path, newline="", encoding="utf-8") as dataset_file:
                reader = csv.DictReader(dataset_file)
                if reader.fieldnames != DATASET_COLUMNS:
                    print("[DATASET] Schema non compatibile, profilo umano disattivato.")
                    return

                for row in reader:
                    track_pos = safe_float(row.get("trackPos"))
                    if abs(track_pos) > 1.0:
                        continue

                    distance = max(0.0, safe_float(row.get("distFromStart")))
                    bin_id = int(distance // PROFILE_BIN_METERS)
                    values = totals.setdefault(
                        bin_id,
                        {
                            "count": 0,
                            "steer": 0.0,
                            "accel": 0.0,
                            "brake": 0.0,
                            "speedX": 0.0,
                            "angle": 0.0,
                            "trackPos": 0.0,
                        },
                    )
                    values["count"] += 1
                    for key in ("steer", "accel", "brake", "speedX", "angle", "trackPos"):
                        values[key] += safe_float(row.get(key))
                    self.rows += 1
        except (OSError, csv.Error) as error:
            print("[DATASET] Impossibile leggere il profilo umano: %s" % error)
            return

        for bin_id, values in totals.items():
            count = values["count"]
            if count < 2:
                continue
            self.bins[bin_id] = {
                key: values[key] / count
                for key in ("steer", "accel", "brake", "speedX", "angle", "trackPos")
            }

    def intention(self, sensors):
        if not self.available:
            return None

        distance = max(0.0, safe_float(sensors.get("distFromStart")))
        bin_id = int(distance // PROFILE_BIN_METERS)
        reference = self.bins.get(bin_id)
        if reference is None:
            return None

        angle_error = abs(safe_float(sensors.get("angle")) - reference["angle"])
        position_error = abs(safe_float(sensors.get("trackPos")) - reference["trackPos"])
        speed_error = abs(safe_float(sensors.get("speedX")) - reference["speedX"])

        if (
            angle_error > PROFILE_ANGLE_TOLERANCE
            or position_error > PROFILE_TRACK_POS_TOLERANCE
            or speed_error > PROFILE_SPEED_TOLERANCE
        ):
            return None

        return {
            "steer": reference["steer"],
            "accel": reference["accel"],
            "brake": reference["brake"],
        }


class AutomaticPolicy:
    def __init__(self):
        self.previous = {"steer": 0.0, "accel": 0.2, "brake": 0.0}

    def intention(self, sensors):
        track_info = legacy_auto.analyze_track(sensors)
        steer = legacy_auto.calculate_steering(sensors, track_info)
        brake = legacy_auto.apply_brakes(sensors, track_info)
        working = self.previous.copy()
        working["steer"] = steer
        working["brake"] = brake
        accel = legacy_auto.calculate_throttle(sensors, working, track_info)

        self.previous = {"steer": steer, "accel": accel, "brake": brake}
        return self.previous.copy(), track_info


def blend_intentions(base_intent, expert_intent):
    if expert_intent is None:
        return base_intent, False

    blended = {}
    for key in ("steer", "accel", "brake"):
        blended[key] = (
            base_intent[key] * (1.0 - PROFILE_BLEND)
            + expert_intent[key] * PROFILE_BLEND
        )
    return blended, True


class RunSummary:
    FIELDS = [
        "timestamp", "driver_version", "dataset_rows", "profile_bins",
        "profile_steps", "steps", "elapsed_s", "lap_time",
        "avg_speed", "max_speed", "final_damage", "offtrack_steps",
        "abs_steps", "tcs_steps", "reason",
    ]

    def __init__(self, profile):
        self.profile = profile
        self.start_time = time.time()
        self.steps = 0
        self.profile_steps = 0
        self.speed_sum = 0.0
        self.max_speed = 0.0
        self.offtrack_steps = 0
        self.abs_steps = 0
        self.tcs_steps = 0
        self.final_sensors = {}

    def record(self, sensors, diagnostics, used_profile):
        speed = safe_float(sensors.get("speedX"))
        track = safe_list(sensors.get("track"), 19, 200.0)
        self.steps += 1
        self.profile_steps += int(used_profile)
        self.speed_sum += speed
        self.max_speed = max(self.max_speed, speed)
        self.offtrack_steps += int(
            abs(safe_float(sensors.get("trackPos"))) > 1.0 or min(track) < 0.0
        )
        self.abs_steps += int(diagnostics["abs_release"] > 0.0)
        self.tcs_steps += int(diagnostics["traction_cut"] > 0.0)
        self.final_sensors = sensors.copy()

    def write(self, reason):
        os.makedirs(os.path.dirname(AUTO_RESULTS_PATH), exist_ok=True)
        row = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "driver_version": legacy_auto.DRIVER_VERSION,
            "dataset_rows": self.profile.rows,
            "profile_bins": len(self.profile.bins),
            "profile_steps": self.profile_steps,
            "steps": self.steps,
            "elapsed_s": round(time.time() - self.start_time, 3),
            "lap_time": round(safe_float(self.final_sensors.get("lastLapTime")), 3),
            "avg_speed": round(self.speed_sum / self.steps, 3) if self.steps else 0.0,
            "max_speed": round(self.max_speed, 3),
            "final_damage": round(safe_float(self.final_sensors.get("damage")), 3),
            "offtrack_steps": self.offtrack_steps,
            "abs_steps": self.abs_steps,
            "tcs_steps": self.tcs_steps,
            "reason": reason,
        }
        file_exists = os.path.exists(AUTO_RESULTS_PATH) and os.path.getsize(AUTO_RESULTS_PATH) > 0
        with open(AUTO_RESULTS_PATH, "a", newline="", encoding="utf-8") as result_file:
            writer = csv.DictWriter(result_file, fieldnames=self.FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)


def main():
    profile = ExpertProfile()
    policy = AutomaticPolicy()
    adas = SharedADAS()
    summary = RunSummary(profile)
    client = legacy_auto.Client(p=PORT)
    reason = "max_steps"

    if profile.available:
        print("[DATASET] Profilo umano attivo: %d righe, %d settori." % (
            profile.rows,
            len(profile.bins),
        ))
    else:
        print("[DATASET] Nessun profilo valido: guida automatica base.")

    try:
        for _ in range(MAX_STEPS):
            client.get_servers_input()
            if not client.so:
                reason = "server_closed"
                break

            sensors = client.S.d
            if safe_float(sensors.get("lastLapTime")) > 0.0:
                reason = "lap_complete"
                break

            base_intent, _ = policy.intention(sensors)
            expert_intent = profile.intention(sensors)
            intent, used_profile = blend_intentions(base_intent, expert_intent)
            action, diagnostics = adas.apply(sensors, intent)
            client.R.d.update(action)
            summary.record(sensors, diagnostics, used_profile)
            client.respond_to_server()
    except KeyboardInterrupt:
        reason = "keyboard_interrupt"
    finally:
        summary.write(reason)
        client.shutdown()
        print("Risultato salvato in %s" % AUTO_RESULTS_PATH)


if __name__ == "__main__":
    main()

import unittest
from pathlib import Path

from src.driver import DriverConfig, TorcsAIDriver, load_config
from src.driver.gears import Gearbox
from src.driver.steering import SteeringController


def base_sensors(**overrides):
    sensors = {
        "angle": 0.0,
        "trackPos": 0.0,
        "speedX": 80.0,
        "speedY": 0.0,
        "speedZ": 0.0,
        "rpm": 5200.0,
        "gear": 2.0,
        "damage": 0.0,
        "track": [120.0] * 19,
        "wheelSpinVel": [30.0, 30.0, 31.0, 31.0],
        "opponents": [200.0] * 36,
        "z": 0.35,
    }
    sensors.update(overrides)
    return sensors


class DriverLogicTest(unittest.TestCase):
    def test_best_lap_config_loads(self):
        config = load_config(Path("configs") / "best_lap.json")
        self.assertEqual(config.name, "best_lap")
        self.assertGreater(config.target_speed, 150)

    def test_actions_stay_in_protocol_limits(self):
        driver = TorcsAIDriver(DriverConfig())
        action = driver.update(base_sensors(angle=0.15, trackPos=0.2))
        self.assertGreaterEqual(action["steer"], -1.0)
        self.assertLessEqual(action["steer"], 1.0)
        self.assertGreaterEqual(action["accel"], 0.0)
        self.assertLessEqual(action["accel"], 1.0)
        self.assertGreaterEqual(action["brake"], 0.0)
        self.assertLessEqual(action["brake"], 1.0)
        self.assertIn(action["gear"], [1, 2, 3, 4, 5, 6])

    def test_offtrack_recovery_limits_speed_and_steers_to_center(self):
        driver = TorcsAIDriver(DriverConfig())
        action = driver.update(base_sensors(trackPos=1.25, speedX=55.0))
        self.assertEqual(driver.last_info["mode"], "offtrack_recovery")
        self.assertLessEqual(action["accel"], 0.35)
        self.assertLess(action["steer"], 0.0)

    def test_high_speed_uses_high_gear(self):
        driver = TorcsAIDriver(DriverConfig())
        action = driver.update(base_sensors(speedX=190.0, rpm=7000.0, gear=4.0))
        self.assertGreaterEqual(action["gear"], 5)

    def test_mid_speed_does_not_drop_back_to_first(self):
        config = load_config(Path("configs") / "best_lap.json")
        gearbox = Gearbox(config)
        first = gearbox.update(base_sensors(speedX=56.0, rpm=6500.0, gear=1.0))
        second = gearbox.update(base_sensors(speedX=56.0, rpm=6500.0, gear=2.0))
        self.assertGreaterEqual(first, 2)
        self.assertGreaterEqual(second, 2)

    def test_low_speed_recovers_from_high_gear(self):
        config = load_config(Path("configs") / "best_lap.json")
        gearbox = Gearbox(config)
        gear = gearbox.update(base_sensors(speedX=36.0, rpm=5235.0, gear=6.0))
        self.assertLessEqual(gear, 3)

    def test_high_speed_steering_is_rate_limited(self):
        config = load_config(Path("configs") / "best_lap.json")
        steering = SteeringController(config)
        first = steering.update(base_sensors(speedX=155.0, speedY=7.0, angle=0.09, trackPos=-0.01))
        second = steering.update(base_sensors(speedX=155.0, speedY=-13.0, angle=-0.14, trackPos=0.0))
        self.assertLess(abs(first), 0.2)
        self.assertLess(abs(second - first), 0.05)

    def test_front_opponent_guard_adds_braking(self):
        driver = TorcsAIDriver(DriverConfig(opponent_enabled=True, opponent_distance=20.0))
        opponents = [200.0] * 36
        opponents[18] = 8.0
        action = driver.update(base_sensors(opponents=opponents))
        self.assertTrue(driver.last_info["opponent_guard"])
        self.assertGreaterEqual(action["brake"], driver.config.opponent_brake)


if __name__ == "__main__":
    unittest.main()

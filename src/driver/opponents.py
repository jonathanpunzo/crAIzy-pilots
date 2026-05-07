from __future__ import annotations

from .config import DriverConfig
from .math_utils import clamp
from .sensors import opponents


class OpponentGuard:
    def __init__(self, config: DriverConfig) -> None:
        self.config = config

    def apply(self, action: dict[str, float | int], sensors: dict[str, object]) -> tuple[dict[str, float | int], bool]:
        if not self.config.opponent_enabled:
            return action, False

        values = opponents(sensors)
        front_arc = values[16:21]
        closest_front = min(front_arc) if front_arc else 200.0
        if closest_front >= self.config.opponent_distance:
            return action, False

        action["accel"] = min(float(action.get("accel", 0.0)), 0.45)
        action["brake"] = max(float(action.get("brake", 0.0)), self.config.opponent_brake)
        action["steer"] = clamp(float(action.get("steer", 0.0)), -0.55, 0.55)
        return action, True


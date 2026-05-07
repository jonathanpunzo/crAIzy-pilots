from __future__ import annotations

import math

from .config import DriverConfig
from .math_utils import clamp, mean
from .sensors import sensor, track


class SteeringController:
    def __init__(self, config: DriverConfig) -> None:
        self.config = config
        self.previous = 0.0

    def update(self, sensors: dict[str, object]) -> float:
        values = track(sensors)
        angle = sensor(sensors, "angle")
        track_pos = sensor(sensors, "trackPos")
        speed_y = sensor(sensors, "speedY")

        left_clearance = mean(values[:8])
        right_clearance = mean(values[11:])
        clearance_total = max(left_clearance + right_clearance, 1.0)
        curve_bias = (left_clearance - right_clearance) / clearance_total

        raw = (angle * self.config.steer_gain / math.pi)
        raw -= track_pos * self.config.centering_gain
        raw += curve_bias * self.config.curve_gain
        raw -= speed_y * self.config.lateral_steer_damping

        speed = max(sensor(sensors, "speedX"), 0.0)
        speed_limit = clamp(0.80 - speed / 265.0, self.config.high_speed_steer_floor, 1.0)
        target = clamp(raw, -speed_limit, speed_limit)

        speed_ratio = clamp(speed / 160.0, 0.0, 1.0)
        max_delta = (
            self.config.steer_rate_low_speed * (1.0 - speed_ratio)
            + self.config.steer_rate_high_speed * speed_ratio
        )
        delta = clamp(target - self.previous, -max_delta, max_delta)
        self.previous = clamp(self.previous + delta, -speed_limit, speed_limit)
        return self.previous

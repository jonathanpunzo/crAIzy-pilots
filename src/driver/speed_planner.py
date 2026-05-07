from __future__ import annotations

from .config import DriverConfig
from .math_utils import clamp, mean
from .sensors import sensor, track


class SpeedPlanner:
    def __init__(self, config: DriverConfig) -> None:
        self.config = config

    def target_speed(self, sensors: dict[str, object], steer: float) -> tuple[float, float]:
        values = track(sensors)
        front = values[9]
        near_front = mean(values[7:12])
        left = mean(values[:8])
        right = mean(values[11:])

        front_pressure = clamp((120.0 - min(front, near_front)) / 120.0, 0.0, 1.0)
        side_pressure = clamp(abs(left - right) / max(left + right, 1.0), 0.0, 1.0)
        steer_pressure = clamp(
            (abs(steer) - self.config.brake_threshold) / max(1.0 - self.config.brake_threshold, 0.05),
            0.0,
            1.0,
        )
        lateral_pressure = clamp(abs(sensor(sensors, "speedY")) / 35.0, 0.0, 1.0)
        offtrack_pressure = 1.0 if abs(sensor(sensors, "trackPos")) > 0.88 else 0.0

        corner_pressure = clamp(
            front_pressure * 0.52
            + side_pressure * 0.18
            + steer_pressure * 0.18
            + lateral_pressure * 0.08
            + offtrack_pressure * 0.04,
            0.0,
            1.0,
        )

        openness = clamp((near_front - 65.0) / 135.0, 0.0, 1.0)
        cruise_target = self.config.target_speed + (self.config.max_speed - self.config.target_speed) * openness
        span = cruise_target - self.config.min_corner_speed
        target = cruise_target - span * corner_pressure * 0.72
        target -= abs(sensor(sensors, "speedY")) * self.config.lateral_speed_gain
        target -= abs(sensor(sensors, "trackPos")) * 12.0
        target = clamp(target, self.config.min_corner_speed, self.config.max_speed)

        if abs(sensor(sensors, "trackPos")) > 1.0:
            target = min(target, self.config.offtrack_speed)

        return target, corner_pressure

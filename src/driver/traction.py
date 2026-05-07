from __future__ import annotations

from .config import DriverConfig
from .math_utils import clamp
from .sensors import sensor, wheel_spin


class TractionController:
    def __init__(self, config: DriverConfig) -> None:
        self.config = config

    def apply(self, sensors: dict[str, object], accel: float) -> tuple[float, float]:
        if not self.config.traction_enabled:
            return clamp(accel, 0.0, 1.0), 0.0

        wheels = wheel_spin(sensors)
        front = wheels[0] + wheels[1]
        rear = wheels[2] + wheels[3]
        slip = rear - front

        if slip > self.config.slip_threshold:
            accel -= self.config.traction_cut * clamp(slip / 12.0, 0.7, 2.5)

        lateral_speed = abs(sensor(sensors, "speedY"))
        if lateral_speed > 18.0:
            accel -= clamp((lateral_speed - 18.0) / 35.0, 0.0, 0.35)

        speed = sensor(sensors, "speedX")
        rpm = sensor(sensors, "rpm")
        gear = int(sensor(sensors, "gear", 1))
        if speed < self.config.launch_speed:
            launch_ratio = clamp(speed / max(self.config.launch_speed, 1.0), 0.0, 1.0)
            launch_cap = self.config.launch_accel + launch_ratio * 0.22
            accel = min(accel, launch_cap)
        if gear <= 2 and speed < 85.0:
            accel = min(accel, self.config.low_gear_accel)
        if rpm > self.config.upshift_rpm + 900 and gear <= 2:
            accel = min(accel, self.config.rpm_accel_cut)

        return clamp(accel, 0.0, 1.0), slip

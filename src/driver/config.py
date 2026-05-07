from __future__ import annotations

from dataclasses import dataclass, fields
import json
from pathlib import Path
from typing import Any


@dataclass
class DriverConfig:
    name: str = "default"
    target_speed: float = 130.0
    max_speed: float = 185.0
    min_corner_speed: float = 52.0
    steer_gain: float = 15.0
    centering_gain: float = 0.37
    curve_gain: float = 0.20
    lateral_steer_damping: float = 0.012
    steer_smoothing: float = 0.42
    steer_rate_low_speed: float = 0.085
    steer_rate_high_speed: float = 0.028
    high_speed_steer_floor: float = 0.18
    pedal_smoothing: float = 0.50
    brake_threshold: float = 0.40
    brake_strength: float = 0.64
    lateral_speed_gain: float = 1.45
    traction_enabled: bool = True
    slip_threshold: float = 4.8
    traction_cut: float = 0.19
    gear_speeds: tuple[float, float, float, float, float, float] = (0, 38, 78, 122, 168, 218)
    upshift_rpm: float = 7800.0
    downshift_rpm: float = 3000.0
    gear_hysteresis: float = 18.0
    launch_speed: float = 42.0
    launch_accel: float = 0.58
    low_gear_accel: float = 0.72
    rpm_accel_cut: float = 0.28
    offtrack_speed: float = 38.0
    stuck_speed_threshold: float = 4.5
    stuck_angle_threshold: float = 0.80
    stuck_steps: int = 78
    reverse_steps: int = 40
    recovery_steer_gain: float = 0.75
    opponent_enabled: bool = True
    opponent_distance: float = 16.0
    opponent_brake: float = 0.20
    log_every: int = 1

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DriverConfig":
        allowed = {field.name for field in fields(cls)}
        values = {key: value for key, value in raw.items() if key in allowed}
        if "gear_speeds" in values:
            values["gear_speeds"] = tuple(values["gear_speeds"])
        return cls(**values)


def load_config(path: str | Path | None) -> DriverConfig:
    if path is None:
        return DriverConfig()
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return DriverConfig.from_dict(raw)

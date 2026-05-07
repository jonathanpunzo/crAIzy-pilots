from __future__ import annotations

from .math_utils import safe_float, safe_list


def sensor(sensors: dict[str, object], name: str, default: float = 0.0) -> float:
    return safe_float(sensors.get(name), default)


def track(sensors: dict[str, object]) -> list[float]:
    values = safe_list(sensors.get("track"), 19, 200.0)
    return [200.0 if value < 0 else value for value in values]


def opponents(sensors: dict[str, object]) -> list[float]:
    return safe_list(sensors.get("opponents"), 36, 200.0)


def wheel_spin(sensors: dict[str, object]) -> list[float]:
    return safe_list(sensors.get("wheelSpinVel"), 4, 0.0)


from __future__ import annotations

from collections.abc import Iterable


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def lerp(current: float, target: float, rate: float) -> float:
    rate = clamp(rate, 0.0, 1.0)
    return current + (target - current) * rate


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_list(value: object, length: int, default: float) -> list[float]:
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        items = [safe_float(item, default) for item in value]
    else:
        items = []
    if len(items) >= length:
        return items[:length]
    return items + [default] * (length - len(items))


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


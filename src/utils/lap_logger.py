from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a TORCS telemetry CSV")
    parser.add_argument("csv", help="Telemetry CSV path")
    args = parser.parse_args()

    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit(f"Missing pandas dependency: {exc}") from exc

    data = pd.read_csv(args.csv)
    summary = {
        "rows": len(data),
        "max_speed": data.get("speedX", []).max(),
        "max_damage": data.get("damage", []).max(),
        "last_lap_time_min": data.get("lastLapTime", []).replace(0, float("nan")).min(),
        "offtrack_samples": int((data.get("trackPos", 0).abs() > 1).sum()),
        "recovery_samples": int((data.get("mode", "") != "normal").sum()),
    }
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()


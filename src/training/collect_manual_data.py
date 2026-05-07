from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare telemetry rows for behavioral cloning")
    parser.add_argument("--input", required=True, help="Telemetry CSV collected from a manual/expert run")
    parser.add_argument("--output", default="data/manual_dataset.csv", help="Clean dataset output")
    args = parser.parse_args()

    try:
        import pandas as pd
    except ImportError as exc:
        raise SystemExit(f"Missing pandas dependency: {exc}") from exc

    keep = [
        "angle",
        "trackPos",
        "speedX",
        "speedY",
        "speedZ",
        "rpm",
        "damage",
        "steer",
        "accel",
        "brake",
    ]
    data = pd.read_csv(args.input)
    aliases = {
        "steer": "cmd_steer",
        "accel": "cmd_accel",
        "brake": "cmd_brake",
    }
    for canonical, alias in aliases.items():
        if canonical not in data.columns and alias in data.columns:
            data[canonical] = data[alias]
    missing = [column for column in keep if column not in data.columns]
    if missing:
        raise SystemExit(f"Missing columns: {', '.join(missing)}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    data[keep].dropna().to_csv(output, index=False)
    print(f"Dataset written: {output}")


if __name__ == "__main__":
    main()

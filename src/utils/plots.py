from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create diagnostic plots from telemetry CSV")
    parser.add_argument("csv", help="Telemetry CSV path")
    parser.add_argument("--output-dir", default="results/plots", help="Plot output directory")
    args = parser.parse_args()

    try:
        import matplotlib.pyplot as plt
        import pandas as pd
    except ImportError as exc:
        raise SystemExit(f"Missing plotting dependency: {exc}") from exc

    data = pd.read_csv(args.csv)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    plots = [
        ("speedX", "speed.png"),
        ("trackPos", "track_position.png"),
        ("steer", "steer.png"),
        ("accel", "accel.png"),
        ("brake", "brake.png"),
        ("corner_pressure", "corner_pressure.png"),
    ]
    for column, filename in plots:
        if column not in data:
            continue
        plt.figure(figsize=(10, 4))
        plt.plot(data["step"], data[column])
        plt.title(column)
        plt.xlabel("step")
        plt.tight_layout()
        plt.savefig(outdir / filename)
        plt.close()
    print(f"Plots written to {outdir}")


if __name__ == "__main__":
    main()


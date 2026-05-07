from __future__ import annotations

import argparse
import pickle
from pathlib import Path


FEATURES = ["angle", "trackPos", "speedX", "speedY", "speedZ", "rpm", "damage"]
TARGETS = ["steer", "accel", "brake"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a behavioral cloning baseline from telemetry CSV")
    parser.add_argument("--input", required=True, help="CSV file with sensor/action rows")
    parser.add_argument("--output", default="results/models/behavioral_cloning.pkl", help="Output pickle path")
    parser.add_argument("--neighbors", type=int, default=7, help="K-NN neighbors")
    args = parser.parse_args()

    try:
        import pandas as pd
        from sklearn.neighbors import KNeighborsRegressor
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise SystemExit(f"Missing ML dependency: {exc}") from exc

    data = pd.read_csv(args.input).dropna(subset=FEATURES + TARGETS)
    if data.empty:
        raise SystemExit("No usable rows found in input CSV.")

    model = make_pipeline(
        StandardScaler(),
        KNeighborsRegressor(n_neighbors=args.neighbors, weights="distance"),
    )
    model.fit(data[FEATURES], data[TARGETS])

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        pickle.dump({"model": model, "features": FEATURES, "targets": TARGETS}, handle)

    print(f"Trained behavioral cloning model on {len(data)} rows: {output}")


if __name__ == "__main__":
    main()


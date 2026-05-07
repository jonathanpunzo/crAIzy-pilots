from __future__ import annotations

import argparse
import pickle


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a behavioral cloning model on telemetry CSV")
    parser.add_argument("--model", required=True, help="Pickle produced by behavioral_cloning.py")
    parser.add_argument("--input", required=True, help="CSV file with sensor/action rows")
    args = parser.parse_args()

    try:
        import pandas as pd
        from sklearn.metrics import mean_absolute_error, mean_squared_error
    except ImportError as exc:
        raise SystemExit(f"Missing ML dependency: {exc}") from exc

    with open(args.model, "rb") as handle:
        bundle = pickle.load(handle)

    data = pd.read_csv(args.input).dropna(subset=bundle["features"] + bundle["targets"])
    predictions = bundle["model"].predict(data[bundle["features"]])

    mae = mean_absolute_error(data[bundle["targets"]], predictions)
    mse = mean_squared_error(data[bundle["targets"]], predictions)
    print(f"Rows: {len(data)}")
    print(f"MAE: {mae:.5f}")
    print(f"MSE: {mse:.5f}")


if __name__ == "__main__":
    main()


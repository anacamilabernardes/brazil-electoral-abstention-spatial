"""Small command-line entry point for data-contract verification."""

import argparse
import pandas as pd
from .core import validate_municipal_panel, historical_round_change


def main():
    parser = argparse.ArgumentParser(description="Electoral abstention research CLI")
    parser.add_argument("--panel", help="Normalized municipal panel CSV (IBGE codes as strings)")
    parser.add_argument("--historical-year", type=int, default=2022)
    parser.add_argument("--target-year", type=int, default=2026)
    parser.add_argument("--output", help="Optional CSV for illustrative baseline results")
    args = parser.parse_args()
    if not args.panel:
        parser.print_help()
        return
    panel = pd.read_csv(args.panel, dtype={"municipality_code": "string"})
    checked = validate_municipal_panel(panel)
    print(f"Validated {len(checked)} municipality/election/round rows.")
    if args.output:
        predicted = historical_round_change(checked, args.historical_year, args.target_year)
        predicted.to_csv(args.output, index=False)
        print("Wrote baseline (no prediction intervals; not a validated forecast):", args.output)


if __name__ == "__main__":
    main()

"""Print numeric observed distributions; p95 is not an alert frequency."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import load_settings
from src.observe import summarize

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    if args.days < 1:
        parser.error("days must be >= 1")
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / "config.yaml")
    summary = summarize(settings.observe_csv_dir, args.days, settings.posture.thresholds)
    for name, row in summary.items():
        values = " ".join(f"{key}={row[key]:.3f}" if row[key] is not None else f"{key}=n/a"
                          for key in ("median", "p90", "p95", "max"))
        print(f"{name}: n={row['count']} {values}" + ("  THRESHOLD BELOW p95" if row["threshold_warning"] else ""))
    print("p95 is a distribution percentile, not the rate of sustained 60-second alerts.")

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median, pstdev
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TZ = ZoneInfo("Asia/Singapore")

def pctile(values, q):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * q
    a = int(pos)
    b = min(a + 1, len(values) - 1)
    return round(values[a] + (values[b] - values[a]) * (pos - a), 1)

def generate():
    by_week = defaultdict(list)
    day_counts = defaultdict(set)
    total_rows = 0
    for path in sorted((DATA / "raw").glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row["pct"]:
                    continue
                try:
                    pct = float(row["pct"])
                    ts = datetime.fromisoformat(row["ts"]).astimezone(TZ)
                except (ValueError, KeyError):
                    continue
                if not 0 <= pct <= 100:
                    continue
                week = f"{ts.isocalendar().year}-W{ts.isocalendar().week:02d}"
                key = (row["id"], str(ts.weekday()), str(ts.hour))
                by_week[(key, week)].append(pct)
                day_counts[key].add(ts.date().isoformat())
                total_rows += 1
    bins = defaultdict(dict)
    for (key, week), observations in by_week.items():
        bins[key][week] = round(median(observations), 1)
    patterns = {}
    for (outlet, day, hour), weeks in sorted(bins.items()):
        vals = list(weeks.values())
        spread = round(max(vals) - min(vals), 1)
        label = ("insufficient" if len(vals) < 3 else
                 "consistent" if spread <= 15 else
                 "moderate" if spread <= 30 else "variable")
        record = {
            "median": round(median(vals), 1),
            "q25": pctile(vals, .25),
            "q75": pctile(vals, .75),
            "std": round(pstdev(vals), 1),
            "spread": spread,
            "consistency": label,
            "weeks": len(vals),
            "days": len(day_counts[(outlet, day, hour)]),
            "samples": sum(len(by_week[((outlet, day, hour), week)]) for week in weeks),
            "weekly": dict(sorted(weeks.items())),
        }
        patterns.setdefault(outlet, {}).setdefault(day, {})[hour] = record
    summary = {
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "description": "Median of weekly medians per weekday and hour.",
        "data_rows": total_rows,
        "patterns": patterns,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "patterns.json").write_text(
        json.dumps(summary, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"Patterns: {sum(len(hours) for ds in patterns.values() for hours in ds.values())}; observations: {total_rows}")

if __name__ == "__main__":
    generate()

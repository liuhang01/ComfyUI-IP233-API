"""Refresh menu metadata from public contracts; never submits paid requests."""
import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ip233.catalog import normalize_catalog, SNAPSHOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, help="Read an already downloaded /api/pricing response")
    args = parser.parse_args()
    if args.source:
        payload = json.loads(args.source.read_text(encoding="utf-8"))
    else:
        import requests
        response = requests.get("https://new.ip233.com/api/pricing", timeout=30)
        response.raise_for_status()
        payload = response.json()
    models = normalize_catalog(payload)
    SNAPSHOT.write_text(json.dumps({
        "source": "https://new.ip233.com/api/pricing",
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "models": models,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {len(models)} public models in {SNAPSHOT.name}")


if __name__ == "__main__":
    main()

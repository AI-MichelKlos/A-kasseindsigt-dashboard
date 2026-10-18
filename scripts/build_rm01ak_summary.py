import argparse
import json
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = BASE / "data" / "rm01ak.json"
DEFAULT_OUTPUT = BASE / "data" / "rm01ak-summary.json"
REQUIRED_KEYS = ("meta", "funds", "series", "counts")


def summary_payload(payload: dict) -> dict:
    missing = [key for key in REQUIRED_KEYS if key not in payload]
    if missing:
        raise ValueError(f"RM01AK mangler felter til forsiden: {', '.join(missing)}")
    return {key: payload[key] for key in REQUIRED_KEYS}


def write_summary(payload: dict, output: Path = DEFAULT_OUTPUT) -> None:
    summary = summary_payload(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Byg kompakt RM01AK-fil til dashboardets forside")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    write_summary(payload, args.output)
    print(f"RM01AK-forside: {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

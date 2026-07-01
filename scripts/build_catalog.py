from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_KEYS = {"name", "url", "test_type"}


def validate_items(items: list[dict]) -> None:
    for index, item in enumerate(items, start=1):
        missing_keys = REQUIRED_KEYS - item.keys()
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ValueError(f"Item {index} is missing required keys: {missing}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and normalize SHL catalog JSON.")
    parser.add_argument("input_path", type=Path, help="Raw catalog JSON path")
    parser.add_argument("output_path", type=Path, help="Processed catalog JSON path")
    args = parser.parse_args()

    items = json.loads(args.input_path.read_text(encoding="utf-8"))
    validate_items(items)

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(items, indent=2), encoding="utf-8")
    print(f"Saved {len(items)} items to {args.output_path}")


if __name__ == "__main__":
    main()


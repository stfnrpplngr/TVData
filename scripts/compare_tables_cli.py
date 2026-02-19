"""CLI helper to generate comparison payloads for selected tariff tables."""

import argparse
import json
import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from scripts.table_comparison import compare_multiple_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare remuneration tables")
    parser.add_argument("tables", nargs="+", help="Table names, e.g. TV-L TVöD-VKA")
    parser.add_argument("--baseline", help="Baseline table for focused comparisons")
    args = parser.parse_args()

    payload = compare_multiple_tables(args.tables, baseline=args.baseline)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
